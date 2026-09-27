from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server import CommandRequest, app, handle_command, state


@pytest.fixture(autouse=True)
def reset_radio_state(tmp_path):
	state.radio_mode_enabled = False
	state.radio_track_counter = 0
	state.radio_tracks_until_next = 2
	state.is_playing_radio_announcement = False
	state.radio_announcement_path = str(tmp_path / "radio.mp3")
	state.queue = []
	state.history = []
	state.current_track = None
	state.mpv = MagicMock()
	state.mpv._send = AsyncMock()
	state.mpv.is_running = True


@pytest.mark.asyncio
async def test_toggle_radio_mode_command():
	req = CommandRequest(cmd="toggle_radio_mode")
	await handle_command(req)
	assert state.radio_mode_enabled is True
	assert state.radio_track_counter == 0
	assert 1 <= state.radio_tracks_until_next <= 2

	# Toggle off
	await handle_command(req)
	assert state.radio_mode_enabled is False

	# Explicit state
	req_explicit = CommandRequest(cmd="toggle_radio_mode", state=True)
	await handle_command(req_explicit)
	assert state.radio_mode_enabled is True


def test_state_to_dict_includes_radio_fields():
	d = state.get_full_state_dict()
	assert "radio_mode_enabled" in d
	assert "is_synthesizing_radio" in d
	assert "is_playing_radio_announcement" in d
	assert "has_edge_tts" in d
	assert d["radio_mode_enabled"] is False


@pytest.mark.asyncio
async def test_play_next_increments_counter_and_triggers_radio():
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/song2.mp3"]
	state.current_track = "/music/song1.mp3"

	mock_create = AsyncMock(return_value=(True, "Momento de la Fortuna 🥠 (Tomás)", "Son las 15 horas..."))

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", side_effect=fake_play_track) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# Normal track was appended to history
		assert "/music/song1.mp3" in state.history

		# Radio announcement was triggered
		mock_create.assert_awaited_once_with(
			state.radio_announcement_path,
			bg_track_path="/music/song2.mp3",
			bg_offset=0.0,
			bg_volume=0.18,
		)
		assert state.is_playing_radio_announcement is True
		assert state.current_track == state.radio_announcement_path
		mock_play.assert_awaited_once_with(state.radio_announcement_path)

		# Counter reset and new random threshold
		assert state.radio_track_counter == 0
		assert 2 <= state.radio_tracks_until_next <= 3


@pytest.mark.asyncio
async def test_radio_announcement_finished_does_not_enter_history():
	state.radio_mode_enabled = True
	state.current_track = state.radio_announcement_path
	state.is_playing_radio_announcement = True
	state.queue = ["/music/next_song.mp3"]

	with (
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		# Announcement finishes naturally
		await state.play_next(skipped_by_user=False)

		# Announcement must NOT be in history
		assert state.radio_announcement_path not in state.history
		assert state.is_playing_radio_announcement is False

		# Next track in queue plays
		mock_play.assert_awaited_once_with("/music/next_song.mp3")


@pytest.mark.asyncio
async def test_skip_during_radio_announcement():
	state.radio_mode_enabled = True
	state.current_track = state.radio_announcement_path
	state.is_playing_radio_announcement = True
	state.queue = ["/music/next_song.mp3"]

	with (
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		# User presses skip
		await state.play_next(skipped_by_user=True)

		assert state.radio_announcement_path not in state.history
		assert state.is_playing_radio_announcement is False
		mock_play.assert_awaited_once_with("/music/next_song.mp3")


@pytest.mark.asyncio
async def test_stop_cleans_up_radio_announcement():
	state.current_track = state.radio_announcement_path
	state.is_playing_radio_announcement = True

	req = CommandRequest(cmd="stop")
	await handle_command(req)

	assert state.radio_announcement_path not in state.history
	assert state.current_track is None
	assert state.is_playing_radio_announcement is False


@pytest.mark.asyncio
async def test_stream_allows_radio_announcement(tmp_path):
	from httpx import ASGITransport, AsyncClient

	audio_file = tmp_path / "radio.mp3"
	audio_file.write_bytes(b"ID3fakeaudiocontent")
	state.radio_announcement_path = str(audio_file)

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
		res = await ac.get(f"/stream?path={state.radio_announcement_path}")
		assert res.status_code == 200
		assert res.content == b"ID3fakeaudiocontent"


@pytest.mark.asyncio
async def test_cover_serves_favicon_for_radio_announcement(tmp_path):
	from httpx import ASGITransport, AsyncClient

	state.radio_announcement_path = str(tmp_path / "radio.mp3")

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
		res = await ac.get(f"/cover?path={state.radio_announcement_path}")
		# Si existe public/favicon.png retorna 200 con imagen png
		favicon_p = Path("public/favicon.png")
		if favicon_p.exists():
			assert res.status_code == 200
			assert res.headers.get("content-type") == "image/png"


@pytest.mark.asyncio
async def test_radio_announcement_failure_logs_reason(caplog):
	import logging

	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/song2.mp3"]
	state.current_track = "/music/song1.mp3"

	mock_create = AsyncMock(return_value=(False, "", "Fallo simulado de conexión"))

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
		caplog.at_level(logging.WARNING),
	):
		await state.play_next(skipped_by_user=False)

		# Synthesizing flag should be cleared
		assert state.is_synthesizing_radio is False
		assert state.is_playing_radio_announcement is False

		# The warning log must explain the failure reason
		assert any("Fallo simulado de conexión" in record.message for record in caplog.records)

		# Next track in queue plays because radio failed
		mock_play.assert_awaited_once_with("/music/song2.mp3")


@pytest.mark.asyncio
async def test_toggle_queue_initial_playback_does_not_trigger_radio():
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 1
	state.current_track = None
	state.queue = []

	mock_create = AsyncMock()

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.toggle_queue("/music/song1.mp3")

		# Locutor should NOT speak before any song has started playing
		mock_create.assert_not_called()
		mock_play.assert_awaited_once_with("/music/song1.mp3")
