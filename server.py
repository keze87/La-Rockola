#!/usr/bin/env python3
"""
La Rockola del Carpincho - Servidor y CLI.
Punto de entrada principal y fachada de compatibilidad hacia el paquete modular `app`.
"""

# ruff: noqa: F401
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import Request, Response, WebSocketDisconnect
from mutagen import File as MutagenFile

# 5. API y WebSockets
from app.api.middleware import SubpathMiddleware
from app.api.schemas import ApiResponse, CommandRequest
from app.api.v1.library import get_library, scan_library
from app.api.v1.media import (
	_COVER_MEM_CACHE,
	_resize_cover,
	serve_cover,
	serve_lrc,
	stream_audio,
)
from app.api.v1.playback import handle_command, mpv_hide, mpv_show
from app.api.websocket import ConnectionManager

# 6. CLI y Application Lifecycle
from app.cli.entrypoint import (
	_check_ffmpeg,
	_check_fpcalc,
	_check_mpv,
	_check_portable_dependency,
	_check_python_packages,
	_check_ytdlp,
	_dependencies_checked,
	build_arg_parser,
	check_dependencies,
	main,
	open_browser_url,
	print_startup_banner,
)
from app.cli.wizard import (
	_parse_selected_dir,
	_select_folder_linux,
	_select_folder_macos,
	_select_folder_powershell,
	_select_folder_tkinter,
	run_interactive_wizard,
	select_folder_dialog,
	select_folder_terminal,
	setup_readline_completion,
)

# 1. Configuración y logging
from app.core.config import (
	DEFAULT_CONFIG,
	Settings,
	get_carpincho_data_dir,
	get_config_path,
	get_local_ip,
	get_server_urls,
	get_url_subpath,
	load_config,
	normalize_url,
	save_config,
)
from app.core.dependencies import get_manager, get_mpv, get_settings, get_state
from app.core.logging import configure_logging, highlight_json, logger, truncate_text

# 2. Base de datos
from app.db.database import (
	DB_PATH,
	backup_db,
	db_query,
	execute_query,
	execute_write,
	get_db_connection,
	init_db,
)

# 3. Motor de audio y MPRIS
from app.engine.audio_analysis import (
	compare_fps,
	extract_audio_features_ffmpeg,
	find_binary,
	get_clean_env,
	parse_fp,
)
from app.engine.mpris import (
	DBUS_AVAILABLE,
	MPRISPlayer,
	MPRISRoot,
	PropertyAccess,
	ServiceInterface,
	Variant,
	build_mpris_metadata,
	dbus_property,
	ensure_display_env,
	method,
)
from app.engine.mpv_controller import AsyncMpvController
from app.engine.state import (
	RADIO_PREGENERATION_MAX_AGE_SECONDS,
	APIState,
	_is_valid_radio_mp3_file,
	_unpack_radio_result,
	broadcast_state,
	check_internet_async,
)
from app.main import (
	app,
	create_app,
	lifespan,
	serve_favicon,
	serve_index,
	state,
	websocket_endpoint,
)

# 4. Servicios: biblioteca, radio y ytdlp
from app.services.library import (
	LibraryService,
	Track,
	calculate_mood_scores,
	generate_smart_hash,
	get_cover_art_uri,
	get_track_duration_seconds,
	parse_duration_str,
)
from app.services.radio import (
	DEFAULT_WEATHER_LOCATION,
	HAS_EDGE_TTS,
	RadioAnnouncementResult,
	RadioService,
	create_radio_announcement,
	embed_cover_art_in_mp3,
	get_carpincho_cover_path,
	mix_announcement_with_bg_track,
)
from app.services.ytdlp import YtDlpService

manager = ConnectionManager()

# Directorios de datos y frontend para compatibilidad con tests
DATA_DIR = get_carpincho_data_dir()
frontend_dir = Path(__file__).resolve().parent
dist_dir = frontend_dir / "dist"


def is_mood_available() -> bool:
	"""Determina si la capacidad de análisis acústico (FFmpeg) está disponible."""
	finder = globals().get("find_binary", find_binary)
	return finder("ffmpeg") is not None


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


def build_frontend() -> None:
	"""Compila el frontend si no estamos en entorno portable/frozen (compatibilidad tests)."""
	if getattr(sys, "frozen", False):
		return
	target_dir = globals().get("frontend_dir", Path(__file__).resolve().parent)
	pkg = target_dir / "package.json"
	if not pkg.exists():
		return
	npm_cmd = shutil.which("npm") or ("npm.cmd" if os.name == "nt" else "npm")
	node_modules = target_dir / "node_modules"
	if not node_modules.exists():
		subprocess.run([npm_cmd, "install"], cwd=str(target_dir), check=True)
	subprocess.run([npm_cmd, "run", "build"], cwd=str(target_dir), check=True)


if __name__ == "__main__":
	main()
