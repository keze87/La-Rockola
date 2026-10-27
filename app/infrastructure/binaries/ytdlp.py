"""
Instalador y actualizador portátil de yt-dlp para La Rockola del Carpincho.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from app.core.logging import get_logger
from app.infrastructure.binaries import manager

logger = get_logger(__name__)

YTDLP_BASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download"
USER_AGENT = "LaRockola-YTDLP-Installer/1.0"


def default_logger(msg: str) -> None:
	print(f"[yt-dlp-installer] {msg}")


def get_ytdlp_asset_name(platform_name: str | None = None, arch: str | None = None) -> str:
	"""Determina el nombre del ejecutable de yt-dlp en GitHub Releases."""
	plat, target_arch = manager.resolve_platform_and_arch(platform_name, arch)
	if plat == "windows":
		if target_arch == "arm64":
			return "yt-dlp_arm64.exe"
		if target_arch == "i686":
			return "yt-dlp_x86.exe"
		return "yt-dlp.exe"
	if plat == "macos":
		return "yt-dlp_macos"
	return "yt-dlp"


def get_ytdlp_download_url(platform_name: str | None = None, arch: str | None = None) -> str:
	"""Obtiene la URL directa de descarga del último ejecutable de yt-dlp."""
	return f"{YTDLP_BASE_URL}/{get_ytdlp_asset_name(platform_name, arch)}"


def get_default_install_dir() -> Path:
	"""Determina el directorio donde ubicar yt-dlp."""
	return manager.get_default_install_dir("ytdlp")


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""Verifica si un binario de yt-dlp fue gestionado por La Rockola."""
	return manager.is_rockola_managed(bin_path, "ytdlp")


def download_file(url: str, dest_path: Path, log_fn: Callable[[str], None] = default_logger) -> None:
	"""Descarga un archivo con reporte de progreso."""
	manager.download_file(url, dest_path, log_fn=log_fn, user_agent=USER_AGENT)


def install_ytdlp(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	force: bool = False,
	log_fn: Callable[[str], None] = default_logger,
) -> Path | None:
	"""Descarga e instala yt-dlp desde GitHub Releases."""
	plat, target_arch = manager.resolve_platform_and_arch(platform_name, arch)
	url = get_ytdlp_download_url(plat, target_arch)

	dest_dir = Path(target_dir) if target_dir else get_default_install_dir()
	dest_dir.mkdir(parents=True, exist_ok=True)

	binary_name = "yt-dlp.exe" if (plat == "windows" or os.name == "nt") else "yt-dlp"
	final_path = dest_dir / binary_name

	if not force and final_path.is_file() and final_path.stat().st_size > 0:
		log_fn(f"yt-dlp ya está disponible en {final_path}. Usá force=True para reinstalar.")
		return final_path

	try:
		log_fn(f"Descargando yt-dlp desde {url}...")
		with tempfile.TemporaryDirectory() as tmp_dir:
			tmp_download = Path(tmp_dir) / "downloaded_binary"
			download_file(url, tmp_download, log_fn=log_fn)

			if not tmp_download.is_file() or tmp_download.stat().st_size == 0:
				log_fn("Error: El archivo descargado está vacío.")
				return None

			shutil.move(str(tmp_download), str(final_path))
			manager.mark_rockola_managed(dest_dir, "ytdlp", log_fn=log_fn)

			if sys.platform != "win32":
				try:
					final_path.chmod(final_path.stat().st_mode | 0o755)
				except OSError as exc:
					log_fn(f"Aviso: no se pudieron otorgar permisos de ejecución a {final_path}: {exc}")

		log_fn(f"¡yt-dlp instalado correctamente en {final_path}!")
		return final_path
	except Exception as e:
		log_fn(f"Error al descargar yt-dlp: {e}")
		return None


def ensure_ytdlp(log_fn: Callable[[str], None] = default_logger) -> str | None:
	"""Garantiza que yt-dlp esté disponible, instalándolo si falta."""
	existing = manager.find_binary("yt-dlp")
	if existing:
		return existing
	installed = install_ytdlp(force=False, log_fn=log_fn)
	return str(installed) if installed else None


def update_ytdlp(bin_path: str | None = None, log_fn: Callable[[str], None] = default_logger) -> bool:
	"""Actualiza yt-dlp en caliente usando -U solo si es gestionado por La Rockola."""
	resolved_bin = bin_path or manager.find_binary("yt-dlp")
	if not resolved_bin or not Path(resolved_bin).is_file():
		log_fn("No se encontró yt-dlp para actualizar.")
		return False

	if not is_rockola_managed(resolved_bin):
		log_fn(f"yt-dlp ({resolved_bin}) es una instalación externa del sistema; se omite la auto-actualización.")
		return False

	log_fn(f"Buscando actualizaciones para yt-dlp ({resolved_bin})...")
	try:
		res = subprocess.run(
			[resolved_bin, "-U"],
			capture_output=True,
			text=True,
			timeout=60,
			check=False,
			env=manager.get_clean_env(),
		)
		stdout = res.stdout.strip()
		if stdout:
			log_fn(stdout)
		if res.returncode == 0:
			log_fn("yt-dlp está al día.")
			return True
		stderr = res.stderr.strip()
		if stderr:
			log_fn(f"Aviso de actualización: {stderr}")
		return False
	except Exception as e:
		log_fn(f"No se pudo actualizar yt-dlp: {e}")
		return False


class YtDlpAdapter:
	"""Adaptador de infraestructura para extraer metadatos remotos mediante yt-dlp."""

	def __init__(self) -> None:
		# Caché en memoria para no recalcular yt-dlp -g en cada seek o rango HTTP (URL, timestamp)
		self._stream_url_cache: dict[str, tuple[str, float]] = {}

	@property
	def is_available(self) -> bool:
		return manager.find_binary("yt-dlp") is not None

	async def get_stream_url(self, url: str) -> str | None:
		"""Extrae la URL directa del flujo de audio mediante yt-dlp -g -f ba/b con caché en memoria."""
		import asyncio

		now = time.time()
		if url in self._stream_url_cache:
			cached_url, ts = self._stream_url_cache[url]
			if now - ts < 7200:
				return cached_url

		bin_path = manager.find_binary("yt-dlp")
		if not bin_path:
			try:
				logger.info("yt-dlp no encontrado para extraer stream directo. Intentando instalar...")
				installed = await asyncio.to_thread(ensure_ytdlp)
				if installed:
					bin_path = installed
			except Exception as e:
				logger.error(f"No se pudo instalar yt-dlp al vuelo: {e}")

		if not bin_path:
			bin_path = "yt-dlp"

		try:
			logger.info(f"Pidiéndole a yt-dlp el enlace directo para la radio/cliente: {url}")
			proc = await asyncio.create_subprocess_exec(
				bin_path,
				"-g",
				"-f",
				"ba/b",
				"--no-warnings",
				"--no-playlist",
				url,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.DEVNULL,
				env=manager.get_clean_env(),
			)
			stdout, _ = await proc.communicate()
			if proc.returncode == 0 and stdout:
				lines = stdout.decode("utf-8", errors="ignore").strip().splitlines()
				for line in lines:
					clean_line = line.strip()
					if clean_line.startswith(("http://", "https://")):
						self._stream_url_cache[url] = (clean_line, now)
						return clean_line
		except Exception as e:
			logger.error(f"Se empacó yt-dlp sacando el stream directo de {url}: {e}")
		return None

	async def fetch_metadata(self, url: str) -> dict[str, object] | None:
		"""Extrae y formatea metadatos de YouTube u otras plataformas para La Rockola."""
		import asyncio
		import json

		bin_path = manager.find_binary("yt-dlp")
		if not bin_path:
			try:
				logger.info("yt-dlp no encontrado para procesar link de YouTube. Intentando instalar...")
				installed = await asyncio.to_thread(ensure_ytdlp)
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
				env=manager.get_clean_env(),
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


YtDlpService = YtDlpAdapter

if __name__ == "__main__":
	if "--update" in sys.argv:
		update_ytdlp()
	else:
		install_ytdlp(force="--force" in sys.argv)
