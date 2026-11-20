#!/usr/bin/env python3
"""
Script de empaquetado para Android (Capacitor + Chaquopy).
Prepara el frontend compilado (`dist/`), copia el backend Python (`app/`)
al source set de Chaquopy, sincroniza Capacitor y opcionalmente compila el APK con Gradle.

Uso:
    python3 scripts/build_android.py [--skip-frontend] [--sync-only] [--release]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")


def stage_android_assets(root_dir: Path) -> tuple[Path, Path]:
	"""Copia app/ hacia Chaquopy y dist/ hacia assets/dist dentro del proyecto android/."""
	android_dir = root_dir / "android"
	if not android_dir.is_dir():
		raise FileNotFoundError("No existe la carpeta 'android/'. Ejecutá 'npx cap add android' primero, fiera.")

	app_src = root_dir / "app"
	dist_src = root_dir / "dist"
	if not (dist_src / "index.html").is_file():
		raise FileNotFoundError(
			"Falta 'dist/index.html'. Compilá el frontend con 'npm run build' o quitá '--skip-frontend'."
		)

	py_dest = android_dir / "app" / "src" / "main" / "python" / "app"
	if py_dest.exists():
		shutil.rmtree(py_dest)
	py_dest.parent.mkdir(parents=True, exist_ok=True)
	shutil.copytree(app_src, py_dest, ignore=IGNORE_PATTERNS)

	dist_dest = android_dir / "app" / "src" / "main" / "assets" / "dist"
	if dist_dest.exists():
		shutil.rmtree(dist_dest)
	dist_dest.parent.mkdir(parents=True, exist_ok=True)
	shutil.copytree(dist_src, dist_dest, ignore=IGNORE_PATTERNS)

	return py_dest, dist_dest


def has_android_sdk(android_dir: Path) -> bool:
	"""Verifica si hay un Android SDK configurado mediante entorno o local.properties."""
	for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
		val = os.environ.get(env_var, "").strip()
		if val and Path(val).is_dir():
			return True

	local_props = android_dir / "local.properties"
	if local_props.is_file():
		content = local_props.read_text(encoding="utf-8", errors="ignore")
		if "sdk.dir=" in content:
			return True

	default_sdk = Path.home() / "Android" / "Sdk"
	return default_sdk.is_dir()


def build_android(
	root_dir: Path | None = None,
	skip_frontend: bool = False,
	sync_only: bool = False,
	release: bool = False,
) -> int:
	"""Orquesta compilación de frontend, staging de assets, cap sync y Gradle."""
	base_dir = (root_dir or Path(__file__).resolve().parents[1]).resolve()
	npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
	npx_cmd = "npx.cmd" if os.name == "nt" else "npx"

	if not skip_frontend:
		print("🛠️ Compilando frontend con Vite...")
		subprocess.run([npm_cmd, "run", "build"], cwd=str(base_dir), check=True)

	print("📦 Copiando backend Python (app/) y assets web (dist/) al proyecto Android...")
	py_dest, dist_dest = stage_android_assets(base_dir)
	print(f"   • Python -> {py_dest}")
	print(f"   • Dist   -> {dist_dest}")

	print("🔄 Sincronizando Capacitor (npx cap sync android)...")
	subprocess.run([npx_cmd, "cap", "sync", "android"], cwd=str(base_dir), check=True)

	if sync_only:
		print("✅ ¡Joyita! Sincronización Android terminada (--sync-only).")
		return 0

	android_dir = base_dir / "android"
	if not has_android_sdk(android_dir):
		print(
			"⚠️ Ojo al piojo: no detecté ANDROID_HOME / ANDROID_SDK_ROOT ni android/local.properties.\n"
			"   Los assets de Python y Vue ya quedaron sincronizados en android/.\n"
			"   Para generar el APK, abrí la carpeta 'android/' en Android Studio o exportá ANDROID_HOME y corré:\n"
			"   cd android && ./gradlew assembleDebug"
		)
		return 0

	gradlew = android_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
	task = "assembleRelease" if release else "assembleDebug"
	print(f"🤖 Compilando APK con Gradle ({task})...")
	subprocess.run([str(gradlew), task], cwd=str(android_dir), check=True)
	print("✅ ¡APK compilado con éxito! Revisá android/app/build/outputs/apk/")
	return 0


def main() -> int:
	parser = argparse.ArgumentParser(description="Prepara y compila el APK Android de La Rockola del Carpincho.")
	parser.add_argument("--skip-frontend", action="store_true", help="Omite 'npm run build' y usa dist/ actual.")
	parser.add_argument("--sync-only", action="store_true", help="Solo sincroniza Python/dist/Capacitor sin Gradle.")
	parser.add_argument("--release", action="store_true", help="Compila assembleRelease en vez de assembleDebug.")
	args = parser.parse_args()

	try:
		return build_android(
			skip_frontend=args.skip_frontend,
			sync_only=args.sync_only,
			release=args.release,
		)
	except Exception as exc:
		print(f"❌ Error preparando build Android: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
