"""
Tests de Observabilidad, Diagnóstico Granular, Blindaje de Dominio y Cobertura Histórica (Stage 6).
Garantiza:
1. Logs granulares en wttr.in (429, 503, JSON malformado, timeout).
2. Soporte de ALLOW_TEST_DUMMY_AUDIO y logs de reintento/fallback en edge-tts / tts_cache.
3. Observabilidad en fallos del comando fortune.
4. Warnings en descarte de pregeneración radial por antigüedad o corrupción.
5. Ausencia de _ManagerProxy, globals().get('manager') y ensure_mpv_methods en PlaybackOrchestrator.
6. _has_local_player() no crea ConnectionManager como efecto colateral.
7. Cobertura de comandos API adicionales y MPRIS dispatcher.
"""

from __future__ import annotations

import io
import logging
import subprocess
import urllib.error
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.container import AppContainer, get_container, set_container
from app.infrastructure.db.connection import init_db


def test_no_test_shortcuts_in_playback_orchestrator(tmp_path):
	"""Verifica que PlaybackOrchestrator no use _ManagerProxy, globals().get('manager') ni ensure_mpv_methods."""
	from app.domain.playback import orchestrator as orch_mod

	# 1. No debe existir _ManagerProxy en el módulo
	assert not hasattr(orch_mod, "_ManagerProxy"), "Se encontró _ManagerProxy en app.domain.playback.orchestrator"
	assert not hasattr(orch_mod, "ensure_mpv_methods"), (
		"orchestrator no debe importar ni envolver con ensure_mpv_methods"
	)

	db_p = tmp_path / "orch_test.db"
	init_db(db_p)
	set_container(AppContainer(db_path=db_p, orchestrator=None, ws_manager=None))

	orch = orch_mod.PlaybackOrchestrator(db_path=db_p)
	# 2. _has_local_player() no debe instanciar ws_manager como efecto colateral
	assert get_container().ws_manager is None
	assert orch._has_local_player() is False
	assert get_container().ws_manager is None, "_has_local_player() instanció perezosamente ws_manager"

	# 3. orchestrator.mpv debe devolver directamente _mpv sin envolver con ensure_mpv_methods
	dummy_mpv = object()
	orch.mpv = dummy_mpv
	assert orch.mpv is dummy_mpv


def test_fetch_weather_json_429_observability(caplog):
	"""Verifica que HTTP 429 en wttr.in registre warning específico."""
	from app.infrastructure.weather import client as weather_client

	err_429 = urllib.error.HTTPError(
		url="https://wttr.in/Rosario",
		code=429,
		msg="Too Many Requests",
		hdrs={},
		fp=io.BytesIO(b"Rate limit exceeded"),
	)
	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", side_effect=err_429):
			res = weather_client.fetch_weather_json("Rosario_Test_429")
			assert res is None
			assert any("429" in rec.message or "Rate Limit" in rec.message for rec in caplog.records)


def test_fetch_weather_json_503_observability(caplog):
	"""Verifica que HTTP 503 en wttr.in registre warning específico."""
	from app.infrastructure.weather import client as weather_client

	err_503 = urllib.error.HTTPError(
		url="https://wttr.in/Rosario",
		code=503,
		msg="Service Unavailable",
		hdrs={},
		fp=io.BytesIO(b"Service Unavailable"),
	)
	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", side_effect=err_503):
			res = weather_client.fetch_weather_json("Rosario_Test_503")
			assert res is None
			assert any("503" in rec.message or "Service Unavailable" in rec.message for rec in caplog.records)


def test_fetch_weather_json_malformed_json_observability(caplog):
	"""Verifica que un JSON roto de wttr.in registre warning específico de malformación."""
	from app.infrastructure.weather import client as weather_client

	mock_resp = MagicMock()
	mock_resp.status = 200
	mock_resp.read.return_value = b"<html><head><title>502 Bad Gateway</title></head></html>"
	mock_resp.__enter__.return_value = mock_resp

	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", return_value=mock_resp):
			res = weather_client.fetch_weather_json("Rosario_Test_Malformed")
			assert res is None
			assert any("malformad" in rec.message.lower() or "json" in rec.message.lower() for rec in caplog.records)


def test_fetch_weather_json_timeout_observability(caplog):
	"""Verifica que un timeout en wttr.in registre warning explícito."""
	from app.infrastructure.weather import client as weather_client

	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
			res = weather_client.fetch_weather_json("Rosario_Test_Timeout")
			assert res is None
			assert any(
				"timeout" in rec.message.lower() or "tiempo de espera" in rec.message.lower() for rec in caplog.records
			)


def test_fortune_stderr_observability(caplog):
	"""Verifica que cuando fortune falla con código != 0 se registre warning con el stderr."""
	from app.domain.radio import nlp

	mock_proc = subprocess.CompletedProcess(
		args=["fortune", "-s"],
		returncode=1,
		stdout="",
		stderr="fortune: memory fault / database corrupted",
	)
	with caplog.at_level(logging.WARNING):
		with patch("shutil.which", return_value="/usr/bin/fortune"):
			with patch.object(nlp, "get_available_spanish_dbs", return_value=["es"]):
				with patch("subprocess.run", return_value=mock_proc):
					res = nlp.get_system_fortune()
					assert res is None
					assert any(
						"database corrupted" in rec.message or "fortune falló" in rec.message for rec in caplog.records
					)


@pytest.mark.asyncio
async def test_allow_test_dummy_audio_in_tts_cache(monkeypatch):
	"""Verifica que ALLOW_TEST_DUMMY_AUDIO permita obtener audio dummy en tests."""
	from app.infrastructure.media import tts_cache

	assert hasattr(tts_cache, "ALLOW_TEST_DUMMY_AUDIO")
	monkeypatch.setattr(tts_cache, "ALLOW_TEST_DUMMY_AUDIO", True)

	mock_comm = MagicMock()
	del mock_comm.stream  # Forzar uso de save()
	mock_comm.save = MagicMock(return_value=None)

	with patch.object(tts_cache, "edge_tts", create=True) as mock_edge:
		mock_edge.Communicate.return_value = mock_comm
		audio_bytes = await tts_cache.synthesize_segment(
			text="Texto de prueba con dummy audio",
			voice="es-AR-TomasNeural",
			category="saludo",
			allow_cache=False,
		)
		assert isinstance(audio_bytes, bytes)
		assert len(audio_bytes) > 0


@pytest.mark.asyncio
async def test_radio_pregeneration_stale_warning(tmp_path, caplog):
	"""Verifica que un anuncio pregenerado vencido por tiempo registre warning al ser descartado."""
	import time

	from app.domain.radio.service import RadioService

	db_p = tmp_path / "radio_stale.db"
	init_db(db_p)
	svc = RadioService(db_path=db_p)

	dummy_mp3 = tmp_path / "old_pre.mp3"
	dummy_mp3.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00VALID_HEADER")

	# Simular anuncio pregenerado hace 20 minutos (más del TTL de 600s)
	pre = {
		"path": str(dummy_mp3),
		"display_title": "Carpincho Viejo",
		"script": "Texto viejo",
		"created_at": time.time() - 1200.0,
		"outro_mode": "continue",
	}

	with caplog.at_level(logging.WARNING):
		ok, _, _ = await svc._consume_pregenerated(
			pre=pre,
			target_ann_path=tmp_path / "target.mp3",
			next_track_path=None,
			bg_offset=0.0,
			outro_mode="continue",
		)
		assert ok is False
		assert any("antigüedad" in rec.message.lower() or "descartado" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_command_dispatcher_extended_coverage(tmp_path):
	"""Verifica comandos de API como seek, seek_absolute, toggle_radio_mode, clear_queue y pause_after."""
	from app.api.commands import handle_command_endpoint
	from app.api.schemas import CommandRequest
	from app.domain.playback.orchestrator import PlaybackOrchestrator

	db_p = tmp_path / "cmd_test.db"
	init_db(db_p)
	orch = PlaybackOrchestrator(db_path=db_p)
	orch.mpv = AsyncMock()
	set_container(AppContainer(db_path=db_p, orchestrator=orch, ws_manager=None))

	# 1. seek
	res = await handle_command_endpoint(CommandRequest(cmd="seek", amount=15.0))
	assert res["status"] == "ok"
	orch.mpv.seek_relative.assert_awaited_with(15.0)

	# 2. seek_absolute
	res = await handle_command_endpoint(CommandRequest(cmd="seek_absolute", amount=60.0))
	assert res["status"] == "ok"
	orch.mpv.seek_absolute.assert_awaited_with(60.0)
	assert orch.time_pos == 60.0

	# 3. clear_queue
	orch.queue_manager.queue = ["/music/song1.mp3", "/music/song2.mp3"]
	res = await handle_command_endpoint(CommandRequest(cmd="clear_queue"))
	assert res["status"] == "ok"
	assert len(orch.queue_manager.queue) == 0

	# 4. toggle_radio_mode
	orch.radio_mode_enabled = True
	res = await handle_command_endpoint(CommandRequest(cmd="toggle_radio_mode", state=False))
	assert res["status"] == "ok"
	assert orch.radio_mode_enabled is False

	# 5. toggle_dj_carpincho
	orch.dj_carpincho_enabled = False
	res = await handle_command_endpoint(CommandRequest(cmd="toggle_dj_carpincho"))
	assert res["status"] == "ok"
	assert orch.dj_carpincho_enabled is True


@pytest.mark.asyncio
async def test_mpris_dispatcher_invokes_command_endpoint(tmp_path):
	"""Verifica que _dispatch_mpris_command despache correctamente comandos a handle_command_endpoint."""
	from app.domain.playback.orchestrator import PlaybackOrchestrator

	db_p = tmp_path / "mpris_test.db"
	init_db(db_p)
	orch = PlaybackOrchestrator(db_path=db_p)
	orch.mpv = MagicMock()
	orch.mpv.set_pause = AsyncMock()
	set_container(AppContainer(db_path=db_p, orchestrator=orch, ws_manager=None))

	# Despachar 'pause' vía el handler de MPRIS
	await orch._dispatch_mpris_command("pause")
	orch.mpv.set_pause.assert_awaited_with(True)


def test_rebuild_frontend_flag_in_arg_parser_and_build_frontend(tmp_path, monkeypatch):
	"""Verifica que build_arg_parser exponga --rebuild-frontend y que build_frontend respete force."""
	from app.cli import entrypoint as cli_entrypoint

	parser = cli_entrypoint.build_arg_parser()
	args = parser.parse_args(["--rebuild-frontend"])
	assert args.rebuild_frontend is True

	dummy_frontend = tmp_path / "frontend"
	dummy_frontend.mkdir()
	(dummy_frontend / "package.json").write_text("{}", encoding="utf-8")
	(dummy_frontend / "node_modules").mkdir()
	dist = dummy_frontend / "dist"
	dist.mkdir()
	(dist / "index.html").write_text("<html></html>", encoding="utf-8")

	mock_run = MagicMock()
	monkeypatch.setattr(cli_entrypoint.subprocess, "run", mock_run)

	# 1. Sin force, con index.html existente, no debe ejecutar npm build
	cli_entrypoint.build_frontend(frontend_dir=dummy_frontend, force=False)
	mock_run.assert_not_called()

	# 2. Con force=True, debe ejecutar npm run build incluso si existe index.html
	cli_entrypoint.build_frontend(frontend_dir=dummy_frontend, force=True)
	mock_run.assert_called_once()
