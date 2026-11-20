"""
NullMpvController: controlador nulo de MPV para servidores headless o dispositivos Android
donde el audio se reproduce directamente desde el navegador/WebView (listenLocally).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class NullMpvController:
	"""Implementa la interfaz pública asíncrona de AsyncMpvController sin lanzar procesos."""

	def __init__(self, callbacks: dict[str, Any] | None = None, state_ref: Any = None) -> None:
		self.callbacks = callbacks or {}
		self.state_ref = state_ref
		self.socket_path: str | None = None
		self.is_windows: bool = False
		self.has_display: bool = False
		self.is_running: bool = False

	@property
	def ipc_path(self) -> str | None:
		"""Ruta del socket IPC (siempre None en modo sin MPV)."""
		return None

	async def start(self, is_restart: bool = False, state_ref: Any = None) -> None:
		"""No-op en modo sin MPV."""
		if state_ref is not None:
			self.state_ref = state_ref

	async def stop(self) -> None:
		"""No-op en modo sin MPV."""

	async def command(self, *args: Any) -> None:
		"""No-op en modo sin MPV."""

	async def set_property(self, name: str, value: Any) -> None:
		"""No-op en modo sin MPV."""

	async def load_file(self, path: str | Path) -> None:
		"""No-op en modo sin MPV."""

	async def set_pause(self, paused: bool) -> None:
		"""No-op en modo sin MPV."""

	async def set_volume(self, volume: float) -> None:
		"""No-op en modo sin MPV."""

	async def set_mute(self, muted: bool) -> None:
		"""No-op en modo sin MPV."""

	async def seek_relative(self, amount: float) -> None:
		"""No-op en modo sin MPV."""

	async def seek_absolute(self, position: float) -> None:
		"""No-op en modo sin MPV."""

	async def toggle_fullscreen(self) -> None:
		"""No-op en modo sin MPV."""

	async def set_force_window(self, visible: bool) -> None:
		"""No-op en modo sin MPV."""

	async def add_subtitle(self, sub_path: str | Path) -> None:
		"""No-op en modo sin MPV."""

	async def stop_playback(self) -> None:
		"""No-op en modo sin MPV."""
