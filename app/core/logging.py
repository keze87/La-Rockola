"""
Configuración unificada de logs con colores ANSI e impronta de La Rockola del Carpincho.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

# Códigos de escape ANSI para colorear logs en terminales compatibles
ANSI_COLORS = {
	"key": "\033[94m",  # Azul
	"string": "\033[92m",  # Verde
	"number": "\033[93m",  # Amarillo
	"boolean": "\033[95m",  # Magenta
	"null": "\033[91m",  # Rojo
	"reset": "\033[0m",  # Reset
	"DEBUG": "\033[36m",  # Cyan
	"INFO": "\033[32m",  # Verde
	"WARNING": "\033[33m",  # Amarillo
	"ERROR": "\033[31m",  # Rojo
	"CRITICAL": "\033[1;31m",  # Rojo negrita
}

logger = logging.getLogger("RockolaCarpincho")


def truncate_text(text: Any, max_len: int) -> str:
	"""Trunca un texto agregando elipsis si excede la longitud máxima indicada."""
	s = str(text)
	return s[: max_len - 1] + "…" if len(s) > max_len else s


def highlight_json(json_data: Any) -> str:
	"""Aplica resaltado de sintaxis ANSI a un string o estructura JSON para logs legibles."""
	if isinstance(json_data, str):
		try:
			parsed = json.loads(json_data)
		except json.JSONDecodeError as e:
			return f"Invalid JSON: {e}"
	else:
		parsed = json_data

	formatted_json = json.dumps(parsed, indent=2, ensure_ascii=False)

	pattern = r'("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b)|(\bnull\b)'

	def replacer(match: re.Match[str]) -> str:
		if match.group(1):  # Clave
			key_str = match.group(1)
			colon_idx = key_str.rfind(":")
			return ANSI_COLORS["key"] + key_str[:colon_idx] + ANSI_COLORS["reset"] + key_str[colon_idx:]
		elif match.group(2):  # String
			return ANSI_COLORS["string"] + match.group(2) + ANSI_COLORS["reset"]
		elif match.group(3):  # Número
			return ANSI_COLORS["number"] + match.group(3) + ANSI_COLORS["reset"]
		elif match.group(4):  # Booleano
			return ANSI_COLORS["boolean"] + match.group(4) + ANSI_COLORS["reset"]
		elif match.group(5):  # Null
			return ANSI_COLORS["null"] + match.group(5) + ANSI_COLORS["reset"]
		return match.group(0)

	return re.sub(pattern, replacer, formatted_json)


def configure_logging(debug: bool = False, level: str | int | None = None) -> logging.Logger:
	"""Configura el nivel de logging global y silencia bibliotecas ruidosas."""
	if debug:
		target_level = logging.DEBUG
	elif level is not None:
		if isinstance(level, str):
			target_level = getattr(logging, level.strip().upper(), logging.INFO)
		else:
			target_level = int(level)
	else:
		target_level = logging.INFO

	is_debug = target_level <= logging.DEBUG
	logging.basicConfig(
		level=target_level,
		format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
		force=True,
	)

	# Silenciamos bibliotecas externas ruidosas
	logging.getLogger("numba").setLevel(logging.WARNING)
	logging.getLogger("llvmlite").setLevel(logging.WARNING)
	logging.getLogger("PIL").setLevel(logging.WARNING)
	logging.getLogger("uvicorn.access").setLevel(logging.DEBUG if is_debug else logging.WARNING)

	return logging.getLogger("RockolaCarpincho")


def get_logger(name: str = "RockolaCarpincho") -> logging.Logger:
	"""Obtiene un logger tipado para los componentes de la aplicación."""
	return logging.getLogger(name)
