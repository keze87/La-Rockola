"""
binary_utils.py — Utilidades compartidas para resolución de plataforma, arquitectura
y sanitización de entorno de ejecución en La Rockola del Carpincho.
"""

import os
import platform
import sys


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


def get_clean_env() -> dict:
	"""
	Retorna una copia de os.environ con las variables alteradas por PyInstaller/AppImage
	restauradas a sus valores originales o eliminadas.
	"""
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
