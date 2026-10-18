"""
Punto de entrada de línea de comandos (CLI) e inicialización del servidor Uvicorn.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from app.core.config import (
	Settings,
	get_config_path,
	load_config,
	save_config,
	set_settings,
)
from app.core.container import get_container
from app.core.logging import configure_logging
from app.core.network import (
	get_local_ip,
	get_server_urls,
	get_url_subpath,
	normalize_url,
)
from app.domain.library.mood import is_mood_available
from app.infrastructure.binaries import ffmpeg as ffmpeg_installer
from app.infrastructure.binaries import fpcalc as fpcalc_installer
from app.infrastructure.binaries import mpv as mpv_installer
from app.infrastructure.binaries import ytdlp as ytdlp_installer
from app.infrastructure.binaries.manager import find_binary, get_clean_env

logger = logging.getLogger("RockolaCarpincho")
_dependencies_checked = False

try:
	import resource

	soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
	resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
except (ImportError, OSError, ValueError, AttributeError):
	pass


def open_browser_url(url: str, delay: float = 0.0) -> None:
	"""Abre la URL en el navegador nativo según la plataforma con aislamiento de entorno."""
	clean_env = get_clean_env()
	if sys.platform == "win32":
		try:
			os.startfile(url)  # type: ignore[attr-defined]
			return
		except Exception:
			pass
	elif sys.platform == "darwin":
		try:
			subprocess.Popen(["open", url], env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			return
		except Exception:
			pass
	elif shutil.which("xdg-open"):
		try:
			subprocess.Popen(["xdg-open", url], env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			return
		except Exception:
			pass

	old_env = os.environ.copy()
	try:
		clean = get_clean_env()
		for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "DYLD_LIBRARY_PATH"):
			if k not in clean and k in os.environ:
				del os.environ[k]
			elif k in clean:
				os.environ[k] = clean[k]
		webbrowser.open(url)
	except Exception as e:
		logger.debug(f"Aviso en webbrowser.open: {e}")
	finally:
		os.environ.clear()
		os.environ.update(old_env)


def print_startup_banner(
	host: str,
	port: int,
	music_dir: str | None,
	music_dir2: str | None,
	open_browser: bool,
	config_path: Path | None = None,
	custom_url: str | None = None,
	weather_location: str | None = None,
	log_level: str | None = None,
) -> None:
	"""Imprime el banner de bienvenida criollo en la consola."""
	urls = get_server_urls(host, port, custom_url=custom_url)
	local_url = urls["local_url"]
	network_url = urls["network_url"]
	resolved_dir = str(Path(music_dir or "~/Music").expanduser().resolve())
	resolved_dir2 = str(Path(music_dir2).expanduser().resolve()) if music_dir2 else None

	border = "=" * 70
	print(f"\n{border}")
	print("             🦦  LA ROCKOLA DEL CARPINCHO  🧉")
	print("   Reproductor y servidor de música con alma de campo y sabor a mate")
	print(f"{border}\n")

	print("  📻 DIRECCIONES DE ACCESO:")
	if urls.get("custom_url"):
		print(f"     • URL configurada:     {urls['custom_url']}")
		print(f"     • Dirección local:     http://{urls['local_ip']}:{port}")
		print(f"     • Desde tu celular:    {urls['custom_url']}")
	else:
		print(f"     • En esta PC:          {local_url}")
		if urls["loopback_url"] != local_url:
			print(f"       (o también en:       {urls['loopback_url']})")
		if network_url:
			print(f"     • Desde tu celular:    {network_url}  (misma red Wi-Fi)")
		else:
			print("     • Red local:           Modo solo local (127.0.0.1)")

	print("\n  📁 CONFIGURACIÓN:")
	print(f"     • Carpeta de música:   {resolved_dir}")
	if resolved_dir2:
		print(f"     • Carpeta secundaria:  {resolved_dir2}")
	if weather_location:
		print(f"     • Clima radial:        {weather_location}")
	if log_level:
		print(f"     • Nivel de registro:   {log_level}")

	print("\n  💡 GUÍA RÁPIDA DE USO:")
	if open_browser:
		print(f"     1. 🌐 La web se abrirá automáticamente en: {local_url}")
	else:
		print(f"     1. 🌐 Abrí tu navegador en: {local_url}")
	print("     2. 📱 Para controlar la música con amigos, conectate al mismo Wi-Fi.")
	print("     3. 🎵 Poné tus temas en la carpeta de música o pegá enlaces de YouTube.")
	print("     4. ⚙️  Para cambiar opciones, ejecutá con '--setup' o editá el config.")
	print("     5. ⏹️  Para detener La Rockola, presioná Ctrl+C.\n")
	print(f"{border}\n")


def _check_python_packages(is_frozen: bool, force: bool = False) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
	import importlib.util

	missing_req = []
	missing_opt = []

	for mod in ("fastapi", "uvicorn", "mutagen", "pydantic", "pydantic_settings", "websockets"):
		if importlib.util.find_spec(mod) is None:
			pkg_name = "pydantic-settings" if mod == "pydantic_settings" else mod
			missing_req.append((mod, f"pip install {pkg_name}"))

	if not is_mood_available():
		fix = (
			"no incluido en la versión portable (instalá 'ffmpeg' en tu sistema para análisis de mood/BPM)"
			if is_frozen
			else "instalar ffmpeg (para el análisis de mood/BPM)"
		)
		missing_opt.append(("ffmpeg", fix))

	if sys.platform not in ("win32", "darwin") and importlib.util.find_spec("dbus_next") is None:
		fix = (
			"no incluido en este build de Linux (para teclas multimedia)"
			if is_frozen
			else "pip install dbus-next (para teclas multimedia)"
		)
		missing_opt.append(("dbus_next", fix))

	return missing_req, missing_opt


def _check_mpv(is_win: bool, is_mac: bool, is_frozen: bool) -> tuple[str, str] | None:
	mpv_bin = find_binary("mpv")
	is_portable = is_win or is_mac or is_frozen

	if mpv_bin is None:
		if is_portable:
			print(
				"🦦 ¡Opa! No se encontró MPV instalado. Descargando MPV portátil automáticamente...",
				file=sys.stderr,
			)
			try:
				installed = mpv_installer.install_mpv(log_fn=lambda m: print(f"  {m}", file=sys.stderr))
				if installed and find_binary("mpv"):
					print("✅ ¡Joya! MPV se descargó e instaló listo para usar.", file=sys.stderr)
					return None
			except Exception as e:
				print(f"⚠️ Falló la descarga automática de MPV: {e}", file=sys.stderr)
		fix = (
			"winget install mpv (o descargá mpv.exe y ponelo al lado de larockola.exe)"
			if is_win
			else ("brew install mpv" if is_mac else "sudo apt install mpv (o lo que use tu distro)")
		)
		return ("mpv", fix)

	if is_portable:
		try:
			if mpv_installer.is_rockola_managed(mpv_bin):
				mpv_installer.update_mpv(bin_path=mpv_bin, log_fn=lambda m: print(f"  {m}", file=sys.stderr))
		except Exception as e:
			print(f"⚠️ No se pudo verificar actualización de MPV: {e}", file=sys.stderr)

	return None


def _check_portable_dependency(
	bin_name: str,
	installer_mod: object,
	install_func_name: str,
	success_msg: str,
	fix_msg: str,
	is_portable: bool,
) -> tuple[str, str] | None:
	if find_binary(bin_name) is not None:
		return None

	if is_portable and installer_mod is not None:
		try:
			install_fn = getattr(installer_mod, install_func_name)
			installed = install_fn(force=False, log_fn=lambda m: print(f"  {m}", file=sys.stderr))
			if installed and find_binary(bin_name):
				print(success_msg, file=sys.stderr)
				return None
		except Exception as e:
			print(f"⚠️ Aviso al intentar auto-instalar {bin_name}: {e}", file=sys.stderr)

	return (bin_name, fix_msg)


def _check_ytdlp(is_win: bool, is_mac: bool, is_frozen: bool) -> tuple[str, str] | None:
	fix = (
		"winget install yt-dlp (o poné yt-dlp.exe al lado de larockola.exe)"
		if is_win
		else "pip install yt-dlp (para reproducir temas de YouTube/Internet)"
	)
	return _check_portable_dependency(
		bin_name="yt-dlp",
		installer_mod=ytdlp_installer,
		install_func_name="install_ytdlp",
		success_msg="🦦 ¡yt-dlp instalado con éxito para temas de YouTube! 🧉🎶\n",
		fix_msg=fix,
		is_portable=is_win or is_mac or is_frozen,
	)


def _check_ffmpeg(is_win: bool, is_mac: bool, is_frozen: bool) -> tuple[str, str] | None:
	fix = (
		"winget install Gyan.FFmpeg (o poné ffmpeg.exe al lado de larockola.exe)"
		if is_win
		else ("brew install ffmpeg" if is_mac else "sudo apt install ffmpeg (para análisis de mood/BPM)")
	)
	return _check_portable_dependency(
		bin_name="ffmpeg",
		installer_mod=ffmpeg_installer,
		install_func_name="install_ffmpeg",
		success_msg="🦦 ¡FFmpeg instalado con éxito para el análisis de mood y BPM! 🧉🎶\n",
		fix_msg=fix,
		is_portable=is_win or is_mac or is_frozen,
	)


def _check_fpcalc(is_win: bool, is_mac: bool, is_frozen: bool) -> tuple[str, str] | None:
	fix = (
		"descargar fpcalc (Chromaprint) y ponerlo al lado de larockola.exe"
		if is_win
		else ("brew install chromaprint" if is_mac else "sudo apt install libchromaprint-tools")
	)
	return _check_portable_dependency(
		bin_name="fpcalc",
		installer_mod=fpcalc_installer,
		install_func_name="install_fpcalc",
		success_msg="🦦 ¡fpcalc instalado con éxito para huellas acústicas! 🧉🎶\n",
		fix_msg=fix,
		is_portable=is_win or is_mac or is_frozen,
	)


def check_dependencies(force: bool = False) -> None:
	"""Verifica dependencias mínimas requeridas por el sistema."""
	global _dependencies_checked
	if _dependencies_checked and not force:
		return
	_dependencies_checked = True

	if any(arg in sys.argv for arg in ("-h", "--help")):
		return

	is_win = sys.platform == "win32" or os.name == "nt"
	is_mac = sys.platform == "darwin"
	is_frozen = getattr(sys, "frozen", False)

	missing_req_py, missing_opt_py = _check_python_packages(is_frozen=is_frozen, force=force)
	missing_req_sys = []
	missing_opt_sys = []

	mpv_res = _check_mpv(is_win=is_win, is_mac=is_mac, is_frozen=is_frozen)
	if mpv_res:
		missing_req_sys.append(mpv_res)

	yt_res = _check_ytdlp(is_win=is_win, is_mac=is_mac, is_frozen=is_frozen)
	if yt_res:
		missing_opt_sys.append(yt_res)

	ff_res = _check_ffmpeg(is_win=is_win, is_mac=is_mac, is_frozen=is_frozen)
	if ff_res and not any(m[0] == "ffmpeg" for m in missing_opt_py):
		missing_opt_sys.append(ff_res)

	fp_res = _check_fpcalc(is_win=is_win, is_mac=is_mac, is_frozen=is_frozen)
	if fp_res:
		missing_opt_sys.append(fp_res)

	if missing_opt_py or missing_opt_sys:
		print(
			"🦦 Ojo al piojo: Faltan algunas cositas opcionales. La Rockola arranca igual, pero con menos magia:",
			file=sys.stderr,
		)
		for mod, fix in missing_opt_py:
			print(f"  - [Opcional] {mod:<10} -> {fix}", file=sys.stderr)
		for bin_name, fix in missing_opt_sys:
			print(f"  - [Opcional] {bin_name:<10} -> {fix}", file=sys.stderr)
		print(file=sys.stderr)

	if missing_req_py or missing_req_sys:
		print(
			"🦦 ¡Pará un cacho, che! La Rockola del Carpincho no puede arrancar así 🧉\n",
			file=sys.stderr,
		)

		if missing_req_py:
			print("📦 Paquetes de Python que faltan en la ronda:", file=sys.stderr)
			for mod, fix in missing_req_py:
				print(f"  - {mod:<10} -> Mandale un: {fix}", file=sys.stderr)

		if missing_req_sys:
			print(
				"\n🛠️ Herramientas del sistema (sin esto el carpincho no canta):",
				file=sys.stderr,
			)
			for bin_name, fix in missing_req_sys:
				print(f"  - {bin_name:<10} -> Fijate con: {fix}", file=sys.stderr)

		print(
			"\nTranqui, instalá eso, cambiale la yerba al mate y volvé a correr el script. ¡Te espero! 🦦🧉🎶",
			file=sys.stderr,
		)
		sys.exit(1)


def build_arg_parser() -> argparse.ArgumentParser:
	"""Construye el parser de argumentos de línea de comandos."""
	parser = argparse.ArgumentParser(
		description="🦦 La Rockola del Carpincho — Servidor de música y reproductor con alma de campo y sabor a mate.",
		epilog="""Ejemplos de uso:
  larockola                              Inicia el servidor y abre el navegador en la IP local
  larockola --no-browser                 Inicia sin abrir el navegador automáticamente
  larockola --setup                      Ejecuta el asistente interactivo para elegir carpetas
  larockola --dir ~/Musica --port 8080   Usa una carpeta y un puerto específicos
  larockola --host 127.0.0.1             Modo solo local (sin acceso desde la red Wi-Fi)
  larockola --debug                      Habilita logs detallados en nivel DEBUG
""",
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	parser.add_argument("--host", type=str, default=None, help="Dirección IP de escucha (default: 0.0.0.0)")
	parser.add_argument("--port", type=int, default=None, help="Puerto del servidor web (default: 1729)")
	parser.add_argument("--url", type=str, default=None, help="URL predeterminada del servidor")
	parser.add_argument("--dir", type=str, default=None, help="Directorio principal con archivos de música")
	parser.add_argument("--dir2", type=str, default=None, help="Directorio secundario con archivos de música")
	parser.add_argument("--config", type=str, default=None, help="Ruta personalizada a rockola_config.json")
	parser.add_argument("--setup", action="store_true", help="Ejecutar asistente interactivo de configuración")
	parser.add_argument("--no-interactive", action="store_true", help="No ejecutar asistente interactivo")
	parser.add_argument(
		"--weather-location",
		dest="weather_location",
		type=str,
		default=None,
		help="Ciudad o localidad para el reporte del clima en la radio",
	)
	parser.add_argument(
		"--open-browser",
		dest="open_browser",
		action="store_true",
		default=None,
		help="Abre automáticamente el navegador web al iniciar el servidor",
	)
	parser.add_argument(
		"--no-browser",
		dest="open_browser",
		action="store_false",
		default=None,
		help="No abre el navegador web automáticamente al iniciar",
	)
	parser.add_argument(
		"--log-level",
		dest="log_level",
		type=str,
		default=None,
		help="Nivel de registro (DEBUG, INFO, WARNING, ERROR)",
	)
	parser.add_argument(
		"--debug",
		action="store_true",
		default=os.environ.get("ROCKOLA_DEBUG", "").lower() in ("1", "true", "yes"),
		help="Activa logs detallados en nivel DEBUG",
	)
	parser.add_argument(
		"--rebuild-frontend",
		dest="rebuild_frontend",
		action="store_true",
		default=False,
		help="Fuerza la recompilación del frontend con Vite antes de iniciar el servidor",
	)
	return parser


def configure_console_encoding() -> None:
	"""Configura UTF-8 en consolas de Windows."""
	if sys.platform == "win32":
		if hasattr(sys.stdout, "reconfigure"):
			try:
				sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
			except Exception:
				pass
		if hasattr(sys.stderr, "reconfigure"):
			try:
				sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
			except Exception:
				pass


def enable_system_site_packages() -> None:
	"""Permite a entornos virtuales o embebidos acceder a paquetes del sistema si faltan."""
	if not getattr(sys, "frozen", False):
		return
	try:
		import site

		user_site = site.getusersitepackages()
		if os.path.exists(user_site) and user_site not in sys.path:
			sys.path.append(user_site)
		for sys_site in site.getsitepackages():
			if os.path.exists(sys_site) and sys_site not in sys.path:
				sys.path.append(sys_site)
	except Exception:
		pass


def build_frontend(frontend_dir: Path | None = None, force: bool = False) -> None:
	"""Compila el frontend si no estamos en un entorno empaquetado (frozen) y aún no existe dist/index.html."""
	if getattr(sys, "frozen", False):
		return
	if any(arg in sys.argv for arg in ("-h", "--help")):
		return
	target_dir = frontend_dir or Path(__file__).resolve().parents[2]
	pkg = target_dir / "package.json"
	if not pkg.exists():
		return
	index_html = target_dir / "dist" / "index.html"
	if not force and index_html.is_file():
		return
	npm_cmd = shutil.which("npm") or ("npm.cmd" if os.name == "nt" else "npm")
	clean_env = get_clean_env()
	node_modules = target_dir / "node_modules"
	if not node_modules.exists():
		subprocess.run([npm_cmd, "install"], cwd=str(target_dir), check=True, env=clean_env)
	subprocess.run([npm_cmd, "run", "build"], cwd=str(target_dir), check=True, env=clean_env)


def main() -> None:
	"""Función principal de arranque para CLI y binarios empaquetados."""
	import uvicorn

	from app.cli.wizard import run_interactive_wizard
	from app.domain.playback.orchestrator import PlaybackOrchestrator
	from app.main import app

	multiprocessing.freeze_support()
	configure_console_encoding()
	enable_system_site_packages()
	parser = build_arg_parser()
	args = parser.parse_args()

	if not getattr(sys, "frozen", False):
		try:
			build_frontend(force=bool(getattr(args, "rebuild_frontend", False)))
		except Exception as e:
			logger.warning(f"No se pudo compilar el frontend automáticamente en el arranque: {e}")

	check_dependencies()
	config_path = get_config_path(args.config)
	config_exists = config_path.is_file()
	config = load_config(config_path)

	if args.debug:
		final_log_level = "DEBUG"
	elif args.log_level is not None:
		final_log_level = args.log_level.upper()
	else:
		final_log_level = str(config.get("log_level", "INFO")).upper()

	is_debug = final_log_level == "DEBUG"
	configure_logging(debug=is_debug, level=final_log_level)

	should_run_wizard = args.setup or (
		not config_exists and not args.no_interactive and sys.stdin.isatty() and not args.dir
	)
	if should_run_wizard:
		config = run_interactive_wizard(config_path, config)
	elif not config_exists:
		initial_settings = Settings.from_config_file(config_path).merge_cli_args(args)
		save_config(config_path, initial_settings.model_dump())

	settings = Settings.from_config_file(config_path).merge_cli_args(args)
	set_settings(settings)

	final_log_level = settings.log_level.upper()
	is_debug = settings.debug or final_log_level == "DEBUG"
	configure_logging(debug=is_debug, level=final_log_level)

	urls = get_server_urls(settings.host, settings.port, custom_url=settings.url)

	state = PlaybackOrchestrator(
		initial_dir=settings.music_dir,
		secondary_dir=settings.music_dir2,
		open_browser=settings.open_browser,
	)
	state.weather_location = settings.weather_location
	state.server_host = settings.host
	state.server_port = settings.port
	state.local_ip = urls["local_ip"]
	state.server_url = urls["local_url"]
	if settings.url:
		state.configured_url = settings.url
		state.subpath = get_url_subpath(settings.url)

	container = get_container()
	container.orchestrator = state
	container.settings = settings

	print_startup_banner(
		host=settings.host,
		port=settings.port,
		music_dir=settings.music_dir,
		music_dir2=settings.music_dir2,
		open_browser=settings.open_browser,
		config_path=config_path,
		custom_url=settings.url,
		weather_location=settings.weather_location,
		log_level=final_log_level,
	)

	uvicorn.run(
		app,
		host=settings.host,
		port=settings.port,
		proxy_headers=True,
		forwarded_allow_ips="*",
		access_log=is_debug,
		log_level=final_log_level.lower(),
	)


__all__ = [
	"build_arg_parser",
	"build_frontend",
	"check_dependencies",
	"configure_console_encoding",
	"enable_system_site_packages",
	"get_local_ip",
	"get_server_urls",
	"get_url_subpath",
	"main",
	"normalize_url",
	"open_browser_url",
	"print_startup_banner",
]

if __name__ == "__main__":
	main()
