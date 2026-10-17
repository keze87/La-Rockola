"""
Contenedor explícito de inyección de dependencias para La Rockola del Carpincho.
Reemplaza los singletons sueltos y proxies dinámicos por un grafo de dependencias claro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_carpincho_data_dir, get_settings


@dataclass
class AppContainer:
	"""Contenedor central de servicios, repositorios y estado de aplicación."""

	settings: Settings = field(default_factory=get_settings)
	db_path: Path = field(default_factory=lambda: get_carpincho_data_dir() / "rockola.db")
	orchestrator: Any = None
	ws_manager: Any = None
	mpv: Any = None

	def ensure_orchestrator(self) -> Any:
		"""Inicializa perezosamente el PlaybackOrchestrator si aún no fue instanciado."""
		if self.orchestrator is None:
			from app.domain.playback.orchestrator import PlaybackOrchestrator

			self.orchestrator = PlaybackOrchestrator(
				initial_dir=self.settings.music_dir,
				secondary_dir=self.settings.music_dir2,
				open_browser=self.settings.open_browser,
				db_path=self.db_path,
			)
		return self.orchestrator

	def ensure_ws_manager(self) -> Any:
		"""Inicializa perezosamente el ConnectionManager de WebSockets si aún no fue instanciado."""
		if self.ws_manager is None:
			from app.api.websocket import ConnectionManager

			self.ws_manager = ConnectionManager()
		return self.ws_manager


_active_container: AppContainer | None = None


def get_container() -> AppContainer:
	"""Obtiene el contenedor activo o inicializa uno por defecto."""
	global _active_container
	if _active_container is None:
		_active_container = AppContainer()
	return _active_container


def set_container(container: AppContainer | None) -> None:
	"""Reemplaza el contenedor activo (ideal para aislamiento en tests)."""
	global _active_container
	_active_container = container


def get_state() -> Any:
	"""Devuelve el PlaybackOrchestrator activo inicializándolo perezosamente si es necesario."""
	return get_container().ensure_orchestrator()


def get_manager() -> Any:
	"""Devuelve el ConnectionManager activo inicializándolo perezosamente si es necesario."""
	return get_container().ensure_ws_manager()


def get_db_path() -> Path:
	"""Devuelve la ruta de la base de datos SQLite activa."""
	return get_container().db_path


def get_db() -> Any:
	"""Generador de conexiones SQLite para inyección de dependencias en FastAPI (Depends(get_db))."""
	from app.infrastructure.db.connection import get_db_connection

	with get_db_connection(get_db_path()) as conn:
		yield conn
