"""
scripts package — Utilidades y scripts de empaquetado/instalación para La Rockola del Carpincho.
"""

import sys

from . import binary_utils, ffmpeg_installer, fpcalc_installer, mpv_installer, radio_announcer, ytdlp_installer

# Provide top-level module aliases in sys.modules pointing to the exact same module instances
sys.modules["binary_utils"] = binary_utils
sys.modules["mpv_installer"] = mpv_installer
sys.modules["ytdlp_installer"] = ytdlp_installer
sys.modules["fpcalc_installer"] = fpcalc_installer
sys.modules["ffmpeg_installer"] = ffmpeg_installer
sys.modules["radio_announcer"] = radio_announcer

__all__ = [
	"binary_utils",
	"ffmpeg_installer",
	"fpcalc_installer",
	"mpv_installer",
	"radio_announcer",
	"ytdlp_installer",
]
