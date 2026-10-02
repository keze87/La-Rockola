#!/usr/bin/env python3
"""
ffmpeg_installer.py — Gestor de descarga e instalación automática de FFmpeg y FFprobe.

Permite descargar y descomprimir FFmpeg directamente desde los lanzamientos optimizados
de yt-dlp/FFmpeg-Builds (o fallback oficial) en GitHub.
"""

import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

GITHUB_API_LATEST = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
GITHUB_HTML_LATEST = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest"
USER_AGENT = "LaRockola-FFmpeg-Installer/1.0"


def default_logger(msg: str):
	print(f"[ffmpeg-installer] {msg}")


try:
	from . import binary_utils
	from .binary_utils import resolve_platform_and_arch
except (ImportError, ValueError):
	import binary_utils
	from binary_utils import resolve_platform_and_arch


def fetch_release_info(timeout: int = 10) -> dict:
	"""
	Obtiene metadatos del último lanzamiento de FFmpeg en GitHub.
	Intenta primero vía GitHub REST API y, si falla (ej. rate limit),
	construye los assets conocidos usando los builds oficiales de yt-dlp/FFmpeg-Builds.
	"""
	headers = {
		"User-Agent": USER_AGENT,
		"Accept": "application/vnd.github.v3+json",
	}

	# Método 1: GitHub API
	try:
		req = urllib.request.Request(GITHUB_API_LATEST, headers=headers)
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			data = json.loads(resp.read().decode("utf-8"))
			tag = data.get("tag_name", "latest")
			assets = [
				{
					"name": a.get("name", ""),
					"url": a.get("browser_download_url", ""),
					"size": a.get("size", 0),
				}
				for a in data.get("assets", [])
			]
			if assets:
				return {"tag": tag, "assets": assets}
	except Exception:
		pass

	# Método 2: Redirección / fallback conocido de yt-dlp/FFmpeg-Builds
	try:
		req2 = urllib.request.Request(GITHUB_HTML_LATEST, headers={"User-Agent": USER_AGENT})
		with urllib.request.urlopen(req2, timeout=timeout) as resp2:
			final_url = resp2.geturl()
			tag = final_url.rstrip("/").split("/")[-1]
	except Exception:
		tag = "latest"

	assets = [
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
	return {"tag": tag, "assets": assets}


def select_best_asset(assets: list[dict], platform_name: str, arch: str) -> dict | None:
	"""Selecciona el asset más conveniente según la plataforma y arquitectura."""
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
		else:  # x86_64
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
		else:  # x86_64
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


def download_file(url: str, dest_path: Path, log_fn=default_logger):
	"""Descarga un archivo con reporte de progreso."""
	binary_utils.download_file(url, dest_path, log_fn=log_fn, user_agent=USER_AGENT)


def extract_ffmpeg_archive(archive_path: Path, dest_dir: Path, log_fn=default_logger) -> bool:
	"""
	Extrae ffmpeg y ffprobe desde un archivo .zip o .tar a dest_dir,
	colocándolos directamente en dest_dir.
	"""
	dest_dir = dest_dir.resolve()
	dest_dir.mkdir(parents=True, exist_ok=True)
	archive_name = archive_path.name.lower()
	extracted_targets = set()

	if archive_name.endswith(".zip"):
		with zipfile.ZipFile(archive_path, "r") as zf:
			for member in zf.infolist():
				member_path = Path(member.filename)
				name_lower = member_path.name.lower()
				if name_lower in ("ffmpeg.exe", "ffmpeg", "ffprobe.exe", "ffprobe"):
					resolved = (dest_dir / name_lower).resolve()
					if not str(resolved).startswith(str(dest_dir)):
						continue
					with zf.open(member) as src, open(resolved, "wb") as dst:
						shutil.copyfileobj(src, dst)
					if sys.platform != "win32":
						try:
							resolved.chmod(resolved.stat().st_mode | 0o755)
						except Exception:
							pass
					extracted_targets.add(name_lower)
	elif archive_name.endswith((".tar.xz", ".tar.gz", ".tar")):
		mode = "r:*"
		with tarfile.open(archive_path, mode) as tf:
			for member in tf.getmembers():
				member_path = Path(member.name)
				name_lower = member_path.name.lower()
				if name_lower in ("ffmpeg.exe", "ffmpeg", "ffprobe.exe", "ffprobe") and member.isfile():
					resolved = (dest_dir / name_lower).resolve()
					if not str(resolved).startswith(str(dest_dir)):
						continue
					f_obj = tf.extractfile(member)
					if f_obj:
						with open(resolved, "wb") as dst:
							shutil.copyfileobj(f_obj, dst)
						if sys.platform != "win32":
							try:
								resolved.chmod(resolved.stat().st_mode | 0o755)
							except Exception:
								pass
						extracted_targets.add(name_lower)

	is_win = sys.platform == "win32" or os.name == "nt"
	target_ffmpeg = "ffmpeg.exe" if is_win else "ffmpeg"
	return (
		bool(extracted_targets)
		or (dest_dir / target_ffmpeg).is_file()
		or (dest_dir / "ffmpeg.exe").is_file()
		or (dest_dir / "ffmpeg").is_file()
	)


def get_default_install_dir() -> Path:
	"""Determina el directorio por defecto donde instalar FFmpeg."""
	return binary_utils.get_default_install_dir("ffmpeg")


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""Verifica si el binario de FFmpeg fue descargado/gestionado por La Rockola."""
	return binary_utils.is_rockola_managed(bin_path, "ffmpeg")


def install_ffmpeg(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	force: bool = False,
	log_fn=default_logger,
) -> Path | None:
	"""
	Descarga e instala FFmpeg y FFprobe desde GitHub Releases.
	Retorna la ruta al ejecutable ffmpeg instalado o None si falló.
	"""
	plat, target_arch = resolve_platform_and_arch(platform_name, arch)
	dest_dir = Path(target_dir) if target_dir else get_default_install_dir()
	dest_dir.mkdir(parents=True, exist_ok=True)

	bin_name = "ffmpeg.exe" if (plat == "windows" or os.name == "nt") else "ffmpeg"
	final_path = dest_dir / bin_name

	if not force and final_path.is_file() and final_path.stat().st_size > 0:
		log_fn(f"FFmpeg ya está disponible en {final_path}. Usá force=True para reinstalar.")
		return final_path

	try:
		log_fn("Consultando últimos lanzamientos de FFmpeg en GitHub...")
		info = fetch_release_info()
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
				try:
					(dest_dir / ".rockola_managed_ffmpeg").touch(exist_ok=True)
				except Exception:
					pass
				log_fn(f"¡FFmpeg instalado exitosamente en {final_path}!")
				return final_path
			else:
				log_fn("Error: No se encontró ffmpeg después de descomprimir.")
				return None

	except Exception as e:
		log_fn(f"Error durante la instalación de FFmpeg: {e}")
		return None


def ensure_ffmpeg(log_fn=default_logger) -> str | None:
	"""
	Garantiza que FFmpeg esté disponible. Si ya existe en el sistema o app,
	retorna su ruta; si no, lo descarga e instala.
	"""
	try:
		import server

		existing = server.find_binary("ffmpeg")
	except Exception:
		existing = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

	if existing:
		return existing

	installed = install_ffmpeg(force=False, log_fn=log_fn)
	return str(installed) if installed else None


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(description="Instalador automático de FFmpeg")
	parser.add_argument("target_dir", nargs="?", type=Path, default=None, help="Directorio destino de instalación")
	parser.add_argument("--force", action="store_true", help="Forzar reinstalación aunque ya exista")
	args = parser.parse_args()

	res = install_ffmpeg(target_dir=args.target_dir, force=args.force)
	if res:
		print(f"FFmpeg listo en: {res}")
		sys.exit(0)
	else:
		print("No se pudo instalar FFmpeg.", file=sys.stderr)
		sys.exit(1)
