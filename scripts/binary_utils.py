"""
binary_utils.py — Utilidades compartidas para resolución de plataforma, arquitectura
y sanitización de entorno de ejecución en La Rockola del Carpincho.
"""

import asyncio
import glob
import os
import platform
import socket
import subprocess
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


def ensure_display_env(env: dict) -> None:
	"""
	Sincroniza dinámicamente variables de display y sesión gráfica (Wayland / X11 / DBus)
	cuando el servidor se ejecuta como servicio (ej. systemd --user) iniciado al arrancar el sistema
	antes del inicio de sesión del usuario.
	"""
	if sys.platform == "win32":
		return

	has_wayland = bool(env.get("WAYLAND_DISPLAY"))
	has_x11 = bool(env.get("DISPLAY"))
	if has_wayland and has_x11:
		return

	# 1. Consultar a systemd user manager
	try:
		res = subprocess.run(
			["systemctl", "--user", "show-environment"],
			capture_output=True,
			text=True,
			timeout=1.0,
			check=False,
		)
		if res.returncode == 0:
			for line in res.stdout.splitlines():
				if "=" in line:
					k, v = line.split("=", 1)
					k, v = k.strip(), v.strip()
					if (
						k
						in (
							"WAYLAND_DISPLAY",
							"DISPLAY",
							"XAUTHORITY",
							"XDG_RUNTIME_DIR",
							"XDG_SESSION_TYPE",
							"XDG_CURRENT_DESKTOP",
							"DBUS_SESSION_BUS_ADDRESS",
						)
						and v
					):
						if not env.get(k):
							env[k] = v
						if not os.environ.get(k):
							os.environ[k] = v
	except Exception:
		pass

	# 2. Reconciliar XDG_RUNTIME_DIR y DBUS
	uid = os.getuid() if hasattr(os, "getuid") else 1000
	runtime_dir = env.get("XDG_RUNTIME_DIR") or os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
	if os.path.isdir(runtime_dir):
		env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
		os.environ.setdefault("XDG_RUNTIME_DIR", runtime_dir)

		if not env.get("WAYLAND_DISPLAY"):
			for sock in sorted(glob.glob(os.path.join(runtime_dir, "wayland-[0-9]*"))):
				if not sock.endswith(".lock"):
					display_name = os.path.basename(sock)
					env["WAYLAND_DISPLAY"] = display_name
					os.environ["WAYLAND_DISPLAY"] = display_name
					break

		if not env.get("XAUTHORITY"):
			for auth in sorted(glob.glob(os.path.join(runtime_dir, "xauth_*"))):
				env["XAUTHORITY"] = auth
				os.environ["XAUTHORITY"] = auth
				break
			if not env.get("XAUTHORITY"):
				home_xauth = os.path.expanduser("~/.Xauthority")
				if os.path.exists(home_xauth):
					env["XAUTHORITY"] = home_xauth
					os.environ["XAUTHORITY"] = home_xauth

		if not env.get("DBUS_SESSION_BUS_ADDRESS"):
			bus_sock = os.path.join(runtime_dir, "bus")
			if os.path.exists(bus_sock):
				bus_addr = f"unix:path={bus_sock}"
				env["DBUS_SESSION_BUS_ADDRESS"] = bus_addr
				os.environ["DBUS_SESSION_BUS_ADDRESS"] = bus_addr

	# 3. Detectar servidor X11 si DISPLAY sigue faltando
	if not env.get("DISPLAY"):
		for xsock in sorted(glob.glob("/tmp/.X11-unix/X[0-9]*")):
			display_num = os.path.basename(xsock)[1:]
			env["DISPLAY"] = f":{display_num}"
			os.environ["DISPLAY"] = f":{display_num}"
			break


def get_clean_env() -> dict:
	"""
	Retorna una copia de os.environ con las variables alteradas por PyInstaller/AppImage
	restauradas a sus valores originales o eliminadas.
	Esto evita que herramientas del sistema como kdialog, zenity, yad, powershell, mpv,
	yt-dlp o el intérprete de python del sistema fallen por incompatibilidad de librerías dinámicas
	o rutas de python cargadas desde el bundle.
	"""
	env = os.environ.copy()
	for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "DYLD_LIBRARY_PATH"):
		orig = f"{var}_ORIG"
		if orig in env and env[orig].strip():
			env[var] = env[orig]
		elif var in env:
			del env[var]

	# Filtrar cualquier rastro de PyInstaller (_MEI*) o AppImage (/tmp/.mount_*) de LD_LIBRARY_PATH
	if "LD_LIBRARY_PATH" in env:
		parts = env["LD_LIBRARY_PATH"].split(":")
		clean_parts = []
		appdir = os.environ.get("APPDIR", "")
		meipass = getattr(sys, "_MEIPASS", "")
		for p in parts:
			p_str = p.strip()
			if not p_str:
				continue
			if meipass and p_str.startswith(str(meipass)):
				continue
			if appdir and p_str.startswith(str(appdir)):
				continue
			if ".mount_" in p_str or "_MEI" in p_str:
				continue
			clean_parts.append(p_str)

		if clean_parts:
			env["LD_LIBRARY_PATH"] = ":".join(clean_parts)
		else:
			del env["LD_LIBRARY_PATH"]

	ensure_display_env(env)

	return env


def is_internet_available(timeout: float = 0.8) -> bool:
	"""
	Comprueba puntualmente si hay conectividad a internet intentando abrir
	un socket TCP a servidores DNS públicos conocidos (Cloudflare y Google).
	"""
	endpoints = [("1.1.1.1", 53), ("8.8.8.8", 53)]
	for host, port in endpoints:
		try:
			with socket.create_connection((host, port), timeout=timeout):
				return True
		except (OSError, TimeoutError):
			continue

	return False


async def check_internet_async(timeout: float = 0.8) -> bool:
	"""Versión asíncrona de is_internet_available que ejecuta el sondeo en un hilo para no bloquear el bucle de eventos."""
	return await asyncio.to_thread(is_internet_available, timeout)
