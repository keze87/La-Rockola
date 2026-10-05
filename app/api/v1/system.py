"""
Enrutador de estado del sistema, capacidades y servicios meteorológicos.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.dependencies import get_state
from app.engine.audio_analysis import is_mood_available
from app.services.ytdlp import YtDlpService

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["System"])


@router.api_route("/weather/preview", methods=["GET", "HEAD"])
async def preview_weather(location: str = Query(..., description="Ciudad o localidad a consultar")) -> JSONResponse:
	"""Consulta wttr.in para obtener el clima actual y la frase armada de DJ Carpincho."""
	try:
		from scripts.radio_announcer import (
			build_weather_phrase,
			extract_location_from_weather_data,
			fetch_weather_json,
		)
	except ImportError:
		try:
			from radio_announcer import (
				build_weather_phrase,
				extract_location_from_weather_data,
				fetch_weather_json,
			)
		except ImportError:
			return JSONResponse(status_code=500, content={"ok": False, "error": "Módulo de radio no disponible"})

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
	state = get_state()
	ytdlp_srv = YtDlpService()
	return {
		"has_ffmpeg": is_mood_available(),
		"has_ytdlp": ytdlp_srv.is_available,
		"has_edge_tts": getattr(state, "has_edge_tts", False) if state else False,
	}
