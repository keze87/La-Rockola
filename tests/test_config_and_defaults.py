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

	settings = Settings()
	assert settings.default_sort == "time"
	assert settings.radio_mode_enabled is True
	assert settings.mpv_visible is True


def test_orchestrator_initializes_with_config_defaults(tmp_path: Path):
	"""El orquestador toma default_sort, radio_mode_enabled y mpv_visible de los argumentos/config."""
	db_file = tmp_path / "test_rockola.db"
	orchestrator = PlaybackOrchestrator(
		db_path=db_file,
		default_sort="artist",
		radio_mode_enabled=False,
		mpv_visible=False,
	)

	assert orchestrator.default_sort == "artist"
	assert orchestrator.radio_mode_enabled is False
	assert orchestrator.mpv_visible is False

	state_dict = orchestrator.get_full_state_dict()
	assert state_dict["default_sort"] == "artist"
	assert state_dict["radio_mode_enabled"] is False
	assert state_dict["mpv_visible"] is False


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
