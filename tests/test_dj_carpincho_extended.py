import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_dj_carpincho_instant_play_on_skip(clean_state):
	"""Test DJ Carpincho picks and immediately starts track when skipped by user."""
	state = clean_state
	t1 = {"path": "/m/1.mp3", "display_title": "Song 1"}
	t2 = {"path": "/m/2.mp3", "display_title": "Song 2"}
	state.tracks_cache = [t1, t2]
	state.dj_carpincho_enabled = True
	state.current_track = "/m/1.mp3"

	# User skips track with empty queue
	await state.play_next(skipped_by_user=True)
	assert state.current_track == "/m/2.mp3"
	assert state.history == ["/m/1.mp3"]


@pytest.mark.asyncio
async def test_dj_carpincho_natural_transition_with_countdown(clean_state):
	"""Test DJ Carpincho transition on natural track finish."""
	state = clean_state
	t1 = {"path": "/m/1.mp3", "display_title": "Song 1"}
	t2 = {"path": "/m/2.mp3", "display_title": "Song 2"}
	state.tracks_cache = [t1, t2]
	state.dj_carpincho_enabled = True
	state.current_track = "/m/1.mp3"

	with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
		await state.play_next(skipped_by_user=False)
		mock_sleep.assert_called_once_with(10)
		assert state.current_track == "/m/2.mp3"


@pytest.mark.asyncio
async def test_dj_carpincho_exhaustion(clean_state):
	"""Test DJ Carpincho turns itself off when all library tracks have been played in session."""
	state = clean_state
	t1 = {"path": "/m/1.mp3", "display_title": "Song 1"}
	state.tracks_cache = [t1]
	state.history = ["/m/1.mp3"]
	state.dj_carpincho_enabled = True
	state.dj_next_track = None

	await state.play_next(skipped_by_user=True)
	assert state.dj_carpincho_enabled is False
	assert state.current_track is None


@pytest.mark.asyncio
async def test_dj_pick_next_clears_when_disabled(clean_state):
	"""Test _pick_dj_next clears dj_next_track when DJ is disabled or queue is not empty."""
	state = clean_state
	t1 = {"path": "/m/1.mp3", "display_title": "Song 1"}
	state.tracks_cache = [t1]
	state.dj_next_track = t1

	# Disabled DJ clears next track
	state.dj_carpincho_enabled = False
	state._pick_dj_next()
	assert state.dj_next_track is None

	# Non-empty queue clears next track
	state.dj_carpincho_enabled = True
	state.queue = ["/m/queued.mp3"]
	state._pick_dj_next()
	assert state.dj_next_track is None
