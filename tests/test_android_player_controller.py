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


@pytest.mark.asyncio
async def test_android_player_controller_syncs_notification_from_orchestrator_state() -> None:
	"""El backend debe actualizar la notificación nativa directamente sin depender de WebKit."""
	from types import SimpleNamespace

	from app.infrastructure.mpv.android_controller import AndroidPlayerController

	kotlin_player = MagicMock()
	ctrl = AndroidPlayerController(native_player=kotlin_player)
	await ctrl.start()

	state = SimpleNamespace(
		current_track="/storage/B6F2-55E6/musica/tema.mp3",
		mpv_paused=False,
		duration=200.0,
		time_pos=15.0,
		pause_after_path="/storage/B6F2-55E6/musica/tema.mp3",
		is_playing_radio_announcement=False,
		server_port=1729,
		favorites=["id-1"],
		path_to_id={"/storage/B6F2-55E6/musica/tema.mp3": "id-1"},
		id_to_current_path={"id-1": "/storage/B6F2-55E6/musica/tema.mp3"},
		tracks_cache=[
			{
				"path": "/storage/B6F2-55E6/musica/tema.mp3",
				"display_title": "Barro Tal Vez",
				"display_artist": "Luis Alberto Spinetta",
			}
		],
		url_metadata={},
	)

	ctrl.sync_notification_from_state(state)
	kotlin_player.updateNotification.assert_called_once_with(
		"Barro Tal Vez",
		"Luis Alberto Spinetta",
		False,
		"http://127.0.0.1:1729/cover?path=%2Fstorage%2FB6F2-55E6%2Fmusica%2Ftema.mp3&size=512",
		"/storage/B6F2-55E6/musica/tema.mp3",
		200000,
		15000,
		True,
		True,
	)

	# Si no cambió nada relevante de metadatos, no spamea a Kotlin
	ctrl.sync_notification_from_state(state)
	assert kotlin_player.updateNotification.call_count == 1

	# Modo locutor
	state.is_playing_radio_announcement = True
	ctrl.sync_notification_from_state(state)
	assert kotlin_player.updateNotification.call_count == 2
	args = kotlin_player.updateNotification.call_args[0]
	assert args[0] == "Carpincho Locutor"
	assert args[1] == "La Rockola del Carpincho"

	# Sin tema activo (frenado)
	state.is_playing_radio_announcement = False
	state.current_track = None
	ctrl.sync_notification_from_state(state)
	assert kotlin_player.updateNotification.call_count == 3
	args = kotlin_player.updateNotification.call_args[0]
	assert args[0] == "La Rockola del Carpincho"
	assert args[1] == "En espera"
	assert args[2] is True


@pytest.mark.asyncio
async def test_android_player_controller_syncs_notification_position_on_progress() -> None:
	"""El tick de ExoPlayer debe refrescar el progreso en la notificación aunque el WebView esté apagado."""
	from types import SimpleNamespace

	from app.infrastructure.mpv.android_controller import AndroidPlayerController

	kotlin_player = MagicMock()
	state = SimpleNamespace(mpv_paused=False)
	ctrl = AndroidPlayerController(state_ref=state, native_player=kotlin_player)
	await ctrl.start()

	handler = kotlin_player.setPythonCallbackHandler.call_args[0][0]
	handler.on_position(10.0, 180.0)
	kotlin_player.updateNotificationPosition.assert_called_once_with(180000, 10000, False)

	# Salto menor a 1.5s inmediato se throttlea
	handler.on_position(10.5, 180.0)
	assert kotlin_player.updateNotificationPosition.call_count == 1

	# Salto > 1.5s actualiza al instante
	handler.on_position(45.0, 180.0)
	assert kotlin_player.updateNotificationPosition.call_count == 2
	kotlin_player.updateNotificationPosition.assert_called_with(180000, 45000, False)
