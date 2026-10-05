"""
Fábrica de aplicación FastAPI, lifespan y configuración de montaje estático.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, TypeAdapter, ValidationError

from app.api.middleware import SubpathMiddleware
from app.api.schemas import (
	LocalPlayerClaim,
	LocalPlayerRelease,
	LocalPlayerUpdate,
)
from app.api.v1.library import scan_library
from app.api.v1.router import api_v1_router, legacy_router
from app.api.websocket import ConnectionManager
from app.core.config import get_carpincho_data_dir
from app.core.dependencies import (
	get_manager,
	get_state,
	set_db_path,
	set_global_manager,
)
from app.db.database import backup_db, get_default_db_path
from app.db.migrations import apply_migrations
from app.engine.state import broadcast_state

logger = logging.getLogger("RockolaCarpincho")

WSIncomingMessage = Annotated[
	LocalPlayerClaim | LocalPlayerRelease | LocalPlayerUpdate,
	Field(discriminator="type"),
]
ws_adapter = TypeAdapter(WSIncomingMessage)


def get_dist_dirs() -> tuple[Path, Path, Path]:
	"""Determina las rutas de frontend, dist y assets según si está empaquetado o en desarrollo."""
	if getattr(sys, "frozen", False):
		exe_dir = Path(sys.executable).parent
		if (exe_dir / "dist").is_dir():
			dist_dir = exe_dir / "dist"
			frontend_dir = exe_dir
		elif hasattr(sys, "_MEIPASS") and (Path(sys._MEIPASS) / "dist").is_dir():
			dist_dir = Path(sys._MEIPASS) / "dist"
			frontend_dir = Path(sys._MEIPASS)
		else:
			dist_dir = exe_dir / "dist"
			frontend_dir = exe_dir
	else:
		root_dir = Path(__file__).resolve().parents[1]
		frontend_dir = root_dir
		dist_dir = frontend_dir / "dist"

	assets_dir = dist_dir / "assets"
	return frontend_dir, dist_dir, assets_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Gestión del ciclo de vida de la aplicación: arranque y apagado seguro."""
	db_path = get_default_db_path()
	set_db_path(db_path)
	data_dir = get_carpincho_data_dir()

	try:
		apply_migrations(db_path)
		backup_db(db_path, data_dir)
	except Exception as e:
		logger.error(f"Error preparando base de datos en arranque: {e}")

	state = get_state()
	if state and hasattr(state, "mpv") and state.mpv and hasattr(state.mpv, "start"):
		try:
			logger.info("Iniciando motor de reproducción MPV...")
			res = state.mpv.start(state_ref=state)
			if asyncio.iscoroutine(res):
				await res
		except Exception as e:
			logger.warning(f"No se pudo arrancar MPV en el inicio: {e}")

	# Disparar escaneo de la biblioteca musical en segundo plano
	asyncio.create_task(scan_library())

	# Abrir navegador automáticamente si está configurado (y no estamos corriendo tests)
	async def _bg_open_browser(target_url: str, port: int, host: str):
		try:
			bind_ip = "127.0.0.1" if host in ("0.0.0.0", "") else host
			for _ in range(30):
				await asyncio.sleep(0.1)
				with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
					s.settimeout(0.2)
					if s.connect_ex((bind_ip, port)) == 0:
						break

			logger.info(f"🌐 Abriendo La Rockola en tu navegador: {target_url}")
			import app.cli.entrypoint as entrypoint_mod

			open_fn = getattr(entrypoint_mod, "open_browser_url", None)
			if open_fn:
				await asyncio.to_thread(open_fn, target_url)
		except Exception as e:
			logger.debug(f"Aviso al abrir el navegador automáticamente: {e}")

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
		if getattr(state, "mpris_bus", None):
			try:
				state.mpris_bus.disconnect()
			except Exception:
				pass
		if hasattr(state, "mpv") and state.mpv and hasattr(state.mpv, "stop"):
			res = state.mpv.stop()
			if asyncio.iscoroutine(res):
				await res
	set_db_path(None)


async def serve_index():
	_, dist_dir, _ = get_dist_dirs()
	html_path = dist_dir / "index.html"
	if not html_path.exists():
		return {"error": f"Falta el archivo {html_path}, se me cayó el mate encima"}
	return FileResponse(html_path)


async def serve_favicon(request: Request = None):
	frontend_dir, dist_dir, _ = get_dist_dirs()
	favicon_path = dist_dir / "favicon.png"
	if not favicon_path.exists():
		favicon_path = frontend_dir / "public" / "favicon.png"
	if not favicon_path.exists() and hasattr(sys, "_MEIPASS"):
		favicon_path = Path(sys._MEIPASS) / "public" / "favicon.png"

	if not favicon_path.exists():
		return {"error": f"No encuentro el favicon en {favicon_path}"}

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

	# Inicializar manager de websockets si no existe
	manager = get_manager()
	if manager is None:
		manager = ConnectionManager()
		set_global_manager(manager)

	app = FastAPI(
		title="La Rockola del Carpincho",
		description="Servidor de música y reproductor con alma de campo y sabor a mate.",
		version="0.0.1",
		lifespan=lifespan,
	)

	# Middlewares
	app.add_middleware(SubpathMiddleware)
	app.add_middleware(
		CORSMiddleware,
		allow_origins=["*"],
		allow_methods=["*"],
		allow_headers=["*"],
	)

	# Enrutadores API
	app.include_router(api_v1_router)
	app.include_router(legacy_router)

	# Montaje condicional de assets estáticos SOLO si existen en disco (sin compilar en import)
	if assets_dir.exists():
		app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
	else:
		logger.debug("La carpeta 'dist/assets' no existe aún. Modo API/Desarrollo.")

	app.add_api_route("/", serve_index, methods=["GET"])
	app.add_api_route("/favicon.ico", serve_favicon, methods=["GET"], include_in_schema=False)
	app.add_api_route("/favicon.png", serve_favicon, methods=["GET"], include_in_schema=False)

	app.add_api_websocket_route("/ws", websocket_endpoint)

	return app


async def websocket_endpoint(websocket: WebSocket):
	mgr = get_manager()
	state = get_state()
	client_host = getattr(websocket.client, "host", "desconocido") if websocket.client else "desconocido"
	if mgr:
		await mgr.connect(websocket)

	# Enviar estado completo inmediatamente
	if state and hasattr(state, "get_full_state_dict"):
		try:
			state_dict = state.get_full_state_dict(include_library=True)
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

			mgr = get_manager()
			state = get_state()
			if isinstance(msg, LocalPlayerClaim):
				ok = mgr.claim_local_player(websocket) if mgr else False
				await websocket.send_json({"type": "local_player_claim_result", "ok": ok})
				if ok and state and hasattr(state, "mpv") and state.mpv:
					logger.info(f"Cliente registrado como reproductor local ({client_host}).")
					await state.mpv._send('{"command": ["set_property", "mute", true]}')
			elif isinstance(msg, LocalPlayerRelease):
				if mgr and mgr.release_local_player(websocket) and state and hasattr(state, "mpv") and state.mpv:
					logger.info("Restaurando mute de MPV...")
					await state.mpv._send(
						json.dumps({"command": ["set_property", "mute", getattr(state, "server_muted", False)]})
					)
			elif isinstance(msg, LocalPlayerUpdate) and mgr and mgr.local_player_ws is websocket:
				changed = False
				if msg.time_pos is not None and state:
					new_pos = msg.time_pos or 0
					should_seek, new_drift = ConnectionManager.arbitrate_seek_drift(
						getattr(state, "time_pos", 0), new_pos, getattr(state, "last_seek_drift", None)
					)
					if should_seek and hasattr(state, "mpv") and state.mpv:
						await state.mpv._send(json.dumps({"command": ["seek", new_pos, "absolute"]}))
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
		curr_mgr = get_manager()
		curr_state = get_state()
		if curr_mgr and curr_mgr.disconnect(websocket) and curr_state and hasattr(curr_state, "mpv") and curr_state.mpv:
			try:
				await curr_state.mpv._send(
					json.dumps({"command": ["set_property", "mute", getattr(curr_state, "server_muted", False)]})
				)
			except Exception:
				pass


app = create_app()
