"""
Enrutador de comandos de reproducción y ventana de MPV.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sys
from typing import Any

from fastapi import APIRouter

from app.api.schemas import CommandRequest
from app.core.config import get_config_path, load_config, save_config
from app.core.dependencies import get_manager, get_state
from app.db.repositories import FavoritesRepository

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["Playback"])


def _srv(name: str, fallback: Any = None) -> Any:
	"""Resuelve símbolos dinámicos desde server.py para soportar monkeypatching en tests."""
	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, name):
		return getattr(srv, name)
	return fallback


@router.post("/command")
async def handle_command_endpoint(req: CommandRequest) -> dict[str, Any]:
	"""Procesa comandos de control de reproducción enviados por la UI o la API."""
	state = get_state()
	manager = get_manager()
	if not state:
		return {"status": "error", "message": "Estado del servidor no inicializado"}

	logger.info(f"LLEGÓ COMANDO: {req.cmd} | Path: {req.path} | Index: {req.index}")
	cmd = req.cmd

	if cmd == "play":
		if state.current_track:
			state.history.append(state.current_track)
			state.current_track = None
		if req.path:
			await state.play_track(req.path)
	elif cmd == "pause":
		if not state.current_track and state.queue:
			await state.play_next(skipped_by_user=True)
		else:
			await state.set_pause(not state.mpv_paused)
	elif cmd == "skip":
		await state.play_next(skipped_by_user=True)
	elif cmd == "prev":
		await state.play_prev()
	elif cmd == "stop":
		if state.current_track and state.current_track != getattr(state, "radio_announcement_path", ""):
			state.history.append(state.current_track)
		await state.stop_playback(reset_ui_state=True)
	elif cmd == "clear_queue":
		state.queue.clear()
		state.history.clear()
	elif cmd == "vol_up":
		await state.set_volume(state.volume + 5)
	elif cmd == "vol_down":
		await state.set_volume(state.volume - 5)
	elif cmd == "set_volume":
		if req.vollevel is not None:
			await state.set_volume(req.vollevel)
	elif cmd == "set_mute":
		if req.state is not None:
			state.server_muted = req.state
			if manager and manager.local_player_ws is not None:
				await state.mpv._send('{"command": ["set_property", "mute", true]}')
			else:
				cmd_payload = json.dumps({"command": ["set_property", "mute", state.server_muted]})
				await state.mpv._send(cmd_payload)
	elif cmd == "fullscreen":
		await state.mpv._send('{"command": ["cycle", "fullscreen"]}')
	elif cmd == "toggle_queue":
		if req.path:
			await state.toggle_queue(req.path)
	elif cmd == "add_url":
		if req.path:
			state.queue.append(req.path)
			state._pick_dj_next()
			if not state.current_track and not getattr(state, "is_synthesizing_radio", False):
				await state.play_next(skipped_by_user=True)
			asyncio.create_task(state.fetch_yt_dlp_metadata(req.path))
	elif cmd == "jump":
		if req.type and req.index is not None:
			await state.jump(req.type, req.index)
	elif cmd == "seek":
		if req.amount is not None:
			if manager and manager.local_player_ws is not None:
				await manager.local_player_ws.send_json(
					{
						"type": "local_player_seek",
						"mode": "relative",
						"amount": req.amount,
					}
				)
			else:
				cmd_payload = json.dumps({"command": ["seek", req.amount]})
				await state.mpv._send(cmd_payload)
	elif cmd == "seek_absolute":
		if req.amount is not None:
			if manager and manager.local_player_ws is not None:
				await manager.local_player_ws.send_json(
					{
						"type": "local_player_seek",
						"mode": "absolute",
						"amount": req.amount,
					}
				)
				await state.mpv._send(json.dumps({"command": ["seek", req.amount, "absolute"]}))
				state.time_pos = req.amount
			else:
				cmd_payload = json.dumps({"command": ["seek", req.amount, "absolute"]})
				await state.mpv._send(cmd_payload)
				state.time_pos = req.amount
	elif cmd == "toggle_favorite":
		if req.path:
			track_id = state.path_to_id.get(req.path, req.path)
			repo = FavoritesRepository()
			if track_id in state.favorites:
				state.favorites.remove(track_id)
				try:
					repo.remove(track_id)
				except Exception as e:
					logger.error(f"Error guardando favorito: {e}")
			else:
				state.favorites.append(track_id)
				try:
					repo.add(track_id)
				except Exception as e:
					logger.error(f"Error guardando favorito: {e}")
	elif cmd == "toggle_dj_carpincho":
		state.dj_carpincho_enabled = not state.dj_carpincho_enabled
		logger.info(f"DJ Carpincho cambiado a: {state.dj_carpincho_enabled}")
		if state.dj_carpincho_enabled and not state.current_track:
			await state.play_next(skipped_by_user=True)
		else:
			state._pick_dj_next()
	elif cmd == "toggle_dj_safe_mode":
		if req.state is not None:
			state.dj_safe_mode = req.state
			state._pick_dj_next()
	elif cmd == "toggle_radio_mode":
		if req.state is not None:
			state.radio_mode_enabled = req.state
		else:
			state.radio_mode_enabled = not state.radio_mode_enabled
		if state.radio_mode_enabled:
			state.radio_tracks_until_next = random.randint(1, 2)
			state.radio_track_counter = 0
	elif cmd == "set_weather_location":
		if req.location and isinstance(req.location, str):
			new_loc = req.location.strip()
			state.weather_location = new_loc
			cfg_path = _srv("get_config_path", get_config_path)()
			cfg = _srv("load_config", load_config)(cfg_path)
			cfg["weather_location"] = new_loc
			_srv("save_config", save_config)(cfg_path, cfg)
			try:
				from scripts.radio_announcer import reset_weather_cache
			except ImportError:
				try:
					from radio_announcer import reset_weather_cache
				except ImportError:

					def reset_weather_cache():
						pass

			reset_weather_cache()
			logger.info(f"Ubicación del clima actualizada a: {state.weather_location}")
	elif cmd == "pause_after":
		if req.path is not None:
			state.pause_after_path = req.path if state.pause_after_path != req.path else None
	elif cmd == "remove_queue_item":
		if req.index is not None and 0 <= req.index < len(state.queue):
			state.queue.pop(req.index)
			state._pick_dj_next()
	elif cmd == "move_queue_item":
		if (
			req.index is not None
			and req.new_index is not None
			and 0 <= req.index < len(state.queue)
			and 0 <= req.new_index < len(state.queue)
		):
			item = state.queue.pop(req.index)
			state.queue.insert(req.new_index, item)
			state._pick_dj_next()
	elif cmd == "remove_history_item":
		if req.index is not None and 0 <= req.index < len(state.history):
			state.history.pop(req.index)
	elif cmd == "move_history_item":
		if (
			req.index is not None
			and req.new_index is not None
			and 0 <= req.index < len(state.history)
			and 0 <= req.new_index < len(state.history)
		):
			item = state.history.pop(req.index)
			state.history.insert(req.new_index, item)
	elif cmd == "insert_queue_item":
		if req.path:
			idx = max(0, min(len(state.queue), req.index if req.index is not None else len(state.queue)))
			state.queue.insert(idx, req.path)
			state._pick_dj_next()
			if not state.current_track:
				await state.play_next(skipped_by_user=True)
			if req.path.startswith("http"):
				asyncio.create_task(state.fetch_yt_dlp_metadata(req.path))
	elif cmd == "move_current_to_queue":
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
				await state.mpv._send('{"command": ["stop"]}')
				state._pick_dj_next()
	elif cmd == "move_current_to_history":
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
	elif cmd == "move_queue_to_history":
		if req.index is not None and 0 <= req.index < len(state.queue):
			item = state.queue.pop(req.index)
			idx = max(
				0, min(len(state.history), req.history_index if req.history_index is not None else len(state.history))
			)
			state.history.insert(idx, item)
			state._pick_dj_next()
	elif cmd == "play_from_queue":
		if req.index is not None and 0 <= req.index < len(state.queue):
			item = state.queue.pop(req.index)
			if state.current_track:
				state.history.append(state.current_track)
				state.current_track = None
			state._pick_dj_next()
			await state.play_track(item)
	elif cmd == "move_in_playlist":
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
					# No track currently playing
					if from_idx < history_boundary <= to_idx:
						history_boundary -= 1
					elif to_idx < history_boundary <= from_idx:
						history_boundary += 1

					state.history = playlist[:history_boundary]
					state.queue = playlist[history_boundary:]
					state._pick_dj_next()

	bc = _srv("broadcast_state", getattr(state, "broadcast_state", None))
	if bc:
		await bc()

	return {"status": "ok"}


@router.post("/mpv/hide")
async def mpv_hide() -> dict[str, str]:
	"""Reinicia MPV con la ventana oculta si está activo."""
	state = get_state()
	if not state:
		return {"status": "error"}
	state.mpv_visible = False
	if state.mpv and state.mpv.is_running:
		logger.info("Reiniciando MPV para ocultar la ventana...")
		await state.mpv.start(is_restart=True, state_ref=state)
	bc = _srv("broadcast_state", getattr(state, "broadcast_state", None))
	if bc:
		await bc()
	return {"status": "ok"}


@router.post("/mpv/show")
async def mpv_show() -> dict[str, str]:
	"""Reinicia MPV con la ventana visible si está activo."""
	state = get_state()
	if not state:
		return {"status": "error"}
	state.mpv_visible = True
	if state.mpv and state.mpv.is_running:
		logger.info("Reiniciando MPV para mostrar la ventana...")
		await state.mpv.start(is_restart=True, state_ref=state)
	bc = _srv("broadcast_state", getattr(state, "broadcast_state", None))
	if bc:
		await bc()
	return {"status": "ok"}


handle_command = handle_command_endpoint
