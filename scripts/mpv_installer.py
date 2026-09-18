#!/usr/bin/env python3
"""
mpv_installer.py — Gestor de descarga e instalación automática de MPV desde GitHub Releases.

Permite descargar y descomprimir MPV (reproductor nativo) directamente desde los lanzamientos
oficiales de mpv-player/mpv en GitHub cuando no se encuentra instalado en el sistema.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

GITHUB_API_LATEST = "https://api.github.com/repos/mpv-player/mpv/releases/latest"
GITHUB_HTML_LATEST = "https://github.com/mpv-player/mpv/releases/latest"
USER_AGENT = "LaRockola-MPV-Installer/1.0"
COOLDOWN_SECONDS = 24 * 60 * 60 * 7  # 1 semana entre chequeos automáticos


def default_logger(msg: str):
	print(f"[mpv-installer] {msg}")


def resolve_platform_and_arch(platform_name: str | None = None, arch: str | None = None) -> tuple[str, str]:
	"""Normaliza la plataforma y la arquitectura deseada."""
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


def _parse_version(v_str: str | None) -> tuple[int, ...]:
	"""Convierte una cadena de versión como 'v0.41.0' o '0.38' en una tupla de enteros (0, 41, 0)."""
	if not v_str:
		return (0,)
	nums = re.findall(r"\d+", v_str)
	return tuple(int(x) for x in nums) if nums else (0,)


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


def get_installed_mpv_version(bin_path: str | Path) -> str | None:
	"""
	Obtiene la versión instalada de MPV ejecutando `mpv --version`.
	Retorna la versión como texto (ej. '0.41.0') o None si no se pudo determinar.
	"""
	p = Path(bin_path)
	if p.is_dir():
		ext = ".exe" if (sys.platform == "win32" or os.name == "nt") else ""
		candidate = p / f"mpv{ext}"
		if candidate.is_file():
			p = candidate
		elif (p / "mpv.exe").is_file():
			p = p / "mpv.exe"
		elif (p / "mpv").is_file():
			p = p / "mpv"

	if not p.is_file():
		return None

	try:
		res = subprocess.run(
			[str(p), "--version"],
			capture_output=True,
			text=True,
			timeout=5,
			check=False,
			env=_get_clean_env(),
		)
		output = res.stdout or res.stderr or ""
		match = re.search(r"mpv\s+(v?[\d\.]+)", output, re.IGNORECASE)
		if match:
			return match.group(1).lstrip("vV")
	except Exception:
		pass

	return None


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""
	Verifica si un binario o directorio de MPV fue descargado/gestionado por La Rockola.
	Solo se deben actualizar binarios gestionados por La Rockola, nunca instalaciones del sistema.
	"""
	path = Path(bin_path).resolve()
	target_dir = path if path.is_dir() else path.parent

	# 1. Marcador explícito en la carpeta de mpv
	if (target_dir / ".rockola_managed_mpv").is_file():
		return True

	# 2. Ubicado dentro del directorio base de la aplicación (ej. en base / "mpv")
	base = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent).resolve()
	base = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent).resolve()
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


def fetch_release_info(timeout: int = 10) -> dict:
	"""
	Obtiene metadatos del último lanzamiento de MPV en GitHub.
	Intenta primero vía GitHub REST API y, si falla (ej. rate limit 403),
	hace fallback siguiendo la redirección HTTP 302 de la URL web para obtener el tag.
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
			tag = data.get("tag_name")
			assets = [
				{
					"name": a.get("name", ""),
					"url": a.get("browser_download_url", ""),
					"size": a.get("size", 0),
				}
				for a in data.get("assets", [])
			]
			if tag and assets:
				return {"tag": tag, "assets": assets}
	except Exception:
		pass

	# Método 2: Redirección de GitHub Releases
	try:
		req2 = urllib.request.Request(GITHUB_HTML_LATEST, headers={"User-Agent": USER_AGENT})
		with urllib.request.urlopen(req2, timeout=timeout) as resp2:
			final_url = resp2.geturl()
			# La URL final tiene la forma https://github.com/mpv-player/mpv/releases/tag/vX.Y.Z
			tag = final_url.rstrip("/").split("/")[-1]
			if tag and tag.startswith("v"):
				# Construimos assets estándar conocidos para Windows y macOS
				assets = [
					{
						"name": f"mpv-{tag}-x86_64-w64-mingw32.zip",
						"url": f"https://github.com/mpv-player/mpv/releases/download/{tag}/mpv-{tag}-x86_64-w64-mingw32.zip",
						"size": 0,
					},
					{
						"name": f"mpv-{tag}-x86_64-pc-windows-msvc.zip",
						"url": f"https://github.com/mpv-player/mpv/releases/download/{tag}/mpv-{tag}-x86_64-pc-windows-msvc.zip",
						"size": 0,
					},
					{
						"name": f"mpv-{tag}-i686-w64-mingw32.zip",
						"url": f"https://github.com/mpv-player/mpv/releases/download/{tag}/mpv-{tag}-i686-w64-mingw32.zip",
						"size": 0,
					},
					{
						"name": f"mpv-{tag}-aarch64-pc-windows-msvc.zip",
						"url": f"https://github.com/mpv-player/mpv/releases/download/{tag}/mpv-{tag}-aarch64-pc-windows-msvc.zip",
						"size": 0,
					},
					{
						"name": f"mpv-{tag}-macos-15-arm.zip",
						"url": f"https://github.com/mpv-player/mpv/releases/download/{tag}/mpv-{tag}-macos-15-arm.zip",
						"size": 0,
					},
				]
				return {"tag": tag, "assets": assets}
	except Exception:
		pass

	raise RuntimeError("No se pudo obtener información de lanzamientos de MPV desde GitHub.")


def select_best_asset(assets: list[dict], platform_name: str, arch: str) -> dict | None:
	"""Selecciona el asset más conveniente según la plataforma y la arquitectura."""
	plat = platform_name.lower()
	a = arch.lower()

	if plat == "windows":
		if a == "x86_64":
			# Priorizar mingw32 (~39MB vs ~77MB de msvc)
			for asset in assets:
				name = asset["name"].lower()
				if "x86_64" in name and "mingw32" in name and name.endswith(".zip"):
					return asset
			for asset in assets:
				name = asset["name"].lower()
				if "x86_64" in name and "windows" in name and name.endswith(".zip"):
					return asset
		elif a == "arm64":
			for asset in assets:
				name = asset["name"].lower()
				if "aarch64" in name and "windows" in name and name.endswith(".zip"):
					return asset
		elif a == "i686":
			for asset in assets:
				name = asset["name"].lower()
				if "i686" in name and "mingw32" in name and name.endswith(".zip"):
					return asset
	elif plat == "macos":
		target_pattern = "arm" if a in ("arm64", "aarch64") else "intel"
		for asset in assets:
			name = asset["name"].lower()
			if "macos" in name and target_pattern in name and name.endswith(".zip"):
				return asset

	return None


def download_asset(url: str, dest_path: Path, log_fn=default_logger):
	"""Descarga un archivo por HTTP con reporte de progreso."""
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
					if pct != last_logged_pct and pct % 10 == 0:
						last_logged_pct = pct
						mb_down = downloaded / (1024 * 1024)
						mb_total = total_size / (1024 * 1024)
						log_fn(f"Descargando MPV: {mb_down:.1f}/{mb_total:.1f} MB ({pct}%)")
				elif downloaded % (5 * 1024 * 1024) == 0:
					log_fn(f"Descargando MPV: {downloaded / (1024 * 1024):.1f} MB...")


def _safe_extract(zf: zipfile.ZipFile, dest_dir: Path):
	"""Extrae archivos de un ZipFile evitando Zip Slip y omitiendo archivos de debug (.pdb)."""
	dest_dir = dest_dir.resolve()
	for member in zf.infolist():
		# Omitir archivos de símbolos de depuración gigantes (.pdb)
		if member.filename.lower().endswith(".pdb"):
			continue
		# Evitar Path Traversal / Zip Slip
		target = (dest_dir / member.filename).resolve()
		if not str(target).startswith(str(dest_dir)):
			continue
		zf.extract(member, dest_dir)
		# En sistemas Unix, restaurar permisos de ejecución si corresponde
		if sys.platform != "win32" and not member.is_dir():
			mode = (member.external_attr >> 16) & 0o777
			if mode & 0o111:
				try:
					target.chmod(target.stat().st_mode | 0o755)
				except Exception:
					pass


def extract_mpv_zip(zip_path: Path, target_dir: Path, log_fn=default_logger) -> bool:
	"""
	Extrae el zip de MPV en target_dir. Si el zip contiene un archivo .zip interno
	(como la versión mingw32 de MPV), extrae automáticamente el archivo interno.
	"""
	target_dir.mkdir(parents=True, exist_ok=True)
	log_fn(f"Descomprimiendo MPV en {target_dir}...")

	with zipfile.ZipFile(zip_path, "r") as outer_zf:
		inner_zips = [name for name in outer_zf.namelist() if name.lower().endswith(".zip")]
		has_mpv_direct = any(name.lower().endswith(("mpv.exe", "mpv")) for name in outer_zf.namelist())

		if inner_zips and not has_mpv_direct:
			# Extraer zip interno en memoria o disco temporal
			inner_name = inner_zips[0]
			with tempfile.TemporaryDirectory() as tmp_inner:
				inner_zip_path = Path(tmp_inner) / "inner.zip"
				with outer_zf.open(inner_name) as src, open(inner_zip_path, "wb") as dst:
					shutil.copyfileobj(src, dst)
				with zipfile.ZipFile(inner_zip_path, "r") as inner_zf:
					_safe_extract(inner_zf, target_dir)
		else:
			_safe_extract(outer_zf, target_dir)

	# Verificar si mpv.exe o mpv quedó presente
	ext = ".exe" if (sys.platform == "win32" or os.name == "nt") else ""
	bin_present = (target_dir / f"mpv{ext}").is_file() or (target_dir / "mpv.exe").is_file()
	return bin_present


def get_default_install_dir() -> Path:
	"""Determina el directorio por defecto donde instalar MPV (portable o datos de usuario)."""
	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

	# Probar si el directorio base es escribible (modo portable)
	try:
		test_file = base / ".carpincho_write_test"
		test_file.touch(exist_ok=True)
		test_file.unlink(missing_ok=True)
		return base / "mpv"
	except OSError:
		pass

	# Si es de solo lectura (ej. C:\\Program Files), usar AppData/Local o similar
	if sys.platform == "win32":
		app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
	elif sys.platform == "darwin":
		app_data = Path.home() / "Library" / "Application Support"
	else:
		app_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

	return app_data / "carpincho" / "mpv"


def install_mpv(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	log_fn=default_logger,
) -> Path | None:
	"""
	Descarga e instala la última versión de MPV desde GitHub en target_dir.
	Retorna la ruta al directorio instalado con éxito, o None si falló.
	"""
	plat, target_arch = resolve_platform_and_arch(platform_name, arch)

	if plat not in ("windows", "macos"):
		log_fn(f"La descarga automática de MPV no está soportada para la plataforma '{plat}'.")
		return None

	dest_dir = Path(target_dir) if target_dir else get_default_install_dir()

	try:
		log_fn("Consultando últimos lanzamientos de MPV en GitHub...")
		info = fetch_release_info()
		tag = info.get("tag", "latest")
		asset = select_best_asset(info.get("assets", []), plat, target_arch)

		if not asset:
			log_fn(f"No se encontró un paquete de MPV compatible para {plat}-{target_arch} en el release {tag}.")
			return None

		log_fn(f"Paquete seleccionado: {asset['name']} ({tag})")

		with tempfile.TemporaryDirectory() as tmp_dir:
			download_path = Path(tmp_dir) / asset["name"]
			log_fn(f"Descargando desde {asset['url']}...")
			download_asset(asset["url"], download_path, log_fn=log_fn)

			if not download_path.is_file() or download_path.stat().st_size == 0:
				log_fn("Error: El archivo descargado está vacío o no se pudo guardar.")
				return None

			success = extract_mpv_zip(download_path, dest_dir, log_fn=log_fn)
			if success:
				try:
					(dest_dir / ".rockola_managed_mpv").touch(exist_ok=True)
					(dest_dir / ".last_mpv_update_check").write_text(str(time.time()))
				except Exception:
					pass
				log_fn(f"¡MPV instalado exitosamente en {dest_dir}!")
				return dest_dir
			else:
				log_fn("Error: No se encontró mpv después de la descompresión.")
				return None

	except Exception as e:
		log_fn(f"Error durante la instalación automática de MPV: {e}")
		return None


def ensure_mpv(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	log_fn=default_logger,
) -> Path | None:
	"""Verifica si MPV ya existe en target_dir o lo instala si no está."""
	dest_dir = Path(target_dir) if target_dir else get_default_install_dir()
	ext = ".exe" if (sys.platform == "win32" or os.name == "nt") else ""
	if (dest_dir / f"mpv{ext}").is_file() or (dest_dir / "mpv.exe").is_file():
		return dest_dir
	return install_mpv(target_dir=dest_dir, platform_name=platform_name, arch=arch, log_fn=log_fn)


def update_mpv(
	bin_path: str | Path | None = None,
	force: bool = False,
	cooldown: int = COOLDOWN_SECONDS,
	log_fn=default_logger,
) -> bool:
	"""
	Verifica y actualiza MPV si hay una nueva versión disponible en GitHub Releases.
	Solo se ejecuta si el binario de MPV es gestionado por La Rockola.
	Aplica un cooldown de 1 semana por defecto para no ralentizar el inicio del servidor.
	"""
	if not bin_path:
		try:
			import server

			bin_path = server.find_binary("mpv")
		except Exception:
			bin_path = shutil.which("mpv")

	if not bin_path:
		log_fn("No se encontró MPV para actualizar.")
		return False

	p = Path(bin_path).resolve()
	target_dir = p if p.is_dir() else p.parent

	if not is_rockola_managed(p):
		log_fn(f"MPV ({p}) es una instalación externa del sistema; se omite la auto-actualización.")
		return False

	plat, _ = resolve_platform_and_arch()
	if plat not in ("windows", "macos"):
		log_fn(f"La actualización automática de MPV no está soportada para la plataforma '{plat}'.")
		return False

	timestamp_file = target_dir / ".last_mpv_update_check"
	if not force and timestamp_file.is_file():
		try:
			last_check = float(timestamp_file.read_text().strip())
			if time.time() - last_check < cooldown:
				return True
		except Exception:
			pass

	cur_ver_str = get_installed_mpv_version(p)
	log_fn(f"Buscando actualizaciones para MPV (versión instalada: {cur_ver_str or 'desconocida'})...")

	try:
		info = fetch_release_info(timeout=5)
	except Exception as e:
		log_fn(f"No se pudo consultar actualizaciones de MPV: {e}")
		return False

	# Actualizar el timestamp del chequeo
	try:
		timestamp_file.write_text(str(time.time()))
	except Exception:
		pass

	tag = info.get("tag", "")
	remote_ver = _parse_version(tag)
	installed_ver = _parse_version(cur_ver_str) if cur_ver_str else (0,)

	if remote_ver > installed_ver:
		log_fn(f"Hay una nueva versión de MPV disponible ({tag} > {cur_ver_str or 'desconocida'}). Actualizando...")
		result = install_mpv(target_dir=target_dir, log_fn=log_fn)
		if result:
			log_fn(f"¡MPV actualizado con éxito a la versión {tag}!")
			return True
		else:
			log_fn("Falló la actualización de MPV.")
			return False
	else:
		log_fn(f"MPV está al día (versión {cur_ver_str or tag}).")
		return True


if __name__ == "__main__":
	if "--update" in sys.argv:
		sys.argv.remove("--update")
		target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
		res = update_mpv(bin_path=target, force=True)
		sys.exit(0 if res else 1)

	target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
	res = install_mpv(target_dir=target)
	if res:
		print(f"MPV listo en: {res}")
		sys.exit(0)
	else:
		print("No se pudo instalar MPV.", file=sys.stderr)
		sys.exit(1)
