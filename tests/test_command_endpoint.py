import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


@pytest.fixture(autouse=True)
def setup_server_state(clean_state, clean_manager, monkeypatch):
	"""Ensure server module uses clean_state and clean_manager for every test."""
	monkeypatch.setattr(server, "state", clean_state)
	monkeypatch.setattr(server, "manager", clean_manager)
	return clean_state


@pytest.mark.asyncio
async def test_command_play_and_history(clean_state):
	"""Test 'play' command starts a track and pushes previous track to history."""
	clean_state.current_track = "/music/prev_song.mp3"

	req = server.CommandRequest(cmd="play", path="/music/new_song.mp3")
	res = await server.handle_command(req)

	assert res == {"status": "ok"}
	assert clean_state.current_track == "/music/new_song.mp3"
	assert clean_state.history == ["/music/prev_song.mp3"]
	clean_state.mpv._send.assert_called()


@pytest.mark.asyncio
async def test_command_pause_toggle_and_idle_queue(clean_state):
	"""Test 'pause' command dual behavior: starts playback from queue when idle vs toggles pause."""
	# 1. Idle with items in queue -> starts playback
	clean_state.current_track = None
	clean_state.queue = ["/music/first.mp3", "/music/second.mp3"]

	res = await server.handle_command(server.CommandRequest(cmd="pause"))
	assert res == {"status": "ok"}
	assert clean_state.current_track == "/music/first.mp3"
	assert clean_state.queue == ["/music/second.mp3"]

	# 2. Playing track -> toggles mpv_paused and sends payload
	assert clean_state.mpv_paused is False
	clean_state.mpv._send.reset_mock()

	res = await server.handle_command(server.CommandRequest(cmd="pause"))
	assert res == {"status": "ok"}
	assert clean_state.mpv_paused is True
	clean_state.mpv._send.assert_called_once_with(json.dumps({"command": ["set_property", "pause", True]}))

	clean_state.mpv._send.reset_mock()
	res = await server.handle_command(server.CommandRequest(cmd="pause"))
	assert res == {"status": "ok"}
	assert clean_state.mpv_paused is False
	clean_state.mpv._send.assert_called_once_with(json.dumps({"command": ["set_property", "pause", False]}))


@pytest.mark.asyncio
async def test_command_skip_and_prev(clean_state):
	"""Test 'skip' and 'prev' playback navigation commands."""
	clean_state.queue = ["/music/next_track.mp3"]
	clean_state.history = ["/music/prev_track.mp3"]

	# Skip
	res_skip = await server.handle_command(server.CommandRequest(cmd="skip"))
	assert res_skip == {"status": "ok"}
	assert clean_state.current_track == "/music/next_track.mp3"

	# Prev
	res_prev = await server.handle_command(server.CommandRequest(cmd="prev"))
	assert res_prev == {"status": "ok"}
	assert clean_state.current_track == "/music/prev_track.mp3"


@pytest.mark.asyncio
async def test_command_stop(clean_state):
	"""Test 'stop' command resets playback state and sends stop to MPV."""
	clean_state.current_track = "/music/active.mp3"
	clean_state.mpv_paused = True
	clean_state.dj_carpincho_enabled = True
	clean_state.time_pos = 120.0

	res = await server.handle_command(server.CommandRequest(cmd="stop"))
	assert res == {"status": "ok"}
	assert clean_state.current_track is None
	assert clean_state.history == ["/music/active.mp3"]
	assert clean_state.mpv_paused is False
	assert clean_state.dj_carpincho_enabled is False
	assert clean_state.time_pos == 0

	# Check MPV commands sent
	calls = [c[0][0] for c in clean_state.mpv._send.call_args_list]
	assert '{"command": ["stop"]}' in calls
	assert '{"command": ["set_property", "force-window", "no"]}' in calls


@pytest.mark.asyncio
async def test_command_volume_controls_and_clamping(clean_state):
	"""Test vol_up, vol_down, set_volume clamping between 0 and 110."""
	# 1. vol_up clamping at 110
	clean_state.volume = 108
	await server.handle_command(server.CommandRequest(cmd="vol_up"))
	assert clean_state.volume == 110
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["set_property", "volume", 110]}))

	await server.handle_command(server.CommandRequest(cmd="vol_up"))
	assert clean_state.volume == 110

	# 2. vol_down clamping at 0
	clean_state.volume = 3
	await server.handle_command(server.CommandRequest(cmd="vol_down"))
	assert clean_state.volume == 0
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["set_property", "volume", 0]}))

	await server.handle_command(server.CommandRequest(cmd="vol_down"))
	assert clean_state.volume == 0

	# 3. set_volume with values above 110 and below 0
	await server.handle_command(server.CommandRequest(cmd="set_volume", vollevel=150))
	assert clean_state.volume == 110

	await server.handle_command(server.CommandRequest(cmd="set_volume", vollevel=-25))
	assert clean_state.volume == 0

	await server.handle_command(server.CommandRequest(cmd="set_volume", vollevel=65))
	assert clean_state.volume == 65
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["set_property", "volume", 65]}))

	# set_volume with None does not change volume
	clean_state.mpv._send.reset_mock()
	await server.handle_command(server.CommandRequest(cmd="set_volume", vollevel=None))
	assert clean_state.volume == 65
	clean_state.mpv._send.assert_not_called()


@pytest.mark.asyncio
async def test_command_mute_and_fullscreen(clean_state):
	"""Test set_mute and fullscreen commands."""
	# Mute True
	await server.handle_command(server.CommandRequest(cmd="set_mute", state=True))
	assert clean_state.server_muted is True
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["set_property", "mute", True]}))

	# Mute False
	await server.handle_command(server.CommandRequest(cmd="set_mute", state=False))
	assert clean_state.server_muted is False
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["set_property", "mute", False]}))

	# Mute None does nothing
	clean_state.mpv._send.reset_mock()
	await server.handle_command(server.CommandRequest(cmd="set_mute", state=None))
	clean_state.mpv._send.assert_not_called()

	# Fullscreen
	await server.handle_command(server.CommandRequest(cmd="fullscreen"))
	clean_state.mpv._send.assert_called_with('{"command": ["cycle", "fullscreen"]}')


@pytest.mark.asyncio
async def test_command_queue_operations(clean_state):
	"""Test toggle_queue, clear_queue, remove_queue_item, and move_queue_item."""
	# 1. toggle_queue when playing
	clean_state.current_track = "/music/playing.mp3"
	await server.handle_command(server.CommandRequest(cmd="toggle_queue", path="/music/song1.mp3"))
	assert clean_state.queue == ["/music/song1.mp3"]

	await server.handle_command(server.CommandRequest(cmd="toggle_queue", path="/music/song1.mp3"))
	assert clean_state.queue == []

	# toggle_queue when idle (auto-plays)
	clean_state.current_track = None
	await server.handle_command(server.CommandRequest(cmd="toggle_queue", path="/music/song2.mp3"))
	assert clean_state.current_track == "/music/song2.mp3"

	# 2. move_queue_item
	clean_state.queue = ["A", "B", "C"]
	await server.handle_command(server.CommandRequest(cmd="move_queue_item", index=0, new_index=2))
	assert clean_state.queue == ["B", "C", "A"]

	# move_queue_item with out-of-bounds index
	await server.handle_command(server.CommandRequest(cmd="move_queue_item", index=10, new_index=0))
	assert clean_state.queue == ["B", "C", "A"]

	# 3. remove_queue_item
	await server.handle_command(server.CommandRequest(cmd="remove_queue_item", index=1))
	assert clean_state.queue == ["B", "A"]

	# remove_queue_item with invalid index
	await server.handle_command(server.CommandRequest(cmd="remove_queue_item", index=99))
	assert clean_state.queue == ["B", "A"]

	# 4. clear_queue
	clean_state.history = ["H1"]
	await server.handle_command(server.CommandRequest(cmd="clear_queue"))
	assert clean_state.queue == []
	assert clean_state.history == []

	# 5. remove_history_item
	clean_state.history = ["H1", "H2", "H3"]
	await server.handle_command(server.CommandRequest(cmd="remove_history_item", index=1))
	assert clean_state.history == ["H1", "H3"]

	await server.handle_command(server.CommandRequest(cmd="remove_history_item", index=-1))
	assert clean_state.history == ["H1", "H3"]

	# 6. move_history_item
	clean_state.history = ["H1", "H2", "H3"]
	await server.handle_command(server.CommandRequest(cmd="move_history_item", index=0, new_index=2))
	assert clean_state.history == ["H2", "H3", "H1"]

	# out of bounds move_history_item
	await server.handle_command(server.CommandRequest(cmd="move_history_item", index=9, new_index=0))
	assert clean_state.history == ["H2", "H3", "H1"]

	# 7. insert_queue_item
	clean_state.current_track = "/music/playing.mp3"
	clean_state.queue = ["Q1", "Q2"]
	await server.handle_command(server.CommandRequest(cmd="insert_queue_item", path="Q_new", index=1))
	assert clean_state.queue == ["Q1", "Q_new", "Q2"]

	# 8. move_current_to_queue (when queue has items)
	clean_state.current_track = "CURRENT"
	clean_state.queue = ["NEXT", "AFTER"]
	clean_state.pause_after_path = "CURRENT"
	await server.handle_command(server.CommandRequest(cmd="move_current_to_queue", index=0))
	assert clean_state.current_track == "NEXT"
	assert clean_state.queue == ["CURRENT", "AFTER"]
	assert clean_state.pause_after_path is None

	# move_current_to_queue (when queue is empty)
	clean_state.current_track = "SOLO"
	clean_state.queue = []
	await server.handle_command(server.CommandRequest(cmd="move_current_to_queue", index=0))
	assert clean_state.current_track is None
	assert clean_state.queue == ["SOLO"]

	# 9. move_current_to_history
	clean_state.current_track = "CURRENT2"
	clean_state.queue = ["NEXT2"]
	clean_state.history = ["H1"]
	await server.handle_command(server.CommandRequest(cmd="move_current_to_history", history_index=1))
	assert clean_state.current_track == "NEXT2"
	assert clean_state.history == ["H1", "CURRENT2"]
	assert clean_state.queue == []

	# 10. move_queue_to_history
	clean_state.queue = ["Q1", "Q2"]
	clean_state.history = ["H1"]
	await server.handle_command(server.CommandRequest(cmd="move_queue_to_history", index=0, history_index=0))
	assert clean_state.queue == ["Q2"]
	assert clean_state.history == ["Q1", "H1"]

	# 11. play_from_queue
	clean_state.current_track = "CURRENT3"
	clean_state.queue = ["Q_TARGET", "Q_OTHER"]
	clean_state.history = ["H1"]
	await server.handle_command(server.CommandRequest(cmd="play_from_queue", index=0))
	assert clean_state.current_track == "Q_TARGET"
	assert clean_state.queue == ["Q_OTHER"]
	assert clean_state.history == ["H1", "CURRENT3"]


@pytest.mark.asyncio
async def test_command_move_in_playlist(clean_state):
	"""Test unified playlist move command across history, current track, and queue."""
	with patch.object(clean_state, "play_track", new_callable=AsyncMock) as mock_play:
		# 1. Reordering within history (current playing track is NOT interrupted)
		clean_state.history = ["H1", "H2", "H3"]
		clean_state.current_track = "CURRENT"
		clean_state.queue = ["Q1", "Q2"]
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=2))
		assert clean_state.history == ["H2", "H3", "H1"]
		assert clean_state.current_track == "CURRENT"
		assert clean_state.queue == ["Q1", "Q2"]
		mock_play.assert_not_called()

		# 2. Reordering within queue (current playing track is NOT interrupted)
		# playlist: ["H2", "H3", "H1", "CURRENT", "Q1", "Q2"] (indices 0..5, current is 3)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=5, new_index=4))
		assert clean_state.history == ["H2", "H3", "H1"]
		assert clean_state.current_track == "CURRENT"
		assert clean_state.queue == ["Q2", "Q1"]
		mock_play.assert_not_called()

		# 3. Moving from history to queue (replay a song! current track NOT interrupted)
		# playlist: ["H2", "H3", "H1", "CURRENT", "Q2", "Q1"] (indices 0..5, current is 3)
		# Move H2 (idx 0) to end of queue (idx 5)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=5))
		assert clean_state.history == ["H3", "H1"]
		assert clean_state.current_track == "CURRENT"
		assert clean_state.queue == ["Q2", "Q1", "H2"]
		mock_play.assert_not_called()

		# 4. Moving from queue to history (current track NOT interrupted)
		# playlist: ["H3", "H1", "CURRENT", "Q2", "Q1", "H2"] (indices 0..5, current is 2)
		# Move Q2 (idx 3) to start of history (idx 0)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=3, new_index=0))
		assert clean_state.history == ["Q2", "H3", "H1"]
		assert clean_state.current_track == "CURRENT"
		assert clean_state.queue == ["Q1", "H2"]
		mock_play.assert_not_called()

		# 5. Moving current song below into queue (continues playing, items above become history)
		# playlist: ["Q2", "H3", "H1", "CURRENT", "Q1", "H2"] (indices 0..5, current is 3)
		# Move CURRENT (idx 3) after Q1 (idx 4)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=3, new_index=4))
		assert clean_state.current_track == "CURRENT"
		assert clean_state.history == ["Q2", "H3", "H1", "Q1"]
		assert clean_state.queue == ["H2"]
		mock_play.assert_not_called()

		# 6. Moving current song up into history (continues playing, items below become queue)
		# playlist: ["Q2", "H3", "H1", "Q1", "CURRENT", "H2"] (indices 0..5, current is 4)
		# Move CURRENT (idx 4) to idx 1 (above H3)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=4, new_index=1))
		assert clean_state.current_track == "CURRENT"
		assert clean_state.history == ["Q2"]
		assert clean_state.queue == ["H3", "H1", "Q1", "H2"]
		mock_play.assert_not_called()

		# 7. Moving current song when queue is empty (continues playing)
		clean_state.history = ["H1"]
		clean_state.current_track = "SOLO"
		clean_state.queue = []
		# playlist: ["H1", "SOLO"] (idx 0, 1)
		# Move SOLO (idx 1) to idx 0
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=1, new_index=0))
		assert clean_state.current_track == "SOLO"
		assert clean_state.history == []
		assert clean_state.queue == ["H1"]
		mock_play.assert_not_called()

		# 8. Moving when current_track is None (idle rockola)
		clean_state.history = ["H1", "H2"]
		clean_state.current_track = None
		clean_state.queue = ["Q1", "Q2"]
		# playlist: ["H1", "H2", "Q1", "Q2"] (boundary = 2)
		# Move from history (idx 0) to queue (idx 3)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=3))
		assert clean_state.history == ["H2"]
		assert clean_state.queue == ["Q1", "Q2", "H1"]
		# Move from queue (idx 2, which is Q2) to history (idx 0)
		# playlist: ["H2", "Q1", "Q2", "H1"] (boundary = 1)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=2, new_index=0))
		assert clean_state.history == ["Q2", "H2"]
		assert clean_state.queue == ["Q1", "H1"]

		# 9. Out of bounds or identical indices (noop)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=-1, new_index=2))
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=10))
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=1, new_index=1))
		assert clean_state.history == ["Q2", "H2"]
		assert clean_state.queue == ["Q1", "H1"]


@pytest.mark.asyncio
async def test_playback_queue_edge_cases(clean_state):
	"""Test edge cases requested by user:
	1. Cuando no hay archivos (empty playlist)
	2. Cuando se reproduce el ultimo (playing last track and it finishes, or re-queuing from history)
	3. Cuando se mueve un ya reproducido al siguiente (history track moved to queue[0])
	4. Cuando se mueve el siguiente antes del actual (queue[0] moved to history[-1])
	"""
	with patch.object(clean_state, "play_track", new_callable=AsyncMock) as mock_play:
		async def fake_play(path):
			clean_state.current_track = path

		mock_play.side_effect = fake_play
		# 1. Cuando no hay archivos
		clean_state.history = []
		clean_state.current_track = None
		clean_state.queue = []
		res = await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=1))
		assert res == {"status": "ok"}
		assert clean_state.history == []
		assert clean_state.current_track is None
		assert clean_state.queue == []
		# play_next on empty state
		await clean_state.play_next()
		assert clean_state.current_track is None
		mock_play.assert_not_called()

		# 2. Cuando se reproduce el ultimo
		clean_state.history = ["H1", "H2"]
		clean_state.current_track = "LAST"
		clean_state.queue = []
		# playlist: ["H1", "H2", "LAST"]
		# While playing the last track, user re-queues H1 to be played next
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=2))
		assert clean_state.history == ["H2"]
		assert clean_state.current_track == "LAST"
		assert clean_state.queue == ["H1"]
		mock_play.assert_not_called()

		# Now LAST finishes playing -> H1 plays next!
		await clean_state.play_next()
		assert clean_state.history == ["H2", "LAST"]
		assert clean_state.current_track == "H1"
		assert clean_state.queue == []
		mock_play.assert_called_once_with("H1")
		mock_play.reset_mock()

		# When H1 (now the last track) finishes playing -> player stops cleanly
		await clean_state.play_next()
		assert clean_state.history == ["H2", "LAST", "H1"]
		assert clean_state.current_track is None
		assert clean_state.queue == []
		clean_state.mpv._send.assert_any_call('{"command": ["stop"]}')

		# 3. Cuando se mueve un ya reproducido al siguiente
		clean_state.history = ["H1", "H2"]
		clean_state.current_track = "CURRENT"
		clean_state.queue = ["Q1", "Q2"]
		# playlist: ["H1", "H2", "CURRENT", "Q1", "Q2"] (indices 0..4, current is 2)
		# Move H1 (idx 0) to be the NEXT track (idx 2, right after CURRENT)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=0, new_index=2))
		assert clean_state.history == ["H2"]
		assert clean_state.current_track == "CURRENT"
		assert clean_state.queue == ["H1", "Q1", "Q2"]
		assert clean_state.queue[0] == "H1"  # H1 is indeed the next track!
		mock_play.assert_not_called()

		# When CURRENT finishes, H1 plays next!
		await clean_state.play_next()
		assert clean_state.current_track == "H1"
		assert clean_state.queue == ["Q1", "Q2"]
		assert clean_state.history == ["H2", "CURRENT"]
		mock_play.assert_called_once_with("H1")
		mock_play.reset_mock()

		# 4. Cuando se mueve el siguiente antes del actual
		clean_state.history = ["H1", "H2"]
		clean_state.current_track = "CURRENT"
		clean_state.queue = ["Q1", "Q2"]
		# playlist: ["H1", "H2", "CURRENT", "Q1", "Q2"] (indices 0..4, current is 2, next is Q1 at 3)
		# Move Q1 (idx 3) before CURRENT (idx 2)
		await server.handle_command(server.CommandRequest(cmd="move_in_playlist", index=3, new_index=2))
		assert clean_state.history == ["H1", "H2", "Q1"]
		assert clean_state.current_track == "CURRENT"
		assert clean_state.queue == ["Q2"]
		assert clean_state.history[-1] == "Q1"  # Q1 is now in history
		assert clean_state.queue[0] == "Q2"  # Q2 is now the next track
		mock_play.assert_not_called()

		# When CURRENT finishes, Q2 plays next (skipping Q1 since it was moved to history)
		await clean_state.play_next()
		assert clean_state.current_track == "Q2"
		assert clean_state.queue == []
		assert clean_state.history == ["H1", "H2", "Q1", "CURRENT"]
		mock_play.assert_called_once_with("Q2")


@pytest.mark.asyncio
async def test_command_add_url(clean_state):
	"""Test add_url command when idle (auto-play) vs when playing, including DJ pre-pick."""
	with patch.object(clean_state, "fetch_yt_dlp_metadata", new_callable=AsyncMock) as mock_fetch:
		# 1. Idle: auto-plays the URL immediately
		clean_state.current_track = None
		clean_state.queue = []

		url1 = "https://youtube.com/watch?v=track1"
		res1 = await server.handle_command(server.CommandRequest(cmd="add_url", path=url1))
		assert res1 == {"status": "ok"}
		assert clean_state.current_track == url1
		mock_fetch.assert_called_with(url1)

		# 2. Currently playing: adds to queue and triggers _pick_dj_next
		url2 = "https://youtube.com/watch?v=track2"
		with patch.object(clean_state, "_pick_dj_next") as mock_dj_pick:
			res2 = await server.handle_command(server.CommandRequest(cmd="add_url", path=url2))
			assert res2 == {"status": "ok"}
			assert clean_state.queue == [url2]
			mock_dj_pick.assert_called_once()
			mock_fetch.assert_called_with(url2)

		# 3. Empty path does nothing
		await server.handle_command(server.CommandRequest(cmd="add_url", path=None))


@pytest.mark.asyncio
async def test_command_jump(clean_state):
	"""Test 'jump' command to specific index in queue or history."""
	clean_state.queue = ["/m/q0.mp3", "/m/q1.mp3", "/m/q2.mp3"]

	res = await server.handle_command(server.CommandRequest(cmd="jump", type="queue", index=1))
	assert res == {"status": "ok"}
	assert clean_state.current_track == "/m/q1.mp3"


@pytest.mark.asyncio
async def test_command_seek_mpv_and_local_player(clean_state, clean_manager):
	"""Test seek and seek_absolute for both MPV mode and connected WebSocket local player."""
	# 1. Seek relative via MPV
	await server.handle_command(server.CommandRequest(cmd="seek", amount=15.0))
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["seek", 15.0]}))

	# 2. Seek absolute via MPV
	await server.handle_command(server.CommandRequest(cmd="seek_absolute", amount=45.0))
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["seek", 45.0, "absolute"]}))
	assert clean_state.time_pos == 45.0

	# 3. Seek with connected Local Player WebSocket
	mock_ws = MagicMock()
	mock_ws.send_json = AsyncMock()
	clean_manager.local_player_ws = mock_ws

	await server.handle_command(server.CommandRequest(cmd="seek", amount=-10.0))
	mock_ws.send_json.assert_called_with({"type": "local_player_seek", "mode": "relative", "amount": -10.0})

	clean_state.mpv._send.reset_mock()
	await server.handle_command(server.CommandRequest(cmd="seek_absolute", amount=90.0))
	mock_ws.send_json.assert_called_with({"type": "local_player_seek", "mode": "absolute", "amount": 90.0})
	clean_state.mpv._send.assert_called_with(json.dumps({"command": ["seek", 90.0, "absolute"]}))
	assert clean_state.time_pos == 90.0

	# 4. Seek with None amount does nothing
	clean_state.mpv._send.reset_mock()
	mock_ws.send_json.reset_mock()
	await server.handle_command(server.CommandRequest(cmd="seek", amount=None))
	await server.handle_command(server.CommandRequest(cmd="seek_absolute", amount=None))
	clean_state.mpv._send.assert_not_called()
	mock_ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_command_toggle_favorite_and_db_persistence(clean_state, temp_db):
	"""Test toggle_favorite persists to SQLite database and handles exceptions."""
	clean_state.path_to_id["/music/song.mp3"] = "track_hash_123"

	# Add favorite
	await server.handle_command(server.CommandRequest(cmd="toggle_favorite", path="/music/song.mp3"))
	assert "track_hash_123" in clean_state.favorites

	with sqlite3.connect(temp_db) as conn:
		count = conn.execute("SELECT COUNT(*) FROM favorites WHERE track_id = 'track_hash_123'").fetchone()[0]
		assert count == 1

	# Remove favorite
	await server.handle_command(server.CommandRequest(cmd="toggle_favorite", path="/music/song.mp3"))
	assert "track_hash_123" not in clean_state.favorites

	with sqlite3.connect(temp_db) as conn:
		count = conn.execute("SELECT COUNT(*) FROM favorites WHERE track_id = 'track_hash_123'").fetchone()[0]
		assert count == 0

	# Test DB error branch does not crash handler
	with patch("server.sqlite3.connect", side_effect=sqlite3.OperationalError("DB locked")):
		res = await server.handle_command(server.CommandRequest(cmd="toggle_favorite", path="/music/song.mp3"))
		assert res == {"status": "ok"}


@pytest.mark.asyncio
async def test_command_dj_toggles_and_pause_after(clean_state):
	"""Test toggle_dj_carpincho, toggle_dj_safe_mode, and pause_after commands."""
	# 1. toggle_dj_carpincho when idle -> enables and calls play_next
	clean_state.current_track = None
	clean_state.dj_carpincho_enabled = False
	clean_state.tracks_cache = [{"path": "/music/sample.mp3", "bpm": 120.0, "energy": 0.5, "spectral_centroid": 1500.0}]

	with patch.object(clean_state, "play_next", new_callable=AsyncMock) as mock_play_next:
		await server.handle_command(server.CommandRequest(cmd="toggle_dj_carpincho"))
		assert clean_state.dj_carpincho_enabled is True
		mock_play_next.assert_called_once_with(skipped_by_user=True)

	# 2. toggle_dj_carpincho when playing -> disables and calls _pick_dj_next
	clean_state.current_track = "/music/sample.mp3"
	with patch.object(clean_state, "_pick_dj_next") as mock_dj_pick:
		await server.handle_command(server.CommandRequest(cmd="toggle_dj_carpincho"))
		assert clean_state.dj_carpincho_enabled is False
		mock_dj_pick.assert_called_once()

	# 3. toggle_dj_safe_mode
	with patch.object(clean_state, "_pick_dj_next") as mock_dj_pick:
		await server.handle_command(server.CommandRequest(cmd="toggle_dj_safe_mode", state=True))
		assert clean_state.dj_safe_mode is True
		mock_dj_pick.assert_called_once()

		# None state does nothing
		mock_dj_pick.reset_mock()
		await server.handle_command(server.CommandRequest(cmd="toggle_dj_safe_mode", state=None))
		mock_dj_pick.assert_not_called()

	# 4. pause_after
	await server.handle_command(server.CommandRequest(cmd="pause_after", path="/music/stop_here.mp3"))
	assert clean_state.pause_after_path == "/music/stop_here.mp3"


@pytest.mark.asyncio
async def test_command_unknown_or_malformed(clean_state):
	"""Test unknown or unhandled cmd values return ok without mutating state."""
	with patch("server.broadcast_state", new_callable=AsyncMock) as mock_broadcast:
		res = await server.handle_command(server.CommandRequest(cmd="unknown_invalid_command_xyz"))
		assert res == {"status": "ok"}
		mock_broadcast.assert_called_once()
