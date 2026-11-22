"""
Pruebas para la persistencia de configuración por defecto:
- Modo de ordenamiento de la biblioteca (default_sort)
- Locutor de radio (radio_mode_enabled)
- Visibilidad de MPV (mpv_visible)
"""

import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.api.commands import COMMAND_HANDLERS, mpv_hide, mpv_show
from app.api.schemas import CommandRequest
from app.core.config import DEFAULT_CONFIG, Settings, load_config, update_config
from app.domain.playback.orchestrator import PlaybackOrchestrator


def test_default_config_values():
	"""Verifica los valores por defecto requeridos en la configuración."""
	assert DEFAULT_CONFIG["default_sort"] == "time"
	assert DEFAULT_CONFIG["radio_mode_enabled"] is True
	assert DEFAULT_CONFIG["mpv_visible"] is True
	assert DEFAULT_CONFIG["dj_mode"] == "shuffle"
	assert DEFAULT_CONFIG["volume"] == 100

	settings = Settings()
	assert settings.default_sort == "time"
	assert settings.radio_mode_enabled is True
	assert settings.mpv_visible is True
	assert settings.dj_mode == "shuffle"
	assert settings.volume == 100


def test_orchestrator_initializes_with_config_defaults(tmp_path: Path):
	"""El orquestador toma default_sort, radio_mode_enabled, mpv_visible, dj y volume de la config."""
	db_file = tmp_path / "test_rockola.db"
	orchestrator = PlaybackOrchestrator(
		db_path=db_file,
		default_sort="artist",
		radio_mode_enabled=False,
		mpv_visible=False,
		dj_carpincho_enabled=True,
		dj_mode="favorites",
		volume=65,
	)

	assert orchestrator.default_sort == "artist"
	assert orchestrator.radio_mode_enabled is False
	assert orchestrator.mpv_visible is False
	assert orchestrator.dj_carpincho_enabled is True
	assert orchestrator.dj_mode == "favorites"
	assert orchestrator.volume == 65

	state_dict = orchestrator.get_full_state_dict()
	assert state_dict["default_sort"] == "artist"
	assert state_dict["radio_mode_enabled"] is False
	assert state_dict["mpv_visible"] is False
	assert state_dict["dj_carpincho_enabled"] is True
	assert state_dict["dj_mode"] == "favorites"
	assert state_dict["volume"] == 65


@pytest.mark.asyncio
async def test_cmd_toggle_radio_mode_saves_to_config(tmp_path: Path):
	"""Al conmutar el modo locutor, se debe persistir el nuevo estado en rockola_config.json."""
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"radio_mode_enabled": True}), encoding="utf-8")

	orchestrator = MagicMock(spec=PlaybackOrchestrator)
	orchestrator.radio_mode_enabled = True
	orchestrator._reset_radio_schedule = MagicMock()

	handler = COMMAND_HANDLERS["toggle_radio_mode"]

	with patch("app.core.config.get_config_path", return_value=config_file):
		await handler(orchestrator, CommandRequest(cmd="toggle_radio_mode", state=False), None)

	assert orchestrator.radio_mode_enabled is False
	loaded = json.loads(config_file.read_text(encoding="utf-8"))
	assert loaded["radio_mode_enabled"] is False


@pytest.mark.asyncio
async def test_cmd_set_default_sort_saves_to_config(tmp_path: Path):
	"""El comando set_default_sort debe actualizar el estado del orquestador y guardarse en disco."""
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"default_sort": "time"}), encoding="utf-8")

	orchestrator = MagicMock(spec=PlaybackOrchestrator)
	orchestrator.default_sort = "time"

	assert "set_default_sort" in COMMAND_HANDLERS
	handler = COMMAND_HANDLERS["set_default_sort"]

	with patch("app.core.config.get_config_path", return_value=config_file):
		await handler(orchestrator, CommandRequest(cmd="set_default_sort", sort="mood"), None)

	assert orchestrator.default_sort == "mood"
	loaded = json.loads(config_file.read_text(encoding="utf-8"))
	assert loaded["default_sort"] == "mood"


@pytest.mark.asyncio
async def test_mpv_show_hide_persists_to_config(tmp_path: Path):
	"""mpv_hide y mpv_show deben persistir mpv_visible en la configuración."""
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"mpv_visible": True}), encoding="utf-8")

	mock_state = MagicMock(spec=PlaybackOrchestrator)
	mock_state.mpv_visible = True
	mock_state.mpv = MagicMock()
	mock_state.mpv.is_running = False
	mock_state.mpv.has_display = True

	mock_container = MagicMock()
	mock_container.ensure_orchestrator.return_value = mock_state

	with (
		patch("app.core.container.get_container", return_value=mock_container),
		patch("app.api.commands.get_container", return_value=mock_container),
		patch("app.core.config.get_config_path", return_value=config_file),
		patch("app.api.commands.broadcast_state", new_callable=AsyncMock),
	):
		await mpv_hide()
		loaded = json.loads(config_file.read_text(encoding="utf-8"))
		assert loaded["mpv_visible"] is False
		assert mock_state.mpv_visible is False

		await mpv_show()
		loaded = json.loads(config_file.read_text(encoding="utf-8"))
		assert loaded["mpv_visible"] is True
		assert mock_state.mpv_visible is True


def test_update_config_merges_and_preserves_existing_keys(tmp_path: Path):
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"port": 4000, "mpv_visible": True}), encoding="utf-8")

	update_config({"default_sort": "artist"}, path=config_file)

	loaded = json.loads(config_file.read_text(encoding="utf-8"))
	assert loaded["default_sort"] == "artist"
	assert loaded["port"] == 4000
	assert loaded["mpv_visible"] is True


def test_update_config_resolves_default_path_lazily(tmp_path: Path):
	config_file = tmp_path / "rockola_config.json"
	with patch("app.core.config.get_config_path", return_value=config_file):
		update_config({"radio_mode_enabled": False})
	assert json.loads(config_file.read_text(encoding="utf-8"))["radio_mode_enabled"] is False


def test_update_config_is_safe_under_concurrent_writers(tmp_path: Path):
	"""Escrituras simultáneas de claves distintas no deben pisarse entre sí."""
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text("{}", encoding="utf-8")
	keys = [f"clave_{i}" for i in range(40)]

	threads = [threading.Thread(target=update_config, args=({k: True}, config_file)) for k in keys]
	for t in threads:
		t.start()
	for t in threads:
		t.join()

	loaded = load_config(config_file)
	assert all(loaded.get(k) is True for k in keys)


def test_settings_reject_invalid_default_sort():
	assert Settings(default_sort="mood").default_sort == "mood"
	with pytest.raises(ValidationError):
		Settings(default_sort="cualquier_cosa")


@pytest.mark.asyncio
async def test_cmd_set_default_sort_ignores_invalid_value(tmp_path: Path):
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"default_sort": "time"}), encoding="utf-8")
	orchestrator = MagicMock(spec=PlaybackOrchestrator)
	orchestrator.default_sort = "time"

	with patch("app.core.config.get_config_path", return_value=config_file):
		await COMMAND_HANDLERS["set_default_sort"](
			orchestrator, CommandRequest(cmd="set_default_sort", sort="nope"), None
		)

	assert orchestrator.default_sort == "time"
	assert json.loads(config_file.read_text(encoding="utf-8"))["default_sort"] == "time"


@pytest.mark.asyncio
async def test_dj_volume_and_weather_commands_persist_to_config(tmp_path: Path):
	"""Los comandos de DJ Bara, modo DJ, volumen y ubicación del clima deben guardarse en rockola_config.json."""
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text("{}", encoding="utf-8")

	db_file = tmp_path / "cmd_persist.db"
	from app.infrastructure.db.connection import init_db

	init_db(db_file)
	orchestrator = PlaybackOrchestrator(db_path=db_file, open_browser=False, use_mpv=False)

	with patch("app.core.config.get_config_path", return_value=config_file):
		await COMMAND_HANDLERS["toggle_dj_carpincho"](
			orchestrator, CommandRequest(cmd="toggle_dj_carpincho", state=True), None
		)
		assert orchestrator.dj_carpincho_enabled is True

		await COMMAND_HANDLERS["toggle_dj_carpincho"](
			orchestrator, CommandRequest(cmd="toggle_dj_carpincho", state=False), None
		)
		assert orchestrator.dj_carpincho_enabled is False

		await COMMAND_HANDLERS["toggle_dj_carpincho"](orchestrator, CommandRequest(cmd="toggle_dj_carpincho"), None)
		assert orchestrator.dj_carpincho_enabled is True

		await COMMAND_HANDLERS["set_dj_mode"](orchestrator, CommandRequest(cmd="set_dj_mode", mode="library"), None)
		await COMMAND_HANDLERS["set_volume"](orchestrator, CommandRequest(cmd="set_volume", vollevel=72), None)
		await COMMAND_HANDLERS["vol_down"](orchestrator, CommandRequest(cmd="vol_down"), None)
		await COMMAND_HANDLERS["set_weather_location"](
			orchestrator, CommandRequest(cmd="set_weather_location", location="Tafí del Valle"), None
		)
		from app.api.commands import flush_pending_volume_persist

		flush_pending_volume_persist()

	saved = json.loads(config_file.read_text(encoding="utf-8"))
	assert "dj_carpincho_enabled" not in saved
	assert saved["dj_mode"] == "library"
	assert saved["volume"] == 67
	assert saved["weather_location"] == "Tafí del Valle"


@pytest.mark.asyncio
async def test_toggle_dj_safe_mode_does_not_mutate_dj_mode_config(tmp_path: Path):
	"""_cmd_toggle_dj_safe_mode no debe pisar dj_mode en rockola_config.json."""
	from app.api.commands import COMMAND_HANDLERS
	from app.api.schemas import CommandRequest
	from app.domain.playback.orchestrator import PlaybackOrchestrator

	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"dj_mode": "shuffle"}), encoding="utf-8")
	orch = PlaybackOrchestrator(initial_dir=str(tmp_path), db_path=tmp_path / "rockola.db", use_mpv=False)
	orch.dj_mode = "library"  # distinto al guardado en disco

	with patch("app.core.config.get_config_path", return_value=config_file):
		await COMMAND_HANDLERS["toggle_dj_safe_mode"](orch, CommandRequest(cmd="toggle_dj_safe_mode", state=True), None)

	saved = json.loads(config_file.read_text(encoding="utf-8"))
	assert saved["dj_mode"] == "shuffle"


@pytest.mark.asyncio
async def test_volume_commands_debounce_config_writes(tmp_path: Path):
	"""Arrastrar el volumen no debe escribir el JSON a disco en cada evento (debounce 500 ms)."""
	import asyncio

	from app.api import commands as commands_mod
	from app.api.schemas import CommandRequest
	from app.domain.playback.orchestrator import PlaybackOrchestrator

	config_file = tmp_path / "rockola_config.json"
	orch = PlaybackOrchestrator(initial_dir=str(tmp_path), db_path=tmp_path / "rockola.db", use_mpv=False)

	write_calls = 0
	orig_update = commands_mod.config_mod.update_config

	def counted_update(updates: dict):
		nonlocal write_calls
		write_calls += 1
		return orig_update(updates)

	with (
		patch("app.core.config.get_config_path", return_value=config_file),
		patch.object(commands_mod.config_mod, "update_config", side_effect=counted_update),
	):
		for v in (20, 35, 50, 65, 80):
			await commands_mod.COMMAND_HANDLERS["set_volume"](orch, CommandRequest(cmd="set_volume", vollevel=v), None)
		# Todavía no debió escribir 5 veces
		assert write_calls == 0
		await asyncio.sleep(0.6)
		assert write_calls == 1
		saved = json.loads(config_file.read_text(encoding="utf-8"))
		assert saved["volume"] == 80


def test_settings_from_config_sanitizes_invalid_dj_mode_and_volume(tmp_path: Path):
	"""Settings.from_config_file sanea dj_mode y volume corruptos sin fallar en el arranque."""
	config_file = tmp_path / "rockola_config.json"
	config_file.write_text(json.dumps({"dj_mode": "invalido", "volume": 999}), encoding="utf-8")

	settings = Settings.from_config_file(config_file)
	assert settings.dj_mode == "shuffle"
	assert settings.volume == 110


def test_shutdown_flushes_pending_volume_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Un set_volume seguido de shutdown inmediato (lifespan o stop_embedded_server) debe persistir el volumen."""
	from fastapi.testclient import TestClient

	from app import android_entry
	from app.api import commands as commands_mod
	from app.core import config as config_mod
	from app.main import create_app

	config_file = tmp_path / "rockola_config.json"
	music_dir = tmp_path / "music"
	music_dir.mkdir()
	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	monkeypatch.setattr(config_mod, "get_config_path", lambda: config_file)
	config_mod.set_settings(config_mod.Settings(music_dir=str(music_dir), music_dir_configured=True))

	app = create_app()
	with TestClient(app) as client:
		res = client.post("/command", json={"cmd": "set_volume", "vollevel": 42})
		assert res.status_code == 200
		# Antes del shutdown aún no venció el debounce de 500 ms
		assert not config_file.exists()

	saved = json.loads(config_file.read_text(encoding="utf-8"))
	assert saved["volume"] == 42

	# También stop_embedded_server debe vaciar el debounce pendiente
	commands_mod._schedule_volume_persist(37)
	android_entry.stop_embedded_server()
	saved_after_stop = json.loads(config_file.read_text(encoding="utf-8"))
	assert saved_after_stop["volume"] == 37
