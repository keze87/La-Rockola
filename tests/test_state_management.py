import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_get_full_state_dict_strips_heavy_keys(clean_state):
	"""Verify get_full_state_dict excludes fingerprints and heavy metrics from library and dj_next_track."""
	state = clean_state
	raw_track = {
		"path": "/home/music/song.mp3",
		"display_title": "Song Title",
		"display_artist": "Artist",
		"album": "Album",
		"duration_str": "3:45",
		"fingerprint": "AQAAz0mUJUqUJEqSR...",
		"bpm": 120.0,
		"energy": 0.85,
		"spectral_centroid": 2400.5,
	}
	state.tracks_cache = [raw_track]
	state.dj_next_track = raw_track

	full_state = state.get_full_state_dict(include_library=True)

	# Check library
	assert len(full_state["library"]) == 1
	lib_track = full_state["library"][0]
	assert "fingerprint" not in lib_track
	assert "bpm" not in lib_track
	assert "energy" not in lib_track
	assert "spectral_centroid" not in lib_track
	assert lib_track["display_title"] == "Song Title"

	# Check dj_next_track
	dj_track = full_state["dj_next_track"]
	assert "fingerprint" not in dj_track
	assert "bpm" not in dj_track
	assert "energy" not in dj_track
	assert dj_track["display_title"] == "Song Title"


@pytest.mark.asyncio
async def test_play_track_and_navigation(clean_state):
	"""Test play_track, play_next, and play_prev track navigation."""
	state = clean_state
	track1 = "/music/track1.mp3"
	track2 = "/music/track2.mp3"
	track3 = "/music/track3.mp3"

	# 1. Play first track
	await state.play_track(track1)
	assert state.current_track == track1
	assert state.mpv_paused is False

	# 2. Add track 2 and 3 to queue
	state.queue = [track2, track3]

	# 3. Next track
	await state.play_next()
	assert state.current_track == track2
	assert state.history == [track1]
	assert state.queue == [track3]

	# 4. Prev track
	await state.play_prev()
	assert state.current_track == track1
	assert state.history == []
	assert state.queue == [track2, track3]


@pytest.mark.asyncio
async def test_queue_manipulation(clean_state):
	"""Test queue toggling, jump, item moves, and removals."""
	state = clean_state
	track1 = "/music/track1.mp3"
	track2 = "/music/track2.mp3"
	track3 = "/music/track3.mp3"

	# toggle_queue on empty queue starts playing if no track
	await state.toggle_queue(track1)
	assert state.current_track == track1
	assert state.queue == []

	# toggle_queue adds to queue
	await state.toggle_queue(track2)
	assert state.queue == [track2]

	# toggle_queue on existing removes it
	await state.toggle_queue(track2)
	assert state.queue == []

	# Test jump to queue item
	state.queue = [track2, track3]
	await state.jump("queue", 1)  # Jump to track3 (skips track2)
	assert state.current_track == track3
	assert state.history == [track1, track2]
	assert state.queue == []


@pytest.mark.asyncio
async def test_dj_carpincho_selection(clean_state):
	"""Test DJ Carpincho random selection in Classic vs Safe Mode."""
	state = clean_state
	t1 = {"path": "/music/fav.mp3", "display_title": "Fav Song"}
	t2 = {"path": "/music/normal.mp3", "display_title": "Normal Song"}
	state.tracks_cache = [t1, t2]
	state.path_to_id = {t1["path"]: "id_fav", t2["path"]: "id_normal"}
	state.favorites = ["id_fav"]

	state.dj_carpincho_enabled = True

	# Test Classic Mode (Wild):
	state.dj_safe_mode = False
	state._pick_dj_next()
	assert state.dj_next_track in [t1, t2]

	# Test Safe Mode:
	state.dj_safe_mode = True
	state._pick_dj_next()
	assert state.dj_next_track is not None


@pytest.mark.asyncio
async def test_pause_after_path_handling(clean_state):
	"""Test that pause_after_path pauses playback once the target track finishes."""
	state = clean_state
	track1 = "/music/track1.mp3"
	track2 = "/music/track2.mp3"

	state.current_track = track1
	state.queue = [track2]
	state.pause_after_path = track1

	await state.play_next()
	assert state.current_track == track2
	assert state.mpv_paused is True
	assert state.pause_after_path is None


@pytest.mark.asyncio
async def test_time_and_duration_updates(clean_state, clean_manager, monkeypatch):
	"""Test state updates for time_pos, duration, and server_muted."""
	monkeypatch.setattr(server, "manager", clean_manager)
	state = clean_state

	# MPV time update without local player
	with patch("server.broadcast_state", new_callable=AsyncMock):
		await state.handle_time_update(12.5)
		assert state.time_pos == 12.5

		await state.handle_duration_update(240.0)
		assert state.duration == 240.0

		await state.handle_mute_update(True)
		assert state.server_muted is True

	# Time update ignored when local player is active
	mock_ws = MagicMock()
	clean_manager.local_player_ws = mock_ws
	await state.handle_time_update(99.0)
	assert state.time_pos == 12.5  # Kept previous value


@pytest.mark.asyncio
async def test_pause_command_toggles(clean_state, monkeypatch):
	"""Test pause command behavior when playing vs when queue exists vs unpausing."""
	monkeypatch.setattr(server, "state", clean_state)
	state = clean_state
	state.current_track = "/m/playing.mp3"
	state.mpv_paused = False

	# 1. Toggle to pause
	await server.handle_command(server.CommandRequest(cmd="pause"))
	assert state.mpv_paused is True

	# 2. Toggle to unpause
	await server.handle_command(server.CommandRequest(cmd="pause"))
	assert state.mpv_paused is False

	# 3. Pause when stopped but queue exists starts playing next track
	state.current_track = None
	state.queue = ["/m/next.mp3"]
	await server.handle_command(server.CommandRequest(cmd="pause"))
	assert state.current_track == "/m/next.mp3"


@pytest.mark.asyncio
async def test_fetch_yt_dlp_metadata(clean_state):
	"""Test fetch_yt_dlp_metadata extracting title, artist, and duration from yt-dlp."""
	state = clean_state
	url = "https://youtube.com/watch?v=mock123"

	mock_proc = MagicMock()
	mock_json = json.dumps({"title": "Mock YT Song", "uploader": "Mock Channel", "duration": 215}).encode("utf-8")
	mock_proc.communicate = AsyncMock(return_value=(mock_json, b""))

	with (
		patch("asyncio.create_subprocess_exec", return_value=mock_proc),
		patch("server.broadcast_state", new_callable=AsyncMock),
	):
		await state.fetch_yt_dlp_metadata(url)
		assert url in state.url_metadata
		meta = state.url_metadata[url]
		assert meta["display_title"] == "Mock YT Song"
		assert meta["display_artist"] == "Mock Channel"
		assert meta["duration_str"] == "3:35"
