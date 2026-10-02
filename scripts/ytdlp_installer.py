#!/usr/bin/env python3
"""
ytdlp_installer.py — Gestor de descarga, instalación y actualización automática de yt-dlp.

Descarga la versión independiente oficial de yt-dlp desde GitHub Releases y permite
actualizarla en caliente para mantener la compatibilidad con YouTube.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

YTDLP_BASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download"
USER_AGENT = "LaRockola-YTDLP-Installer/1.0"


def default_logger(msg: str):
	print(f"[yt-dlp-installer] {msg}")


try:
	from . import binary_utils
	from .binary_utils import get_clean_env, resolve_platform_and_arch
except (ImportError, ValueError):
	import binary_utils
	from binary_utils import get_clean_env, resolve_platform_and_arch


def get_ytdlp_asset_name(platform_name: str | None = None, arch: str | None = None) -> str:
	"""Determina el nombre del ejecutable de yt-dlp en GitHub Releases."""
	plat, target_arch = resolve_platform_and_arch(platform_name, arch)

	if plat == "windows":
		if target_arch == "arm64":
			return "yt-dlp_arm64.exe"
		elif target_arch == "i686":
			return "yt-dlp_x86.exe"
		return "yt-dlp.exe"
	elif plat == "macos":
		return "yt-dlp_macos"
	else:
		return "yt-dlp"


def get_ytdlp_download_url(platform_name: str | None = None, arch: str | None = None) -> str:
	"""Obtiene la URL directa de descarga del último ejecutable de yt-dlp."""
	asset_name = get_ytdlp_asset_name(platform_name, arch)
	return f"{YTDLP_BASE_URL}/{asset_name}"


def get_default_install_dir() -> Path:
	"""Determina el directorio donde ubicar yt-dlp (en el mismo directorio que mpv para que lo reconozca)."""
	return binary_utils.get_default_install_dir("ytdlp")


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""
	Verifica si un binario de yt-dlp fue descargado/gestionado por La Rockola.
	Solo se deben actualizar binarios gestionados por La Rockola, nunca instalaciones del sistema.
	"""
	return binary_utils.is_rockola_managed(bin_path, "ytdlp")


def download_file(url: str, dest_path: Path, log_fn=default_logger):
	"""Descarga un archivo con reporte de progreso."""
	binary_utils.download_file(url, dest_path, log_fn=log_fn, user_agent=USER_AGENT)


def install_ytdlp(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	force: bool = False,
	log_fn=default_logger,
) -> Path | None:
	"""
	Descarga e instala yt-dlp desde GitHub Releases.
	Retorna la ruta al archivo binario instalado o None si falló.
	"""
	plat, target_arch = resolve_platform_and_arch(platform_name, arch)
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

			# Mover al destino final
			shutil.move(str(tmp_download), str(final_path))

			# Dejar constancia de que fue instalado por La Rockola
			try:
				(dest_dir / ".rockola_managed_ytdlp").touch(exist_ok=True)
			except Exception:
				pass

			# Asignar permisos de ejecución en POSIX
			if sys.platform != "win32":
				try:
					final_path.chmod(final_path.stat().st_mode | 0o755)
				except Exception:
					pass

		log_fn(f"¡yt-dlp instalado correctamente en {final_path}!")
		return final_path
	except Exception as e:
		log_fn(f"Error al descargar yt-dlp: {e}")
		return None


def ensure_ytdlp(log_fn=default_logger) -> str | None:
	"""
	Garantiza que yt-dlp esté disponible. Si ya se encuentra en el sistema
	o en la carpeta de la app, retorna su ruta; si no, lo descarga e instala.
	"""
	# Buscar si server o shutil lo encuentran
	try:
		import server

		existing = server.find_binary("yt-dlp")
	except Exception:
		existing = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")

	if existing:
		return existing

	installed = install_ytdlp(force=False, log_fn=log_fn)
	return str(installed) if installed else None


def update_ytdlp(bin_path: str | None = None, log_fn=default_logger) -> bool:
	"""
	Actualiza yt-dlp en caliente usando su comando nativo -U.
	Solo se ejecuta si yt-dlp fue descargado y gestionado por La Rockola.
	"""
	if not bin_path:
		try:
			import server

			bin_path = server.find_binary("yt-dlp")
		except Exception:
			bin_path = shutil.which("yt-dlp")

	if not bin_path or not Path(bin_path).is_file():
		log_fn("No se encontró yt-dlp para actualizar.")
		return False

	# Solo actualizar si es gestionado por La Rockola
	if not is_rockola_managed(bin_path):
		log_fn(f"yt-dlp ({bin_path}) es una instalación externa del sistema; se omite la auto-actualización.")
		return False

	log_fn(f"Buscando actualizaciones para yt-dlp ({bin_path})...")
	try:
		res = subprocess.run(
			[bin_path, "-U"],
			capture_output=True,
			text=True,
			timeout=60,
			check=False,
			env=get_clean_env(),
		)
		stdout = res.stdout.strip()
		if stdout:
			log_fn(stdout)
		if res.returncode == 0:
			log_fn("yt-dlp está al día.")
			return True
		else:
			stderr = res.stderr.strip()
			if stderr:
				log_fn(f"Aviso de actualización: {stderr}")
			return False
	except Exception as e:
		log_fn(f"No se pudo actualizar yt-dlp: {e}")
		return False


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(description="Instalador y actualizador automático de yt-dlp")
	parser.add_argument("target_dir", nargs="?", type=Path, default=None, help="Directorio destino de instalación")
	parser.add_argument("--force", action="store_true", help="Forzar reinstalación aunque ya exista")
	args = parser.parse_args()

	res = install_ytdlp(target_dir=args.target_dir, force=args.force)
	if res:
		print(f"yt-dlp listo en: {res}")
		sys.exit(0)
	else:
		print("No se pudo instalar yt-dlp.", file=sys.stderr)
		sys.exit(1)
