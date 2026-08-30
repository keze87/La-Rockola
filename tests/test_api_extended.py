import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_serve_index(tmp_path, monkeypatch):
	"""Test / endpoint serving index.html."""
	dist = tmp_path / "dist"
	dist.mkdir()
	index = dist / "index.html"
	index.write_text("<html><body>La Rockola</body></html>")
	monkeypatch.setattr(server, "dist_dir", dist)

	# When index.html exists
	res = await server.serve_index()
	assert res.status_code == 200

	# When index.html is missing
	index.unlink()
	res_missing = await server.serve_index()
	assert "error" in res_missing


@pytest.mark.asyncio
async def test_serve_favicon(tmp_path, monkeypatch):
	"""Test /favicon.ico and /favicon.png."""
	dist = tmp_path / "dist"
	dist.mkdir()
	fav = dist / "favicon.png"
	fav.write_bytes(b"FAVICON_DATA")
	monkeypatch.setattr(server, "dist_dir", dist)

	res = await server.serve_favicon()
	assert res.status_code == 200


@pytest.mark.asyncio
async def test_seek_commands_with_local_player(clean_state, clean_manager, monkeypatch):
	"""Test relative and absolute seek commands dispatched to local player websocket."""
	monkeypatch.setattr(server, "state", clean_state)
	monkeypatch.setattr(server, "manager", clean_manager)

	mock_ws = MagicMock()
	mock_ws.send_json = AsyncMock()
	clean_manager.local_player_ws = mock_ws

	# Relative seek
	await server.handle_command(server.CommandRequest(cmd="seek", amount=15))
	mock_ws.send_json.assert_called_with({"type": "local_player_seek", "mode": "relative", "amount": 15})

	# Absolute seek
	await server.handle_command(server.CommandRequest(cmd="seek_absolute", amount=45))
	mock_ws.send_json.assert_called_with({"type": "local_player_seek", "mode": "absolute", "amount": 45})


@pytest.mark.asyncio
async def test_history_jump(clean_state):
	"""Test rewinding to a past track in history via jump("history", index)."""
	state = clean_state
	state.history = ["/m/h1.mp3", "/m/h2.mp3", "/m/h3.mp3"]
	state.current_track = "/m/playing.mp3"
	state.queue = ["/m/q1.mp3"]

	# Rewind to /m/h2.mp3 (index 1)
	await state.jump("history", 1)
	assert state.current_track == "/m/h2.mp3"
	assert state.history == ["/m/h1.mp3"]
	assert state.queue == ["/m/h3.mp3", "/m/playing.mp3", "/m/q1.mp3"]


@pytest.mark.asyncio
async def test_websocket_drift_and_non_json_messages(clean_state, clean_manager, monkeypatch):
	"""Test websocket error handling for malformed non-JSON messages and seek drift synchronization."""
	monkeypatch.setattr(server, "state", clean_state)
	monkeypatch.setattr(server, "manager", clean_manager)

	mock_ws = MagicMock()
	mock_ws.client.host = "192.168.0.200"
	mock_ws.accept = AsyncMock()
	mock_ws.send_json = AsyncMock()

	# Simulate messages:
	# 1. Invalid non-JSON message
	# 2. Claim local player
	# 3. Update with drift > 3.0s (client at 20s, server at 10s)
	messages = [
		"NOT_A_JSON_STRING",
		json.dumps({"type": "local_player_claim"}),
		json.dumps({"type": "local_player_update", "time_pos": 20.0}),
		json.dumps({"type": "local_player_release"}),
	]
	mock_ws.receive_text = AsyncMock(side_effect=messages + [server.WebSocketDisconnect()])

	clean_state.time_pos = 10.0
	clean_state.duration = 100.0

	with patch("server.broadcast_state", new_callable=AsyncMock):
		await server.websocket_endpoint(mock_ws)

	# Verify drift was detected and seek dispatched to MPV
	clean_state.mpv._send.assert_called()
