import asyncio
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
