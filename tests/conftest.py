"""
Configuración compartida de Pytest y fixtures aislados para la arquitectura limpia de La Rockola.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
	sys.path.insert(0, str(root_dir))

sys.modules["tests.conftest"] = sys.modules[__name__]


@pytest.fixture
def temp_db(tmp_path: Path):
	"""Provee una base de datos SQLite temporal aislada por cada test."""
	from app.core.container import get_container
	from app.infrastructure.db.connection import init_db

	db_path = tmp_path / "test_rockola.db"
	init_db(db_path)
	get_container().db_path = db_path
	yield db_path


@pytest.fixture
def test_db(temp_db: Path) -> Path:
	"""Alias de conveniencia para temp_db."""
	return temp_db


@pytest.fixture
def mock_mpv():
	"""Crea un controlador MPV simulado sin lanzar subprocesos reales."""
	from app.infrastructure.mpv.controller import AsyncMpvController

	mpv = MagicMock(spec=AsyncMpvController)
	mpv.is_running = True
	mpv.has_display = True
	mpv.start = AsyncMock()
	mpv.stop = AsyncMock()
	mpv.load_file = AsyncMock()
	mpv.set_pause = AsyncMock()
	mpv.set_volume = AsyncMock()
	mpv.set_mute = AsyncMock()
	mpv.seek_relative = AsyncMock()
	mpv.seek_absolute = AsyncMock()
	mpv.toggle_fullscreen = AsyncMock()
	mpv.set_force_window = AsyncMock()
	mpv.add_subtitle = AsyncMock()
	mpv.stop_playback = AsyncMock()
	mpv._send = AsyncMock()
	return mpv


@pytest.fixture
def clean_state(temp_db: Path, mock_mpv):
	"""Provee una instancia limpia y aislada de PlaybackOrchestrator."""
	from app.core.container import get_container
	from app.domain.playback.orchestrator import PlaybackOrchestrator

	container = get_container()
	orig_orch = container.orchestrator
	orch = PlaybackOrchestrator(db_path=temp_db, open_browser=False)
	orch.mpv = mock_mpv
	container.orchestrator = orch
	yield orch
	container.orchestrator = orig_orch


@pytest.fixture
def clean_manager():
	"""Provee una instancia limpia de ConnectionManager."""
	from app.api.websocket import ConnectionManager
	from app.core.container import get_container

	container = get_container()
	orig_mgr = container.ws_manager
	mgr = ConnectionManager()
	container.ws_manager = mgr
	yield mgr
	mgr.local_player_ws = None
	container.ws_manager = orig_mgr


@pytest.fixture
def client(clean_state, clean_manager):
	"""Provee un TestClient de FastAPI aislado con dependencias inyectadas en AppContainer."""
	from fastapi.testclient import TestClient

	from app.main import create_app

	app_instance = create_app()
	yield TestClient(app_instance)


@pytest.fixture
def dummy_audio_file(tmp_path: Path) -> Path:
	"""Crea un archivo de audio simulado (>3MB) para probar el muestreo 15% / 85%."""
	audio_path = tmp_path / "test_track.mp3"
	data = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"AUDIO_DATA_" * (400 * 1024)
	audio_path.write_bytes(data)
	return audio_path


@pytest.fixture
def small_audio_file(tmp_path: Path) -> Path:
	"""Crea un archivo de audio simulado pequeño (<3MB)."""
	audio_path = tmp_path / "small_track.mp3"
	audio_path.write_bytes(b"SHORT_AUDIO_DATA_" * 1024)
	return audio_path


class TestTimeoutError(TimeoutError):
	"""Excepción lanzada cuando un test excede el tiempo límite establecido."""


DEFAULT_TEST_TIMEOUT: float = 30.0


def _get_test_timeout(item) -> float:
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
	"""Ejecuta automáticamente funciones de test async usando asyncio.run."""
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
	"""Aplica un límite de tiempo por test (30s por defecto)."""
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
	if config.getoption("--run-downloads"):
		return
	skip_download = pytest.mark.skip(reason="Requiere descargas de red (usá --run-downloads para ejecutar)")
	for item in items:
		if "download" in item.keywords:
			item.add_marker(skip_download)
