import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure server.py in root directory can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
	"""Provides an isolated temporary SQLite database for each test."""
	db_file = tmp_path / "test_carpincho.db"
	monkeypatch.setattr(server, "DB_PATH", db_file)
	server.init_db()
	return db_file


@pytest.fixture
def mock_mpv():
	"""Creates a mocked MPV controller to test without launching actual MPV process."""
	mpv = MagicMock(spec=server.AsyncMpvController)
	mpv.is_running = True
	mpv.start = AsyncMock()
	mpv.stop = AsyncMock()
	mpv._send = AsyncMock()
	return mpv


@pytest.fixture
def clean_state(temp_db, mock_mpv):
	"""Provides a fresh, isolated APIState instance."""
	state = server.APIState()
	state.mpv = mock_mpv
	return state


@pytest.fixture
def clean_manager():
	"""Provides a fresh ConnectionManager instance."""
	return server.ConnectionManager()


@pytest.fixture
def dummy_audio_file(tmp_path):
	"""Creates a dummy audio file with some binary content."""
	audio_path = tmp_path / "test_track.mp3"
	# Write >3MB of dummy data to test smart hash 15% / 85% chunk sampling
	data = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"AUDIO_DATA_" * (400 * 1024)
	audio_path.write_bytes(data)
	return audio_path


@pytest.fixture
def small_audio_file(tmp_path):
	"""Creates a small dummy audio file (<3MB)."""
	audio_path = tmp_path / "small_track.mp3"
	audio_path.write_bytes(b"SHORT_AUDIO_DATA_" * 1024)
	return audio_path


def pytest_pyfunc_call(pyfuncitem):
	"""Auto-run async test functions using asyncio.run when pytest-asyncio is not installed."""
	import asyncio
	import inspect

	test_fn = pyfuncitem.obj
	if inspect.iscoroutinefunction(test_fn):
		raw_kwargs = {
			arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames if arg in pyfuncitem.funcargs
		}
		asyncio.run(test_fn(**raw_kwargs))
		return True
	return None
