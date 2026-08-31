import json
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def setup_server(clean_state, clean_manager, monkeypatch):
	"""Set up clean state and manager, and mock startup builds."""
	monkeypatch.setattr(server, "state", clean_state)
	monkeypatch.setattr(server, "manager", clean_manager)
	monkeypatch.setattr(server, "build_frontend", lambda: None)
	monkeypatch.setattr(server, "backup_db", lambda: None)
	return clean_state


def test_websocket_initial_state_push(clean_state):
	"""Test client receives initial state_update push upon connecting."""
	clean_state.volume = 85
	clean_state.current_track = "/music/intro.mp3"

	client = TestClient(server.app)
	with client.websocket_connect("/ws") as ws:
		msg = ws.receive_json()
		assert msg["type"] == "state_update"
		assert msg["volume"] == 85
		assert msg["current_track"] == "/music/intro.mp3"


def test_websocket_local_player_claim_and_release(clean_state, clean_manager):
	"""Test claiming local player, rejecting duplicate claims, and releasing."""
	client = TestClient(server.app)
	with client.websocket_connect("/ws") as ws1:
		ws1.receive_json()  # Consume initial state

		# 1. First client claims local player
		ws1.send_json({"type": "local_player_claim"})
		res1 = ws1.receive_json()
		assert res1 == {"type": "local_player_claim_result", "ok": True}
		assert clean_manager.local_player_ws is not None

		# 2. Second client attempts to claim while first is active -> rejected
		with client.websocket_connect("/ws") as ws2:
			ws2.receive_json()  # Consume initial state
			ws2.send_json({"type": "local_player_claim"})
			res2 = ws2.receive_json()
			assert res2 == {"type": "local_player_claim_result", "ok": False}

		# 3. First client releases local player
		ws1.send_json({"type": "local_player_release"})
		# Send a ping/dummy to ensure release processed
		ws1.send_json({"type": "dummy_ping"})
		assert clean_manager.local_player_ws is None


def test_websocket_local_player_time_drift_reconciliation(clean_state, clean_manager):
	"""Test small vs large time drift reconciliation and MPV seek dispatching."""
	clean_state.time_pos = 10.0
	clean_state.last_seek_drift = None
	clean_state.last_time_broadcast = time.time()

	client = TestClient(server.app)
	with client.websocket_connect("/ws") as ws:
		ws.receive_json()  # initial state

		# Claim local player
		ws.send_json({"type": "local_player_claim"})
		ws.receive_json()

		# 1. Small drift (<= 5.0s): time_pos 10.0 -> 13.0 (diff 3.0) -> No MPV seek
		clean_state.mpv._send.reset_mock()
		ws.send_json({"type": "local_player_update", "time_pos": 13.0})
		ws.send_json({"type": "dummy_ping"})  # flush

		assert clean_state.time_pos == 13.0
		assert clean_state.last_seek_drift is None
		clean_state.mpv._send.assert_not_called()

		# 2. Large drift (> 5.0s): time_pos 13.0 -> 40.0 (diff 27.0) -> Triggers MPV seek
		# 2. Large drift (> 5.0s): time_pos 13.0 -> 40.0 (diff 27.0) -> Triggers MPV seek and broadcast when interval passed
		clean_state.time_pos = 13.0
		clean_state.last_seek_drift = None
		clean_state.last_time_broadcast = time.time() - 10.0
		clean_state.mpv._send.reset_mock()

		ws.send_json({"type": "local_player_update", "time_pos": 40.0})
		ws.send_json({"type": "dummy_ping"})  # flush
		broadcast_msg = ws.receive_json()
		assert broadcast_msg["type"] == "state_update"

		assert clean_state.time_pos == 40.0
		assert clean_state.last_seek_drift == 27.0
		clean_state.mpv._send.assert_called_once_with(
			json.dumps({"command": ["seek", 40.0, "absolute"]})
		)

		# 3. Subsequent small drift change from same offset (diff change <= 1.0s) -> No duplicate seek spam
		clean_state.time_pos = 13.0
		clean_state.mpv._send.reset_mock()

		ws.send_json({"type": "local_player_update", "time_pos": 40.5})
		ws.send_json({"type": "dummy_ping"})  # flush

		assert clean_state.time_pos == 40.5
		clean_state.mpv._send.assert_not_called()


def test_websocket_local_player_duration_paused_and_song_ended(clean_state, clean_manager, temp_db):
	"""Test duration, pause updates, and song_ended advancing queue with stats recorded."""
	clean_state.current_track = "/music/song1.mp3"
	clean_state.queue = ["/music/song2.mp3"]
	clean_state.path_to_id["/music/song1.mp3"] = "track_1_hash"

	client = TestClient(server.app)
	with client.websocket_connect("/ws") as ws:
		ws.receive_json()  # initial state

		# Claim local player
		ws.send_json({"type": "local_player_claim"})
		ws.receive_json()

		# Update duration and paused
		ws.send_json({"type": "local_player_update", "duration": 240.0, "paused": True})
		ws.send_json({"type": "dummy_ping"})

		update_msg = ws.receive_json()
		assert update_msg["type"] == "state_update"
		assert update_msg["duration"] == 240.0
		assert update_msg["paused"] is True
		assert clean_state.duration == 240.0
		assert clean_state.mpv_paused is True

		# song_ended -> advances queue and records play history stat
		ws.send_json({"type": "local_player_update", "song_ended": True})
		ws.send_json({"type": "dummy_ping"})

		song_ended_update = ws.receive_json()
		assert song_ended_update["type"] == "state_update"
		assert song_ended_update["current_track"] == "/music/song2.mp3"
		assert clean_state.current_track == "/music/song2.mp3"
		assert clean_state.queue == []

		with sqlite3.connect(temp_db) as conn:
			row = conn.execute("SELECT track_id FROM play_history WHERE track_id = 'track_1_hash'").fetchone()
			assert row is not None


def test_websocket_non_json_messages_and_unclaimed_updates(clean_state, clean_manager):
	"""Test non-JSON messages and unclaimed local_player_update are handled without error."""
	client = TestClient(server.app)
	with client.websocket_connect("/ws") as ws:
		ws.receive_json()  # initial state

		# Send raw text (non-JSON)
		ws.send_text("NOT_A_VALID_JSON_STRING {{{")

		# Send local_player_update while NOT claimed as local player
		ws.send_json({"type": "local_player_update", "time_pos": 50.0})

		# State should remain untouched
		assert clean_state.time_pos == 0.0

		# Send normal ping
		ws.send_json({"type": "some_random_msg", "payload": 123})


def test_websocket_disconnect_cleanup(clean_state, clean_manager):
	"""Test client disconnect triggers manager.disconnect and frees local player claim."""
	client = TestClient(server.app)
	with client.websocket_connect("/ws") as ws:
		ws.receive_json()
		ws.send_json({"type": "local_player_claim"})
		ws.receive_json()
		assert len(clean_manager.active_connections) == 1
		assert clean_manager.local_player_ws is not None

	# Upon context exit, websocket disconnects
	assert len(clean_manager.active_connections) == 0
	assert clean_manager.local_player_ws is None
