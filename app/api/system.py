"""
Enrutador de estado del sistema, capacidades y servicios meteorológicos.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.api.library import scan_library
from app.api.schemas import MusicDirRequest
from app.core import config as config_mod
from app.core.container import get_container
from app.domain.library.mood import is_mood_available
from app.domain.playback.orchestrator import broadcast_state
from app.infrastructure.binaries.ytdlp import YtDlpAdapter
from app.infrastructure.db.connection import execute_write
from app.infrastructure.storage import get_storage_backend, normalize_music_root
from app.infrastructure.weather.client import (
	build_weather_phrase,
	extract_location_from_weather_data,
	fetch_weather_json,
)

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["System"])


@router.api_route("/weather/preview", methods=["GET", "HEAD"])
async def preview_weather(location: str = Query(..., description="Ciudad o localidad a consultar")) -> JSONResponse:
	"""Consulta wttr.in para obtener el clima actual y la frase armada de DJ Bara."""
	loc_clean = location.strip() if location else ""
	if not loc_clean:
		return JSONResponse(status_code=400, content={"ok": False, "error": "Ubicación vacía"})

	data = await asyncio.to_thread(fetch_weather_json, lugar=loc_clean, idioma="es", timeout=5.0)
	if not data:
		return JSONResponse(
			status_code=502,
			content={"ok": False, "error": f"No se pudo consultar el clima para '{loc_clean}'"},
		)

	area_name = extract_location_from_weather_data(data) or loc_clean
	curr = data.get("current_condition", [{}])[0]
	temp_c = None
	try:
		temp_c = round(float(curr.get("temp_C", 0)))
	except (ValueError, TypeError):
		pass

	phrase = build_weather_phrase(data, template_idx=0, location=loc_clean)
	return JSONResponse(
		content={
			"ok": True,
			"location": loc_clean,
			"area_name": area_name,
			"temp_c": temp_c,
			"phrase": phrase or "",
		}
	)


@router.get("/system/capabilities")
async def get_system_capabilities() -> dict[str, Any]:
	"""Reporta la disponibilidad de binarios y servicios externos para el frontend."""
	state = get_container().ensure_orchestrator()
	ytdlp_srv = YtDlpAdapter()
	return {
		"has_ffmpeg": is_mood_available(),
		"has_ytdlp": ytdlp_srv.is_available,
		"has_edge_tts": bool(state.has_edge_tts if state else False),
		"has_mpv": bool(getattr(state, "has_mpv", True) if state else False),
	}


@router.get("/system/info")
async def get_system_info() -> dict[str, Any]:
	"""Devuelve configuración de carpetas, estado de permisos SAF y datos de red del servidor."""
	state = get_container().ensure_orchestrator()
	settings = get_container().settings
	initial_dir = (getattr(state, "initial_dir", None) if state else None) or getattr(settings, "music_dir", "") or ""
	secondary_dir = (getattr(state, "secondary_dir", None) if state else None) or getattr(settings, "music_dir2", None)
	configured = bool(
		getattr(state, "music_dir_configured", getattr(settings, "music_dir_configured", False))
		if state
		else getattr(settings, "music_dir_configured", False)
	)
	if state and hasattr(state, "refresh_folder_status"):
		validation = await asyncio.to_thread(state.refresh_folder_status)
	else:
		validation = await asyncio.to_thread(get_storage_backend(initial_dir).validate_root, initial_dir)
	audio_ready = True
	audio_error: str | None = None
	mpv_ctrl = getattr(state, "mpv", None) if state else None
	if mpv_ctrl is not None and hasattr(mpv_ctrl, "_ensure_native"):
		native = await asyncio.to_thread(mpv_ctrl._ensure_native)
		audio_ready = native is not None
		if not audio_ready:
			audio_error = getattr(mpv_ctrl, "native_error", None) or "Reproductor nativo Android no disponible."
	return {
		"music_dir": initial_dir,
		"music_dir2": secondary_dir,
		"music_dir_configured": configured,
		"folder_status": validation.status,
		"folder_display_name": validation.display_name,
		"folder_error": validation.error,
		"audio_ready": audio_ready,
		"audio_error": audio_error,
		"port": getattr(state, "server_port", getattr(settings, "port", 1729))
		if state
		else getattr(settings, "port", 1729),
		"local_ip": getattr(state, "local_ip", "127.0.0.1") if state else "127.0.0.1",
		"server_url": getattr(state, "server_url", "http://127.0.0.1:1729") if state else "http://127.0.0.1:1729",
	}


@router.post("/system/music-dir")
async def update_music_dir(req: MusicDirRequest) -> dict[str, Any]:
	"""Actualiza dinámicamente la carpeta de música (SAF o POSIX) y dispara un reescaneo."""
	raw_dir = normalize_music_root(req.dir)
	validation = await asyncio.to_thread(get_storage_backend(raw_dir).validate_root, raw_dir)
	if validation.status != "ok":
		raise HTTPException(
			status_code=400,
			detail=validation.error or f"La carpeta no existe o no es accesible: {req.dir}",
		)

	resolved_dir = validation.path or raw_dir
	resolved_dir2: str | None = None
	if req.dir2:
		raw_dir2 = normalize_music_root(req.dir2)
		val2 = await asyncio.to_thread(get_storage_backend(raw_dir2).validate_root, raw_dir2)
		if val2.status != "ok":
			raise HTTPException(
				status_code=400,
				detail=val2.error or f"La carpeta secundaria no existe: {req.dir2}",
			)
		resolved_dir2 = val2.path or raw_dir2

	state = get_container().ensure_orchestrator()
	if state:
		state.initial_dir = resolved_dir
		state.secondary_dir = resolved_dir2
		state.music_dir_configured = True
		state.folder_status = validation.status
		state.folder_display_name = validation.display_name
		state.folder_error = None
		state._folder_status_cache = None

	config_mod.update_config(
		{
			"music_dir": resolved_dir,
			"music_dir2": resolved_dir2,
			"music_dir_configured": True,
		}
	)
	asyncio.create_task(scan_library(dir=resolved_dir, dir2=resolved_dir2))

	return {
		"status": "ok",
		"music_dir": resolved_dir,
		"music_dir2": resolved_dir2,
		"music_dir_configured": True,
		"folder_status": validation.status,
		"folder_display_name": validation.display_name,
	}


@router.get("/health")
async def health_check() -> dict[str, str]:
	"""Endpoint liviano para verificar que el servidor HTTP esté vivo."""
	return {"status": "ok"}


@router.post("/test/reset")
async def reset_test_state() -> dict[str, bool]:
	"""Reinicia el estado mutable en tests E2E; solo disponible si ROCKOLA_ENABLE_TEST_ROUTES=1."""
	if os.environ.get("ROCKOLA_ENABLE_TEST_ROUTES") != "1":
		raise HTTPException(status_code=404, detail="Not found")

	container = get_container()
	db_path = container.db_path
	for table in ("favorites", "play_history", "url_logs"):
		execute_write(f"DELETE FROM {table}", db_path=db_path)

	state = container.ensure_orchestrator()
	if state:
		if hasattr(state, "queue_manager"):
			state.queue_manager.clear()
		else:
			state.queue = []
		if hasattr(state, "favorites"):
			state.favorites = []
		if hasattr(state, "history"):
			state.history = []
		if hasattr(state, "local_player_id"):
			state.local_player_id = None
		await broadcast_state()

	return {"reset": True}
