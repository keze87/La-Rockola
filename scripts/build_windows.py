#!/usr/bin/env python3
"""
scripts/build_windows.py — Generador de versión portable de La Rockola del Carpincho para Windows.

Compila el frontend (Vite/Vue3), empaqueta el backend (FastAPI) junto con los assets
estáticos en un ejecutable independiente (larockola.exe) y genera un archivo ZIP listo para distribuir.
Funciona tanto en Windows nativo como en Linux (a través de Wine).
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
PUBLIC_DIR = ROOT_DIR / "public"
SCRIPTS_DIR = ROOT_DIR / "scripts"
RELEASE_DIR = ROOT_DIR / "release"
SPEC_FILE = ROOT_DIR / "larockola.spec"


def log(msg: str):
	print(f"[build] {msg}")


def ensure_icon():
	ico_path = PUBLIC_DIR / "favicon.ico"
	png_path = PUBLIC_DIR / "favicon.png"
	if not ico_path.exists() and png_path.exists():
		log("Generando favicon.ico a partir de favicon.png...")
		try:
			from PIL import Image

			img = Image.open(png_path)
			img.save(ico_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
			log("Icono generado con éxito.")
		except Exception as e:
			log(f"No se pudo generar .ico con Pillow: {e}")


def build_frontend(force=False):
	index_html = DIST_DIR / "index.html"
	if not index_html.exists() or force:
		log("Compilando el frontend de Vue 3 (npm run build)...")
		npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
		subprocess.run([npm_cmd, "run", "build"], cwd=str(ROOT_DIR), check=True)
		log("Frontend compilado con éxito en dist/")
	else:
		log("Frontend ya compilado en dist/. (Usá --rebuild-frontend para forzar)")


def run_pyinstaller():
	log("Ejecutando PyInstaller para crear larockola.exe...")
	is_win = sys.platform == "win32" or os.name == "nt"

	build_dir = ROOT_DIR / "build"
	dist_exe_dir = ROOT_DIR / "dist_bin"

	if is_win:
		cmd = [
			sys.executable,
			"-m",
			"PyInstaller",
			"--noconfirm",
			"--workpath",
			str(build_dir),
			"--distpath",
			str(dist_exe_dir),
			str(SPEC_FILE),
		]
		env = os.environ.copy()
	else:
		# En Linux usamos Wine
		wine_bin = shutil.which("wine")
		if not wine_bin:
			print("Error: No se encontró 'wine' para compilar el ejecutable de Windows en Linux.", file=sys.stderr)
			sys.exit(1)
		cmd = [
			"wine",
			"pyinstaller",
			"--noconfirm",
			"--workpath",
			str(build_dir),
			"--distpath",
			str(dist_exe_dir),
			str(SPEC_FILE),
		]
		env = os.environ.copy()
		env["WINEDEBUG"] = "-all"

	res = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env, check=False)

	exe_path = dist_exe_dir / "larockola.exe"
	if not exe_path.exists():
		alt_path = dist_exe_dir / "larockola"
		if alt_path.exists():
			shutil.move(alt_path, exe_path)

	if not exe_path.exists():
		print(f"Error: No se encontró el ejecutable en {exe_path} (código de salida: {res.returncode})", file=sys.stderr)
		sys.exit(1)

	log(f"Ejecutable Windows generado correctamente: {exe_path} ({exe_path.stat().st_size / (1024*1024):.1f} MB)")
	return exe_path


def ensure_release_mpv(package_dir: Path, skip_mpv: bool = False):
	"""Asegura que mpv.exe (y sus dependencias) estén en package_dir / 'mpv'."""
	if skip_mpv or os.environ.get("ROCKOLA_SKIP_MPV_DOWNLOAD") == "1":
		log("Omitiendo inclusión de MPV (--skip-mpv activado).")
		return

	mpv_target_dir = package_dir / "mpv"
	if (mpv_target_dir / "mpv.exe").is_file() or (package_dir / "mpv.exe").is_file():
		log("MPV ya se encuentra presente en el paquete.")
		return

	# Revisar caché local en dist_bin/mpv
	cache_dir = ROOT_DIR / "dist_bin" / "mpv"
	if (cache_dir / "mpv.exe").is_file():
		log(f"Copiando MPV desde caché local ({cache_dir})...")
		shutil.copytree(cache_dir, mpv_target_dir, dirs_exist_ok=True)
		return

	# Si no está en caché, descargarlo con mpv_installer
	log("MPV no encontrado localmente. Intentando descargar la versión más reciente desde GitHub...")
	if str(ROOT_DIR) not in sys.path:
		sys.path.insert(0, str(ROOT_DIR))
	try:
		import mpv_installer

		installed = mpv_installer.install_mpv(
			target_dir=mpv_target_dir,
			platform_name="windows",
			arch="x86_64",
			log_fn=log,
		)
		if installed and (mpv_target_dir / "mpv.exe").is_file():
			log(f"MPV empaquetado correctamente en {mpv_target_dir}.")
			# Guardar copia en caché local para acelerar builds futuros
			try:
				cache_dir.parent.mkdir(parents=True, exist_ok=True)
				shutil.copytree(mpv_target_dir, cache_dir, dirs_exist_ok=True)
			except Exception as e:
				log(f"No se pudo cachear MPV en dist_bin/mpv: {e}")
		else:
			log("ADVERTENCIA: No se pudo descargar MPV durante el armado del release. El usuario podrá autoinstalarlo al iniciar.")
	except Exception as e:
		log(f"ADVERTENCIA: Error al intentar descargar MPV: {e}")


def create_release_package(exe_path: Path, skip_mpv: bool = False):
	log("Preparando paquete de distribución en carpeta release/...")
	RELEASE_DIR.mkdir(parents=True, exist_ok=True)
	package_dir = RELEASE_DIR / "larockola-windows-x86_64"
	if package_dir.exists():
		shutil.rmtree(package_dir)
	package_dir.mkdir()

	# Copiar ejecutable principal
	shutil.copy2(exe_path, package_dir / "larockola.exe")

	# Asegurar MPV en el paquete release
	ensure_release_mpv(package_dir, skip_mpv=skip_mpv)

	# Crear carpeta DB local para modo portable
	(package_dir / "DB").mkdir(exist_ok=True)

	# Crear LEEME instructivo
	readme_content = """============================================================
           🦫 LA ROCKOLA DEL CARPINCHO - WINDOWS PORTABLE
============================================================

¡Bienvenido a La Rockola del Carpincho!
Este paquete es 100% portable y no requiere instalación previa.

CÓMO USAR:
1. Hacé doble clic en 'iniciar_rockola.bat' (o ejecutá 'larockola.exe').
2. La primera vez que lo abras, un asistente interactivo en la consola te
   permitirá seleccionar la carpeta donde tenés tu música.
3. Tus opciones quedan guardadas automáticamente en 'rockola_config.json'
   para que en las próximas ejecuciones arranque al toque sin preguntar nada.
4. Para cambiar la configuración más adelante, podés editar 'rockola_config.json'
   directamente con el Bloc de notas o ejecutar 'larockola.exe --setup'.
5. Abrí la dirección en tu navegador (ej. http://localhost:1729).
6. Para controlar la música desde tu celular, conectate a la misma red Wi-Fi
   e ingresá a la IP que figura en la consola (o escaneá el código QR en la app).

REQUISITOS DEL SISTEMA:
- MPV Media Player:
  ¡Ya viene incluido en la carpeta 'mpv/'! No necesitás instalar nada.
  (Si alguna vez lo eliminás, La Rockola intentará descargarlo automáticamente
  o podés instalarlo en tu sistema con: winget install mpv).

- YT-DLP (Opcional):
  Si querés reproducir temas desde YouTube / Internet, podés pegar 'yt-dlp.exe'
  junto a larockola.exe o instalarlo con: winget install yt-dlp

DATOS Y CONFIGURACIÓN:
- Configuración: Se almacena en 'rockola_config.json'.
- Base de datos: El historial, favoritos y análisis acústico se guardan
  en la carpeta 'DB/' de este mismo directorio de manera 100% portable.

¡Que disfrutes de la música y unos buenos mates! 🧉🦦
"""
	(package_dir / "LEEME.txt").write_text(readme_content, encoding="utf-8")

	# Script bat de inicio rápido
	bat_content = """@echo off
title La Rockola del Carpincho
echo ========================================
echo   Iniciando La Rockola del Carpincho...
echo ========================================
larockola.exe %*
pause
"""
	(package_dir / "iniciar_rockola.bat").write_text(bat_content, encoding="utf-8")

	# Comprimir en zip
	zip_path = RELEASE_DIR / "larockola-windows-x86_64.zip"
	log(f"Comprimiendo {zip_path.name}...")
	with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
		for item in package_dir.rglob("*"):
			arcname = item.relative_to(package_dir)
			zf.write(item, arcname)

	log(f"Paquete de lanzamiento listo: {zip_path} ({zip_path.stat().st_size / (1024*1024):.1f} MB)")


def main():
	parser = argparse.ArgumentParser(description="Compila la versión portable de La Rockola para Windows")
	parser.add_argument("--rebuild-frontend", action="store_true", help="Fuerza la recompilación del frontend con Vite")
	parser.add_argument("--clean", action="store_true", help="Limpia temporales antes de compilar")
	parser.add_argument("--skip-mpv", action="store_true", help="No incluye ni descarga MPV en el paquete de distribución")
	args = parser.parse_args()

	if args.clean:
		log("Limpiando carpetas de compilación anteriores...")
		for p in [ROOT_DIR / "build", ROOT_DIR / "dist_bin"]:
			if p.exists():
				shutil.rmtree(p)

	ensure_icon()
	build_frontend(force=args.rebuild_frontend)
	exe_path = run_pyinstaller()
	create_release_package(exe_path, skip_mpv=args.skip_mpv)
	log("Proceso finalizado con éxito.")


if __name__ == "__main__":
	main()
