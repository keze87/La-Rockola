"""Pruebas para conteo de clientes remotos y política de servicio en Android."""

from __future__ import annotations

from types import SimpleNamespace

from app.android_entry import get_connected_remote_clients
from app.api.websocket import ConnectionManager


def test_remote_client_count_excludes_loopback() -> None:
	mgr = ConnectionManager()
	local_v4 = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
	local_v6 = SimpleNamespace(client=SimpleNamespace(host="::1"))
	remote_lan = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42"))
	remote_lan_2 = SimpleNamespace(client=SimpleNamespace(host="10.0.0.8"))
	mgr.active_connections = [local_v4, local_v6, remote_lan, remote_lan_2]  # type: ignore[list-item]

	assert mgr.remote_client_count() == 2


def test_get_connected_remote_clients_uses_container(isolate_container) -> None:
	mgr = isolate_container.ensure_ws_manager()
	mgr.active_connections = [
		SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
		SimpleNamespace(client=SimpleNamespace(host="192.168.0.55")),
	]
	assert get_connected_remote_clients() == 1

	mgr.active_connections = [SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))]
	assert get_connected_remote_clients() == 0


def test_stop_embedded_server_signals_exit_before_slow_persistence(monkeypatch) -> None:
	"""stop_embedded_server debe activar should_exit de inmediato sin bloquearse por persistencia lenta."""
	import threading
	import time

	from app import android_entry
	from app.core.container import get_container

	persist_started = threading.Event()
	persist_release = threading.Event()
	persist_calls = 0

	class FakeOrch:
		def save_playback_session(self, force: bool = False) -> None:
			nonlocal persist_calls
			persist_calls += 1
			persist_started.set()
			persist_release.wait(timeout=3.0)

	class FakeServer:
		should_exit = False
		force_exit = False

	fake_server = FakeServer()
	container = get_container()
	container.orchestrator = FakeOrch()

	monkeypatch.setattr("app.api.commands.flush_pending_volume_persist", lambda: None)
	with android_entry._server_lock:
		android_entry._active_server = fake_server
		android_entry._host_state = "ready"
		android_entry._stop_requested = False

	t0 = time.monotonic()
	android_entry.stop_embedded_server()
	elapsed = time.monotonic() - t0

	assert fake_server.should_exit is True
	assert fake_server.force_exit is False
	assert elapsed < 0.5, f"stop_embedded_server se bloqueó {elapsed:.2f}s esperando persistencia"
	assert persist_started.wait(timeout=1.0)

	# Segunda llamada concurrente activa force_exit y no lanza segundo guardado paralelo
	android_entry.stop_embedded_server()
	assert fake_server.force_exit is True
	persist_release.set()
	time.sleep(0.05)
	assert persist_calls == 1

	with android_entry._server_lock:
		android_entry._active_server = None
		android_entry._host_state = "stopped"
		android_entry._stop_requested = False


def test_stop_embedded_server_logs_persistence_exception_without_failing(monkeypatch) -> None:
	"""Una excepción al guardar la sesión durante el apagado no debe impedir should_exit."""
	import time

	from app import android_entry
	from app.core.container import get_container

	class BrokenOrch:
		def save_playback_session(self, force: bool = False) -> None:
			raise OSError("disco lleno")

	class FakeServer:
		should_exit = False
		force_exit = False

	fake_server = FakeServer()
	get_container().orchestrator = BrokenOrch()
	monkeypatch.setattr("app.api.commands.flush_pending_volume_persist", lambda: None)

	with android_entry._server_lock:
		android_entry._active_server = fake_server
		android_entry._host_state = "ready"
		android_entry._stop_requested = False

	android_entry.stop_embedded_server()
	time.sleep(0.05)
	assert fake_server.should_exit is True

	with android_entry._server_lock:
		android_entry._active_server = None
		android_entry._host_state = "stopped"
		android_entry._stop_requested = False


def test_get_connected_remote_clients_counts_active_http_stream_without_websocket(
	isolate_container, monkeypatch
) -> None:
	"""Un stream HTTP remoto activo debe contar como cliente conectado aunque el WebSocket haya cerrado."""
	from app.api import media as media_mod

	mgr = isolate_container.ensure_ws_manager()
	mgr.active_connections = []
	assert get_connected_remote_clients() == 0

	with media_mod.track_remote_stream(is_remote=True):
		assert media_mod.active_remote_stream_count() == 1
		assert get_connected_remote_clients() == 1

	assert media_mod.active_remote_stream_count() == 0
	assert media_mod.has_recent_remote_stream(grace_sec=30.0) is True
	assert get_connected_remote_clients() == 1

	# Tras vencer la ventana de gracia, ya no queda retenido como conectado
	media_mod._last_remote_stream_at -= 60.0
	assert get_connected_remote_clients() == 0

	with media_mod.track_remote_stream(is_remote=False):
		assert media_mod.active_remote_stream_count() == 0
		assert get_connected_remote_clients() == 0
