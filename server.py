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
	select_folder_dialog,
	select_folder_terminal,
	setup_readline_completion,
)
from app.cli.wizard import (
	run_interactive_wizard as _app_run_interactive_wizard,
)

# 1. Configuración y logging
from app.core.config import (
	DEFAULT_CONFIG,
	Settings,
	get_carpincho_data_dir,
	get_local_ip,
	get_server_urls,
	get_url_subpath,
	load_config,
	normalize_url,
	save_config,
)
from app.core.config import (
	get_config_path as _app_get_config_path,
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
)


def init_db(db_path: Path | str | None = None) -> None:
	"""Inicializa la base de datos sincronizando DB_PATH con el sistema de dependencias."""
	from app.core.dependencies import set_db_path
	from app.db import database as _db_mod

	target = db_path or globals().get("DB_PATH") or _db_mod.DB_PATH
	if target:
		set_db_path(target)
	_db_mod.init_db(target)


# 3. Motor de audio y MPRIS
from fastapi.responses import FileResponse

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
	broadcast_state,
	check_internet_async,
)
from app.main import (
	app,
	create_app,
	lifespan,
	serve_favicon,
	websocket_endpoint,
)
from app.main import (
	serve_index as _app_serve_index,
)


class _StateProxy:
	"""Proxy dinámico para server.state que delega en get_state() de app.core.dependencies."""

	def __getattr__(self, name: str) -> Any:
		return getattr(get_state(), name)

	def __setattr__(self, name: str, value: Any) -> None:
		setattr(get_state(), name, value)

	def __delattr__(self, name: str) -> None:
		try:
			delattr(get_state(), name)
		except AttributeError:
			pass

	def __dir__(self) -> list[str]:
		return dir(get_state())


state = _StateProxy()

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
	_is_valid_radio_mp3_file,
	_unpack_radio_result,
	create_radio_announcement,
	embed_cover_art_in_mp3,
	get_carpincho_cover_path,
	mix_announcement_with_bg_track,
)
from app.services.ytdlp import YtDlpService


class _ManagerProxy:
	"""Proxy dinámico para server.manager que delega en get_manager()."""

	def __getattr__(self, name: str) -> Any:
		return getattr(get_manager(), name)

	def __setattr__(self, name: str, value: Any) -> None:
		setattr(get_manager(), name, value)

	def __delattr__(self, name: str) -> None:
		try:
			delattr(get_manager(), name)
		except AttributeError:
			pass


manager = _ManagerProxy()

# Directorios de datos y frontend para compatibilidad con tests
DATA_DIR = get_carpincho_data_dir()
frontend_dir = Path(__file__).resolve().parent
dist_dir = frontend_dir / "dist"


def run_interactive_wizard(
	config_path: Path, current_config: dict[str, Any] | None = None, select_folder_fn: Any = None
) -> dict[str, Any]:
	"""Fachada de compatibilidad para ejecutar el wizard CLI considerando select_folder_dialog parcheado."""
	fn = select_folder_fn or globals().get("select_folder_dialog", select_folder_dialog)
	return _app_run_interactive_wizard(config_path, current_config=current_config, select_folder_fn=fn)


def get_config_path(custom_path: str | Path | None = None) -> Path:
	"""Fachada de compatibilidad que respeta monkeypatching de server.DATA_DIR en tests."""
	if custom_path:
		return _app_get_config_path(custom_path)
	data_dir = globals().get("DATA_DIR")
	if data_dir is not None:
		return Path(data_dir) / "rockola_config.json"
	return _app_get_config_path()


async def serve_index():
	"""Fachada de compatibilidad para serve_index respetando monkeypatching de server.dist_dir."""
	custom_dist = globals().get("dist_dir")
	if custom_dist is not None:
		html_path = Path(custom_dist) / "index.html"
		if not html_path.exists():
			return {"error": f"Falta el archivo {html_path}, se me cayó el mate encima"}
		return FileResponse(html_path)
	return await _app_serve_index()


def is_mood_available() -> bool:
	"""Determina si la capacidad de análisis acústico (FFmpeg) está disponible."""
	import app.engine.audio_analysis as aa

	return aa.find_binary("ffmpeg") is not None


def enable_system_site_packages() -> None:
	"""Permite a entornos virtuales o embebidos acceder a paquetes del sistema si faltan."""
	from app.cli.entrypoint import enable_system_site_packages as _app_enable_system_site_packages

	_app_enable_system_site_packages()


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
	enable_system_site_packages()
	main()
