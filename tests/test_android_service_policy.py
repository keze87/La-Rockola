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
