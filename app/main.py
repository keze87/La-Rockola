"""
Fábrica de aplicación FastAPI, lifespan y configuración de montaje estático.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, TypeAdapter, ValidationError

from app import __version__
from app.api.library import scan_library
from app.api.middleware import SubpathMiddleware
from app.api.router import api_v1_router, root_api_router
from app.api.schemas import (
	LocalPlayerClaim,
	LocalPlayerRelease,
	LocalPlayerReset,
	LocalPlayerUpdate,
)
from app.api.websocket import ConnectionManager
from app.core.config import get_carpincho_data_dir, get_dist_dirs
from app.core.container import get_container
from app.domain.playback.orchestrator import broadcast_state
from app.infrastructure.binaries import ytdlp as ytdlp_installer
from app.infrastructure.binaries.manager import find_binary
from app.infrastructure.db.connection import backup_db, get_default_db_path
from app.infrastructure.db.migrations import apply_migrations

logger = logging.getLogger("RockolaCarpincho")

WSIncomingMessage = Annotated[
	LocalPlayerClaim | LocalPlayerRelease | LocalPlayerReset | LocalPlayerUpdate,
	Field(discriminator="type"),
]
ws_adapter = TypeAdapter(WSIncomingMessage)


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Gestión del ciclo de vida de la aplicación: arranque y apagado seguro."""
	container = get_container()
	db_path = container.db_path or get_default_db_path()
	container.db_path = Path(db_path)
	data_dir = get_carpincho_data_dir()

	try:
		apply_migrations(db_path)
		backup_db(db_path, data_dir)
	except Exception as e:
		logger.error(f"Error preparando base de datos en arranque: {e}")

	state = container.ensure_orchestrator()
	if state and hasattr(state, "mpv") and state.mpv and hasattr(state.mpv, "start"):
		try:
			res = state.mpv.start(state_ref=state)
			if asyncio.iscoroutine(res):
				await res
		except Exception as e:
			logger.warning(f"No se pudo arrancar MPV en el inicio: {e}")

	asyncio.create_task(scan_library())

	async def _bg_update_ytdlp() -> None:
		try:
			await asyncio.to_thread(ytdlp_installer.update_ytdlp)
		except Exception as e:
			logger.warning(f"Error actualizando yt-dlp en segundo plano: {e}")

	if find_binary("yt-dlp"):
		asyncio.create_task(_bg_update_ytdlp())

	async def _bg_open_browser(target_url: str, port: int, host: str) -> None:
		try:
			bind_ip = "127.0.0.1" if host in ("0.0.0.0", "") else host
			for _ in range(30):
				await asyncio.sleep(0.1)
				with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
					s.settimeout(0.2)
					if s.connect_ex((bind_ip, port)) == 0:
						break
			import app.cli.entrypoint as entrypoint_mod

			await asyncio.to_thread(entrypoint_mod.open_browser_url, target_url)
		except Exception:
			pass

	if state and state.open_browser and "PYTEST_CURRENT_TEST" not in os.environ:
		asyncio.create_task(
			_bg_open_browser(
				getattr(state, "server_url", "http://localhost:1729"),
				getattr(state, "server_port", 1729),
				getattr(state, "server_host", "0.0.0.0"),
			)
		)

	yield

	logger.info("Cerrando La Rockola del Carpincho. ¡Nos vemos en los fogones!")
	if state:
		if hasattr(state, "mpris_service") and state.mpris_service:
			state.mpris_service.disconnect()
		if hasattr(state, "mpv") and state.mpv:
			if (
				hasattr(state.mpv, "socket_path")
				and state.mpv.socket_path
				and not getattr(state.mpv, "is_windows", False)
			):
				try:
					if os.path.exists(state.mpv.socket_path):
						os.remove(state.mpv.socket_path)
				except OSError:
					pass
			if hasattr(state.mpv, "stop"):
				res = state.mpv.stop()
				if asyncio.iscoroutine(res):
					await res


async def serve_index():
	headers = {
		"Cache-Control": "no-cache, no-store, must-revalidate",
		"Pragma": "no-cache",
		"Expires": "0",
	}
	_, dist_dir, _ = get_dist_dirs()
	html_path = dist_dir / "index.html"
	if not html_path.exists():
		return JSONResponse(
			content={"error": f"Falta el archivo {html_path}, se me cayó el mate encima"},
			headers=headers,
		)
	return FileResponse(html_path, headers=headers)


async def serve_radio_jpg(request: Request = None):  # type: ignore[assignment]
	from app.infrastructure.media.mixer import get_static_asset_path

	radio_path = get_static_asset_path("radio.jpg")
	if not radio_path or not radio_path.exists():
		return Response(status_code=404)

	stat = radio_path.stat()
	etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
	cache_headers = {
		"ETag": etag,
		"Cache-Control": "public, max-age=86400, stale-while-revalidate=3600",
	}

	if request:
		if_none_match = request.headers.get("if-none-match")
		if if_none_match and etag in if_none_match:
			return Response(status_code=304, headers=cache_headers)

	return FileResponse(radio_path, media_type="image/jpeg", headers=cache_headers)


async def serve_favicon(request: Request = None):  # type: ignore[assignment]
	from app.infrastructure.media.mixer import get_static_asset_path

	favicon_path = get_static_asset_path("favicon.png")
	if not favicon_path or not favicon_path.exists():
		return Response(status_code=404)

	stat = favicon_path.stat()
	etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
	cache_headers = {
		"ETag": etag,
		"Cache-Control": "public, max-age=31536000, immutable",
	}

	if request:
		if_none_match = request.headers.get("if-none-match")
		if if_none_match and etag in if_none_match:
			return Response(status_code=304, headers=cache_headers)

	return FileResponse(favicon_path, media_type="image/png", headers=cache_headers)


def create_app() -> FastAPI:
	"""Crea y configura la instancia de FastAPI con sus middlewares y enrutadores."""
	_, _, assets_dir = get_dist_dirs()

	container = get_container()
	container.ensure_ws_manager()

	app = FastAPI(
		title="La Rockola del Carpincho",
		description="Servidor de música y reproductor con alma de campo y sabor a mate.",
		version=__version__,
		lifespan=lifespan,
	)

	app.add_middleware(SubpathMiddleware)
	app.add_middleware(
		CORSMiddleware,
		allow_origins=["*"],
		allow_methods=["*"],
		allow_headers=["*"],
	)

	app.include_router(api_v1_router)
	app.include_router(root_api_router)

	if assets_dir.exists():
		app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

	app.add_api_route("/", serve_index, methods=["GET"])
	# Rutas del frontend SPA para permitir navegación directa y recarga sin 404
	for spa_route in (
		"/vibra",
		"/fogon",
		"/queue",
		"/ronda",
		"/top",
		"/clasicos",
		"/controls",
		"/perillas",
		"/temazos",
	):
		app.add_api_route(spa_route, serve_index, methods=["GET"], include_in_schema=False)
	app.add_api_route("/favicon.ico", serve_favicon, methods=["GET"], include_in_schema=False)
	app.add_api_route("/favicon.png", serve_favicon, methods=["GET"], include_in_schema=False)
	app.add_api_route("/radio.jpg", serve_radio_jpg, methods=["GET"], include_in_schema=False)
	app.add_api_websocket_route("/ws", websocket_endpoint)

	return app


async def websocket_endpoint(websocket: WebSocket) -> None:
	container = get_container()
	mgr = container.ensure_ws_manager()
	state = container.ensure_orchestrator()
	client_host = getattr(websocket.client, "host", "desconocido") if websocket.client else "desconocido"
	if mgr:
		await mgr.connect(websocket)

	if state and hasattr(state, "get_full_state_dict"):
		try:
			state_dict = state.get_full_state_dict(include_library=False)
			state_dict["type"] = "state_update"
			await websocket.send_json(state_dict)
		except Exception as e:
			logger.debug(f"Error mandando estado inicial por WS: {e}")

	try:
		while True:
			raw = await websocket.receive_text()
			try:
				msg = ws_adapter.validate_json(raw)
			except ValidationError:
				continue

			container = get_container()
			mgr = container.ensure_ws_manager()
			state = container.ensure_orchestrator()
			if isinstance(msg, LocalPlayerClaim):
				if mgr:
					ok, old_ws = mgr.claim_local_player(websocket)
					if old_ws and old_ws is not websocket:
						try:
							await old_ws.send_json({"type": "local_player_evicted", "reason": "replaced"})
						except Exception:
							pass
				else:
					ok = False
				await websocket.send_json({"type": "local_player_claim_result", "ok": ok})
				if ok and state and hasattr(state, "mpv") and state.mpv:
					await state.mpv.set_mute(True)
				await broadcast_state()
			elif isinstance(msg, LocalPlayerRelease):
				if mgr and mgr.release_local_player(websocket) and state and hasattr(state, "mpv") and state.mpv:
					await state.mpv.set_mute(getattr(state, "server_muted", False))
					await broadcast_state()
			elif isinstance(msg, LocalPlayerReset):
				if mgr:
					old_ws = mgr.reset_local_player()
					if old_ws:
						try:
							await old_ws.send_json({"type": "local_player_evicted", "reason": "server_requested"})
						except Exception:
							pass
				if state and hasattr(state, "mpv") and state.mpv:
					await state.mpv.set_mute(getattr(state, "server_muted", False))
				await broadcast_state()
			elif isinstance(msg, LocalPlayerUpdate) and mgr and mgr.local_player_ws is websocket:
				changed = False
				if msg.time_pos is not None and state:
					new_pos = msg.time_pos or 0
					should_seek, new_drift = ConnectionManager.arbitrate_seek_drift(
						getattr(state, "time_pos", 0), new_pos, getattr(state, "last_seek_drift", None)
					)
					if should_seek and hasattr(state, "mpv") and state.mpv:
						await state.mpv.seek_absolute(new_pos)
					state.last_seek_drift = new_drift
					state.time_pos = new_pos
					now = time.time()
					if now - getattr(state, "last_time_broadcast", 0) >= 5.0:
						state.last_time_broadcast = now
						changed = True

				if msg.duration is not None and state and msg.duration != getattr(state, "duration", 0):
					state.duration = msg.duration or 0
					changed = True

				if msg.paused is not None and state and msg.paused != getattr(state, "mpv_paused", False):
					state.mpv_paused = msg.paused
					changed = True

				if msg.song_ended and state and hasattr(state, "play_next"):
					is_radio = getattr(state, "is_playing_radio_announcement", False) or (
						state.is_radio_announcement(state.current_track)
						if hasattr(state, "is_radio_announcement")
						else False
					)
					if state.current_track and not is_radio and hasattr(state, "_register_play_stat"):
						state._register_play_stat(state.current_track)
					await state.play_next(skipped_by_user=False)
					await broadcast_state()
					continue

				if changed and state:
					await broadcast_state()
	except WebSocketDisconnect:
		logger.info(f"Cliente desconectado: {client_host}")
	finally:
		curr_container = get_container()
		curr_mgr = curr_container.ensure_ws_manager()
		curr_state = curr_container.ensure_orchestrator()
		if curr_mgr and curr_mgr.disconnect(websocket) and curr_state and hasattr(curr_state, "mpv") and curr_state.mpv:
			try:
				await curr_state.mpv.set_mute(getattr(curr_state, "server_muted", False))
			except Exception:
				pass
			try:
				await broadcast_state()
			except Exception:
				pass


app = create_app()
