"""
scripts package — Utilidades y scripts de empaquetado/instalación para La Rockola del Carpincho.
"""

import sys
from . import mpv_installer, ytdlp_installer

# Provide top-level module aliases in sys.modules pointing to the exact same module instances
sys.modules["mpv_installer"] = mpv_installer
sys.modules["ytdlp_installer"] = ytdlp_installer

__all__ = ["mpv_installer", "ytdlp_installer"]
