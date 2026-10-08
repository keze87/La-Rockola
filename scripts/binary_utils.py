"""
binary_utils.py — Utilidades compartidas para resolución de plataforma, arquitectura
y sanitización de entorno de ejecución en La Rockola del Carpincho.
"""

import asyncio
import glob
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path


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
	except (FileNotFoundError, subprocess.SubprocessError, OSError):
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


def download_file(
	url: str,
	dest_path: Path,
	log_fn=None,
	user_agent: str = "LaRockola-Installer/1.0",
	timeout: int = 30,
) -> None:
	"""Descarga un archivo con reporte de progreso unificado."""
	headers = {"User-Agent": user_agent}
	req = urllib.request.Request(url, headers=headers)
	dest_path.parent.mkdir(parents=True, exist_ok=True)

	with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as out_f:
		total_size = int(resp.headers.get("Content-Length", 0))
		downloaded = 0
		last_percent = -1
		chunk_size = 1024 * 1024

		while True:
			chunk = resp.read(chunk_size)
			if not chunk:
				break
			out_f.write(chunk)
			downloaded += len(chunk)
			if total_size > 0 and log_fn:
				percent = int(downloaded * 100 / total_size)
				if percent >= last_percent + 5 or percent == 100:
					log_fn(
						f"Descargando: {percent}% ({downloaded // (1024 * 1024)}MB / {total_size // (1024 * 1024)}MB)"
					)
					last_percent = percent


def is_rockola_managed(bin_path: str | Path, tool_name: str | None = None) -> bool:
	"""
	Verifica si un binario fue descargado o gestionado por La Rockola.
	Evita tocar o actualizar binarios gestionados por el sistema operativo.
	"""
	path = Path(bin_path).resolve()
	parent = path if path.is_dir() else path.parent

	if tool_name:
		if (parent / f".rockola_managed_{tool_name}").is_file():
			return True
	else:
		# Check any rockola marker file
		if list(parent.glob(".rockola_managed_*")):
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
	except (ImportError, AttributeError, ValueError):
		pass

	return False


def get_default_install_dir(tool_name: str = "mpv") -> Path:
	"""Determina el directorio por defecto donde instalar un binario o herramienta."""
	if tool_name != "mpv":
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
		except (ImportError, AttributeError, OSError):
			pass

	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

	# Probar si el directorio base es escribible (modo portable)
	try:
		test_file = base / ".carpincho_write_test"
		test_file.touch(exist_ok=True)
		test_file.unlink(missing_ok=True)
		if (base / "mpv").is_dir():
			return base / "mpv"
		if (base / "bin").is_dir():
			return base / "bin"
		return base / "mpv" if tool_name == "mpv" else base
	except OSError:
		pass

	# Si es de solo lectura (ej. AppDir o C:\Program Files), recurrir al directorio de datos del usuario
	if sys.platform == "win32":
		app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
	elif sys.platform == "darwin":
		app_data = Path.home() / "Library" / "Application Support"
	else:
		app_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

	return app_data / "carpincho" / (tool_name if tool_name == "mpv" else "bin")


def build_frontend(root_dir: Path | None = None, force: bool = False, log_fn=None) -> None:
	"""Compila el frontend de Vue 3 (npm run build) de forma unificada para los scripts de empaquetado."""
	root = root_dir or Path(__file__).resolve().parent.parent
	dist_dir = root / "dist"
	index_html = dist_dir / "index.html"

	if not index_html.exists() or force:
		if log_fn:
			log_fn("Compilando el frontend de Vue 3 (npm run build)...")
		npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
		subprocess.run([npm_cmd, "run", "build"], cwd=str(root), check=True)
		if log_fn:
			log_fn("Frontend compilado con éxito en dist/")
	else:
		if log_fn:
			log_fn("Frontend ya compilado en dist/. (Usá --rebuild-frontend para forzar)")


def fetch_github_release_assets(
	api_url: str,
	html_url: str,
	user_agent: str,
	fallback_builder: Callable[[str], list[dict]] | None = None,
	timeout: int = 10,
	log_fn: Callable[[str], None] | None = None,
) -> dict:
	"""
	Obtiene metadatos y lista de assets del último release de GitHub.
	Intenta primero vía GitHub REST API; ante fallos (por ej. rate limit 403),
	hace fallback siguiendo la redirección del HTML del release si hay un builder provisto.
	"""
	headers = {
		"User-Agent": user_agent,
		"Accept": "application/vnd.github.v3+json",
	}

	# 1. GitHub REST API
	try:
		req = urllib.request.Request(api_url, headers=headers)
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			data = json.loads(resp.read().decode("utf-8"))
			tag = data.get("tag_name", "latest")
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
	except Exception as exc:
		if log_fn:
			log_fn(f"GitHub API falló al consultar {api_url}: {exc}. Intentando fallback HTML...")

	# 2. Fallback vía URL HTML de releases
	if fallback_builder:
		try:
			req2 = urllib.request.Request(html_url, headers={"User-Agent": user_agent})
			with urllib.request.urlopen(req2, timeout=timeout) as resp2:
				final_url = resp2.geturl()
				tag = final_url.rstrip("/").split("/")[-1]
				if tag and not tag.lower().startswith("latest"):
					assets = fallback_builder(tag)
					if assets:
						return {"tag": tag, "assets": assets}
		except Exception as exc:
			if log_fn:
				log_fn(f"Fallback HTML falló al consultar {html_url}: {exc}")

	return {"tag": "", "assets": []}


def extract_archive_binary(
	archive_path: Path,
	dest_dir: Path,
	target_names: Iterable[str],
	log_fn: Callable[[str], None] | None = None,
) -> bool:
	"""
	Extrae binarios específicos desde un archivo (.zip, .tar.gz, .tar.xz, .tar) hacia dest_dir.
	Aplica protección Zip Slip y restaura permisos de ejecución (0o755) en sistemas POSIX.
	"""
	dest_dir = dest_dir.resolve()
	dest_dir.mkdir(parents=True, exist_ok=True)
	archive_name = archive_path.name.lower()
	targets_normalized = {name.lower() for name in target_names}
	extracted = False

	if archive_name.endswith(".zip"):
		with zipfile.ZipFile(archive_path, "r") as zf:
			for member in zf.infolist():
				member_path = Path(member.filename)
				name_lower = member_path.name.lower()
				if name_lower in targets_normalized:
					safe_check = (dest_dir / member.filename).resolve()
					if not str(safe_check).startswith(str(dest_dir)):
						if log_fn:
							log_fn(f"Alerta de seguridad: se omitió archivo sospechoso {member.filename}")
						continue
					resolved = (dest_dir / member_path.name).resolve()
					with zf.open(member) as src, open(resolved, "wb") as dst:
						shutil.copyfileobj(src, dst)
					if sys.platform != "win32":
						try:
							resolved.chmod(resolved.stat().st_mode | 0o755)
						except OSError as exc:
							if log_fn:
								log_fn(f"No se pudieron ajustar permisos para {resolved}: {exc}")
					extracted = True

	elif archive_name.endswith((".tar.xz", ".tar.gz", ".tar")):
		with tarfile.open(archive_path, "r:*") as tf:
			for member in tf.getmembers():
				member_path = Path(member.name)
				name_lower = member_path.name.lower()
				if name_lower in targets_normalized and member.isfile():
					safe_check = (dest_dir / member.name).resolve()
					if not str(safe_check).startswith(str(dest_dir)):
						if log_fn:
							log_fn(f"Alerta de seguridad: se omitió archivo sospechoso {member.name}")
						continue
					resolved = (dest_dir / member_path.name).resolve()
					f_obj = tf.extractfile(member)
					if f_obj:
						with open(resolved, "wb") as dst:
							shutil.copyfileobj(f_obj, dst)
						if sys.platform != "win32":
							try:
								resolved.chmod(resolved.stat().st_mode | 0o755)
							except OSError as exc:
								if log_fn:
									log_fn(f"No se pudieron ajustar permisos para {resolved}: {exc}")
						extracted = True

	return extracted


def mark_rockola_managed(
	dest_dir: Path,
	tool_name: str,
	log_fn: Callable[[str], None] | None = None,
) -> bool:
	"""
	Registra que una herramienta fue instalada por La Rockola creando un archivo marcador
	y registrando el timestamp del último chequeo/actualización.
	"""
	dest = Path(dest_dir).resolve()
	dest.mkdir(parents=True, exist_ok=True)
	marker_file = dest / f".rockola_managed_{tool_name}"
	timestamp_file = dest / f".last_{tool_name}_update_check"
	try:
		marker_file.touch(exist_ok=True)
		timestamp_file.write_text(str(time.time()), encoding="utf-8")
		return True
	except OSError as exc:
		if log_fn:
			log_fn(f"Error al marcar {tool_name} como administrado por Rockola: {exc}")
		return False

