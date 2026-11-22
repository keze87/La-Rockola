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
		"http://127.0.0.1:1729/cover?path=%2Fstorage%2FB6F2-55E6%2Fmusica%2Ftema.mp3&size=256",
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


@pytest.mark.asyncio
async def test_cmd_pause_with_explicit_state_never_unpauses() -> None:
	"""_cmd_pause con state=True debe pausar explícitamente sin togglear si ya estaba pausado (ej. AUDIO_BECOMING_NOISY)."""
	from app.api.commands import _cmd_pause
	from app.api.schemas import CommandRequest

	state = MagicMock()
	state.current_track = "/music/zamba.mp3"
	state.queue = []
	state.mpv_paused = True
	state.set_pause = AsyncMock()

	# Caso explícito state=True cuando ya estaba pausado -> sigue pausado (NO despausa)
	await _cmd_pause(state, CommandRequest(cmd="pause", state=True), MagicMock())
	state.set_pause.assert_awaited_once_with(True)

	# Caso toggle sin state -> alterna normalmente
	state.set_pause.reset_mock()
	await _cmd_pause(state, CommandRequest(cmd="pause"), MagicMock())
	state.set_pause.assert_awaited_once_with(False)


@pytest.mark.asyncio
async def test_android_player_controller_re_resolves_when_active_instance_changes(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""_ensure_native debe re-enlazar si AndroidAudioPlayer fue recreado por el servicio."""
	from app.infrastructure.mpv import android_controller

	player_v1 = MagicMock(name="player_v1")
	player_v2 = MagicMock(name="player_v2")
	active_ref: list[object | None] = [player_v1]
	monkeypatch.setattr(android_controller, "resolve_native_android_player", lambda: active_ref[0])

	ctrl = android_controller.AndroidPlayerController(native_player=player_v1)
	await ctrl.start()
	assert ctrl._ensure_native() is player_v1

	# Simula recreación del servicio con nueva instancia de AndroidAudioPlayer
	active_ref[0] = player_v2
	resolved = ctrl._ensure_native()
	assert resolved is player_v2
	player_v2.setPythonCallbackHandler.assert_called_once()


@pytest.mark.asyncio
async def test_android_player_controller_reports_error_when_unavailable_and_recovers(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Si no hay player nativo expone native_error y lo limpia al reintentar y resolver."""
	from app.infrastructure.mpv import android_controller

	active_ref: list[object | None] = [None]
	monkeypatch.setattr(android_controller, "resolve_native_android_player", lambda: active_ref[0])

	ctrl = android_controller.AndroidPlayerController(native_player=None)
	assert ctrl._ensure_native() is None
	assert ctrl.native_error

	player_v1 = MagicMock(name="player_v1")
	active_ref[0] = player_v1
	assert ctrl._ensure_native() is player_v1
	assert ctrl.native_error is None


@pytest.mark.asyncio
async def test_system_info_exposes_audio_error_when_android_player_missing(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""GET /system/info debe reportar audio_ready=False y audio_error si falta AndroidAudioPlayer."""
	from types import SimpleNamespace

	from app.api import system as system_api
	from app.infrastructure.mpv import android_controller

	monkeypatch.setattr(android_controller, "resolve_native_android_player", lambda: None)
	ctrl = android_controller.AndroidPlayerController(native_player=None)

	fake_orch = SimpleNamespace(
		initial_dir="",
		secondary_dir=None,
		music_dir_configured=False,
		server_port=1729,
		local_ip="127.0.0.1",
		server_url="http://127.0.0.1:1729",
		mpv=ctrl,
		refresh_folder_status=lambda: SimpleNamespace(status="unconfigured", display_name=None, error=None),
	)
	fake_settings = SimpleNamespace(music_dir="", music_dir2=None, music_dir_configured=False, port=1729)
	fake_container = SimpleNamespace(ensure_orchestrator=lambda: fake_orch, settings=fake_settings)
	monkeypatch.setattr(system_api, "get_container", lambda: fake_container)

	info = await system_api.get_system_info()
	assert info["audio_ready"] is False
	assert isinstance(info["audio_error"], str) and info["audio_error"]


@pytest.mark.asyncio
async def test_consecutive_position_ticks_do_not_re_resolve_jclass(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Muchos ticks consecutivos no deben volver a resolver jclass ni consultar JNI innecesariamente."""
	import sys
	from types import SimpleNamespace

	from app.infrastructure.mpv import android_controller

	player = MagicMock(name="player")
	jclass_calls = 0
	active_instance_calls = 0

	class _FakePlayerClass:
		@staticmethod
		def getActiveInstance() -> object:
			nonlocal active_instance_calls
			active_instance_calls += 1
			return player

	def _fake_jclass(name: str) -> object:
		nonlocal jclass_calls
		assert name == "ar.carpincho.rockola.AndroidAudioPlayer"
		jclass_calls += 1
		return _FakePlayerClass

	monkeypatch.setitem(sys.modules, "java", SimpleNamespace(jclass=_fake_jclass))
	if hasattr(android_controller, "_ANDROID_PLAYER_CLS"):
		monkeypatch.setattr(android_controller, "_ANDROID_PLAYER_CLS", None)

	ctrl = android_controller.AndroidPlayerController(native_player=None)
	assert ctrl.is_native_available() is True

	for i in range(20):
		ctrl._bridge.on_position(i * 4.0, 180.0)

	assert jclass_calls == 1
	assert active_instance_calls == 1
