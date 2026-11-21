"""
Punto de entrada embebido para Android (invocado desde Kotlin/Chaquopy en RockolaForegroundService).
Configura el entorno portable sin MPV, desactiva signal handlers en hilos secundarios
y expone ciclo de vida limpio de inicio y apagado para Uvicorn.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.core.config import (
	Settings,
	get_config_path,
	get_default_music_dir,
	save_config,
	set_settings,
)
from app.core.container import AppContainer, get_container, set_container
from app.core.logging import configure_logging
from app.core.network import get_server_urls

logger = logging.getLogger("RockolaCarpincho")

_active_server: Any = None


def configure_android_environment(
	data_dir: str,
	dist_dir: str,
	music_dir: str | None = None,
	port: int = 1729,
	host: str = "0.0.0.0",
) -> dict[str, Any]:
	"""Prepara variables de entorno, configuración e inyección de dependencias para Android."""
	resolved_data = str(Path(data_dir).expanduser().resolve())
	resolved_dist = str(Path(dist_dir).expanduser().resolve())
	Path(resolved_data).mkdir(parents=True, exist_ok=True)

	os.environ["ROCKOLA_DATA_DIR"] = resolved_data
	os.environ["ROCKOLA_DIST_DIR"] = resolved_dist
	os.environ["ROCKOLA_SKIP_FRONTEND_BUILD"] = "1"

	configure_logging(debug=False, level="INFO")

	config_path = get_config_path()
	file_settings = Settings.from_config_file(config_path)
	chosen_music = music_dir or file_settings.music_dir or get_default_music_dir()
	if chosen_music and chosen_music != "~/Music":
		chosen_music = str(Path(chosen_music).expanduser().resolve())

	settings = file_settings.model_copy(
		update={
			"music_dir": chosen_music,
			"port": port,
			"host": host,
			"open_browser": False,
			"mpv_visible": False,
			"no_mpv": True,
		}
	)
	set_settings(settings)
	save_config(config_path, settings.model_dump())

	from app.domain.playback.orchestrator import PlaybackOrchestrator
	from app.infrastructure.db.migrations import apply_migrations

	db_path = Path(resolved_data) / "rockola.db"
	apply_migrations(db_path)
	urls = get_server_urls(host, port)
	orch = PlaybackOrchestrator(
		initial_dir=settings.music_dir,
		secondary_dir=settings.music_dir2,
		open_browser=False,
		db_path=db_path,
		default_sort=settings.default_sort,
		radio_mode_enabled=settings.radio_mode_enabled,
		mpv_visible=False,
		use_mpv=False,
		dj_carpincho_enabled=False,
		dj_mode=settings.dj_mode,
		volume=settings.volume,
	)
	orch.server_host = host
	orch.server_port = port
	orch.local_ip = urls["local_ip"]
	orch.server_url = urls["local_url"]
	orch.weather_location = settings.weather_location

	container = AppContainer(settings=settings, db_path=db_path, orchestrator=orch)
	set_container(container)

	return {
		"port": port,
		"host": host,
		"local_ip": urls["local_ip"],
		"server_url": urls["local_url"],
		"music_dir": settings.music_dir,
		"data_dir": resolved_data,
		"dist_dir": resolved_dist,
	}


def start_embedded_server(
	data_dir: str,
	dist_dir: str,
	music_dir: str | None = None,
	port: int = 1729,
	host: str = "0.0.0.0",
	already_configured: bool = False,
) -> None:
	"""Arranca Uvicorn de forma bloqueante dentro de un hilo secundario del ForegroundService."""
	global _active_server
	import uvicorn

	from app.main import create_app

	if not already_configured:
		configure_android_environment(
			data_dir=data_dir,
			dist_dir=dist_dir,
			music_dir=music_dir,
			port=port,
			host=host,
		)
	fastapi_app = create_app()
	uv_config = uvicorn.Config(
		fastapi_app,
		host=host,
		port=port,
		proxy_headers=True,
		forwarded_allow_ips="*",
		access_log=False,
		log_level="info",
	)
	server = uvicorn.Server(uv_config)
	# En Android el servidor corre en un hilo worker y signal.signal() falla fuera del hilo principal
	server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
	_active_server = server
	try:
		server.run()
	finally:
		if _active_server is server:
			_active_server = None


def stop_embedded_server() -> None:
	"""Solicita el apagado limpio del servidor Uvicorn embebido."""
	if _active_server is not None:
		_active_server.should_exit = True


def get_server_info() -> dict[str, Any]:
	"""Devuelve el estado actual del servidor embebido para el puente Kotlin."""
	container = get_container()
	orch = container.orchestrator
	running = _active_server is not None and not getattr(_active_server, "should_exit", False)
	return {
		"running": running,
		"port": getattr(orch, "server_port", 1729) if orch else 1729,
		"local_ip": getattr(orch, "local_ip", "127.0.0.1") if orch else "127.0.0.1",
		"server_url": getattr(orch, "server_url", "http://127.0.0.1:1729") if orch else "http://127.0.0.1:1729",
		"music_dir": getattr(orch, "initial_dir", None) if orch else None,
	}
