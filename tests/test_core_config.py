"""
Tests para app.core.config, app.core.logging y app.core.dependencies.
"""

from unittest.mock import MagicMock

from app.core.config import Settings, load_config, save_config
from app.core.dependencies import get_settings
from app.core.logging import configure_logging


def test_settings_defaults():
	settings = Settings()
	assert settings.port == 1729
	assert settings.host == "0.0.0.0"
	assert settings.open_browser is True
	assert settings.log_level == "INFO"


def test_settings_load_from_json(tmp_path):
	config_file = tmp_path / "custom_config.json"
	config_file.write_text('{"port": 8080, "host": "127.0.0.1", "open_browser": false}', encoding="utf-8")

	loaded = load_config(config_file)
	assert loaded["port"] == 8080
	assert loaded["host"] == "127.0.0.1"
	assert loaded["open_browser"] is False

	# Guardamos cambios y verificamos persistencia
	loaded["port"] = 9090
	save_config(config_file, loaded)
	reloaded = load_config(config_file)
	assert reloaded["port"] == 9090


def test_settings_merge_cli_args():
	settings = Settings()
	args = MagicMock()
	args.port = 8888
	args.host = "192.168.1.50"
	args.dir = "/tmp/music"
	args.dir2 = None
	args.open_browser = False
	args.url = "http://rockola.local"
	args.weather_location = "Córdoba"
	args.log_level = "DEBUG"

	merged = settings.merge_cli_args(args)
	assert merged.port == 8888
	assert merged.host == "192.168.1.50"
	assert str(merged.music_dir) == "/tmp/music"
	assert merged.open_browser is False
	assert merged.url == "http://rockola.local"
	assert merged.weather_location == "Córdoba"
	assert merged.log_level == "DEBUG"


def test_configure_logging():
	logger = configure_logging(debug=True)
	assert logger is not None


def test_dependencies(monkeypatch):
	settings = get_settings()
	assert isinstance(settings, Settings)

	import app.core.dependencies as deps

	orig_state = deps.get_state()
	dummy_state = MagicMock()
	try:
		deps.set_global_state(dummy_state)
		assert deps.get_state() is dummy_state
	finally:
		deps.set_global_state(orig_state)
