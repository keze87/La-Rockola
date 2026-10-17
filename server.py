#!/usr/bin/env python3
"""
Punto de entrada principal del servidor de La Rockola del Carpincho.
Sin efectos colaterales en importación ni proxies de monkeypatching.
"""

from __future__ import annotations

from app.cli.entrypoint import (
	build_frontend,
	configure_console_encoding,
	enable_system_site_packages,
	main,
)
from app.main import app

__all__ = [
	"app",
	"build_frontend",
	"configure_console_encoding",
	"enable_system_site_packages",
	"main",
]

if __name__ == "__main__":
	configure_console_encoding()
	enable_system_site_packages()
	main()
