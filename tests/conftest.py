import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure server.py in root directory can be imported
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
	sys.path.insert(0, str(root_dir))

import scripts  # noqa: F401 - Registers sys.modules["binary_utils"], etc.
import server


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
	"""Provides an isolated temporary SQLite database for each test."""
	from app.core.dependencies import set_db_path

	db_file = tmp_path / "test_carpincho.db"
	monkeypatch.setattr(server, "DB_PATH", db_file)
	set_db_path(db_file)
	server.init_db()
	yield db_file
	set_db_path(None)


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
def test_db(temp_db):
	"""Alias de conveniencia para temp_db compatible con la arquitectura modular."""
	return temp_db


@pytest.fixture
def clean_manager():
	"""Provides a fresh ConnectionManager instance."""
	mgr = server.ConnectionManager()
	yield mgr
	mgr.local_player_ws = None
	if hasattr(server, "manager") and server.manager is not None:
		server.manager.local_player_ws = None


@pytest.fixture
def client(clean_state, clean_manager):
	"""Provee un TestClient de FastAPI aislado con dependencias inyectadas."""
	from fastapi.testclient import TestClient

	import app.core.dependencies as deps
	from app.main import create_app

	orig_state = deps.get_state()
	orig_mgr = deps.get_manager()

	deps.set_global_state(clean_state)
	deps.set_global_manager(clean_manager)
	app_instance = create_app()
	yield TestClient(app_instance)

	deps.set_global_state(orig_state)
	deps.set_global_manager(orig_mgr)
	if hasattr(server, "manager") and server.manager is not None:
		server.manager.local_player_ws = None


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
