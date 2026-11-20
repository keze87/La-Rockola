"""
Enrutador de estado del sistema, capacidades y servicios meteorológicos.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
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


@router.post("/system/music-dir")
async def update_music_dir(req: MusicDirRequest) -> dict[str, Any]:
	"""Actualiza dinámicamente la carpeta de música (ej. MicroSD en Android) y dispara un reescaneo."""
	target_path = Path(req.dir).expanduser().resolve()
	if not target_path.is_dir():
		raise HTTPException(status_code=400, detail=f"La carpeta no existe o no es accesible: {req.dir}")

	resolved_dir = str(target_path)
	resolved_dir2: str | None = None
	if req.dir2:
		target_path2 = Path(req.dir2).expanduser().resolve()
		if not target_path2.is_dir():
			raise HTTPException(status_code=400, detail=f"La carpeta secundaria no existe: {req.dir2}")
		resolved_dir2 = str(target_path2)

	state = get_container().ensure_orchestrator()
	if state:
		state.initial_dir = resolved_dir
		state.secondary_dir = resolved_dir2

	config_mod.update_config({"music_dir": resolved_dir, "music_dir2": resolved_dir2})
	asyncio.create_task(scan_library(dir=resolved_dir, dir2=resolved_dir2))

	return {
		"status": "ok",
		"music_dir": resolved_dir,
		"music_dir2": resolved_dir2,
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
