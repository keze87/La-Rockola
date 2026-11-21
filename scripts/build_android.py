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
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")

ARCH_TO_ANDROID_TAG: dict[str, str] = {
	"linux_aarch64": "android_24_arm64_v8a",
	"linux_armv7l": "android_24_armeabi_v7a",
	"linux_x86_64": "android_24_x86_64",
}
PYDANTIC_CORE_VERSION = "2.46.3"
PYDANTIC_CORE_RELEASE_BASE = (
	f"https://github.com/Eutalix/android-pydantic-core/releases/download/v{PYDANTIC_CORE_VERSION}"
)


def _compute_record_digest(data: bytes) -> str:
	digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
	return f"sha256={digest},{len(data)}"


def retag_wheel_for_android(src_wheel: Path, dest_dir: Path) -> Path:
	"""Reetiqueta un wheel cp311 linux_* de Chaquopy/android-pydantic-core a android_24_*."""
	matched_pair = next(
		((src_tag, dst_tag) for src_tag, dst_tag in ARCH_TO_ANDROID_TAG.items() if src_tag in src_wheel.name),
		None,
	)
	if not matched_pair:
		raise ValueError(f"Wheel sin arquitectura soportada para Android: {src_wheel.name}")

	src_tag, dst_tag = matched_pair
	dest_dir.mkdir(parents=True, exist_ok=True)
	dest_wheel = dest_dir / src_wheel.name.replace(src_tag, dst_tag)

	new_wheel_bytes: bytes | None = None
	wheel_entry_name: str | None = None

	with (
		zipfile.ZipFile(src_wheel, "r") as zin,
		zipfile.ZipFile(dest_wheel, "w", compression=zipfile.ZIP_DEFLATED) as zout,
	):
		entries = zin.infolist()
		for info in entries:
			raw = zin.read(info.filename)
			if info.filename.endswith(".dist-info/WHEEL"):
				wheel_entry_name = info.filename
				text = raw.decode("utf-8").replace(src_tag, dst_tag)
				new_wheel_bytes = text.encode("utf-8")
				raw = new_wheel_bytes
			elif info.filename.endswith(".dist-info/RECORD"):
				continue
			zout.writestr(info, raw)

		# Recalculamos RECORD con el nuevo hash de WHEEL
		record_entry = next((i for i in entries if i.filename.endswith(".dist-info/RECORD")), None)
		if record_entry is not None and wheel_entry_name is not None and new_wheel_bytes is not None:
			new_digest = _compute_record_digest(new_wheel_bytes)
			lines = []
			for line in zin.read(record_entry.filename).decode("utf-8").splitlines():
				if line.startswith(f"{wheel_entry_name},"):
					lines.append(f"{wheel_entry_name},{new_digest}")
				else:
					lines.append(line)
			zout.writestr(record_entry, ("\n".join(lines) + "\n").encode("utf-8"))

	return dest_wheel


def ensure_android_pydantic_wheels(android_dir: Path) -> Path:
	"""Descarga y reetiqueta los wheels cp311 de pydantic_core si faltan en android/app/wheels/."""
	wheels_dir = android_dir / "app" / "wheels"
	wheels_dir.mkdir(parents=True, exist_ok=True)

	missing = [
		(src_tag, dst_tag)
		for src_tag, dst_tag in ARCH_TO_ANDROID_TAG.items()
		if not (wheels_dir / f"pydantic_core-{PYDANTIC_CORE_VERSION}-cp311-cp311-{dst_tag}.whl").is_file()
	]
	if not missing:
		return wheels_dir

	with tempfile.TemporaryDirectory(prefix="rockola_wheels_") as tmp_dir:
		tmp_path = Path(tmp_dir)
		for src_tag, _dst_tag in missing:
			whl_name = f"pydantic_core-{PYDANTIC_CORE_VERSION}-cp311-cp311-{src_tag}.whl"
			url = f"{PYDANTIC_CORE_RELEASE_BASE}/{whl_name}"
			downloaded = tmp_path / whl_name
			print(f"⬇️ Descargando wheel Android: {whl_name}...")
			urllib.request.urlretrieve(url, downloaded)
			out = retag_wheel_for_android(downloaded, wheels_dir)
			print(f"   • Reetiquetado -> {out.name}")

	return wheels_dir


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

	# Capacitor ya copia dist/ a assets/public/; removemos assets/dist legado si quedó de antes
	stale_dist = android_dir / "app" / "src" / "main" / "assets" / "dist"
	if stale_dist.exists():
		shutil.rmtree(stale_dist)

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

	print("📦 Copiando backend Python (app/) al proyecto Android...")
	py_dest = stage_android_assets(base_dir)
	print(f"   • Python -> {py_dest}")

	print("🔄 Sincronizando Capacitor (npx cap sync android)...")
	subprocess.run([npx_cmd, "cap", "sync", "android"], cwd=str(base_dir), check=True)

	if sync_only:
		print("✅ ¡Joyita! Sincronización Android terminada (--sync-only).")
		return 0

	android_dir = base_dir / "android"
	ensure_android_pydantic_wheels(android_dir)

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
