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

# Register tests.conftest alias so tests can import helpers without module duplication
sys.modules["tests.conftest"] = sys.modules[__name__]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
	"""Provides an isolated temporary SQLite database for each test."""
	db_path = tmp_path / "test_rockola.db"
	from app.core.dependencies import set_db_path

	set_db_path(db_path)
	monkeypatch.setattr(server, "DB_PATH", db_path, raising=False)
	server.init_db(db_path)
	yield db_path
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
def clean_state(temp_db, mock_mpv, monkeypatch):
	"""Provides a fresh, isolated APIState instance."""
	from app.core.dependencies import get_state, set_db_path, set_global_state

	set_db_path(temp_db)
	state = server.APIState()
	state.mpv = mock_mpv
	orig_state = get_state()
	set_global_state(state)
	monkeypatch.setattr(server, "state", state, raising=False)
	yield state
	set_global_state(orig_state)


@pytest.fixture
def test_db(temp_db):
	"""Alias de conveniencia para temp_db compatible con la arquitectura modular."""
	return temp_db


@pytest.fixture
def clean_manager(monkeypatch):
	"""Provides a fresh ConnectionManager instance."""
	from app.core.dependencies import get_manager, set_global_manager

	mgr = server.ConnectionManager()
	orig_mgr = get_manager()
	set_global_manager(mgr)
	monkeypatch.setattr(server, "manager", mgr, raising=False)
	yield mgr
	mgr.local_player_ws = None
	set_global_manager(orig_mgr)


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


class TestTimeoutError(TimeoutError):
	"""Excepción lanzada cuando un test excede el tiempo límite establecido."""


DEFAULT_TEST_TIMEOUT: float = 30.0


def _get_test_timeout(item) -> float:
	"""Determina el timeout en segundos aplicable a un ítem de test."""
	marker = item.get_closest_marker("timeout")
	if marker and marker.args:
		return float(marker.args[0])
	config = getattr(item, "config", None)
	if config:
		opt = config.getoption("--test-timeout", default=None)
		if opt is not None:
			return float(opt)
	return DEFAULT_TEST_TIMEOUT


def pytest_pyfunc_call(pyfuncitem):
	"""Auto-run async test functions using asyncio.run when pytest-asyncio is not installed."""
	import asyncio
	import inspect

	test_fn = pyfuncitem.obj
	if inspect.iscoroutinefunction(test_fn):
		raw_kwargs = {
			arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames if arg in pyfuncitem.funcargs
		}
		timeout_val = _get_test_timeout(pyfuncitem)
		asyncio.run(asyncio.wait_for(test_fn(**raw_kwargs), timeout=timeout_val))
		return True
	return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
	"""Aplica un límite de tiempo por test (30s por defecto) para frenar ejecuciones colgadas."""
	import signal
	import threading

	timeout_val = _get_test_timeout(item)
	if timeout_val <= 0:
		yield
		return

	timer = None
	old_handler = None

	if hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"):

		def _timeout_sig_handler(signum, frame):
			raise TestTimeoutError(f"El test {item.name} excedió el límite de {timeout_val}s ⏱️")

		old_handler = signal.signal(signal.SIGALRM, _timeout_sig_handler)
		signal.setitimer(signal.ITIMER_REAL, timeout_val)
	else:
		import _thread

		def _timeout_thread_handler():
			_thread.interrupt_main()

		timer = threading.Timer(timeout_val, _timeout_thread_handler)
		timer.daemon = True
		timer.start()

	try:
		yield
	finally:
		if hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"):
			signal.setitimer(signal.ITIMER_REAL, 0)
			if old_handler is not None:
				signal.signal(signal.SIGALRM, old_handler)
		elif timer is not None:
			timer.cancel()


def pytest_addoption(parser):
	"""Agrega la opción por CLI para correr tests con descargas de red y configurar timeouts."""
	parser.addoption(
		"--run-downloads",
		action="store_true",
		default=False,
		help="Ejecuta tests con descargas de red (salteados por defecto)",
	)
	parser.addoption(
		"--test-timeout",
		action="store",
		type=float,
		default=30.0,
		help="Tiempo límite en segundos por test (por defecto: 30s)",
	)


def pytest_collection_modifyitems(config, items):
	"""Saltea los tests marcados con 'download' salvo que se pase --run-downloads."""
	if config.getoption("--run-downloads"):
		return
	skip_download = pytest.mark.skip(reason="Requiere descargas de red (usá --run-downloads para ejecutar)")
	for item in items:
		if "download" in item.keywords:
			item.add_marker(skip_download)
