"""
Módulo core de La Rockola del Carpincho.
Contiene la configuración tipada, logging unificado e inyección de dependencias.
"""

from app.core.config import Settings, get_config_path, get_settings, load_config, save_config
from app.core.container import AppContainer, get_container, get_db, get_state, set_container
from app.core.logging import configure_logging, get_logger

__all__ = [
	"AppContainer",
	"Settings",
	"configure_logging",
	"get_config_path",
	"get_container",
	"get_db",
	"get_logger",
	"get_settings",
	"get_state",
	"load_config",
	"save_config",
	"set_container",
]
