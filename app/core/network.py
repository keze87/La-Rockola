"""
Utilidades de red y resolución de URLs para La Rockola del Carpincho.
Manejo de IP local, rutas relativas/subpaths y formateo de URLs de acceso.
"""

from __future__ import annotations

import re
import socket
from typing import Any
from urllib.parse import urlparse


def get_local_ip() -> str:
	"""Obtiene la dirección IP local de la máquina en la red LAN."""
	# Intentamos abrir un socket UDP contra un DNS público para descubrir la IP de salida
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(("8.8.8.8", 80))
		ip = s.getsockname()[0]
	except Exception:
		try:
			ip = socket.gethostbyname(socket.gethostname())
		except Exception:
			ip = "127.0.0.1"
	finally:
		s.close()
	return ip


def normalize_url(url: str | None) -> str | None:
	"""Normaliza una URL asegurando http/https y sin trailing slashes."""
	if not url:
		return None
	url = str(url).strip()
	if not url:
		return None
	if not re.match(r"^https?://", url, re.IGNORECASE):
		url = f"http://{url}"
	return url.rstrip("/")


def get_url_subpath(url: str | None) -> str:
	"""Extrae el subpath de una URL (ej: '/rockola')."""
	norm = normalize_url(url)
	if not norm:
		return ""
	path = urlparse(norm).path.rstrip("/")
	return path if (path.startswith("/") or not path) else f"/{path}"


def get_server_urls(host: str, port: int, custom_url: str | None = None) -> dict[str, Any]:
	"""Calcula las URLs disponibles para acceder a La Rockola en la red."""
	local_ip = get_local_ip()
	loopback_url = f"http://localhost:{port}"
	norm_custom = normalize_url(custom_url)

	if norm_custom:
		local_url = norm_custom
		network_url = norm_custom
	elif host in ("0.0.0.0", ""):
		display_ip = local_ip if local_ip != "127.0.0.1" else "localhost"
		local_url = f"http://{display_ip}:{port}"
		network_url = f"http://{local_ip}:{port}" if local_ip != "127.0.0.1" else None
	elif host in ("127.0.0.1", "localhost"):
		local_url = loopback_url
		network_url = None
	else:
		local_url = f"http://{host}:{port}"
		network_url = f"http://{host}:{port}"

	return {
		"custom_url": norm_custom,
		"local_ip": local_ip,
		"local_url": local_url,
		"network_url": network_url,
		"loopback_url": loopback_url,
	}
