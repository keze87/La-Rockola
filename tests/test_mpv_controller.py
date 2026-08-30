import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_mpv_process_event_line_property_changes():
	"""Test parsing of property-change IPC messages for volume, pause, time-pos, duration, mute."""
	callbacks = {
		"volume_update": AsyncMock(),
		"pause_update": AsyncMock(),
		"time_update": AsyncMock(),
		"duration_update": AsyncMock(),
		"mute_update": AsyncMock(),
	}
	mpv = server.AsyncMpvController(callbacks)

	# 1. Volume update
	line = json.dumps({"event": "property-change", "name": "volume", "data": 75}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["volume_update"].assert_called_once_with(75)

	# 2. Pause update
	line = json.dumps({"event": "property-change", "name": "pause", "data": True}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["pause_update"].assert_called_once_with(True)

	# 3. Time update
	line = json.dumps({"event": "property-change", "name": "time-pos", "data": 42.5}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["time_update"].assert_called_once_with(42.5)

	# 4. Duration update
	line = json.dumps({"event": "property-change", "name": "duration", "data": 210.0}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["duration_update"].assert_called_once_with(210.0)

	# 5. Mute update
	line = json.dumps({"event": "property-change", "name": "mute", "data": True}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["mute_update"].assert_called_once_with(True)


@pytest.mark.asyncio
async def test_mpv_process_event_line_end_file():
	"""Test parsing of end-file events with reason eof and stop."""
	callbacks = {
		"song_ended": AsyncMock(),
		"track_stopped": AsyncMock(),
	}
	mpv = server.AsyncMpvController(callbacks)

	# EOF triggers song_ended
	line = json.dumps({"event": "end-file", "reason": "eof"}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["song_ended"].assert_called_once()

	# Stop triggers track_stopped
	line = json.dumps({"event": "end-file", "reason": "stop"}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["track_stopped"].assert_called_once()


@pytest.mark.asyncio
async def test_mpv_start_is_restart_behavior():
	"""Verify that start(is_restart=False) does not invoke mpv_restarted, but start(is_restart=True) does."""
	callbacks = {
		"mpv_restarted": AsyncMock(),
	}
	mpv = server.AsyncMpvController(callbacks)

	mock_reader = MagicMock()
	mock_reader.readline = AsyncMock(return_value=b"")
	mock_writer = MagicMock()
	mock_writer.drain = AsyncMock()
	mock_writer.write = MagicMock()

	with (
		patch("asyncio.create_subprocess_exec") as mock_exec,
		patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer)),
		patch("os.path.exists", return_value=True),
		patch.object(mpv, "_send", new_callable=AsyncMock),
	):
		mock_process = MagicMock()
		mock_process.returncode = None
		mock_process.wait = AsyncMock(return_value=0)
		mock_exec.return_value = mock_process

		# Initial startup (is_restart=False)
		await mpv.start(is_restart=False)
		await asyncio.sleep(0.01)
		callbacks["mpv_restarted"].assert_not_called()

		# Explicit restart (is_restart=True)
		await mpv.start(is_restart=True)
		await asyncio.sleep(0.01)
		callbacks["mpv_restarted"].assert_called_once()
