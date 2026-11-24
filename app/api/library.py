"""
Enrutador de biblioteca musical: listado de canciones y disparo de escaneo.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter

from app.core.container import get_container
from app.domain.playback.orchestrator import broadcast_state
from app.infrastructure.storage import normalize_music_root

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["Library"])


@router.get("/library")
async def get_library() -> dict[str, Any]:
	"""Devuelve la biblioteca cacheada sin disparar un nuevo escaneo."""
	state = get_container().ensure_orchestrator()
	if not state:
		return {"status": "ok", "data": []}

	keys_to_exclude = {"fingerprint", "audio_hash", "bpm", "energy", "spectral_centroid"}
	clean_library = [
		{k: v for k, v in track.items() if k not in keys_to_exclude} for track in getattr(state, "tracks_cache", [])
	]
	return {"status": "ok", "data": clean_library, "default_sort": getattr(state, "default_sort", "time")}


@router.get("/scan")
async def scan_library(dir: str | None = None, dir2: str | None = None, silent: bool = False) -> dict[str, Any]:
	"""Dispara el proceso de escaneo de carpetas de música."""
	state = get_container().ensure_orchestrator()
	if not state:
		return {"status": "error", "data": []}

	while getattr(state, "is_scanning", False):
		await asyncio.sleep(0.5)

	raw_target = dir or getattr(state, "initial_dir", None)
	if not raw_target:
		from app.infrastructure.binaries.manager import is_android

		if is_android():
			return {
				"status": "unconfigured",
				"folder_status": "unconfigured",
				"data": [],
				"message": "Elegí una carpeta de música antes de escanear.",
			}
		raw_target = "~/Music"
	target1 = raw_target
	target2 = dir2 or getattr(state, "secondary_dir", None)

	target_dirs = [normalize_music_root(target1)] if target1 else []
	if target2:
		norm2 = normalize_music_root(target2)
		if norm2:
			target_dirs.append(norm2)

	logger.info(f"Iniciando escaneo {'silencioso ' if silent else ''}de directorios: {target_dirs}")
	stop_ticker = asyncio.Event()
	ticker_task: asyncio.Task[None] | None = None

	if not silent:
		state.is_scanning = True
		state.scan_phase = "discovering"
		state.scan_current = 0
		state.scan_total = 0
		state.scan_message = "Buscando archivos de audio..."

		await broadcast_state()

		async def _progress_ticker() -> None:
			while not stop_ticker.is_set():
				try:
					await asyncio.sleep(0.4)
					await broadcast_state()
				except asyncio.CancelledError:
					break
				except Exception:
					pass

		ticker_task = asyncio.create_task(_progress_ticker())

	try:
		if hasattr(state, "scan_directory"):
			if silent:
				state.tracks_cache = await asyncio.to_thread(state.scan_directory, target_dirs, False, silent=True)
			else:
				state.tracks_cache = await asyncio.to_thread(state.scan_directory, target_dirs, False)
	finally:
		if not silent:
			state.is_scanning = False
			state.scan_phase = "idle"
			state.scan_message = ""
		stop_ticker.set()
		if ticker_task is not None:
			ticker_task.cancel()
			try:
				await ticker_task
			except asyncio.CancelledError:
				pass

	await broadcast_state(include_library=True)
	if hasattr(state, "start_background_mood_analysis"):
		state.start_background_mood_analysis()

	return {"status": "ok", "data": getattr(state, "tracks_cache", [])}
