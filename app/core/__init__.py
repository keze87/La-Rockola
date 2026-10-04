"""
Módulo core de La Rockola del Carpincho.
Contiene la configuración tipada, logging unificado e inyección de dependencias.
"""

from app.core.config import Settings, get_config_path, get_settings, load_config, save_config
from app.core.dependencies import get_db, get_state
from app.core.logging import configure_logging, get_logger

__all__ = [
	"Settings",
	"configure_logging",
	"get_config_path",
	"get_db",
	"get_logger",
	"get_settings",
	"get_state",
	"load_config",
	"save_config",
]
