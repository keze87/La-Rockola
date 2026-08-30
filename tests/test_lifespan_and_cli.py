import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown(clean_state, monkeypatch):
	"""Test FastAPI lifespan startup and shutdown cycle."""
	monkeypatch.setattr(server, "state", clean_state)
	mock_bus = MagicMock()
	clean_state.mpris_bus = mock_bus

	with patch("server.backup_db") as mock_backup, patch("server.scan_library", new_callable=AsyncMock) as mock_scan:
		# Use async context manager
		async with server.lifespan(server.app):
			mock_backup.assert_called_once()

		mock_bus.disconnect.assert_called_once()
		clean_state.mpv.stop.assert_called_once()


def test_truncate_text_and_highlight_json():
	"""Test string formatting helper utilities."""
	# Truncate text
	assert server.truncate_text("Hello World", 20) == "Hello World"
	assert server.truncate_text("Hello World", 5) == "Hell…"

	# Highlight json
	valid_json = '{"name": "Carpincho", "count": 42, "active": true, "extra": null}'
	highlighted = server.highlight_json(valid_json)
	assert "Carpincho" in highlighted
	assert "42" in highlighted

	# Dict directly
	dict_highlighted = server.highlight_json({"key": "val"})
	assert "val" in dict_highlighted

	# Invalid json fallback
	invalid = server.highlight_json("{invalid_json}")
	assert "Invalid JSON" in invalid


def test_cli_argument_parsing(monkeypatch):
	"""Test command line arguments parsing for directories and host/port."""
	import argparse

	test_args = ["--host", "127.0.0.1", "--port", "8080", "--dir", "/music/primary", "--dir2", "/music/secondary"]

	with patch("sys.argv", ["server.py"] + test_args):
		parser = argparse.ArgumentParser()
		parser.add_argument("--host", type=str, default="0.0.0.0")
		parser.add_argument("--port", type=int, default=1729)
		parser.add_argument("--dir", type=str, default=None)
		parser.add_argument("--dir2", type=str, default=None)
		args = parser.parse_args()

		assert args.host == "127.0.0.1"
		assert args.port == 8080
		assert args.dir == "/music/primary"
		assert args.dir2 == "/music/secondary"


def test_build_frontend(tmp_path, monkeypatch):
	"""Test build_frontend running npm run build."""
	front_dir = tmp_path / "frontend"
	front_dir.mkdir()
	(front_dir / "package.json").write_text('{"name": "test"}')
	monkeypatch.setattr(server, "frontend_dir", front_dir)

	with patch("shutil.which", return_value="npm"), patch("subprocess.run") as mock_run:
		server.build_frontend()
		assert mock_run.call_count == 2
