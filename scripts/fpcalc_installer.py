#!/usr/bin/env python3
"""
fpcalc_installer.py — Gestor de descarga e instalación automática de fpcalc (Chromaprint).

Permite descargar y descomprimir la herramienta de huella acústica fpcalc directamente
desde los lanzamientos oficiales de acoustid/chromaprint en GitHub.
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

GITHUB_API_LATEST = "https://api.github.com/repos/acoustid/chromaprint/releases/latest"
GITHUB_HTML_LATEST = "https://github.com/acoustid/chromaprint/releases/latest"
USER_AGENT = "LaRockola-FPCalc-Installer/1.0"


def default_logger(msg: str):
	print(f"[fpcalc-installer] {msg}")


try:
	from .binary_utils import resolve_platform_and_arch
except (ImportError, ValueError):
	from binary_utils import resolve_platform_and_arch


def fetch_release_info(timeout: int = 10) -> dict:
	"""
	Obtiene metadatos del último lanzamiento de chromaprint en GitHub.
	Intenta primero vía GitHub REST API y, si falla (ej. rate limit),
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
			tag = final_url.rstrip("/").split("/")[-1]
			ver = tag.lstrip("vV")
			if tag and ver:
				assets = [
					{
						"name": f"chromaprint-fpcalc-{ver}-windows-x86_64.zip",
						"url": f"https://github.com/acoustid/chromaprint/releases/download/{tag}/chromaprint-fpcalc-{ver}-windows-x86_64.zip",
						"size": 0,
					},
					{
						"name": f"chromaprint-fpcalc-{ver}-linux-x86_64.tar.gz",
						"url": f"https://github.com/acoustid/chromaprint/releases/download/{tag}/chromaprint-fpcalc-{ver}-linux-x86_64.tar.gz",
						"size": 0,
					},
					{
						"name": f"chromaprint-fpcalc-{ver}-linux-arm64.tar.gz",
						"url": f"https://github.com/acoustid/chromaprint/releases/download/{tag}/chromaprint-fpcalc-{ver}-linux-arm64.tar.gz",
						"size": 0,
					},
					{
						"name": f"chromaprint-fpcalc-{ver}-macos-universal.tar.gz",
						"url": f"https://github.com/acoustid/chromaprint/releases/download/{tag}/chromaprint-fpcalc-{ver}-macos-universal.tar.gz",
						"size": 0,
					},
					{
						"name": f"chromaprint-fpcalc-{ver}-macos-arm64.tar.gz",
						"url": f"https://github.com/acoustid/chromaprint/releases/download/{tag}/chromaprint-fpcalc-{ver}-macos-arm64.tar.gz",
						"size": 0,
					},
					{
						"name": f"chromaprint-fpcalc-{ver}-macos-x86_64.tar.gz",
						"url": f"https://github.com/acoustid/chromaprint/releases/download/{tag}/chromaprint-fpcalc-{ver}-macos-x86_64.tar.gz",
						"size": 0,
					},
				]
				return {"tag": tag, "assets": assets}
	except Exception:
		pass

	raise RuntimeError("No se pudo obtener información de lanzamientos de fpcalc desde GitHub.")


def select_best_asset(assets: list[dict], platform_name: str, arch: str) -> dict | None:
	"""Selecciona el paquete más adecuado para fpcalc según la plataforma y arquitectura."""
	plat = platform_name.lower()
	a = arch.lower()

	if plat == "windows":
		for asset in assets:
			name = asset["name"].lower()
			if "windows" in name and ("x86_64" in name or "x64" in name) and name.endswith(".zip"):
				return asset
		for asset in assets:
			name = asset["name"].lower()
			if "windows" in name and name.endswith(".zip"):
				return asset
	elif plat == "linux":
		if a in ("arm64", "aarch64"):
			for asset in assets:
				name = asset["name"].lower()
				if "linux" in name and "arm64" in name and name.endswith((".tar.gz", ".tar.xz")):
					return asset
		else:
			for asset in assets:
				name = asset["name"].lower()
				if "linux" in name and ("x86_64" in name or "x64" in name) and name.endswith((".tar.gz", ".tar.xz")):
					return asset
	elif plat == "macos":
		if a in ("arm64", "aarch64"):
			for asset in assets:
				name = asset["name"].lower()
				if "macos" in name and "arm64" in name and name.endswith((".tar.gz", ".tar.xz")):
					return asset
		for asset in assets:
			name = asset["name"].lower()
			if "macos" in name and "universal" in name and name.endswith((".tar.gz", ".tar.xz")):
				return asset
		for asset in assets:
			name = asset["name"].lower()
			if "macos" in name and ("x86_64" in name or "x64" in name) and name.endswith((".tar.gz", ".tar.xz")):
				return asset

	return None


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
						log_fn(f"Descargando fpcalc: {mb_down:.1f}/{mb_total:.1f} MB ({pct}%)")


def extract_fpcalc_archive(archive_path: Path, dest_dir: Path, log_fn=default_logger) -> bool:
	"""
	Extrae fpcalc desde un archivo .zip o .tar.gz a dest_dir,
	colocando el ejecutable directamente en dest_dir.
	"""
	dest_dir = dest_dir.resolve()
	dest_dir.mkdir(parents=True, exist_ok=True)
	archive_name = archive_path.name.lower()
	extracted_any = False

	if archive_name.endswith(".zip"):
		with zipfile.ZipFile(archive_path, "r") as zf:
			for member in zf.infolist():
				member_path = Path(member.filename)
				name_lower = member_path.name.lower()
				if name_lower in ("fpcalc.exe", "fpcalc"):
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
					extracted_any = True
	elif archive_name.endswith((".tar.gz", ".tar.xz", ".tar")):
		mode = "r:*"
		with tarfile.open(archive_path, mode) as tf:
			for member in tf.getmembers():
				member_path = Path(member.name)
				name_lower = member_path.name.lower()
				if name_lower in ("fpcalc.exe", "fpcalc") and member.isfile():
					resolved = (dest_dir / name_lower).resolve()
					if not str(resolved).startswith(str(dest_dir)):
						continue
					extracted_file = tf.extractfile(member)
					if extracted_file:
						with open(resolved, "wb") as dst:
							shutil.copyfileobj(extracted_file, dst)
						if sys.platform != "win32":
							try:
								resolved.chmod(resolved.stat().st_mode | 0o755)
							except Exception:
								pass
						extracted_any = True

	return extracted_any or (dest_dir / "fpcalc.exe").is_file() or (dest_dir / "fpcalc").is_file()


def get_default_install_dir() -> Path:
	"""Determina el directorio por defecto donde instalar fpcalc."""
	# 1. Si MPV ya está instalado, ubicar fpcalc en el mismo directorio (o bin/)
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

	# 2. Consultar directorio por defecto de mpv_installer
	try:
		from scripts import mpv_installer

		return mpv_installer.get_default_install_dir()
	except Exception:
		pass

	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
	if (base / "mpv").is_dir():
		return base / "mpv"
	if (base / "bin").is_dir():
		return base / "bin"
	return base


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""Verifica si el binario de fpcalc fue gestionado por La Rockola."""
	path = Path(bin_path).resolve()
	parent = path if path.is_dir() else path.parent

	if (parent / ".rockola_managed_fpcalc").is_file():
		return True

	base = (
		Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
	).resolve()
	try:
		path.relative_to(base)
		return True
	except ValueError:
		pass

	try:
		import server

		data_dir = getattr(server, "DATA_DIR", None)
		if data_dir:
			path.relative_to(Path(data_dir).resolve().parent)
			return True
	except Exception:
		pass

	return False


def install_fpcalc(
	target_dir: Path | None = None,
	platform_name: str | None = None,
	arch: str | None = None,
	force: bool = False,
	log_fn=default_logger,
) -> Path | None:
	"""
	Descarga e instala fpcalc desde GitHub Releases.
	Retorna la ruta al archivo binario instalado o None si falló.
	"""
	plat, target_arch = resolve_platform_and_arch(platform_name, arch)
	dest_dir = Path(target_dir) if target_dir else get_default_install_dir()
	dest_dir.mkdir(parents=True, exist_ok=True)

	bin_name = "fpcalc.exe" if (plat == "windows" or os.name == "nt") else "fpcalc"
	final_path = dest_dir / bin_name

	if not force and final_path.is_file() and final_path.stat().st_size > 0:
		log_fn(f"fpcalc ya está disponible en {final_path}. Usá force=True para reinstalar.")
		return final_path

	try:
		log_fn("Consultando últimos lanzamientos de fpcalc (chromaprint) en GitHub...")
		info = fetch_release_info()
		tag = info.get("tag", "latest")
		asset = select_best_asset(info.get("assets", []), plat, target_arch)

		if not asset:
			log_fn(f"No se encontró un paquete de fpcalc compatible para {plat}-{target_arch} en el release {tag}.")
			return None

		log_fn(f"Paquete seleccionado: {asset['name']} ({tag})")

		with tempfile.TemporaryDirectory() as tmp_dir:
			download_path = Path(tmp_dir) / asset["name"]
			log_fn(f"Descargando desde {asset['url']}...")
			download_file(asset["url"], download_path, log_fn=log_fn)

			if not download_path.is_file() or download_path.stat().st_size == 0:
				log_fn("Error: El archivo descargado está vacío.")
				return None

			success = extract_fpcalc_archive(download_path, dest_dir, log_fn=log_fn)
			if success and final_path.is_file():
				try:
					(dest_dir / ".rockola_managed_fpcalc").touch(exist_ok=True)
				except Exception:
					pass
				log_fn(f"¡fpcalc instalado exitosamente en {final_path}!")
				return final_path
			else:
				log_fn("Error: No se encontró fpcalc después de descomprimir.")
				return None

	except Exception as e:
		log_fn(f"Error durante la instalación de fpcalc: {e}")
		return None


def ensure_fpcalc(log_fn=default_logger) -> str | None:
	"""
	Garantiza que fpcalc esté disponible. Si ya existe en el sistema o app,
	retorna su ruta; si no, lo descarga e instala.
	"""
	try:
		import server

		existing = server.find_binary("fpcalc")
	except Exception:
		existing = shutil.which("fpcalc") or shutil.which("fpcalc.exe")

	if existing:
		return existing

	installed = install_fpcalc(force=False, log_fn=log_fn)
	return str(installed) if installed else None


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(description="Instalador automático de fpcalc (Chromaprint)")
	parser.add_argument("target_dir", nargs="?", type=Path, default=None, help="Directorio destino de instalación")
	parser.add_argument("--force", action="store_true", help="Forzar reinstalación aunque ya exista")
	args = parser.parse_args()

	res = install_fpcalc(target_dir=args.target_dir, force=args.force)
	if res:
		print(f"fpcalc listo en: {res}")
		sys.exit(0)
	else:
		print("No se pudo instalar fpcalc.", file=sys.stderr)
		sys.exit(1)
