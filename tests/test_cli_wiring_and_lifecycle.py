"""
Tests TDD para el wiring de configuración en CLI/entrypoint y ciclo de vida de FastAPI:
- Wiring de configuración resuelta (args CLI y config.json) en APIState.
- open_browser como parámetro con default explícito en APIState.__init__.
- Eliminación de estado global default al importar app.main.
- Reutilización de la instancia única de app sin doble construcción.
"""

from __future__ import annotations

import importlib
import json
from unittest.mock import patch

import app.core.dependencies as deps
from app.engine.state import APIState


def test_api_state_init_open_browser():
	"""Verifica que APIState.__init__ acepte open_browser con default True."""
	state_default = APIState()
	assert state_default.open_browser is True

	state_no_browser = APIState(open_browser=False)
	assert state_no_browser.open_browser is False


def test_import_main_does_not_install_default_global_state():
	"""
	Importar app.main NO debe instalar un APIState 'default' como estado global.
	El estado global debe quedar None hasta que entrypoint lo configure o se invoque get_state().
	"""
	deps.set_global_state(None)

	# Recargar app.main asegurando que no llame a set_global_state a nivel de módulo
	import app.main as main_mod

	importlib.reload(main_mod)

	# _global_state en dependencies debe permanecer None tras el import
	assert deps._global_state is None


def test_entrypoint_main_wires_cli_args_to_global_state(tmp_path):
	"""
	Verifica que arrancar con --dir, --dir2, --weather-location y --no-browser
	instale en get_state() un APIState con los valores resueltos de CLI.
	"""
	deps.set_global_state(None)

	cli_args = [
		"entrypoint.py",
		"--dir",
		str(tmp_path / "primary"),
		"--dir2",
		str(tmp_path / "secondary"),
		"--weather-location",
		"Rosario, Santa Fe",
		"--no-browser",
		"--host",
		"127.0.0.1",
		"--port",
		"1820",
		"--no-interactive",
	]

	with (
		patch("sys.argv", cli_args),
		patch("uvicorn.run") as mock_uvicorn,
		patch("app.cli.entrypoint.check_dependencies"),
	):
		import app.cli.entrypoint as ep

		ep.main()

		mock_uvicorn.assert_called_once()
		# La app pasada a uvicorn.run debe ser la instancia de app.main.app
		import app.main as main_mod

		assert mock_uvicorn.call_args[0][0] is main_mod.app

		state = deps.get_state()
		assert state is not None
		assert state.initial_dir == str(tmp_path / "primary")
		assert state.secondary_dir == str(tmp_path / "secondary")
		assert state.open_browser is False
		assert state.radio_service.weather_location == "Rosario, Santa Fe"
		assert state.weather_location == "Rosario, Santa Fe"
		assert state.server_host == "127.0.0.1"
		assert state.server_port == 1820
		assert state.server_url == "http://localhost:1820"


def test_entrypoint_main_wires_config_json_to_global_state(tmp_path):
	"""
	Verifica que arrancar con valores definidos en config.json (sin flags CLI)
	instale en get_state() un APIState con dichos valores resueltos y no los defaults.
	"""
	deps.set_global_state(None)

	cfg_file = tmp_path / "rockola_config.json"
	cfg_content = {
		"music_dir": str(tmp_path / "config_music"),
		"music_dir2": str(tmp_path / "config_music2"),
		"weather_location": "Córdoba, Argentina",
		"open_browser": False,
		"host": "0.0.0.0",
		"port": 1900,
	}
	cfg_file.write_text(json.dumps(cfg_content), encoding="utf-8")

	cli_args = [
		"entrypoint.py",
		"--config",
		str(cfg_file),
		"--no-interactive",
	]

	with (
		patch("sys.argv", cli_args),
		patch("uvicorn.run") as mock_uvicorn,
		patch("app.cli.entrypoint.check_dependencies"),
	):
		import app.cli.entrypoint as ep

		ep.main()

		mock_uvicorn.assert_called_once()
		state = deps.get_state()
		assert state is not None
		assert state.initial_dir == str(tmp_path / "config_music")
		assert state.secondary_dir == str(tmp_path / "config_music2")
		assert state.open_browser is False
		assert state.radio_service.weather_location == "Córdoba, Argentina"
		assert state.weather_location == "Córdoba, Argentina"
		assert state.server_port == 1900
