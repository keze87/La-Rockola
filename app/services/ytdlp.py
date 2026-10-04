"""
Servicio para manejo de yt-dlp: metadatos de URLs remotas y actualización del binario.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.engine import audio_analysis
from app.engine.audio_analysis import get_clean_env

logger = logging.getLogger("RockolaCarpincho")


class YtDlpService:
	"""Maneja la interacción con yt-dlp para streaming y metadatos remotos."""

	def __init__(self) -> None:
		pass

	@property
	def is_available(self) -> bool:
		"""Indica si el binario de yt-dlp se encuentra disponible en el sistema."""
		return audio_analysis.find_binary("yt-dlp") is not None

	async def fetch_metadata(self, url: str) -> dict[str, Any] | None:
		"""Extrae y formatea metadatos de YouTube u otras plataformas para La Rockola."""
		bin_path = audio_analysis.find_binary("yt-dlp")
		if not bin_path:
			try:
				try:
					from scripts import ytdlp_installer
				except ImportError:
					import ytdlp_installer

				logger.info("yt-dlp no encontrado para procesar link de YouTube. Intentando instalar...")
				installed = await asyncio.to_thread(ytdlp_installer.ensure_ytdlp)
				if installed:
					bin_path = installed
			except Exception as e:
				logger.error(f"No se pudo instalar yt-dlp en tiempo de ejecución: {e}")

		if not bin_path:
			bin_path = "yt-dlp"

		try:
			logger.info(f"Che yt-dlp, averiguate la data de este link: {url}")
			proc = await asyncio.create_subprocess_exec(
				bin_path,
				"--dump-json",
				"--no-warnings",
				"--no-playlist",
				url,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.DEVNULL,
				env=get_clean_env(),
			)
			stdout, _ = await proc.communicate()

			if stdout:
				data = json.loads(stdout.decode("utf-8"))
				title = data.get("title", "Título Misterioso")
				artist = data.get("uploader", "Artista NN")
				duration = data.get("duration", 0)

				mins = int(duration // 60) if duration else 0
				secs = int(duration % 60) if duration else 0

				return {
					"path": url,
					"display_title": title,
					"display_artist": artist,
					"album": "Internet",
					"duration_str": f"{mins}:{secs:02d}",
					"search_string": f"{artist} {title}".lower(),
					"title": title,
					"artist": artist,
				}
		except Exception as e:
			logger.error(f"Pifió yt-dlp sacando la info de {url}, se empacó: {e}")

		return None
