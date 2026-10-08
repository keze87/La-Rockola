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
	from . import binary_utils
	from .binary_utils import resolve_platform_and_arch
except (ImportError, ValueError):
	import binary_utils
	from binary_utils import resolve_platform_and_arch


def _build_fallback_assets(tag: str) -> list[dict]:
	"""Construye la lista de assets de fallback para un tag de chromaprint."""
	ver = tag.lstrip("vV")
	return [
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


def fetch_release_info(timeout: int = 10, log_fn=default_logger) -> dict:
	"""
	Obtiene metadatos del último lanzamiento de chromaprint en GitHub.
	Intenta primero vía GitHub REST API y, si falla (ej. rate limit),
	hace fallback siguiendo la redirección HTTP 302 de la URL web para obtener el tag.
	"""
	res = binary_utils.fetch_github_release_assets(
		api_url=GITHUB_API_LATEST,
		html_url=GITHUB_HTML_LATEST,
		user_agent=USER_AGENT,
		fallback_builder=_build_fallback_assets,
		timeout=timeout,
		log_fn=log_fn,
	)
	if not res.get("assets"):
		raise RuntimeError("No se pudo obtener información de lanzamientos de fpcalc desde GitHub.")
	return res


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
	binary_utils.download_file(url, dest_path, log_fn=log_fn, user_agent=USER_AGENT)


def extract_fpcalc_archive(archive_path: Path, dest_dir: Path, log_fn=default_logger) -> bool:
	"""
	Extrae fpcalc desde un archivo .zip o .tar.gz a dest_dir,
	colocando el ejecutable directamente en dest_dir.
	"""
	targets = {"fpcalc.exe", "fpcalc"}
	extracted = binary_utils.extract_archive_binary(
		archive_path=archive_path,
		dest_dir=dest_dir,
		target_names=targets,
		log_fn=log_fn,
	)
	return extracted or (dest_dir / "fpcalc.exe").is_file() or (dest_dir / "fpcalc").is_file()


def get_default_install_dir() -> Path:
	"""Determina el directorio por defecto donde instalar fpcalc."""
	return binary_utils.get_default_install_dir("fpcalc")


def is_rockola_managed(bin_path: str | Path) -> bool:
	"""Verifica si el binario de fpcalc fue gestionado por La Rockola."""
	return binary_utils.is_rockola_managed(bin_path, "fpcalc")


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
		info = fetch_release_info(log_fn=log_fn)
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
				binary_utils.mark_rockola_managed(dest_dir, "fpcalc", log_fn=log_fn)
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
