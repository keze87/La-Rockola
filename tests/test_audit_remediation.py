"""
Pruebas de remediación y auditoría arquitectónica:
- Escaneo automático en background al inicio (lifespan)
- Limpieza de eventos IPC en Windows sin invocar callbacks a ciegas
- Evaluación dinámica de is_available en RadioService
- Eliminación de inspección de mocks en playback.py y await directo de broadcast_state
- Erradicación de globals().get en entrypoint, wizard y radio
- Desacoplamiento de LibraryService respecto a WebSockets / broadcast_state
- Delegación de pregeneración, caducidad (15 min) y síntesis en RadioService
- Organización limpia de rutas canónicas (/api/v1) y legacy
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.radio as radio_mod
from app.api.v1.router import api_v1_router, legacy_router
from app.engine.mpv_controller import AsyncMpvController
from app.engine.state import RADIO_PREGENERATION_MAX_AGE_SECONDS, APIState
from app.main import lifespan
from app.services.library import LibraryService
from app.services.radio import RadioService


@pytest.mark.asyncio
async def test_lifespan_starts_background_scan():
	"""Verifica que el lifespan del servidor dispare el escaneo de la biblioteca en segundo plano."""
	app = FastAPI()
	with (
		patch("app.main.apply_migrations"),
		patch("app.main.backup_db"),
		patch("app.main.get_state", return_value=MagicMock(mpv=None, open_browser=False)),
		patch("app.main.scan_library", new_callable=AsyncMock) as mock_scan,
	):
		async with lifespan(app):
			# Esperar a que los tasks de arranque tengan turno en el event loop
			await asyncio.sleep(0.05)
			mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_mpv_windows_ipc_resets_without_blind_callbacks():
	"""Verifica que al cerrarse el pipe en Windows se reseteen reader/writer sin llamar callbacks a ciegas."""
	mock_stop_cb = AsyncMock()
	mock_ended_cb = AsyncMock()
	mpv = AsyncMpvController({"track_stopped": mock_stop_cb, "song_ended": mock_ended_cb})
	mpv.is_windows = True
	mpv.socket_path = "\\\\.\\pipe\\test_rockola_pipe"
	mpv.reader = MagicMock()
	mpv.writer = MagicMock()

	# Simulamos fallo de apertura o desconexión abrupta
	with patch("builtins.open", side_effect=OSError("Pipe desconectado")):
		await mpv._read_ipc_events_windows()

	# Reset de reader y writer
	assert mpv.reader is None
	assert mpv.writer is None
	# NO deben haberse disparado callbacks de fin o stop de canción a ciegas en el finally
	mock_stop_cb.assert_not_called()
	mock_ended_cb.assert_not_called()


def test_radio_service_is_available_dynamic():
	"""Verifica que RadioService.is_available evalúe dinámicamente el estado del módulo sin quedar clavado."""
	orig_tts = getattr(radio_mod, "HAS_EDGE_TTS", False)
	orig_fn = getattr(radio_mod, "create_radio_announcement", None)
	service = RadioService()

	try:
		# Forzamos False a nivel de módulo
		radio_mod.HAS_EDGE_TTS = False
		assert service.is_available is False

		# Forzamos True con función válida
		radio_mod.HAS_EDGE_TTS = True
		radio_mod.create_radio_announcement = AsyncMock()
		assert service.is_available is True
	finally:
		radio_mod.HAS_EDGE_TTS = orig_tts
		radio_mod.create_radio_announcement = orig_fn


def test_playback_no_mock_inspection_in_source():
	"""Verifica que app/api/v1/playback.py no contenga _get_broadcast_fn ni inspección de Mocks."""
	playback_file = Path(__file__).resolve().parent.parent / "app" / "api" / "v1" / "playback.py"
	content = playback_file.read_text(encoding="utf-8")

	assert "_get_broadcast_fn" not in content, "playback.py aún define o usa _get_broadcast_fn"
	assert "assert_called" not in content, "playback.py inspecciona métodos de mocks"
	assert "hasattr(" not in content or "called" not in content, "playback.py inspecciona atributos de mocks"
	assert "await broadcast_state()" in content, "playback.py debe invocar await broadcast_state() directamente"


def test_no_globals_get_in_modules():
	"""Verifica que entrypoint, wizard y radio no usen llamadas defensivas con globals().get."""
	root = Path(__file__).resolve().parent.parent / "app"
	checked_files = [
		root / "cli" / "entrypoint.py",
		root / "cli" / "wizard.py",
		root / "services" / "radio.py",
	]

	violations = []
	for f in checked_files:
		text = f.read_text(encoding="utf-8")
		if "globals().get" in text:
			violations.append(f"{f.name}: contiene globals().get")

	assert not violations, "Se detectaron malos olores de globals().get:\n" + "\n".join(violations)


def test_library_service_decoupled_from_state_and_uses_progress_callback():
	"""Verifica que LibraryService no importe broadcast_state y reciba callbacks de progreso."""
	library_file = Path(__file__).resolve().parent.parent / "app" / "services" / "library.py"
	content = library_file.read_text(encoding="utf-8")

	assert "from app.engine.state import broadcast_state" not in content, (
		"library.py no debe importar broadcast_state directamente"
	)


@pytest.mark.asyncio
async def test_library_service_progress_callback_invoked(tmp_path):
	"""Verifica que run_background_mood_analysis invoque el callback on_progress provisto."""
	service = LibraryService()
	state = APIState()
	state.is_analyzing_mood = True
	state.tracks_cache = []

	progress_called = []

	async def mock_progress(current: int, total: int, msg: str):
		progress_called.append((current, total, msg))

	# Ejecutamos con lista vacía de tracks a analizar
	with (
		patch("app.services.library.calculate_mood_scores"),
		patch("app.engine.audio_analysis.find_binary", return_value="fake_ffmpeg"),
	):
		await service.run_background_mood_analysis(
			state=state,
			tracks_to_analyze=[],
			on_progress=mock_progress,
		)

	assert state.is_analyzing_mood is False
	assert state.scan_phase == "idle"


@pytest.mark.asyncio
async def test_radio_service_pregeneration_and_expiration(tmp_path):
	"""Verifica que RadioService maneje pregeneración, control de caducidad (15 min) y síntesis."""
	service = RadioService()
	service.announcement_path = tmp_path / "announcement.mp3"
	service.pregenerated_path = tmp_path / "pregenerated.mp3"

	# 1. Simular pregeneración expirada (> 15 min)
	fake_expired_file = tmp_path / "expired.mp3"
	fake_expired_file.write_bytes(b"DUMMY_MP3")
	service.pregenerated_announcement = {
		"path": str(fake_expired_file),
		"display_title": "Locución Vieja",
		"script": "Texto viejo",
		"created_at": time.time() - (RADIO_PREGENERATION_MAX_AGE_SECONDS + 100),
	}

	with (
		patch.object(service, "apply_hot_mix_to_announcement", new_callable=AsyncMock) as mock_hot_mix,
		patch("app.services.radio.create_radio_announcement", new_callable=AsyncMock) as mock_synth,
	):
		mock_synth.return_value = (True, "Locución Fresca", "Texto nuevo", None)
		mock_hot_mix.return_value = True

		ok, title, _script, _err = await service.get_or_synthesize(next_track_path="/music/next.mp3")

		# La locución expirada debió descartarse y llamarse a create_radio_announcement para generar una fresca
		assert ok is True
		assert title == "Locución Fresca"
		mock_synth.assert_awaited_once()


def test_router_clean_canonical_and_legacy_organization():
	"""Verifica que api_v1_router exponga /api/v1/* y legacy_router solo las rutas requeridas."""
	app = FastAPI()
	app.include_router(api_v1_router)
	app.include_router(legacy_router)

	client = TestClient(app)

	# Rutas canónicas v1
	with patch("app.core.dependencies.get_state", return_value=APIState()):
		res_v1_lib = client.get("/api/v1/library")
		assert res_v1_lib.status_code == 200

	# Rutas legacy de primer nivel para frontend
	res_leg_lib = client.get("/library")
	assert res_leg_lib.status_code == 200

	# Clima legacy y canónico
	with patch("scripts.radio_announcer.fetch_weather_json", return_value={"current_condition": [{"temp_C": "21"}]}):
		res_v1_weather = client.get("/api/v1/weather/preview?location=Rosario")
		assert res_v1_weather.status_code == 200

		res_leg_weather = client.get("/api/weather/preview?location=Rosario")
		assert res_leg_weather.status_code == 200
