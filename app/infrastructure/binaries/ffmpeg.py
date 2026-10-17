"""
Instalador automático de FFmpeg y FFprobe para plataformas portables.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.infrastructure.binaries import manager

GITHUB_API_LATEST = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
GITHUB_HTML_LATEST = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest"
USER_AGENT = "LaRockola-FFmpeg-Installer/1.0"


def default_logger(msg: str) -> None:
	print(f"[ffmpeg-installer] {msg}")


def _build_fallback_assets(tag: str) -> list[dict]:
	"""Construye la lista de paquetes oficiales de fallback para FFmpeg."""
	return [
		{
			"name": "ffmpeg-master-latest-win64-gpl.zip",
			"url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
			"size": 0,
		},
		{
			"name": "ffmpeg-master-latest-winarm64-gpl.zip",
			"url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-winarm64-gpl.zip",
			"size": 0,
		},
		{
			"name": "ffmpeg-master-latest-win32-gpl.zip",
			"url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip",
			"size": 0,
		},
		{
			"name": "ffmpeg-master-latest-linux64-gpl.tar.xz",
			"url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
			"size": 0,
		},
		{
			"name": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
			"url": "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
			"size": 0,
		},
	]


def fetch_release_info(timeout: int = 10, log_fn: Callable[[str], None] = default_logger) -> dict:
	"""Obtiene metadatos del último lanzamiento de FFmpeg en GitHub."""
	res = manager.fetch_github_release_assets(
		api_url=GITHUB_API_LATEST,
		html_url=GITHUB_HTML_LATEST,
		user_agent=USER_AGENT,
		fallback_builder=_build_fallback_assets,
		timeout=timeout,
		log_fn=log_fn,
	)
	if not res.get("assets"):
		tag = res.get("tag") or "latest"
		return {"tag": tag, "assets": _build_fallback_assets(tag)}
	return res


def select_best_asset(assets: list[dict], platform_name: str, arch: str) -> dict | None:
	"""Selecciona el paquete de FFmpeg más conveniente según SO y arquitectura."""
	plat = platform_name.lower()
	a = arch.lower()

	if plat == "windows":
		if a in ("arm64", "aarch64"):
			for asset in assets:
				name = asset["name"].lower()
				if "winarm64" in name and "shared" not in name and name.endswith(".zip"):
					return asset
		elif a in ("i386", "i686", "x86"):
			for asset in assets:
				name = asset["name"].lower()
				if "win32" in name and "shared" not in name and name.endswith(".zip"):
					return asset
		else:
			for asset in assets:
				name = asset["name"].lower()
				if "win64" in name and "shared" not in name and name.endswith(".zip"):
					return asset
			for asset in assets:
				name = asset["name"].lower()
				if "win" in name and "64" in name and name.endswith(".zip"):
					return asset
	elif plat == "linux":
		if a in ("arm64", "aarch64"):
			for asset in assets:
				name = asset["name"].lower()
				if ("linuxarm64" in name or ("linux" in name and "arm64" in name)) and "shared" not in name:
					return asset
		else:
			for asset in assets:
				name = asset["name"].lower()
				if ("linux64" in name or ("linux" in name and "x86_64" in name)) and "shared" not in name:
					return asset
			for asset in assets:
				name = asset["name"].lower()
				if "linux" in name and "64" in name:
					return asset
	elif plat == "macos":
		for asset in assets:
			name = asset["name"].lower()
			if ("darwin" in name or "macos" in name or "osx" in name) and (
				a in name or "universal" in name or "64" in name
			):
				return asset
	return None


def download_file(url: str, dest_path: Path, log_fn: Callable[[str], None] = default_logger) -> None:
	"""Descarga un archivo de FFmpeg con reporte de progreso."""
	manager.download_file(url, dest_path, log_fn=log_fn, user_agent=USER_AGENT)


def extract_ffmpeg_archive(archive_path: Path, dest_dir: Path, log_fn: Callable[[str], None] = default_logger) -> bool:
	"""Extrae ffmpeg y ffprobe directamente en dest_dir."""
	targets = {"ffmpeg.exe", "ffmpeg", "ffprobe.exe", "ffprobe"}
	extracted = manager.extract_archive_binary(
		archive_path=archive_path,
		dest_dir=dest_dir,
		target_names=targets,
		log_fn=log_fn,
	)
	is_win = sys.platform == "win32" or os.name == "nt"
	target_ffmpeg = "ffmpeg.exe" if is_win else "ffmpeg"
	return (
		extracted
		or (dest_dir / target_ffmpeg).is_file()
		or (dest_dir / "ffmpeg.exe").is_file()
		or (dest_dir / "ffmpeg").is_file()
	)


def get_default_install_dir() -> Path:
	"""Determina el directorio por defecto donde instalar FFmpeg."""
	return manager.get_default_install_dir("ffmpeg")


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""Verifica si el binario de FFmpeg fue gestionado por La Rockola."""
	return manager.is_rockola_managed(bin_path, "ffmpeg")


def install_ffmpeg(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	force: bool = False,
	log_fn: Callable[[str], None] = default_logger,
) -> Path | None:
	"""Descarga e instala FFmpeg y FFprobe desde GitHub Releases."""
	plat, target_arch = manager.resolve_platform_and_arch(platform_name, arch)
	dest_dir = Path(target_dir) if target_dir else get_default_install_dir()
	dest_dir.mkdir(parents=True, exist_ok=True)

	bin_name = "ffmpeg.exe" if (plat == "windows" or os.name == "nt") else "ffmpeg"
	final_path = dest_dir / bin_name

	if not force and final_path.is_file() and final_path.stat().st_size > 0:
		log_fn(f"FFmpeg ya está disponible en {final_path}. Usá force=True para reinstalar.")
		return final_path

	try:
		log_fn("Consultando últimos lanzamientos de FFmpeg en GitHub...")
		info = fetch_release_info(log_fn=log_fn)
		tag = info.get("tag", "latest")
		asset = select_best_asset(info.get("assets", []), plat, target_arch)

		if not asset:
			log_fn(f"No se encontró un paquete de FFmpeg compatible para {plat}-{target_arch} en el release {tag}.")
			return None

		log_fn(f"Paquete seleccionado: {asset['name']} ({tag})")
		with tempfile.TemporaryDirectory() as tmp_dir:
			download_path = Path(tmp_dir) / asset["name"]
			log_fn(f"Descargando desde {asset['url']}...")
			download_file(asset["url"], download_path, log_fn=log_fn)

			if not download_path.is_file() or download_path.stat().st_size == 0:
				log_fn("Error: El archivo descargado está vacío.")
				return None

			success = extract_ffmpeg_archive(download_path, dest_dir, log_fn=log_fn)
			if success and final_path.is_file():
				manager.mark_rockola_managed(dest_dir, "ffmpeg", log_fn=log_fn)
				log_fn(f"¡FFmpeg instalado exitosamente en {final_path}!")
				return final_path
			log_fn("Error: No se encontró ffmpeg después de descomprimir.")
			return None
	except Exception as e:
		log_fn(f"Error durante la instalación de FFmpeg: {e}")
		return None


def ensure_ffmpeg(log_fn: Callable[[str], None] = default_logger) -> str | None:
	"""Garantiza que FFmpeg esté disponible, descargándolo si falta."""
	existing = manager.find_binary("ffmpeg")
	if existing:
		return existing
	installed = install_ffmpeg(force=False, log_fn=log_fn)
	return str(installed) if installed else None


if __name__ == "__main__":
	install_ffmpeg(force="--force" in sys.argv)
