"""
Gestión de binarios portables, resolución de rutas, saneamiento de entorno y descargas seguras.
"""

from __future__ import annotations

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

from app.core.config import get_carpincho_data_dir


def resolve_platform_and_arch(platform_name: str | None = None, arch: str | None = None) -> tuple[str, str]:
	"""Normaliza el nombre del sistema operativo y la arquitectura del procesador."""
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


def ensure_display_env(env: dict[str, str]) -> None:
	"""
	Sincroniza dinámicamente variables de display y sesión gráfica (Wayland / X11 / DBus)
	cuando el servidor corre como servicio de usuario antes de abrir la sesión de escritorio.
	"""
	if sys.platform == "win32":
		return

	if env.get("WAYLAND_DISPLAY") and env.get("DISPLAY"):
		return

	try:
		res = subprocess.run(
			["systemctl", "--user", "show-environment"],
			capture_output=True,
			text=True,
			timeout=1.0,
			check=False,
		)
		if res.returncode == 0 and res.stdout:
			stdout_str = res.stdout if isinstance(res.stdout, str) else res.stdout.decode("utf-8", errors="ignore")
			for line in stdout_str.splitlines():
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
						env.setdefault(k, v)
						os.environ.setdefault(k, v)
	except Exception:
		pass

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

	if not env.get("DISPLAY"):
		for xsock in sorted(glob.glob("/tmp/.X11-unix/X[0-9]*")):
			display_num = os.path.basename(xsock)[1:]
			env["DISPLAY"] = f":{display_num}"
			os.environ["DISPLAY"] = f":{display_num}"
			break


def get_clean_env() -> dict[str, str]:
	"""
	Retorna una copia limpia de os.environ restaurando las variables modificadas por
	PyInstaller o AppImage para que mpv, ffmpeg, yt-dlp y diálogos nativos no fallen.
	"""
	env = os.environ.copy()
	for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "DYLD_LIBRARY_PATH"):
		orig = f"{var}_ORIG"
		if orig in env and env[orig].strip():
			env[var] = env[orig]
		elif var in env:
			del env[var]

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


def find_binary(bin_name: str) -> str | None:
	"""Busca un ejecutable en carpetas portables prioritarias, entorno Python y PATH del sistema."""
	is_win = sys.platform == "win32" or os.name == "nt"
	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
	exts = [".exe", ""] if is_win else [""]

	py_bin_dir = Path(sys.prefix) / ("Scripts" if is_win else "bin")
	dirs: list[Path] = [base, base / "bin", base / "mpv", base / bin_name, py_bin_dir]
	data_dir = get_carpincho_data_dir()
	dirs.extend(
		[
			data_dir,
			data_dir / "bin",
			data_dir / "mpv",
			data_dir / bin_name,
			data_dir.parent / "mpv",
			data_dir.parent / bin_name,
		]
	)

	for d in dirs:
		for ext in exts:
			cand = d / f"{bin_name}{ext}"
			if cand.is_file():
				return str(cand)

	def _safe_which(cmd: str) -> str | None:
		try:
			return shutil.which(cmd)
		except Exception:
			return None

	found = _safe_which(bin_name)
	if not found and is_win and not bin_name.lower().endswith(".exe"):
		found = _safe_which(f"{bin_name}.exe")
	if found:
		return found

	if bin_name == "yt-dlp":
		mpv_found = _safe_which("mpv") or (_safe_which("mpv.exe") if is_win else None)
		if mpv_found:
			mpv_dir = Path(mpv_found).parent
			for ext in exts:
				cand = mpv_dir / f"{bin_name}{ext}"
				if cand.is_file():
					return str(cand)

	py_scripts = "Scripts" if is_win else "bin"
	py_dirs = [
		Path(sys.prefix) / py_scripts,
		Path(sys.exec_prefix) / py_scripts,
		Path(sys.executable).parent / py_scripts,
	]
	try:
		import site

		user_base = getattr(site, "USER_BASE", None)
		if user_base:
			py_dirs.append(Path(user_base) / py_scripts)
	except Exception:
		pass

	for pd in py_dirs:
		for ext in exts:
			cand = pd / f"{bin_name}{ext}"
			if cand.is_file():
				return str(cand)

	if is_win:
		home = Path.home()
		prog_data = os.environ.get("ProgramData", "C:\\ProgramData")
		mgr_dirs = [
			home / "scoop" / "shims",
			home / "scoop" / "apps" / bin_name / "current",
			home / "scoop" / "apps" / "python" / "current" / "Scripts",
			home / "scoop" / "apps" / "mpv" / "current",
			Path(prog_data) / "scoop" / "shims",
		]
		local_app_data = os.environ.get("LOCALAPPDATA")
		if local_app_data:
			mgr_dirs.append(Path(local_app_data) / "Microsoft" / "WinGet" / "Links")
		choco = os.environ.get("ChocolateyInstall", os.path.join(prog_data, "chocolatey"))
		if choco:
			mgr_dirs.append(Path(choco) / "bin")

		for md in mgr_dirs:
			for ext in exts:
				cand = md / f"{bin_name}{ext}"
				if cand.is_file():
					return str(cand)

	return None


def is_internet_available(timeout: float = 0.8) -> bool:
	"""Comprueba conectividad saliente abriendo un socket TCP rápido a DNS públicos."""
	for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
		try:
			with socket.create_connection((host, port), timeout=timeout):
				return True
		except (OSError, TimeoutError):
			continue
	return False


async def check_internet_async(timeout: float = 0.8) -> bool:
	"""Verifica conectividad a internet de forma asíncrona sin bloquear el event loop."""
	return await asyncio.to_thread(is_internet_available, timeout)


def download_file(
	url: str,
	dest_path: Path,
	log_fn: Callable[[str], None] | None = None,
	user_agent: str = "LaRockola-Installer/1.0",
	timeout: int = 30,
) -> None:
	"""Descarga un archivo por HTTP reportando progreso cada 5%."""
	req = urllib.request.Request(url, headers={"User-Agent": user_agent})
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
	"""Verifica si un binario pertenece al directorio portable gestionado por La Rockola."""
	path = Path(bin_path).resolve()
	parent = path if path.is_dir() else path.parent

	if tool_name:
		if (parent / f".rockola_managed_{tool_name}").is_file():
			return True
	elif list(parent.glob(".rockola_managed_*")):
		return True

	base = (
		Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
	).resolve()
	try:
		path.relative_to(base)
		return True
	except ValueError:
		pass

	try:
		data_dir = get_carpincho_data_dir()
		path.relative_to(data_dir.resolve().parent)
		return True
	except ValueError:
		return False


def get_default_install_dir(tool_name: str = "mpv") -> Path:
	"""Determina la carpeta portable donde instalar herramientas descargadas."""
	if tool_name != "mpv":
		mpv_path = find_binary("mpv")
		if mpv_path:
			mpv_dir = Path(mpv_path).parent
			try:
				test_file = mpv_dir / ".carpincho_write_test"
				test_file.touch(exist_ok=True)
				test_file.unlink(missing_ok=True)
				return mpv_dir
			except OSError:
				pass

	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
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

	if sys.platform == "win32":
		app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
	elif sys.platform == "darwin":
		app_data = Path.home() / "Library" / "Application Support"
	else:
		app_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

	return app_data / "carpincho" / (tool_name if tool_name == "mpv" else "bin")


def build_frontend(
	root_dir: Path | None = None, force: bool = False, log_fn: Callable[[str], None] | None = None
) -> None:
	"""Compila el frontend de Vue 3 bajo demanda para los scripts de empaquetado."""
	root = root_dir or Path(__file__).resolve().parents[3]
	dist_dir = root / "dist"
	index_html = dist_dir / "index.html"

	if not index_html.exists() or force:
		if log_fn:
			log_fn("Compilando el frontend de Vue 3 (npm run build)...")
		npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
		subprocess.run([npm_cmd, "run", "build"], cwd=str(root), check=True)
		if log_fn:
			log_fn("Frontend compilado con éxito en dist/")
	elif log_fn:
		log_fn("Frontend ya compilado en dist/. (Usá --rebuild-frontend para forzar)")


def fetch_github_release_assets(
	api_url: str,
	html_url: str,
	user_agent: str,
	fallback_builder: Callable[[str], list[dict]] | None = None,
	timeout: int = 10,
	log_fn: Callable[[str], None] | None = None,
) -> dict:
	"""Obtiene los assets del último release en GitHub con fallback a redirección HTML."""
	headers = {
		"User-Agent": user_agent,
		"Accept": "application/vnd.github.v3+json",
	}

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
	"""Extrae binarios específicos de archivos comprimidos con protección Zip Slip."""
	dest_dir = dest_dir.resolve()
	dest_dir.mkdir(parents=True, exist_ok=True)
	archive_name = archive_path.name.lower()
	targets_normalized = {name.lower() for name in target_names}
	extracted = False

	if archive_name.endswith(".zip"):
		with zipfile.ZipFile(archive_path, "r") as zf:
			for member in zf.infolist():
				member_path = Path(member.filename)
				if member_path.name.lower() in targets_normalized:
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
						except OSError:
							pass
					extracted = True

	elif archive_name.endswith((".tar.xz", ".tar.gz", ".tar")):
		with tarfile.open(archive_path, "r:*") as tf:
			for member in tf.getmembers():
				member_path = Path(member.name)
				if member_path.name.lower() in targets_normalized and member.isfile():
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
							except OSError:
								pass
						extracted = True

	return extracted


def mark_rockola_managed(
	dest_dir: Path,
	tool_name: str,
	log_fn: Callable[[str], None] | None = None,
) -> bool:
	"""Crea el archivo marcador de herramienta gestionada por La Rockola."""
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
