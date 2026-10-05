"""
Enrutador de biblioteca musical: listado de canciones y disparo de escaneo.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.core.dependencies import get_state
from app.engine.state import broadcast_state

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["Library"])


@router.get("/library")
async def get_library() -> dict[str, Any]:
	"""Devuelve la biblioteca cacheada sin disparar un nuevo escaneo."""
	state = get_state()
	if not state:
		return {"status": "ok", "data": []}

	while getattr(state, "is_scanning", False):
		await asyncio.sleep(0.5)

	keys_to_exclude = {"fingerprint", "bpm", "energy", "spectral_centroid"}
	clean_library = [
		{k: v for k, v in track.items() if k not in keys_to_exclude} for track in getattr(state, "tracks_cache", [])
	]
	return {"status": "ok", "data": clean_library}


@router.get("/scan")
async def scan_library(dir: str | None = None, dir2: str | None = None) -> dict[str, Any]:
	"""Dispara el proceso de escaneo de carpetas de música."""
	state = get_state()
	if not state:
		return {"status": "error", "data": []}

	while getattr(state, "is_scanning", False):
		logger.info("Escaneo ya en curso, esperando...")
		await asyncio.sleep(0.5)

	target1 = dir or getattr(state, "initial_dir", None) or "~/Music"
	target2 = dir2 or getattr(state, "secondary_dir", None)

	target_dirs = [str(Path(target1).expanduser().resolve())]
	if target2:
		target_dirs.append(str(Path(target2).expanduser().resolve()))

	logger.info(f"Iniciando escaneo de directorios: {target_dirs}")
	state.is_scanning = True
	state.scan_phase = "discovering"
	state.scan_current = 0
	state.scan_total = 0
	state.scan_message = "Buscando archivos de audio..."

	await broadcast_state()

	stop_ticker = asyncio.Event()

	async def _progress_ticker():
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
			state.tracks_cache = await asyncio.to_thread(state.scan_directory, target_dirs, False)
	finally:
		state.is_scanning = False
		state.scan_phase = "idle"
		state.scan_message = ""
		stop_ticker.set()
		ticker_task.cancel()
		try:
			await ticker_task
		except asyncio.CancelledError:
			pass

	await broadcast_state(include_library=True)
	if state and hasattr(state, "start_background_mood_analysis"):
		state.start_background_mood_analysis()

	return {"status": "ok", "data": getattr(state, "tracks_cache", [])}
