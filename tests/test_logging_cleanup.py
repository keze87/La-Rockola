import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


def test_default_log_level_and_silenced_loggers():
	"""Verify that default logging is INFO and noisy third-party loggers are silenced."""
	server.configure_logging(debug=False)
	assert logging.getLogger().level == logging.INFO
	assert logging.getLogger("PIL").level >= logging.WARNING
	assert logging.getLogger("numba").level >= logging.WARNING
	assert logging.getLogger("llvmlite").level >= logging.WARNING
	assert logging.getLogger("uvicorn.access").level >= logging.WARNING


def test_configure_logging_debug_mode():
	"""Verify that debug mode enables DEBUG while keeping PIL and math loggers silenced."""
	server.configure_logging(debug=True)
	assert logging.getLogger().level == logging.DEBUG
	assert logging.getLogger("PIL").level >= logging.WARNING
	assert logging.getLogger("numba").level >= logging.WARNING
	assert logging.getLogger("llvmlite").level >= logging.WARNING

	# Reset back to INFO
	server.configure_logging(debug=False)


@pytest.mark.asyncio
async def test_broadcast_skips_routine_time_pos_spam(clean_manager):
	"""Verify that routine time_pos ticks do not spam AVISANDO A LA MUCHACHADA debug logs."""
	manager = clean_manager
	ws = MagicMock()
	ws.accept = AsyncMock()
	ws.send_json = AsyncMock()
	await manager.connect(ws)

	# 1. Routine progress tick
	routine_message = {"type": "state_update", "time_pos": 42.5}
	with patch("server.logger.debug") as mock_debug:
		await manager.broadcast(routine_message)
		ws.send_json.assert_called_once_with(routine_message)
		# Should not spam the diff
		assert not any("AVISANDO A LA MUCHACHADA" in str(c) for c in mock_debug.call_args_list)

	# 2. Structural change
	ws.send_json.reset_mock()
	structural_message = {
		"type": "state_update",
		"time_pos": 42.5,
		"paused": True,
		"current_track": "/music/song.mp3",
	}
	with patch("server.logger.debug") as mock_debug:
		await manager.broadcast(structural_message)
		ws.send_json.assert_called_once_with(structural_message)
		# Should log structural state change
		assert any("AVISANDO A LA MUCHACHADA" in str(c) for c in mock_debug.call_args_list)


def test_build_arg_parser_debug_flag():
	"""Verify that build_arg_parser supports the --debug flag."""
	parser = server.build_arg_parser()
	args_default = parser.parse_args([])
	assert args_default.debug is False

	args_debug = parser.parse_args(["--debug"])
	assert args_debug.debug is True


def test_default_config_has_log_level():
	"""Verify that DEFAULT_CONFIG contains log_level with default INFO."""
	assert "log_level" in server.DEFAULT_CONFIG
	assert server.DEFAULT_CONFIG["log_level"] == "INFO"


def test_configure_logging_with_log_level_string():
	"""Verify configure_logging accepts string log level."""
	server.configure_logging(level="DEBUG")
	assert logging.getLogger().level == logging.DEBUG

	server.configure_logging(level="WARNING")
	assert logging.getLogger().level == logging.WARNING

	server.configure_logging(level="INFO")
	assert logging.getLogger().level == logging.INFO

	# Reset
	server.configure_logging(debug=False)


def test_build_arg_parser_log_level_option():
	"""Verify that build_arg_parser supports the --log-level flag."""
	parser = server.build_arg_parser()
	args_default = parser.parse_args([])
	assert args_default.log_level is None

	args_warn = parser.parse_args(["--log-level", "WARNING"])
	assert args_warn.log_level == "WARNING"


def test_load_config_loads_log_level(tmp_path):
	"""Verify load_config reads log_level from rockola_config.json."""
	cfg_path = tmp_path / "rockola_config.json"
	cfg_path.write_text('{"log_level": "DEBUG"}', encoding="utf-8")
	loaded = server.load_config(cfg_path)
	assert loaded.get("log_level") == "DEBUG"
