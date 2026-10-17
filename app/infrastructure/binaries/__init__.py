"""
Paquete de gestión e instalación automática de binarios externos (mpv, ffmpeg, fpcalc, yt-dlp).
"""

from app.infrastructure.binaries.manager import (
	build_frontend,
	check_internet_async,
	download_file,
	ensure_display_env,
	extract_archive_binary,
	fetch_github_release_assets,
	find_binary,
	get_clean_env,
	get_default_install_dir,
	is_internet_available,
	is_rockola_managed,
	mark_rockola_managed,
	resolve_platform_and_arch,
)

__all__ = [
	"build_frontend",
	"check_internet_async",
	"download_file",
	"ensure_display_env",
	"extract_archive_binary",
	"fetch_github_release_assets",
	"find_binary",
	"get_clean_env",
	"get_default_install_dir",
	"is_internet_available",
	"is_rockola_managed",
	"mark_rockola_managed",
	"resolve_platform_and_arch",
]
