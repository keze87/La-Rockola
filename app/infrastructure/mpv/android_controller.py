"""
Controlador nativo de audio para Android respaldado por Media3 ExoPlayer (Kotlin)
en lugar de MPV o el <audio> del WebView.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
		pos = float(pos_sec)
		dur = float(dur_sec) if dur_sec else 0.0
		self._ctrl._emit("time_update", pos)
		if dur > 0:
			self._ctrl._emit("duration_update", dur)
		self._ctrl.sync_position(pos, dur)

	def on_duration(self, dur_sec: float) -> None:
		if dur_sec and float(dur_sec) > 0:
			self._ctrl._emit("duration_update", float(dur_sec))

	def on_pause_changed(self, paused: bool) -> None:
		self._ctrl._emit("pause_update", bool(paused))

	def on_eof(self) -> None:
		self._ctrl._emit("song_ended")

	def on_playback_error(self, message: str = "") -> None:
		logger.error(f"Error persistente de reproducción en ExoPlayer: {message}")
		self._ctrl._emit("pause_update", True)


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
		self.native_error: str | None = None
		self._loop: asyncio.AbstractEventLoop | None = None
		self._bridge = _KotlinCallbackBridge(self)
		self.socket_path: str | None = None
		self.is_windows: bool = False
		self.has_display: bool = False
		self.is_running: bool = False
		self._last_notif_sig: tuple[Any, ...] | None = None
		self._last_pos_sent_at: float = 0.0
		self._last_pos_sec: float = -1.0
		self._last_dur_sec: float = -1.0
		self._last_pos_paused: bool | None = None

	def sync_notification_from_state(self, state: Any) -> None:
		"""Sincroniza la notificación MediaStyle nativa directamente desde el estado del orquestador."""
		native = self._ensure_native()
		if native is None or state is None:
			return

		track_path = getattr(state, "current_track", None)
		paused = bool(getattr(state, "mpv_paused", True)) if track_path else True
		duration_sec = float(getattr(state, "duration", 0.0) or 0.0)
		position_sec = float(getattr(state, "time_pos", 0.0) or 0.0)
		is_radio = bool(getattr(state, "is_playing_radio_announcement", False))

		title = "La Rockola del Carpincho"
		artist = "En espera"
		cover_url: str | None = None

		if track_path:
			if is_radio:
				title = "Carpincho Locutor"
				artist = "La Rockola del Carpincho"
			else:
				info = None
				for t in getattr(state, "tracks_cache", []) or []:
					if t.get("path") == track_path:
						info = t
						break
				if info is None:
					info = (getattr(state, "url_metadata", {}) or {}).get(track_path)
				title = (
					(info.get("display_title") or info.get("title") or Path(str(track_path)).stem)
					if info
					else Path(str(track_path)).stem
				)
				artist = (info.get("display_artist") or info.get("artist") or "Desconocido") if info else "Desconocido"
				if not str(track_path).startswith(("http://", "https://")):
					port = int(getattr(state, "server_port", 1729) or 1729)
					cover_url = f"http://127.0.0.1:{port}/cover?path={quote(str(track_path), safe='')}&size=512"

		path_to_id = getattr(state, "path_to_id", {}) or {}
		favorites = getattr(state, "favorites", []) or []
		track_id = path_to_id.get(track_path, track_path) if track_path else None
		is_favorite = bool(track_path and (track_id in favorites or track_path in favorites))
		is_pause_after = bool(track_path and getattr(state, "pause_after_path", None) == track_path)

		dur_ms = int(max(0.0, duration_sec) * 1000)
		pos_ms = int(max(0.0, position_sec) * 1000)
		sig = (title, artist, paused, cover_url, track_path, dur_ms, is_favorite, is_pause_after)
		if sig == self._last_notif_sig:
			return

		self._last_notif_sig = sig
		self._last_pos_sent_at = time.monotonic()
		self._last_pos_sec = position_sec
		self._last_dur_sec = duration_sec
		self._last_pos_paused = paused
		try:
			native.updateNotification(
				title,
				artist,
				paused,
				cover_url,
				track_path,
				dur_ms,
				pos_ms,
				is_favorite,
				is_pause_after,
			)
		except Exception as exc:
			logger.debug(f"Error actualizando notificación nativa Android: {exc}")

	def sync_position(self, pos_sec: float, dur_sec: float, paused: bool | None = None) -> None:
		"""Actualiza el seekbar de la notificación nativa con throttling de 3s o salto de seek."""
		native = self._ensure_native()
		if native is None:
			return

		resolved_paused = bool(getattr(self.state_ref, "mpv_paused", False)) if paused is None else bool(paused)
		resolved_dur = (
			float(dur_sec) if dur_sec and dur_sec > 0 else float(getattr(self.state_ref, "duration", 0.0) or 0.0)
		)
		now = time.monotonic()

		is_first = self._last_pos_paused is None
		paused_changed = resolved_paused != self._last_pos_paused
		dur_changed = abs(resolved_dur - self._last_dur_sec) > 0.5
		jumped = abs(pos_sec - self._last_pos_sec) > 1.5
		elapsed = now - self._last_pos_sent_at >= 3.0

		if not (is_first or paused_changed or dur_changed or jumped or elapsed):
			return

		self._last_pos_sent_at = now
		self._last_pos_sec = pos_sec
		self._last_dur_sec = resolved_dur
		self._last_pos_paused = resolved_paused
		try:
			native.updateNotificationPosition(
				int(max(0.0, resolved_dur) * 1000),
				int(max(0.0, pos_sec) * 1000),
				resolved_paused,
			)
		except Exception as exc:
			logger.debug(f"Error actualizando progreso de notificación Android: {exc}")

	@property
	def ipc_path(self) -> str | None:
		return None

	def _ensure_native(self) -> Any | None:
		active = resolve_native_android_player()
		if active is not None:
			if active is not self._native:
				self._native = active
				try:
					self._native.setPythonCallbackHandler(self._bridge)
				except Exception as exc:
					logger.warning("No se pudo enlazar callback handler al AndroidAudioPlayer: %s", exc)
			self.native_error = None
			self.is_running = True
			return self._native

		if self._native is None:
			self.native_error = "Reproductor nativo Android (ExoPlayer) no disponible."
			return None

		from app.infrastructure.binaries.manager import is_android

		if is_android():
			self._native = None
			self.is_running = False
			self.native_error = "Reproductor nativo Android (ExoPlayer) no disponible."
			return None

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
