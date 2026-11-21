"""
Controlador nativo de audio para Android respaldado por Media3 ExoPlayer (Kotlin)
en lugar de MPV o el <audio> del WebView.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("RockolaCarpincho")


def resolve_native_android_player() -> Any | None:
	"""Obtiene la instancia activa de AndroidAudioPlayer desde la JVM vía Chaquopy."""
	try:
		from java import jclass

		cls = jclass("ar.carpincho.rockola.AndroidAudioPlayer")
		return cls.getActiveInstance()
	except Exception as exc:
		logger.debug(f"AndroidAudioPlayer no disponible en este entorno: {exc}")
		return None


class _KotlinCallbackBridge:
	"""Adaptador de callbacks síncronos de ExoPlayer hacia el event loop de Python."""

	def __init__(self, controller: AndroidPlayerController) -> None:
		self._ctrl = controller

	def on_position(self, pos_sec: float, dur_sec: float) -> None:
		self._ctrl._emit("time_update", float(pos_sec))
		if dur_sec and float(dur_sec) > 0:
			self._ctrl._emit("duration_update", float(dur_sec))

	def on_duration(self, dur_sec: float) -> None:
		if dur_sec and float(dur_sec) > 0:
			self._ctrl._emit("duration_update", float(dur_sec))

	def on_pause_changed(self, paused: bool) -> None:
		self._ctrl._emit("pause_update", bool(paused))

	def on_eof(self) -> None:
		self._ctrl._emit("song_ended")


class AndroidPlayerController:
	"""Implementa la interfaz de AsyncMpvController delegando en AndroidAudioPlayer (ExoPlayer)."""

	def __init__(
		self,
		callbacks: dict[str, Any] | None = None,
		state_ref: Any = None,
		native_player: Any = None,
	) -> None:
		self.callbacks = callbacks or {}
		self.state_ref = state_ref
		self._native = native_player
		self._loop: asyncio.AbstractEventLoop | None = None
		self._bridge = _KotlinCallbackBridge(self)
		self.socket_path: str | None = None
		self.is_windows: bool = False
		self.has_display: bool = False
		self.is_running: bool = False

	@property
	def ipc_path(self) -> str | None:
		return None

	def _ensure_native(self) -> Any | None:
		if self._native is None:
			self._native = resolve_native_android_player()
			if self._native is not None:
				self._native.setPythonCallbackHandler(self._bridge)
		return self._native

	def _emit(self, event_name: str, *args: Any) -> None:
		cb = self.callbacks.get(event_name)
		if cb is None:
			return

		def _invoke() -> None:
			try:
				res = cb(*args)
				if inspect.isawaitable(res):
					asyncio.ensure_future(res)
			except Exception as exc:
				logger.debug(f"Error en callback Android '{event_name}': {exc}")

		if self._loop and self._loop.is_running():
			self._loop.call_soon_threadsafe(_invoke)
		else:
			_invoke()

	async def start(self, is_restart: bool = False, state_ref: Any = None) -> None:
		"""Registra el callback handler en ExoPlayer y marca el controlador activo."""
		if state_ref is not None:
			self.state_ref = state_ref
		try:
			self._loop = asyncio.get_running_loop()
		except RuntimeError:
			self._loop = None

		native = self._ensure_native()
		if native is not None:
			native.setPythonCallbackHandler(self._bridge)
			self.is_running = True

	async def stop(self) -> None:
		"""Desconecta callbacks y detiene la reproducción activa."""
		self.is_running = False
		if self._native is not None:
			try:
				self._native.setPythonCallbackHandler(None)
				self._native.stopPlayback()
			except Exception:
				pass

	async def command(self, *args: Any) -> None:
		"""Compatibilidad de comandos genéricos (loadfile, seek, etc.)."""
		if not args:
			return
		cmd = str(args[0])
		if cmd == "loadfile" and len(args) > 1:
			await self.load_file(str(args[1]))
		elif cmd == "seek" and len(args) > 1:
			mode = str(args[2]) if len(args) > 2 else "relative"
			if mode == "absolute":
				await self.seek_absolute(float(args[1]))
			else:
				await self.seek_relative(float(args[1]))
		elif cmd == "stop":
			await self.stop_playback()

	async def set_property(self, name: str, value: Any) -> None:
		if name == "pause":
			await self.set_pause(bool(value))
		elif name == "volume":
			await self.set_volume(float(value))
		elif name == "mute":
			await self.set_mute(bool(value))

	async def load_file(self, path: str | Path) -> None:
		native = self._ensure_native()
		if native is not None:
			native.loadFile(str(path))

	async def set_pause(self, paused: bool) -> None:
		native = self._ensure_native()
		if native is not None:
			native.setPause(bool(paused))

	async def set_volume(self, volume: float) -> None:
		native = self._ensure_native()
		if native is not None:
			native.setVolume(float(volume))

	async def set_mute(self, muted: bool) -> None:
		native = self._ensure_native()
		if native is not None:
			native.setMute(bool(muted))

	async def seek_relative(self, amount: float) -> None:
		native = self._ensure_native()
		if native is not None:
			native.seekRelative(float(amount))

	async def seek_absolute(self, position: float) -> None:
		native = self._ensure_native()
		if native is not None:
			native.seekAbsolute(float(position))

	async def toggle_fullscreen(self) -> None:
		"""No-op en Android (fullscreen lo maneja SystemBars en Capacitor)."""

	async def set_force_window(self, visible: bool) -> None:
		"""No-op en Android."""

	async def add_subtitle(self, sub_path: str | Path) -> None:
		"""No-op en Android."""

	async def stop_playback(self) -> None:
		native = self._ensure_native()
		if native is not None:
			native.stopPlayback()
