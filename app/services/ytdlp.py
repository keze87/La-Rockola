"""
Servicio para manejo de yt-dlp: metadatos de URLs remotas y actualización del binario.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.engine.audio_analysis import find_binary, get_clean_env

logger = logging.getLogger("RockolaCarpincho")


class YtDlpService:
	"""Maneja la interacción con yt-dlp para streaming y metadatos remotos."""

	def __init__(self) -> None:
		pass

	@property
	def is_available(self) -> bool:
		"""Indica si el binario de yt-dlp se encuentra disponible en el sistema."""
		return find_binary("yt-dlp") is not None

	async def get_metadata(self, url: str) -> dict[str, Any] | None:
		"""Extrae metadatos de una URL remota de forma asíncrona usando yt-dlp."""
		bin_path = find_binary("yt-dlp")
		if not bin_path:
			logger.warning("yt-dlp no está disponible para extraer metadatos.")
			return None

		cmd = [
			bin_path,
			"--dump-single-json",
			"--no-warnings",
			"--no-playlist",
			url,
		]

		try:
			proc = await asyncio.create_subprocess_exec(
				*cmd,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
				env=get_clean_env(),
			)
			stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
			if proc.returncode == 0 and stdout:
				return json.loads(stdout.decode("utf-8"))
		except Exception as e:
			logger.error(f"Error extrayendo metadatos de {url} con yt-dlp: {e}")

		return None
