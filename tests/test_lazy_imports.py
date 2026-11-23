"""Verifica que app.main difiera imports pesados (edge_tts, aiohttp) al arranque."""

from __future__ import annotations

import subprocess
import sys


def test_app_main_defers_edge_tts_and_aiohttp_at_import_time() -> None:
	code = """
import sys
import app.main  # noqa: F401
assert "edge_tts" not in sys.modules, "edge_tts no debe importarse al importar app.main"
assert "aiohttp" not in sys.modules, "aiohttp no debe importarse al importar app.main"
"""
	res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
	assert res.returncode == 0, res.stderr or res.stdout
