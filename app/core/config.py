"""
Configuración tipada con Pydantic Settings para La Rockola del Carpincho.
Maneja rockola_config.json, variables de entorno, defaults y argumentos de CLI.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("RockolaCarpincho")

DEFAULT_WEATHER_LOCATION = "San Miguel de Tucumán"

DEFAULT_CONFIG: dict[str, Any] = {
	"music_dir": "~/Music",
	"music_dir2": None,
	"port": 1729,
	"host": "0.0.0.0",
	"open_browser": True,
	"url": None,
	"weather_location": DEFAULT_WEATHER_LOCATION,
	"log_level": "INFO",
}


def get_carpincho_data_dir() -> Path:
	"""Determina el directorio de datos (DB, config, etc.) respetando portabilidad y OS."""
	if getattr(sys, "frozen", False):
		# Modo portable empaquetado: chequeamos si estamos adentro de un AppImage en Linux
		appimage_path = os.environ.get("APPIMAGE")
		if appimage_path:
			appimage_dir = Path(appimage_path).resolve().parent
			try:
				test_file = appimage_dir / ".carpincho_write_test"
				test_file.touch(exist_ok=True)
				test_file.unlink(missing_ok=True)
				portable_db = appimage_dir / "DB"
				if portable_db.is_dir():
					return portable_db
			except OSError:
				pass

		exe_dir = Path(sys.executable).parent
		# Si la carpeta del ejecutable es escribible, usamos la carpeta DB que está al lado
		try:
			test_file = exe_dir / ".carpincho_write_test"
			test_file.touch(exist_ok=True)
			test_file.unlink(missing_ok=True)
			db_dir = exe_dir / "DB"
		except OSError:
			# Si está en una ruta de solo lectura, usamos el directorio de datos del usuario
			if sys.platform == "win32":
				base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
			elif sys.platform == "darwin":
				base = Path.home() / "Library" / "Application Support"
			else:
				base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
			db_dir = base / "carpincho" / "DB"
	else:
		# En desarrollo buscamos la carpeta DB en la raíz del repositorio
		root_dir = Path(__file__).resolve().parents[2]
		db_dir = root_dir / "DB"

	db_dir.mkdir(parents=True, exist_ok=True)
	return db_dir


def get_config_path(custom_path: str | Path | None = None) -> Path:
	"""Devuelve la ruta absoluta al archivo de configuración."""
	if custom_path:
		return Path(custom_path).expanduser().resolve()
	return get_carpincho_data_dir() / "rockola_config.json"


def load_config(config_path: Path | None = None) -> dict[str, Any]:
	"""Carga la configuración desde el JSON persistente o devuelve los valores por defecto."""
	path = config_path or get_config_path()
	cfg = dict(DEFAULT_CONFIG)
	if path.is_file():
		try:
			with open(path, "r", encoding="utf-8") as f:
				data = json.load(f)
				if isinstance(data, dict):
					cfg.update(data)
		except Exception as e:
			logger.warning(f"No se pudo leer {path}, usamos los valores por defecto: {e}")
	return cfg


def save_config(config_path: Path, cfg: dict[str, Any]) -> None:
	"""Guarda la configuración en disco de forma atómica para no corromper el JSON."""
	try:
		config_path.parent.mkdir(parents=True, exist_ok=True)
		temp_file = config_path.parent / f".tmp_{config_path.name}"
		with open(temp_file, "w", encoding="utf-8") as f:
			json.dump(cfg, f, indent=4, ensure_ascii=False)
		temp_file.replace(config_path)
	except Exception as e:
		logger.error(f"Error guardando la configuración en {config_path}: {e}")


class Settings(BaseSettings):
	"""Configuración centralizada y tipada de La Rockola."""

	model_config = SettingsConfigDict(
		env_prefix="ROCKOLA_",
		case_sensitive=False,
		extra="ignore",
	)

	music_dir: str = Field(default="~/Music", description="Carpeta principal de música")
	music_dir2: str | None = Field(default=None, description="Carpeta secundaria de música")
	port: int = Field(default=1729, description="Puerto del servidor HTTP")
	host: str = Field(default="0.0.0.0", description="IP de escucha del servidor")
	open_browser: bool = Field(default=True, description="Abrir navegador automáticamente al iniciar")
	url: str | None = Field(default=None, description="URL pública o personalizada del servidor")
	weather_location: str = Field(
		default=DEFAULT_WEATHER_LOCATION,
		description="Ubicación para pronóstico meteorológico en la radio",
	)
	log_level: str = Field(default="INFO", description="Nivel de logs (DEBUG, INFO, WARNING, ERROR)")
	debug: bool = Field(default=False, description="Modo debug habilitado")

	@classmethod
	def from_config_file(cls, path: Path | None = None) -> Settings:
		"""Instancia los settings combinando el archivo JSON con defaults y variables de entorno."""
		loaded = load_config(path)
		return cls(**loaded)

	def merge_cli_args(self, args: argparse.Namespace) -> Settings:
		"""Combina los argumentos pasados por línea de comandos (CLI) con prioridad sobre el config."""
		data = self.model_dump()
		if getattr(args, "host", None) is not None:
			data["host"] = args.host
		if getattr(args, "port", None) is not None:
			data["port"] = args.port
		if getattr(args, "url", None) is not None:
			data["url"] = args.url
		if getattr(args, "dir", None) is not None:
			data["music_dir"] = args.dir
		if getattr(args, "dir2", None) is not None:
			data["music_dir2"] = args.dir2
		if getattr(args, "weather_location", None) is not None:
			data["weather_location"] = args.weather_location
		if getattr(args, "open_browser", None) is not None:
			data["open_browser"] = args.open_browser
		if getattr(args, "log_level", None) is not None:
			data["log_level"] = args.log_level
		if getattr(args, "debug", False):
			data["debug"] = True
			data["log_level"] = "DEBUG"

		return Settings(**data)


_global_settings: Settings | None = None


def get_settings() -> Settings:
	"""Retorna la instancia global de configuración o una nueva por defecto."""
	global _global_settings
	if _global_settings is None:
		_global_settings = Settings.from_config_file()
	return _global_settings


def set_settings(settings: Settings) -> None:
	"""Actualiza la instancia global de configuración."""
	global _global_settings
	_global_settings = settings


from app.core.network import (  # noqa: F401
	get_local_ip,
	get_server_urls,
	get_url_subpath,
	normalize_url,
)
