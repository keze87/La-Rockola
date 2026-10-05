"""
Pruebas TDD para la eliminación de _srv, desmantelamiento de state.py,
corrección de regresiones (pause_after, ruta de clima, LocalPlayerSeek, Windows IPC)
y singleton tipado de ConnectionManager.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas import LocalPlayerSeek
from app.api.v1.playback import handle_command
from app.api.v1.router import api_v1_router, legacy_router
from app.core.dependencies import get_manager, set_global_manager
from app.engine.state import APIState


def test_pause_after_logic_with_none_and_toggle():
	"""Verifica que pause_after limpie explícitamente con None y haga toggle con la misma ruta."""
	import asyncio

	from app.core.dependencies import get_state, set_global_state

	orig_state = get_state()
	state = APIState()
	state.pause_after_path = "/musica/tango.mp3"

	try:
		set_global_state(state)
		req_none = MagicMock(cmd="pause_after", path=None)
		asyncio.run(handle_command(req_none))
		assert state.pause_after_path is None, "pause_after no limpió cuando path era None"

		# 2. Si asignamos una ruta nueva
		req_new = MagicMock(cmd="pause_after", path="/musica/chacarera.mp3")
		asyncio.run(handle_command(req_new))
		assert state.pause_after_path == "/musica/chacarera.mp3"

		# 3. Si mandamos la misma ruta de nuevo, debe togglear a None
		req_same = MagicMock(cmd="pause_after", path="/musica/chacarera.mp3")
		asyncio.run(handle_command(req_same))
		assert state.pause_after_path is None, "pause_after no toggleó a None al recibir la misma ruta"
	finally:
		set_global_state(orig_state)


def test_weather_preview_routes():
	"""Verifica que la ruta de clima esté accesible en /api/v1/weather/preview y /api/weather/preview."""
	app = FastAPI()
	app.include_router(api_v1_router)
	app.include_router(legacy_router)

	client = TestClient(app)

	with patch("scripts.radio_announcer.fetch_weather_json", return_value={"current_condition": [{"temp_C": "24"}]}):
		# Ruta canónica v1
		res_v1 = client.get("/api/v1/weather/preview?location=Rosario")
		assert res_v1.status_code == 200
		assert res_v1.json()["ok"] is True

		# Ruta legacy /api/weather/preview
		res_legacy = client.get("/api/weather/preview?location=Rosario")
		assert res_legacy.status_code == 200
		assert res_legacy.json()["ok"] is True


def test_local_player_seek_schema():
	"""Verifica el esquema Pydantic corregido para LocalPlayerSeek con mode y amount."""
	seek_event = LocalPlayerSeek(mode="relative", amount=15.0)
	assert seek_event.type == "local_player_seek"
	assert seek_event.mode == "relative"
	assert seek_event.amount == 15.0

	# Verificación de serialización a dict
	data = seek_event.model_dump()
	assert data["mode"] == "relative"
	assert data["amount"] == 15.0
	assert data["type"] == "local_player_seek"


@pytest.mark.asyncio
async def test_mpv_windows_ipc_error_handling_resets():
	"""Verifica que al atrapar error o EOF en _read_ipc_events_windows se limpien sockets sin disparar callbacks a ciegas."""
	from app.engine.mpv_controller import AsyncMpvController

	mock_stop_cb = AsyncMock()
	mock_ended_cb = AsyncMock()
	mpv = AsyncMpvController({"track_stopped": mock_stop_cb, "song_ended": mock_ended_cb})
	mpv.is_windows = True
	mpv.socket_path = "\\\\.\\pipe\\test_pipe"

	# Simulamos apertura de pipe que falla o da EOF de inmediato
	with patch("builtins.open", side_effect=OSError("Pipe desconectada de prepo")):
		await mpv._read_ipc_events_windows()

	assert mpv.reader is None
	assert mpv.writer is None
	# No debe haber invocado callbacks a ciegas
	mock_stop_cb.assert_not_called()
	mock_ended_cb.assert_not_called()


def test_connection_manager_singleton_in_dependencies():
	"""Verifica que get_manager() devuelva siempre una única instancia singleton."""
	# Reseteamos por si acaso
	set_global_manager(None)
	m1 = get_manager()
	m2 = get_manager()
	assert m1 is not None
	assert m1 is m2, "get_manager() no está operando como singleton"


def test_no_srv_or_server_dependency_in_app():
	"""Verifica que ningún archivo .py dentro de app/ defina ni llame a _srv ni importe sys.modules['server']."""
	app_dir = Path(__file__).resolve().parent.parent / "app"
	assert app_dir.is_dir()

	violations = []
	for py_file in app_dir.rglob("*.py"):
		code = py_file.read_text(encoding="utf-8")
		if "_srv(" in code or "def _srv" in code:
			violations.append(f"{py_file.name}: contiene _srv")
		if 'sys.modules.get("server")' in code or 'sys.modules["server"]' in code:
			violations.append(f"{py_file.name}: consulta sys.modules['server']")

	assert not violations, "Se encontraron violaciones de acoplamiento:\n" + "\n".join(violations)
