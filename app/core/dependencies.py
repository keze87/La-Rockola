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


def get_state() -> Any:
	"""Retorna la instancia activa del estado de la aplicación."""
	global _global_state
	if _global_state is None:
		from app.engine.state import APIState

		_global_state = APIState()
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


def get_manager() -> Any:
	"""Retorna el ConnectionManager activo, instanciándolo como singleton si no existe."""
	global _global_manager
	if _global_manager is None:
		from app.api.websocket import ConnectionManager

		_global_manager = ConnectionManager()
	return _global_manager


def set_db_path(db_path: Any) -> None:
	"""Asigna la ruta de la base de datos activa."""
	global _global_db_path
	_global_db_path = db_path


def get_db_path() -> Any:
	"""Retorna la ruta de la base de datos activa."""
	if _global_db_path is None:
		from app.core.config import get_carpincho_data_dir

		return get_carpincho_data_dir() / "rockola.db"
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
