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
	set_settings,
)
from app.core.logging import configure_logging
from app.core.network import (  # noqa: F401
	get_local_ip,
	get_server_urls,
	get_url_subpath,
	normalize_url,
)

logger = logging.getLogger("RockolaCarpincho")
_dependencies_checked = False

# Aumentamos el límite de descriptores de archivos en sistemas POSIX para soportar colecciones grandes
try:
	import resource

	soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
	resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
except (ImportError, OSError, ValueError, AttributeError):
	pass


def open_browser_url(url: str, delay: float = 0.0) -> None:
	"""Abre la URL en el navegador nativo según la plataforma con aislamiento de entorno."""
	from app.engine.audio_analysis import get_clean_env

	clean_env = get_clean_env()
	if sys.platform == "win32":
		try:
			os.startfile(url)
			return
		except Exception:
			pass
	elif sys.platform == "darwin":
		try:
			subprocess.Popen(
				["open", url],
				env=clean_env,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
			)
			return
		except Exception:
			pass
	else:
		if shutil.which("xdg-open"):
			try:
				subprocess.Popen(
					["xdg-open", url],
					env=clean_env,
					stdout=subprocess.DEVNULL,
					stderr=subprocess.DEVNULL,
				)
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
	"""Verifica los módulos de Python requeridos y opcionales."""
	import importlib.util

	from app.engine.audio_analysis import is_mood_available

	missing_req = []
	missing_opt = []

	for mod in ("fastapi", "uvicorn", "mutagen", "pydantic", "websockets"):
		if importlib.util.find_spec(mod) is None:
			missing_req.append((mod, f"pip install {mod}"))

	has_ffmpeg = is_mood_available()
	if not has_ffmpeg:
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
	"""Verifica la presencia de MPV, gestionando instalación o actualizaciones automáticas."""
	from app.engine import audio_analysis

	finder = audio_analysis.find_binary
	mpv_bin = finder("mpv")
	is_portable = is_win or is_mac or is_frozen

	if mpv_bin is None:
		if is_portable:
			try:
				print(
					"🦦 ¡Opa! No se encontró MPV instalado. Intentando descargarlo automáticamente...",
					file=sys.stderr,
				)
				try:
					from scripts import mpv_installer
				except ImportError:
					import mpv_installer

				installed = mpv_installer.install_mpv(log_fn=lambda m: print(f"  {m}", file=sys.stderr))
				if installed and finder("mpv"):
					print("🦦 ¡MPV instalado con éxito! Siguiendo con la música... 🧉🎶\n", file=sys.stderr)
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
			try:
				from scripts import mpv_installer
			except ImportError:
				import mpv_installer

			if mpv_installer.is_rockola_managed(mpv_bin):
				mpv_installer.update_mpv(bin_path=mpv_bin, log_fn=lambda m: print(f"  {m}", file=sys.stderr))
		except Exception as e:
			print(f"⚠️ Aviso al verificar actualizaciones de MPV: {e}", file=sys.stderr)

	return None


def _check_portable_dependency(
	bin_name: str,
	installer_mod,
	install_func_name: str,
	success_msg: str,
	fix_msg: str,
	is_portable: bool,
) -> tuple[str, str] | None:
	"""Función compartida para verificación e instalación automática de binarios externos."""
	from app.engine import audio_analysis

	if audio_analysis.find_binary(bin_name) is not None:
		return None

	if is_portable and installer_mod is not None:
		try:
			install_fn = getattr(installer_mod, install_func_name)
			installed = install_fn(force=False, log_fn=lambda m: print(f"  {m}", file=sys.stderr))
			if installed and audio_analysis.find_binary(bin_name):
				print(success_msg, file=sys.stderr)
				return None
		except Exception as e:
			print(f"⚠️ Aviso al intentar auto-instalar {bin_name}: {e}", file=sys.stderr)

	return (bin_name, fix_msg)


def _check_ytdlp(is_win: bool, is_mac: bool, is_frozen: bool) -> tuple[str, str] | None:
	"""Verifica la presencia de yt-dlp, gestionando instalación automática si está disponible."""
	try:
		from scripts import ytdlp_installer
	except ImportError:
		try:
			import ytdlp_installer
		except ImportError:
			ytdlp_installer = None

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
	"""Verifica la presencia de FFmpeg, gestionando instalación automática si está disponible."""
	try:
		from scripts import ffmpeg_installer
	except ImportError:
		try:
			import ffmpeg_installer
		except ImportError:
			ffmpeg_installer = None

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
	"""Verifica la presencia de fpcalc (Chromaprint), gestionando instalación automática si está disponible."""
	try:
		from scripts import fpcalc_installer
	except ImportError:
		try:
			import fpcalc_installer
		except ImportError:
			fpcalc_installer = None

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

	# Avisar si faltan dependencias opcionales
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

	# Si falta algo requerido, frenar el arranque
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
	parser.add_argument(
		"--host",
		type=str,
		default=None,
		help="Dirección IP de escucha (default: del config o 0.0.0.0)",
	)
	parser.add_argument(
		"--port",
		type=int,
		default=None,
		help="Puerto del servidor web (default: del config o 1729)",
	)
	parser.add_argument(
		"--url",
		type=str,
		default=None,
		help="URL predeterminada del servidor",
	)
	parser.add_argument(
		"--dir",
		type=str,
		default=None,
		help="Directorio principal con archivos de música",
	)
	parser.add_argument(
		"--dir2",
		type=str,
		default=None,
		help="Directorio secundario con archivos de música",
	)
	parser.add_argument(
		"--config",
		type=str,
		default=None,
		help="Ruta personalizada a rockola_config.json",
	)
	parser.add_argument(
		"--setup",
		action="store_true",
		help="Ejecutar asistente interactivo de configuración de carpetas",
	)
	parser.add_argument(
		"--no-interactive",
		action="store_true",
		help="No ejecutar asistente interactivo automáticamente",
	)
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
	return parser


def main() -> None:
	"""Función principal de arranque para CLI y binarios empaquetados."""
	import uvicorn

	from app.cli.wizard import run_interactive_wizard
	from app.core.dependencies import set_global_state
	from app.engine.state import APIState
	from app.main import app

	multiprocessing.freeze_support()
	parser = build_arg_parser()
	args = parser.parse_args()

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

	# Cargamos los settings tipados desde el JSON y mergeamos los argumentos de CLI
	settings = Settings.from_config_file(config_path)
	settings = settings.merge_cli_args(args)
	set_settings(settings)

	final_log_level = settings.log_level.upper()
	is_debug = settings.debug or final_log_level == "DEBUG"
	configure_logging(debug=is_debug, level=final_log_level)

	urls = get_server_urls(settings.host, settings.port, custom_url=settings.url)

	state = APIState(
		initial_dir=settings.music_dir,
		secondary_dir=settings.music_dir2,
		open_browser=settings.open_browser,
	)
	state.radio_service.weather_location = settings.weather_location
	state.weather_location = settings.weather_location
	state.server_host = settings.host
	state.server_port = settings.port
	state.local_ip = urls["local_ip"]
	state.server_url = urls["local_url"]
	if settings.url:
		state.configured_url = settings.url
		state.subpath = get_url_subpath(settings.url)
	set_global_state(state)

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
