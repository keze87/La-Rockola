import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_handle_song_ended_advances_queue(clean_state, clean_manager, monkeypatch):
	"""Test handle_song_ended registers play stat and advances queue."""
	monkeypatch.setattr(server, "manager", clean_manager)
	state = clean_state
	state.current_track = "/m/song1.mp3"
	state.queue = ["/m/song2.mp3"]

	with (
		patch.object(state, "_register_play_stat") as mock_reg,
		patch("server.broadcast_state", new_callable=AsyncMock),
	):
		await state.handle_song_ended()
		mock_reg.assert_called_once_with("/m/song1.mp3")
		assert state.current_track == "/m/song2.mp3"


@pytest.mark.asyncio
async def test_handle_song_ended_ignored_when_local_player_active(clean_state, clean_manager, monkeypatch):
	"""Test handle_song_ended is bypassed when local player is active."""
	monkeypatch.setattr(server, "manager", clean_manager)
	clean_manager.local_player_ws = MagicMock()
	state = clean_state
	state.current_track = "/m/song1.mp3"
	state.queue = ["/m/song2.mp3"]

	with patch.object(state, "_register_play_stat") as mock_reg:
		await state.handle_song_ended()
		mock_reg.assert_not_called()
		assert state.current_track == "/m/song1.mp3"


@pytest.mark.asyncio
async def test_handle_mpv_restarted(clean_state):
	"""Test handle_mpv_restarted re-loads active song into new MPV process."""
	state = clean_state
	state.current_track = "/m/playing_now.mp3"

	await state.handle_mpv_restarted()
	assert state.mpv._send.call_count >= 1
	first_call = json.loads(state.mpv._send.call_args_list[0][0][0])
	assert first_call["command"] == ["loadfile", "/m/playing_now.mp3"]


@pytest.mark.asyncio
async def test_handle_track_stopped_debounce(clean_state, clean_manager, monkeypatch):
	"""Test handle_track_stopped debounces within 1.5s of track change."""
	monkeypatch.setattr(server, "manager", clean_manager)
	state = clean_state
	state.current_track = "/m/song1.mp3"
	state.last_track_change = time.time()  # Just changed

	with patch("server.broadcast_state", new_callable=AsyncMock) as mock_broadcast:
		# Within 1.5s: ignored
		await state.handle_track_stopped()
		mock_broadcast.assert_not_called()
		assert state.current_track == "/m/song1.mp3"

		# After 2s: resets state and broadcasts
		state.last_track_change = time.time() - 2.0
		await state.handle_track_stopped()
		mock_broadcast.assert_called_once()
		assert state.current_track is None


@pytest.mark.asyncio
async def test_handle_volume_and_pause_updates(clean_state):
	"""Test handle_volume_update and handle_pause_update broadcast state."""
	state = clean_state

	with patch("server.broadcast_state", new_callable=AsyncMock) as mock_broadcast:
		await state.handle_volume_update(85)
		assert state.volume == 85

		await state.handle_pause_update(True)
		assert state.mpv_paused is True
		assert mock_broadcast.call_count == 2
