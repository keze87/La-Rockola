#!/usr/bin/env python3
"""
scripts/build_appimage.py — Generador de AppImage para La Rockola del Carpincho en Linux.

Compila el frontend (Vite/Vue3), empaqueta el backend (FastAPI) con PyInstaller en un
ejecutable ELF nativo, ensambla la estructura estándar de AppDir y genera el archivo
LaRockola-x86_64.AppImage listo para distribuir en cualquier distribución Linux.
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
PUBLIC_DIR = ROOT_DIR / "public"
SCRIPTS_DIR = ROOT_DIR / "scripts"
BUILD_DIR = ROOT_DIR / "build"
DIST_BIN_DIR = ROOT_DIR / "dist_bin"
RELEASE_DIR = ROOT_DIR / "release"
SPEC_FILE = ROOT_DIR / "larockola.spec"
DESKTOP_FILE = SCRIPTS_DIR / "larockola.desktop"
APPDIR_PATH = BUILD_DIR / "LaRockola.AppDir"

APPIMAGETOOL_URLS = [
	"https://github.com/AppImage/appimagetool/releases/latest/download/appimagetool-x86_64.AppImage",
	"https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage",
]


def log(msg: str):
	print(f"[build-appimage] {msg}")


def build_frontend(force=False):
	index_html = DIST_DIR / "index.html"
	if not index_html.exists() or force:
		log("Compilando el frontend de Vue 3 (npm run build)...")
		npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
		subprocess.run([npm_cmd, "run", "build"], cwd=str(ROOT_DIR), check=True)
		log("Frontend compilado con éxito en dist/")
	else:
		log("Frontend ya compilado en dist/. (Usá --rebuild-frontend para forzar)")


def run_pyinstaller(skip=False) -> Path:
	exe_path = DIST_BIN_DIR / "larockola"
	if skip and exe_path.exists():
		log(f"Usando ejecutable compilado existente: {exe_path}")
		return exe_path

	log("Ejecutando PyInstaller para compilar el ejecutable Linux...")
	pyinstaller_bin = shutil.which("pyinstaller")
	if pyinstaller_bin:
		cmd = [
			pyinstaller_bin,
			"--noconfirm",
			"--workpath",
			str(BUILD_DIR),
			"--distpath",
			str(DIST_BIN_DIR),
			str(SPEC_FILE),
		]
	else:
		cmd = [
			sys.executable,
			"-m",
			"PyInstaller",
			"--noconfirm",
			"--workpath",
			str(BUILD_DIR),
			"--distpath",
			str(DIST_BIN_DIR),
			str(SPEC_FILE),
		]
	env = os.environ.copy()
	res = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env, check=False)

	if not exe_path.exists():
		print(f"Error: No se encontró el ejecutable en {exe_path} (código de salida: {res.returncode})", file=sys.stderr)
		sys.exit(1)

	log(f"Ejecutable Linux generado con éxito: {exe_path} ({exe_path.stat().st_size / (1024*1024):.1f} MB)")
	return exe_path


def create_appdir(binary_path: Path, appdir: Path = APPDIR_PATH) -> Path:
	log(f"Creando estructura AppDir en {appdir}...")
	if appdir.exists():
		shutil.rmtree(appdir)

	# Directorios estándar de AppDir
	bin_dir = appdir / "usr" / "bin"
	apps_dir = appdir / "usr" / "share" / "applications"
	icons_base = appdir / "usr" / "share" / "icons" / "hicolor"

	bin_dir.mkdir(parents=True, exist_ok=True)
	apps_dir.mkdir(parents=True, exist_ok=True)

	# 1. Copiar ejecutable principal
	dest_bin = bin_dir / "larockola"
	shutil.copy2(binary_path, dest_bin)
	dest_bin.chmod(dest_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

	# 2. Crear script AppRun
	apprun_path = appdir / "AppRun"
	apprun_content = """#!/bin/sh
set -e
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

exec "${HERE}/usr/bin/larockola" "$@"
"""
	apprun_path.write_text(apprun_content, encoding="utf-8")
	apprun_path.chmod(apprun_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

	# 3. Copiar archivo .desktop
	if not DESKTOP_FILE.exists():
		desktop_content = """[Desktop Entry]
Type=Application
Name=La Rockola del Carpincho
GenericName=Music Player & Server
Comment=Reproductor y servidor de música con alma de campo y sabor a mate
Exec=larockola %F
Icon=larockola
Terminal=true
Categories=AudioVideo;Audio;Player;
Keywords=music;audio;player;carpincho;rockola;mate;
StartupWMClass=larockola
"""
		DESKTOP_FILE.write_text(desktop_content, encoding="utf-8")

	shutil.copy2(DESKTOP_FILE, appdir / "larockola.desktop")
	shutil.copy2(DESKTOP_FILE, apps_dir / "larockola.desktop")

	# 4. Copiar y dimensionar iconos
	png_source = PUBLIC_DIR / "favicon.png"
	if png_source.exists():
		shutil.copy2(png_source, appdir / "larockola.png")

		# Guardar en hicolor 256x256
		icon_256 = icons_base / "256x256" / "apps"
		icon_256.mkdir(parents=True, exist_ok=True)
		shutil.copy2(png_source, icon_256 / "larockola.png")

		# Si Pillow está instalado, generar tamaños adicionales
		try:
			from PIL import Image

			img = Image.open(png_source)
			for size in (128, 64, 48, 32, 16):
				size_dir = icons_base / f"{size}x{size}" / "apps"
				size_dir.mkdir(parents=True, exist_ok=True)
				resized = img.resize((size, size), Image.Resampling.LANCZOS)
				resized.save(size_dir / "larockola.png")
		except Exception as e:
			log(f"Aviso al redimensionar iconos: {e}")

	log(f"Estructura AppDir completada exitosamente en {appdir}")
	return appdir


def ensure_appimagetool() -> Path:
	"""Localiza appimagetool en el sistema o lo descarga automáticamente."""
	# 1. Probar si ya está en PATH
	tool_path = shutil.which("appimagetool")
	if tool_path:
		return Path(tool_path)

	# 2. Probar si ya lo tenemos descargado en build/tools
	tools_dir = BUILD_DIR / "tools"
	tools_dir.mkdir(parents=True, exist_ok=True)
	local_tool = tools_dir / "appimagetool"

	if local_tool.exists() and local_tool.stat().st_size > 0:
		return local_tool

	# 3. Descargar appimagetool desde GitHub
	log("appimagetool no encontrado en PATH. Descargando versión oficial...")
	headers = {"User-Agent": "LaRockola-AppImage-Builder/1.0"}

	for url in APPIMAGETOOL_URLS:
		try:
			log(f"Descargando desde {url}...")
			req = urllib.request.Request(url, headers=headers)
			with urllib.request.urlopen(req, timeout=30) as resp, open(local_tool, "wb") as f:
				shutil.copyfileobj(resp, f)

			if local_tool.exists() and local_tool.stat().st_size > 1024 * 1024:
				local_tool.chmod(local_tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
				log(f"appimagetool descargado con éxito en {local_tool}")
				return local_tool
		except Exception as e:
			log(f"Falló la descarga desde {url}: {e}")

	raise RuntimeError("No se pudo obtener appimagetool para empaquetar el AppImage.")


def build_appimage(appdir: Path = APPDIR_PATH, output_path: Path | None = None) -> Path:
	"""Empaqueta el AppDir en un archivo ejecutable .AppImage usando appimagetool."""
	RELEASE_DIR.mkdir(parents=True, exist_ok=True)
	final_output = output_path if output_path else RELEASE_DIR / "LaRockola-x86_64.AppImage"

	tool_bin = ensure_appimagetool()
	log(f"Generando AppImage con {tool_bin.name}...")

	env = os.environ.copy()
	env["ARCH"] = "x86_64"
	# Evitar dependencia de libfuse2 en entornos CI o sistemas sin FUSE
	env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
	env["NO_STRIP"] = "1"

	cmd = [str(tool_bin), str(appdir), str(final_output)]

	res = subprocess.run(cmd, env=env, check=False)
	if res.returncode != 0:
		# Fallback con flag explícito --appimage-extract-and-run
		cmd_fallback = [str(tool_bin), "--appimage-extract-and-run", str(appdir), str(final_output)]
		res = subprocess.run(cmd_fallback, env=env, check=False)

	if not final_output.exists() or final_output.stat().st_size == 0:
		print(f"Error: Falló la creación del AppImage en {final_output} (código: {res.returncode})", file=sys.stderr)
		sys.exit(1)

	final_output.chmod(final_output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
	log(f"¡AppImage generado exitosamente!: {final_output} ({final_output.stat().st_size / (1024*1024):.1f} MB)")
	return final_output


def main():
	parser = argparse.ArgumentParser(description="Compila el paquete Linux AppImage de La Rockola del Carpincho")
	parser.add_argument("--rebuild-frontend", action="store_true", help="Fuerza la recompilación del frontend con Vite")
	parser.add_argument("--clean", action="store_true", help="Limpia temporales antes de compilar")
	parser.add_argument("--no-appimage", action="store_true", help="Solo genera el AppDir sin crear el archivo .AppImage")
	parser.add_argument("--skip-pyinstaller", action="store_true", help="Usa el ejecutable existente en dist_bin/ si ya está compilado")
	args = parser.parse_args()

	if args.clean:
		log("Limpiando carpetas de compilación anteriores...")
		for p in [BUILD_DIR, DIST_BIN_DIR]:
			if p.exists():
				shutil.rmtree(p)

	build_frontend(force=args.rebuild_frontend)
	exe_path = run_pyinstaller(skip=args.skip_pyinstaller)
	appdir = create_appdir(exe_path)

	if not args.no_appimage:
		build_appimage(appdir)
	else:
		log(f"AppDir listo para inspección en: {appdir}")

	log("Proceso finalizado con éxito.")


if __name__ == "__main__":
	main()
