#!/usr/bin/env python3
"""
Script de empaquetado para Android (Capacitor + Chaquopy 17.2 / Python 3.13).
Prepara el frontend compilado (`dist/`), copia el backend Python (`app/`)
al source set de Chaquopy, sincroniza Capacitor, compila APK/AAB con Gradle,
verifica alineamiento ELF 16 KB (0x4000) y genera checksums `.sha256`.

Uso:
    python3 scripts/build_android.py [--skip-frontend] [--sync-only] [--release] [--bundle] [--flavor arm64|x86_64]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
	sys.path.insert(0, str(_REPO_ROOT))

from scripts.verify_android_apk import verify_android_archive

IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")
SUPPORTED_FLAVORS = ("arm64", "x86_64")


def write_sha256_file(artifact_path: Path) -> Path:
	"""Genera archivo `<artefacto>.sha256` con digest SHA-256 estándar."""
	hasher = hashlib.sha256()
	with artifact_path.open("rb") as f:
		for chunk in iter(lambda: f.read(65536), b""):
			hasher.update(chunk)
	sha_path = Path(f"{artifact_path}.sha256")
	sha_path.write_text(f"{hasher.hexdigest()}  {artifact_path.name}\n", encoding="utf-8")
	return sha_path


def stage_android_assets(root_dir: Path) -> Path:
	"""Copia app/ hacia Chaquopy y limpia assets/dist redundante (Capacitor usa assets/public)."""
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

	fortunes_src = root_dir / "scripts" / "fortune-es"
	if fortunes_src.is_dir():
		fortunes_dest = py_dest / "domain" / "radio" / "fortune-es"
		shutil.copytree(fortunes_src, fortunes_dest, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

	# Capacitor ya copia dist/ a assets/public/; removemos assets/dist legado si quedó de antes
	stale_dist = android_dir / "app" / "src" / "main" / "assets" / "dist"
	if stale_dist.exists():
		shutil.rmtree(stale_dist)

	# Eliminamos carpeta wheels/ heredada del reetiquetado manual anterior
	legacy_wheels = android_dir / "app" / "wheels"
	if legacy_wheels.exists():
		shutil.rmtree(legacy_wheels)

	return py_dest


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


def ensure_jdk_env() -> None:
	"""Asegura que JAVA_HOME apunte a un JDK con javac (Java 21/17) y agrega ~/.local/bin al PATH."""
	local_bin = Path.home() / ".local" / "bin"
	if local_bin.is_dir():
		path_parts = os.environ.get("PATH", "").split(os.pathsep)
		if str(local_bin) not in path_parts:
			os.environ["PATH"] = f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}"
	if "JAVA_HOME" in os.environ and Path(os.environ["JAVA_HOME"], "bin", "javac").is_file():
		return
	for candidate in [Path("/usr/lib/jvm/java-21-openjdk"), Path("/usr/lib/jvm/java-17-openjdk")]:
		if (candidate / "bin" / "javac").is_file():
			os.environ["JAVA_HOME"] = str(candidate)
			os.environ["PATH"] = f"{candidate / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"
			return


def find_built_artifacts(android_dir: Path, release: bool, flavor: str | None, bundle: bool) -> list[Path]:
	"""Localiza los APK o AAB recién generados por Gradle para la variante solicitada."""
	variant_dir = "release" if release else "debug"
	base_dir = android_dir / "app" / "build" / "outputs" / ("bundle" if bundle else "apk")
	ext = ".aab" if bundle else ".apk"
	flavors = [flavor] if flavor else list(SUPPORTED_FLAVORS)

	found: list[Path] = []
	for flv in flavors:
		candidate_root = (
			base_dir / (f"{flv}Release" if release else f"{flv}Debug") if bundle else base_dir / flv / variant_dir
		)
		if not candidate_root.is_dir():
			continue
		for item in sorted(candidate_root.rglob(f"*{ext}")):
			if item.is_file() and not item.name.endswith("-androidTest.apk"):
				found.append(item)
	return found


def build_android(
	root_dir: Path | None = None,
	skip_frontend: bool = False,
	sync_only: bool = False,
	release: bool = False,
	flavor: str | None = None,
	bundle: bool = False,
) -> int:
	"""Orquesta compilación de frontend, staging de assets, cap sync, Gradle y verificación 16 KB."""
	base_dir = (root_dir or Path(__file__).resolve().parents[1]).resolve()
	npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
	npx_cmd = "npx.cmd" if os.name == "nt" else "npx"

	if not skip_frontend:
		print("🛠️ Compilando frontend con Vite...")
		subprocess.run([npm_cmd, "run", "build"], cwd=str(base_dir), check=True)

	print("📦 Copiando backend Python (app/) al proyecto Android...")
	py_dest = stage_android_assets(base_dir)
	print(f"   • Python -> {py_dest}")

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
			"   cd android && ./gradlew assembleArm64Debug"
		)
		return 0

	ensure_jdk_env()
	gradlew = android_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
	prefix = "bundle" if bundle else "assemble"
	variant = "Release" if release else "Debug"
	flavor_cap = f"{flavor[0].upper()}{flavor[1:]}" if flavor else ""
	task = f"{prefix}{flavor_cap}{variant}" if flavor_cap else f"{prefix}{variant}"
	print(f"🤖 Compilando artefacto Android con Gradle ({task})...")
	subprocess.run([str(gradlew), task], cwd=str(android_dir), check=True)

	artifacts = find_built_artifacts(android_dir, release=release, flavor=flavor, bundle=bundle)
	if not artifacts:
		raise RuntimeError(f"Gradle terminó {task} pero no encontré artefactos generados en build/outputs/.")

	for artifact in artifacts:
		res = verify_android_archive(artifact)
		if not res.ok:
			detail = "\n".join(f"  - {err}" for err in res.errors)
			raise RuntimeError(f"Falló la verificación ELF/16 KB en {artifact}:\n{detail}")
		sha_file = write_sha256_file(artifact)
		print(f"✅ {artifact.name}: {res.inspected_so_count} binarios .so OK (16 KB) · SHA-256 -> {sha_file.name}")

	return 0


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Prepara, compila y verifica el APK/AAB Android de La Rockola del Carpincho."
	)
	parser.add_argument("--skip-frontend", action="store_true", help="Omite 'npm run build' y usa dist/ actual.")
	parser.add_argument("--sync-only", action="store_true", help="Solo sincroniza Python/dist/Capacitor sin Gradle.")
	parser.add_argument("--release", action="store_true", help="Compila variante Release firmada obligatoriamente.")
	parser.add_argument("--bundle", action="store_true", help="Genera AAB (Android App Bundle) en vez de APK.")
	parser.add_argument(
		"--flavor",
		choices=list(SUPPORTED_FLAVORS),
		default=None,
		help="Flavour de arquitectura específica (ej. arm64 o x86_64).",
	)
	args = parser.parse_args()

	try:
		return build_android(
			skip_frontend=args.skip_frontend,
			sync_only=args.sync_only,
			release=args.release,
			flavor=args.flavor,
			bundle=args.bundle,
		)
	except Exception as exc:
		print(f"❌ Error preparando build Android: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
