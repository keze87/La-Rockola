"""
Proveedores de inyección de dependencias para FastAPI.
Permite desacoplar el estado global, facilitando tests unitarios con mocks aislados.
"""

from __future__ import annotations

from typing import Any

_global_state: Any = None
_global_mpv: Any = None
_global_manager: Any = None
_global_db_path: Any = None


def set_global_state(state: Any) -> None:
	"""Asigna el estado global del reproductor para inyección en FastAPI."""
	global _global_state
	_global_state = state
	import sys

	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "state"):
		srv.state = state


def get_state() -> Any:
	"""Retorna la instancia activa del estado de la aplicación."""
	import sys

	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "state"):
		return srv.state
	return _global_state


def set_global_mpv(mpv: Any) -> None:
	"""Asigna el controlador MPV activo."""
	global _global_mpv
	_global_mpv = mpv


def get_mpv() -> Any:
	"""Retorna el controlador MPV activo."""
	return _global_mpv


def set_global_manager(manager: Any) -> None:
	"""Asigna el ConnectionManager activo de WebSockets."""
	global _global_manager
	_global_manager = manager
	import sys

	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "manager"):
		srv.manager = manager


def get_manager() -> Any:
	"""Retorna el ConnectionManager activo."""
	import sys

	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "manager"):
		return srv.manager
	return _global_manager


def set_db_path(db_path: Any) -> None:
	"""Asigna la ruta de la base de datos activa."""
	global _global_db_path
	_global_db_path = db_path
	import sys

	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "DB_PATH"):
		srv.DB_PATH = str(db_path) if db_path else None


def get_db_path() -> Any:
	"""Retorna la ruta de la base de datos activa, priorizando monkeypatch en server.DB_PATH."""
	import sys

	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "DB_PATH") and srv.DB_PATH is not None:
		return srv.DB_PATH
	return _global_db_path


def get_db() -> Any:
	"""Generador de conexión de base de datos para Depends() de FastAPI."""
	from app.db.database import get_db_connection

	with get_db_connection() as conn:
		yield conn


def get_settings() -> Any:
	"""Retorna la configuración activa de la aplicación."""
	from app.core.config import get_settings as _get_settings

	return _get_settings()
