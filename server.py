#!/usr/bin/env python3
"""
Punto de entrada principal del servidor de La Rockola del Carpincho.
Sin efectos colaterales en importación ni proxies de monkeypatching.
"""

from __future__ import annotations

from app.cli.entrypoint import main
from app.main import app

__all__ = ["app", "main"]

if __name__ == "__main__":
	main()
