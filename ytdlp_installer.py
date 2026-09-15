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
	"""Determina el directorio donde ubicar yt-dlp (en el mismo directorio que mpv para que lo reconozca)."""
	# 1. Si MPV ya está instalado, ubicar yt-dlp en el mismo directorio que mpv
	try:
		import server

		mpv_path = server.find_binary("mpv")
		if mpv_path:
			mpv_dir = Path(mpv_path).parent
			try:
				test_file = mpv_dir / ".carpincho_write_test"
				test_file.touch(exist_ok=True)
				test_file.unlink(missing_ok=True)
				return mpv_dir
			except OSError:
				pass
	except Exception:
		pass

	# 2. Si no, consultar el directorio por defecto de mpv_installer (mpv/ o datos de usuario)
	try:
		import mpv_installer

		return mpv_installer.get_default_install_dir()
	except Exception:
		pass

	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
	if (base / "mpv").is_dir():
		return base / "mpv"
	return base


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""
	Verifica si un binario de yt-dlp fue descargado/gestionado por La Rockola.
	Solo se deben actualizar binarios gestionados por La Rockola, nunca instalaciones del sistema.
	"""
	path = Path(bin_path).resolve()
	parent = path.parent

	# 1. Marcador explícito
	if (parent / ".rockola_managed_ytdlp").is_file():
		return True

	# 2. Ubicado dentro del directorio base de la aplicación (ej. en mpv/)
	base = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent).resolve()
	try:
		path.relative_to(base)
		return True
	except ValueError:
		pass

	# 3. Ubicado dentro de los datos de usuario de Rockola
	try:
		import server

		data_dir = getattr(server, "DATA_DIR", None)
		if data_dir:
			path.relative_to(Path(data_dir).resolve().parent)
			return True
	except Exception:
		pass

	return False


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
		existing = shutil.which("yt-dlp")

	if existing:
		return existing

	installed = install_ytdlp(log_fn=log_fn)
	return str(installed) if installed else None


def _get_clean_env() -> dict:
	env = os.environ.copy()
	for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "DYLD_LIBRARY_PATH"):
		orig = f"{var}_ORIG"
		if orig in env and env[orig].strip():
			env[var] = env[orig]
		elif var in env:
			del env[var]
	if "LD_LIBRARY_PATH" in env:
		parts = [p.strip() for p in env["LD_LIBRARY_PATH"].split(":") if p.strip()]
		clean_parts = [p for p in parts if "_MEI" not in p and ".mount_" not in p]
		if clean_parts:
			env["LD_LIBRARY_PATH"] = ":".join(clean_parts)
		else:
			del env["LD_LIBRARY_PATH"]
	return env


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
			env=_get_clean_env(),
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
