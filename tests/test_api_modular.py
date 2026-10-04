"""
Tests TDD para app.api (schemas, websocket, router v1).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas import ApiResponse, CommandRequest, LocalPlayerClaim, LocalPlayerUpdate
from app.api.websocket import ConnectionManager


def test_command_request_validation():
	req = CommandRequest(cmd="play", path="/music/song.mp3")
	assert req.cmd == "play"
	assert req.path == "/music/song.mp3"

	seek_req = CommandRequest(cmd="seek", amount=15.0)
	assert seek_req.amount == 15.0


def test_api_response_generic():
	res = ApiResponse(status="ok", data={"count": 5})
	assert res.status == "ok"
	assert res.data["count"] == 5


def test_websocket_schemas():
	claim = LocalPlayerClaim()
	assert claim.type == "local_player_claim"

	update = LocalPlayerUpdate(time_pos=42.5)
	assert update.type == "local_player_update"
	assert update.time_pos == 42.5


@pytest.mark.asyncio
async def test_connection_manager_claim_and_release():
	manager = ConnectionManager()
	ws1 = AsyncMock()
	ws2 = AsyncMock()

	await manager.connect(ws1)
	await manager.connect(ws2)

	assert ws1 in manager.active_connections
	assert ws2 in manager.active_connections

	# ws1 reclama ser el reproductor local
	assert manager.claim_local_player(ws1) is True
	assert manager.local_player_ws is ws1

	# ws2 intenta reclamar pero es rechazado
	assert manager.claim_local_player(ws2) is False
	assert manager.local_player_ws is ws1

	# ws1 libera
	assert manager.release_local_player(ws1) is True
	assert manager.local_player_ws is None

	manager.disconnect(ws1)
	assert ws1 not in manager.active_connections


def test_api_routers_mounting(monkeypatch):
	import app.core.dependencies as deps
	from app.api.v1.router import api_v1_router, legacy_router

	app = FastAPI()
	app.include_router(api_v1_router)
	app.include_router(legacy_router)

	orig_state = deps.get_state()
	mock_state = MagicMock()
	mock_state.tracks_cache = [{"path": "/music/a.mp3", "title": "A", "artist": "B"}]
	mock_state.is_scanning = False
	deps.set_global_state(mock_state)

	try:
		client = TestClient(app)

		# Endpoint canónico v1
		res_v1 = client.get("/api/v1/library")
		assert res_v1.status_code == 200
		assert len(res_v1.json()["data"]) == 1

		# Endpoint legacy
		res_legacy = client.get("/library")
		assert res_legacy.status_code == 200
		assert len(res_legacy.json()["data"]) == 1
	finally:
		deps.set_global_state(orig_state)
