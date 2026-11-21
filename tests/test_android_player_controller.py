"""Tests para AndroidPlayerController (puente Python <-> ExoPlayer Kotlin)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_android_player_controller_delegates_commands_to_kotlin_bridge() -> None:
	"""AndroidPlayerController debe delegar comandos de reproducción al objeto Kotlin ExoPlayer."""
	from app.infrastructure.mpv.android_controller import AndroidPlayerController

	kotlin_player = MagicMock()
	ctrl = AndroidPlayerController(native_player=kotlin_player)
	await ctrl.start()

	kotlin_player.setPythonCallbackHandler.assert_called_once()
	assert ctrl.is_running is True

	await ctrl.load_file("/storage/emulated/0/Music/zamba.mp3")
	kotlin_player.loadFile.assert_called_once_with("/storage/emulated/0/Music/zamba.mp3")

	await ctrl.set_pause(True)
	kotlin_player.setPause.assert_called_once_with(True)

	await ctrl.seek_absolute(42.5)
	kotlin_player.seekAbsolute.assert_called_once_with(42.5)

	await ctrl.seek_relative(-5.0)
	kotlin_player.seekRelative.assert_called_once_with(-5.0)

	await ctrl.set_volume(75.0)
	kotlin_player.setVolume.assert_called_once_with(75.0)

	await ctrl.set_mute(True)
	kotlin_player.setMute.assert_called_once_with(True)

	await ctrl.stop_playback()
	kotlin_player.stopPlayback.assert_called_once()

	await ctrl.stop()
	assert ctrl.is_running is False


@pytest.mark.asyncio
async def test_android_player_controller_dispatches_callbacks_to_event_loop() -> None:
	"""Los callbacks síncronos desde Kotlin deben invocar los handlers async del orquestador."""
	from app.infrastructure.mpv.android_controller import AndroidPlayerController

	kotlin_player = MagicMock()
	on_duration = AsyncMock()
	on_pause = AsyncMock()
	on_time = AsyncMock()
	on_eof = AsyncMock()

	ctrl = AndroidPlayerController(
		callbacks={
			"duration_update": on_duration,
			"pause_update": on_pause,
			"time_update": on_time,
			"song_ended": on_eof,
		},
		native_player=kotlin_player,
	)
	await ctrl.start()

	handler = kotlin_player.setPythonCallbackHandler.call_args[0][0]
	handler.on_duration(180.0)
	handler.on_pause_changed(False)
	handler.on_position(12.5, 180.0)
	handler.on_eof()

	await asyncio.sleep(0.05)

	assert on_duration.await_count == 2
	on_duration.assert_awaited_with(180.0)
	on_pause.assert_awaited_once_with(False)
	on_time.assert_awaited_once_with(12.5)
	on_eof.assert_awaited_once()
