"""
Punto de entrada embebido para Android (invocado desde Kotlin/Chaquopy en RockolaForegroundService).
Configura el entorno portable sin MPV, desactiva signal handlers en hilos secundarios
y expone ciclo de vida limpio de inicio y apagado para Uvicorn.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import threading
import time
from collections.abc import Callable
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

_server_lock = threading.Lock()
_active_server: Any = None
_active_thread: threading.Thread | None = None
_server_loop: asyncio.AbstractEventLoop | None = None
_host_state: str = "stopped"
_last_error: str | None = None
_stop_requested: bool = False
_server_generation: int = 0


def set_server_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
	"""Registra el event loop activo de Uvicorn para despachar comandos nativos sin HTTP."""
	global _server_loop
	with _server_lock:
		_server_loop = loop


def dispatch_native_command(cmd: str, extra_json: str = "{}", timeout_sec: float = 2.0) -> str:
	"""Ejecuta un comando del orquestador en el event loop de Uvicorn esperando resultado real o timeout."""
	with _server_lock:
		loop = _server_loop
	if loop is None or loop.is_closed():
		return "unavailable"

	from app.api.commands import COMMAND_HANDLERS
	from app.api.schemas import CommandRequest
	from app.domain.playback.orchestrator import broadcast_state

	handler = COMMAND_HANDLERS.get(cmd)
	if handler is None:
		return "unavailable"

	container = get_container()
	state = container.orchestrator
	if state is None:
		return "unavailable"
	mgr = container.ws_manager

	try:
		raw_extra = json.loads(extra_json) if extra_json else {}
		if not isinstance(raw_extra, dict):
			raw_extra = {}
		raw_extra["cmd"] = cmd
		req = CommandRequest(**raw_extra)
	except Exception:
		logger.warning("Payload inválido en dispatch_native_command(%s)", cmd)
		return "unavailable"

	async def _run() -> None:
		await handler(state, req, mgr)
		await broadcast_state()

	future = asyncio.run_coroutine_threadsafe(_run(), loop)
	try:
		future.result(timeout=timeout_sec)
		return "ok"
	except concurrent.futures.TimeoutError:
		future.cancel()
		logger.warning("Timeout ejecutando comando nativo '%s' (%.1fs)", cmd, timeout_sec)
		return "timeout"
	except Exception:
		logger.exception("Error ejecutando comando nativo '%s'", cmd)
		return "error"


def get_connected_remote_clients() -> int:
	"""Devuelve clientes remotos activos (WebSocket + streams HTTP en curso o en ventana de gracia)."""
	ws_count = 0
	mgr = get_container().ws_manager
	if mgr is not None and hasattr(mgr, "remote_client_count"):
		try:
			ws_count = int(mgr.remote_client_count())
		except Exception:
			ws_count = 0
	http_count = 0
	try:
		from app.api.media import active_remote_stream_count, has_recent_remote_stream

		http_count = active_remote_stream_count()
		if http_count == 0 and ws_count == 0 and has_recent_remote_stream(grace_sec=30.0):
			http_count = 1
	except Exception:
		http_count = 0
	return ws_count + http_count


def is_radio_synthesizing() -> bool:
	"""Indica si el orquestador está sintetizando una locución radial entre temas."""
	try:
		orch = get_container().orchestrator
		return bool(getattr(orch, "is_synthesizing_radio", False))
	except Exception:
		return False


def _invoke_ready_callback(callback: Any) -> None:
	"""Invoca callback Python o Runnable Java sin propagar errores al ciclo de Uvicorn."""
	if callback is None:
		return
	try:
		if hasattr(callback, "run") and callable(callback.run):
			callback.run()
		elif callable(callback):
			callback()
	except Exception:
		logger.exception("Error ejecutando callback on_ready del servidor embebido")


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

	from app.infrastructure.storage import normalize_music_root

	explicit_arg = (music_dir or "").strip()
	if explicit_arg:
		chosen_music = normalize_music_root(explicit_arg)
		music_configured = True
	elif file_settings.music_dir_configured and file_settings.music_dir:
		chosen_music = normalize_music_root(file_settings.music_dir)
		music_configured = True
	else:
		chosen_music = get_default_music_dir()
		music_configured = bool(chosen_music)

	settings = file_settings.model_copy(
		update={
			"music_dir": chosen_music,
			"music_dir_configured": music_configured,
			"port": port,
			"host": host,
			"open_browser": False,
			"mpv_visible": False,
			"no_mpv": True,
		}
	)
	set_settings(settings)
	save_config(config_path, settings.model_dump())

	from app.api import media as _media_preload  # noqa: F401
	from app.domain.playback.orchestrator import PlaybackOrchestrator
	from app.infrastructure.db.migrations import apply_migrations
	from app.infrastructure.mpv.android_controller import AndroidPlayerController, resolve_native_android_player

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
		music_dir_configured=settings.music_dir_configured,
	)
	native_player = resolve_native_android_player()
	if native_player is not None:
		try:
			if hasattr(native_player, "setVolume"):
				native_player.setVolume(float(settings.volume))
		except Exception:
			pass
	else:
		logger.warning(
			"⚠️ AndroidAudioPlayer no disponible en configure_android_environment; "
			"se usará AndroidPlayerController con reintento automático."
		)
	orch.mpv = AndroidPlayerController(
		callbacks={
			"duration_update": orch.handle_duration_update,
			"pause_update": orch.handle_pause_update,
			"song_ended": orch.handle_song_ended,
			"time_update": orch.handle_time_update,
		},
		state_ref=orch,
		native_player=native_player,
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
		"music_dir_configured": settings.music_dir_configured,
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
	on_ready: Callable[[], None] | Any = None,
) -> bool:
	"""Arranca Uvicorn de forma bloqueante dentro de un hilo secundario del ForegroundService."""
	global _active_server, _active_thread, _host_state, _last_error, _stop_requested, _server_generation
	import uvicorn

	from app.main import create_app

	with _server_lock:
		if _active_thread is not None and not _active_thread.is_alive():
			# Un hilo anterior murió o quedó huérfano sin limpiar estado: recuperamos para no bloquear reinicios
			_active_server = None
			_active_thread = None
			if _host_state in ("starting", "ready", "stopping"):
				_host_state = "stopped"

		if _active_server is not None or _host_state in ("starting", "ready", "stopping"):
			logger.warning("Se omitió arranque duplicado del servidor embebido (estado actual: %s)", _host_state)
			return False
		_server_generation += 1
		my_generation = _server_generation
		_host_state = "starting"
		_last_error = None
		_stop_requested = False
		_active_thread = threading.current_thread()

	server = None
	try:
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

		orig_startup = getattr(server, "startup", None)
		has_async_startup = callable(orig_startup)

		with _server_lock:
			if _stop_requested or _server_generation != my_generation:
				if _server_generation == my_generation:
					_host_state = "stopped"
				return True
			_active_server = server
			if not has_async_startup:
				_host_state = "ready"

		if has_async_startup:

			async def _startup_and_mark_ready(sockets: Any = None) -> None:
				global _host_state
				set_server_event_loop(asyncio.get_running_loop())
				await orig_startup(sockets=sockets)
				should_notify = False
				with _server_lock:
					if _active_server is server and _server_generation == my_generation and not _stop_requested:
						_host_state = "ready"
						should_notify = True
				if should_notify:
					_invoke_ready_callback(on_ready)

			server.startup = _startup_and_mark_ready  # type: ignore[method-assign]
		else:
			_invoke_ready_callback(on_ready)

		server.run()
		return True
	except SystemExit as exc:
		code = getattr(exc, "code", 1)
		if code in (None, 0):
			return True
		msg = f"No se pudo abrir el puerto {port} (¿ya está en uso?)"
		logger.exception(msg)
		with _server_lock:
			if _server_generation == my_generation:
				_last_error = msg
				_host_state = "failed"
		raise RuntimeError(msg) from exc
	except Exception as exc:
		logger.exception("Error fatal en servidor embebido")
		with _server_lock:
			if _server_generation == my_generation:
				_last_error = str(exc) or exc.__class__.__name__
				_host_state = "failed"
		raise
	finally:
		set_server_event_loop(None)
		with _server_lock:
			if _server_generation == my_generation and (server is None or _active_server is server):
				_active_server = None
				_active_thread = None
				if _host_state != "failed":
					_host_state = "stopped"


_persist_cond = threading.Condition()
_persist_in_flight = False
_in_flight_persist_snapshot: tuple[int, Any] | None = None
_pending_persist_snapshot: tuple[int, Any] | None = None
_persist_executor: concurrent.futures.ThreadPoolExecutor | None = None


def _drain_stop_persistence() -> None:
	"""Drena snapshots coalescidos de persistencia al apagar sin pisar generaciones más nuevas."""
	global _persist_in_flight, _in_flight_persist_snapshot, _pending_persist_snapshot
	while True:
		with _persist_cond:
			snapshot = _pending_persist_snapshot
			_pending_persist_snapshot = None
			if snapshot is None:
				_persist_in_flight = False
				_in_flight_persist_snapshot = None
				_persist_cond.notify_all()
				return
			_in_flight_persist_snapshot = snapshot

		snap_gen, snap_orch = snapshot
		try:
			from app.api.commands import flush_pending_volume_persist

			flush_pending_volume_persist()
		except Exception as exc:
			logger.warning("Error haciendo flush de volumen al apagar: %s", exc)

		with _server_lock:
			current_gen = _server_generation

		if current_gen != snap_gen:
			logger.info(
				"Se omitió guardar sesión de generación %d porque ya arrancó generación %d",
				snap_gen,
				current_gen,
			)
			continue

		try:
			if snap_orch is not None and hasattr(snap_orch, "save_playback_session"):
				snap_orch.save_playback_session(force=True)
		except Exception as exc:
			logger.warning("Error guardando sesión de reproducción al apagar: %s", exc)


def wait_for_stop_persistence(timeout_sec: float = 5.0) -> bool:
	"""Espera de forma acotada hasta que termine la persistencia en vuelo al apagar."""
	deadline = time.monotonic() + max(0.0, timeout_sec)
	with _persist_cond:
		while _persist_in_flight or _pending_persist_snapshot is not None:
			remaining = deadline - time.monotonic()
			if remaining <= 0:
				return False
			_persist_cond.wait(timeout=remaining)
		return True


def stop_embedded_server() -> None:
	"""Solicita el apagado limpio del servidor Uvicorn embebido coalesciendo la persistencia final."""
	global _host_state, _stop_requested, _persist_in_flight, _pending_persist_snapshot, _persist_executor
	with _server_lock:
		_stop_requested = True
		snap_gen = _server_generation
		if _active_server is not None:
			if _host_state == "stopping":
				# Segundo pedido de apagado sobre un servidor trabado: forzamos salida de conexiones
				_active_server.force_exit = True
			_active_server.should_exit = True
			_host_state = "stopping"
		elif _host_state == "starting":
			_host_state = "stopping"
		elif _host_state != "failed":
			_host_state = "stopped"

	snap_orch = get_container().orchestrator
	with _persist_cond:
		same_in_flight = (
			_persist_in_flight
			and _pending_persist_snapshot is None
			and _in_flight_persist_snapshot is not None
			and _in_flight_persist_snapshot[0] == snap_gen
			and _in_flight_persist_snapshot[1] is snap_orch
		)
		if not same_in_flight and (_pending_persist_snapshot is None or snap_gen >= _pending_persist_snapshot[0]):
			_pending_persist_snapshot = (snap_gen, snap_orch)
		if not _persist_in_flight:
			_persist_in_flight = True
			if _persist_executor is None:
				_persist_executor = concurrent.futures.ThreadPoolExecutor(
					max_workers=1,
					thread_name_prefix="RockolaStopPersist",
				)
			_persist_executor.submit(_drain_stop_persistence)


def get_server_info() -> dict[str, Any]:
	"""Devuelve el estado actual del servidor embebido para el puente Kotlin."""
	container = get_container()
	orch = container.orchestrator
	with _server_lock:
		running = _active_server is not None and not getattr(_active_server, "should_exit", False)
		host_state = _host_state
		last_error = _last_error
	return {
		"running": running,
		"host_state": host_state,
		"last_error": last_error,
		"port": getattr(orch, "server_port", 1729) if orch else 1729,
		"local_ip": getattr(orch, "local_ip", "127.0.0.1") if orch else "127.0.0.1",
		"server_url": getattr(orch, "server_url", "http://127.0.0.1:1729") if orch else "http://127.0.0.1:1729",
		"music_dir": getattr(orch, "initial_dir", None) if orch else None,
	}
