"""
Enrutador declarativo de comandos de reproducción, fila, historial, DJ y ventana de MPV.
Reemplaza las cascadas if/elif por una tabla de despacho tipada (COMMAND_HANDLERS).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter

import app.core.config as config_mod
from app.api.schemas import CommandRequest
from app.core.container import get_container
from app.domain.playback.orchestrator import PlaybackOrchestrator, broadcast_state
from app.infrastructure.weather.client import reset_weather_cache

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["Playback"])

CommandHandlerFn = Callable[[PlaybackOrchestrator, CommandRequest, Any], Awaitable[None]]


async def _cmd_play(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if state.current_track:
		state.history.append(state.current_track)
		state.current_track = None
	if req.path:
		await state.play_track(req.path)


async def _cmd_pause(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	if not state.current_track and state.queue:
		await state.play_next(skipped_by_user=True)
	else:
		await state.set_pause(not state.mpv_paused)


async def _cmd_skip(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	await state.play_next(skipped_by_user=True)


async def _cmd_prev(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	await state.play_prev()


async def _cmd_stop(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	if state.current_track and state.current_track != getattr(state, "radio_announcement_path", ""):
		state.history.append(state.current_track)
	await state.stop_playback(reset_ui_state=True)


async def _cmd_clear_queue(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	state.queue_manager.clear()


async def _cmd_vol_up(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	await state.set_volume(state.volume + 5)


async def _cmd_vol_down(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	await state.set_volume(state.volume - 5)


async def _cmd_set_volume(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.vollevel is not None:
		await state.set_volume(req.vollevel)


async def _cmd_set_mute(state: PlaybackOrchestrator, req: CommandRequest, mgr: Any) -> None:
	if req.state is not None:
		state.server_muted = req.state
		has_local = bool(mgr and getattr(mgr, "local_player_ws", None) is not None)
		await state.mpv.set_mute(True if has_local else state.server_muted)


async def _cmd_fullscreen(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	await state.mpv.toggle_fullscreen()


async def _cmd_toggle_queue(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.path:
		await state.toggle_queue(req.path)


async def _cmd_add_url(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.path:
		state.queue.append(req.path)
		state._pick_dj_next()
		if not state.current_track and not getattr(state, "is_synthesizing_radio", False):
			await state.play_next(skipped_by_user=True)
		asyncio.create_task(state.fetch_yt_dlp_metadata(req.path))


async def _cmd_jump(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.type and req.index is not None:
		await state.jump(req.type, req.index)


async def _cmd_seek(state: PlaybackOrchestrator, req: CommandRequest, mgr: Any) -> None:
	if req.amount is not None:
		if mgr and getattr(mgr, "local_player_ws", None) is not None:
			await mgr.local_player_ws.send_json(
				{
					"type": "local_player_seek",
					"mode": "relative",
					"amount": req.amount,
				}
			)
		else:
			await state.mpv.seek_relative(req.amount)


async def _cmd_seek_absolute(state: PlaybackOrchestrator, req: CommandRequest, mgr: Any) -> None:
	if req.amount is not None:
		if mgr and getattr(mgr, "local_player_ws", None) is not None:
			await mgr.local_player_ws.send_json(
				{
					"type": "local_player_seek",
					"mode": "absolute",
					"amount": req.amount,
				}
			)
		await state.mpv.seek_absolute(req.amount)
		state.time_pos = req.amount


async def _cmd_toggle_favorite(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.path:
		track_id = state.path_to_id.get(req.path, req.path)
		if track_id in state.favorites:
			state.favorites.remove(track_id)
			try:
				await asyncio.to_thread(state.favorites_repo.remove, track_id)
			except Exception as e:
				logger.error(f"Error guardando favorito: {e}")
		else:
			state.favorites.append(track_id)
			try:
				await asyncio.to_thread(state.favorites_repo.add, track_id)
			except Exception as e:
				logger.error(f"Error guardando favorito: {e}")


async def _cmd_toggle_dj_carpincho(state: PlaybackOrchestrator, _req: CommandRequest, _mgr: Any) -> None:
	state.dj_carpincho_enabled = not state.dj_carpincho_enabled
	logger.info(f"DJ Carpincho cambiado a: {state.dj_carpincho_enabled}")
	if state.dj_carpincho_enabled and not state.current_track:
		await state.play_next(skipped_by_user=True)
	else:
		state._pick_dj_next()


async def _cmd_toggle_dj_safe_mode(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.state is not None:
		state.dj_safe_mode = req.state
		state._pick_dj_next()


async def _cmd_toggle_radio_mode(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.state is not None:
		state.radio_mode_enabled = req.state
	else:
		state.radio_mode_enabled = not state.radio_mode_enabled
	if state.radio_mode_enabled:
		state._reset_radio_schedule()


async def _cmd_set_weather_location(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.location and isinstance(req.location, str):
		new_loc = req.location.strip()
		state.weather_location = new_loc
		cfg_path = config_mod.get_config_path()
		cfg = config_mod.load_config(cfg_path)
		cfg["weather_location"] = new_loc
		config_mod.save_config(cfg_path, cfg)
		reset_weather_cache()
		logger.info(f"Ubicación del clima actualizada a: {state.weather_location}")


async def _cmd_pause_after(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	state.queue_manager.toggle_pause_after(req.path)


async def _cmd_remove_queue_item(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None:
		state.queue_manager.remove_queue_item(req.index)
		state._pick_dj_next()


async def _cmd_move_queue_item(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None and req.new_index is not None:
		state.queue_manager.move_queue_item(req.index, req.new_index)
		state._pick_dj_next()


async def _cmd_remove_history_item(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None:
		state.queue_manager.remove_history_item(req.index)


async def _cmd_move_history_item(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None and req.new_index is not None:
		state.queue_manager.move_history_item(req.index, req.new_index)


async def _cmd_insert_queue_item(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.path:
		state.queue_manager.insert(req.path, req.index)
		state._pick_dj_next()
		if not state.current_track:
			await state.play_next(skipped_by_user=True)
		if req.path.startswith("http"):
			asyncio.create_task(state.fetch_yt_dlp_metadata(req.path))


async def _cmd_move_current_to_queue(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if state.current_track:
		old_current = state.current_track
		state.current_track = None
		if state.pause_after_path == old_current:
			state.pause_after_path = None
		if state.queue:
			next_track = state.queue.pop(0)
			idx = max(0, min(len(state.queue), req.index if req.index is not None else 0))
			state.queue.insert(idx, old_current)
			state._pick_dj_next()
			await state.play_track(next_track)
		else:
			state.queue.append(old_current)
			state.mpv_paused = False
			await state.mpv.stop_playback()
			state._pick_dj_next()


async def _cmd_move_current_to_history(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if state.current_track:
		old_current = state.current_track
		state.current_track = None
		if state.pause_after_path == old_current:
			state.pause_after_path = None
		idx = max(
			0, min(len(state.history), req.history_index if req.history_index is not None else len(state.history))
		)
		state.history.insert(idx, old_current)
		await state.play_next(skipped_by_user=True)


async def _cmd_move_queue_to_history(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None and 0 <= req.index < len(state.queue):
		item = state.queue.pop(req.index)
		idx = max(
			0, min(len(state.history), req.history_index if req.history_index is not None else len(state.history))
		)
		state.history.insert(idx, item)
		state._pick_dj_next()


async def _cmd_play_from_queue(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None and 0 <= req.index < len(state.queue):
		item = state.queue.pop(req.index)
		if state.current_track:
			state.history.append(state.current_track)
			state.current_track = None
		state._pick_dj_next()
		await state.play_track(item)


async def _cmd_move_in_playlist(state: PlaybackOrchestrator, req: CommandRequest, _mgr: Any) -> None:
	if req.index is not None and req.new_index is not None:
		from_idx = req.index
		to_idx = req.new_index
		playlist = list(state.history)
		current_idx = None
		if state.current_track:
			current_idx = len(playlist)
			playlist.append(state.current_track)
		history_boundary = len(state.history)
		playlist.extend(state.queue)

		n = len(playlist)
		if 0 <= from_idx < n and 0 <= to_idx < n and from_idx != to_idx:
			item = playlist.pop(from_idx)
			playlist.insert(to_idx, item)

			if current_idx is not None:
				if from_idx == current_idx:
					new_current_idx = to_idx
				elif from_idx < current_idx <= to_idx:
					new_current_idx = current_idx - 1
				elif to_idx <= current_idx < from_idx:
					new_current_idx = current_idx + 1
				else:
					new_current_idx = current_idx

				state.history = playlist[:new_current_idx]
				state.current_track = playlist[new_current_idx]
				state.queue = playlist[new_current_idx + 1 :]
				state._pick_dj_next()
			else:
				if from_idx < history_boundary <= to_idx:
					history_boundary -= 1
				elif to_idx < history_boundary <= from_idx:
					history_boundary += 1
				state.history = playlist[:history_boundary]
				state.queue = playlist[history_boundary:]
				state._pick_dj_next()


COMMAND_HANDLERS: dict[str, CommandHandlerFn] = {
	"play": _cmd_play,
	"pause": _cmd_pause,
	"skip": _cmd_skip,
	"prev": _cmd_prev,
	"stop": _cmd_stop,
	"clear_queue": _cmd_clear_queue,
	"vol_up": _cmd_vol_up,
	"vol_down": _cmd_vol_down,
	"set_volume": _cmd_set_volume,
	"set_mute": _cmd_set_mute,
	"fullscreen": _cmd_fullscreen,
	"toggle_queue": _cmd_toggle_queue,
	"add_url": _cmd_add_url,
	"jump": _cmd_jump,
	"seek": _cmd_seek,
	"seek_absolute": _cmd_seek_absolute,
	"toggle_favorite": _cmd_toggle_favorite,
	"toggle_dj_carpincho": _cmd_toggle_dj_carpincho,
	"toggle_dj_safe_mode": _cmd_toggle_dj_safe_mode,
	"toggle_radio_mode": _cmd_toggle_radio_mode,
	"set_weather_location": _cmd_set_weather_location,
	"pause_after": _cmd_pause_after,
	"remove_queue_item": _cmd_remove_queue_item,
	"move_queue_item": _cmd_move_queue_item,
	"remove_history_item": _cmd_remove_history_item,
	"move_history_item": _cmd_move_history_item,
	"insert_queue_item": _cmd_insert_queue_item,
	"move_current_to_queue": _cmd_move_current_to_queue,
	"move_current_to_history": _cmd_move_current_to_history,
	"move_queue_to_history": _cmd_move_queue_to_history,
	"play_from_queue": _cmd_play_from_queue,
	"move_in_playlist": _cmd_move_in_playlist,
}


@router.post("/command")
async def handle_command_endpoint(req: CommandRequest) -> dict[str, Any]:
	"""Despacha comandos de reproducción utilizando la tabla declarativa COMMAND_HANDLERS."""
	container = get_container()
	state = container.ensure_orchestrator()
	manager = container.ensure_ws_manager()
	if not state:
		return {"status": "error", "message": "Estado del servidor no inicializado"}

	logger.info(f"LLEGÓ COMANDO: {req.cmd} | Path: {req.path} | Index: {req.index}")
	handler = COMMAND_HANDLERS.get(req.cmd)
	if handler:
		await handler(state, req, manager)

	await broadcast_state()
	return {"status": "ok"}


@router.post("/mpv/hide")
async def mpv_hide() -> dict[str, str]:
	"""Reinicia MPV con la ventana oculta si está activo."""
	state = get_container().ensure_orchestrator()
	if not state:
		return {"status": "error"}
	state.mpv_visible = False
	if state.mpv and state.mpv.is_running:
		logger.info("Reiniciando MPV para ocultar la ventana...")
		await state.mpv.start(is_restart=True, state_ref=state)
	await broadcast_state()
	return {"status": "ok"}


@router.post("/mpv/show")
async def mpv_show() -> dict[str, str]:
	"""Reinicia MPV con la ventana visible si está activo."""
	state = get_container().ensure_orchestrator()
	if not state:
		return {"status": "error"}
	if state.mpv and not getattr(state.mpv, "has_display", True):
		state.mpv_visible = False
		await broadcast_state()
		return {"status": "ok"}
	state.mpv_visible = True
	if state.mpv and state.mpv.is_running:
		logger.info("Reiniciando MPV para mostrar la ventana...")
		await state.mpv.start(is_restart=True, state_ref=state)
	await broadcast_state()
	return {"status": "ok"}


handle_command = handle_command_endpoint
