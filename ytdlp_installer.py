#!/usr/bin/env python3
"""
ytdlp_installer.py — Gestor de descarga, instalación y actualización automática de yt-dlp.

Descarga la versión independiente oficial de yt-dlp desde GitHub Releases y permite
actualizarla en caliente para mantener la compatibilidad con YouTube.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

YTDLP_BASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download"
USER_AGENT = "LaRockola-YTDLP-Installer/1.0"


def default_logger(msg: str):
	print(f"[yt-dlp-installer] {msg}")


def resolve_platform_and_arch(platform_name: str | None = None, arch: str | None = None) -> tuple[str, str]:
	"""Normaliza la plataforma y la arquitectura para yt-dlp."""
	if not platform_name:
		plat = sys.platform.lower()
		if plat in ("win32", "cygwin") or os.name == "nt":
			platform_name = "windows"
		elif "darwin" in plat:
			platform_name = "macos"
		elif "linux" in plat:
			platform_name = "linux"
		else:
			platform_name = platform.system().lower()

	if not arch:
		mach = platform.machine().lower()
		if mach in ("amd64", "x86_64", "x64"):
			arch = "x86_64"
		elif mach in ("arm64", "aarch64"):
			arch = "arm64"
		elif mach in ("i386", "i686", "x86"):
			arch = "i686"
		else:
			arch = mach

	return platform_name, arch


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
	"""Determina el directorio donde ubicar yt-dlp (base de la app o datos de usuario)."""
	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

	# Si base es escribible, guardamos junto al ejecutable o en mpv/
	try:
		test_file = base / ".carpincho_write_test"
		test_file.touch(exist_ok=True)
		test_file.unlink(missing_ok=True)
		# Si existe la carpeta mpv/, podemos ponerlo allí para que MPV lo detecte de una
		if (base / "mpv").is_dir():
			return base / "mpv"
		return base
	except OSError:
		pass

	# Si es de solo lectura (ej. C:\\Program Files), usar AppData/Local o similar
	if sys.platform == "win32":
		app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
	elif sys.platform == "darwin":
		app_data = Path.home() / "Library" / "Application Support"
	else:
		app_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

	return app_data / "carpincho" / "bin"


def download_file(url: str, dest_path: Path, log_fn=default_logger):
	"""Descarga un archivo con reporte de progreso."""
	headers = {"User-Agent": USER_AGENT}
	req = urllib.request.Request(url, headers=headers)
	dest_path.parent.mkdir(parents=True, exist_ok=True)

	with urllib.request.urlopen(req, timeout=30) as resp:
		total_size = int(resp.headers.get("content-length", 0))
		downloaded = 0
		chunk_size = 64 * 1024
		last_logged_pct = -1

		with open(dest_path, "wb") as f:
			while True:
				chunk = resp.read(chunk_size)
				if not chunk:
					break
				f.write(chunk)
				downloaded += len(chunk)
				if total_size > 0:
					pct = int((downloaded / total_size) * 100)
					if pct != last_logged_pct and pct % 20 == 0:
						last_logged_pct = pct
						mb_down = downloaded / (1024 * 1024)
						mb_total = total_size / (1024 * 1024)
						log_fn(f"Descargando yt-dlp: {mb_down:.1f}/{mb_total:.1f} MB ({pct}%)")


def install_ytdlp(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
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
		existing = shutil.which("yt-dlp")

	if existing:
		return existing

	installed = install_ytdlp(log_fn=log_fn)
	return str(installed) if installed else None


def update_ytdlp(bin_path: str | None = None, log_fn=default_logger) -> bool:
	"""
	Actualiza yt-dlp en caliente usando su comando nativo -U.
	Retorna True si la actualización se completó con éxito.
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

	log_fn(f"Buscando actualizaciones para yt-dlp ({bin_path})...")
	try:
		res = subprocess.run(
			[bin_path, "-U"],
			capture_output=True,
			text=True,
			timeout=60,
			check=False,
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
	target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
	res = install_ytdlp(target_dir=target)
	if res:
		print(f"yt-dlp listo en: {res}")
		sys.exit(0)
	else:
		print("No se pudo instalar yt-dlp.", file=sys.stderr)
		sys.exit(1)
