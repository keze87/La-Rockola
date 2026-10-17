"""
Adaptador D-Bus / MPRIS para integración con controles multimedia del sistema operativo.
Encapsula el registro de bus, emisión de cambios de propiedades y despacho de comandos.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from app.infrastructure.binaries.manager import ensure_display_env

logger = logging.getLogger("RockolaCarpincho")

DBUS_AVAILABLE = False
MessageBus: Any = None
if sys.platform == "linux":
	try:
		from dbus_next import Variant
		from dbus_next.aio import MessageBus as _MessageBus
		from dbus_next.constants import PropertyAccess
		from dbus_next.service import ServiceInterface, dbus_property, method

		MessageBus = _MessageBus
		DBUS_AVAILABLE = True
	except ImportError:
		pass

if not DBUS_AVAILABLE:

	class Variant:  # type: ignore[no-redef]
		"""Fallback Variant para cuando dbus_next no está disponible."""

		def __init__(self, signature: str, value: object) -> None:
			self.signature = signature
			self.value = value

		def __repr__(self) -> str:
			return f"Variant('{self.signature}', {self.value!r})"

		def __eq__(self, other: object) -> bool:
			if hasattr(other, "signature") and hasattr(other, "value"):
				return self.signature == other.signature and self.value == other.value
			return False

	class PropertyAccess:  # type: ignore[no-redef]
		READ = "read"
		WRITE = "write"
		READWRITE = "readwrite"

	def dbus_property(access: Any = None) -> Any:
		def decorator(fn: Any) -> Any:
			if hasattr(fn, "setter"):
				return fn
			return property(fn)

		return decorator

	def method() -> Any:
		def decorator(fn: Any) -> Any:
			return fn

		return decorator

	class ServiceInterface:  # type: ignore[no-redef]
		def __init__(self, name: str) -> None:
			self.name = name


b = s = d = x = o = str


def build_mpris_metadata(
	track_or_state: Any,
	server_url: str = "",
	variant_cls: Any = None,
	cover_resolver: Any = None,
) -> dict[str, Any]:
	"""Construye el diccionario de metadatos para MPRIS (MediaPlayer2.Player.Metadata)."""
	v_cls = variant_cls or Variant
	if cover_resolver is None:
		try:
			from app.domain.library.service import get_cover_art_uri

			if isinstance(track_or_state, dict):
				cover_resolver = get_cover_art_uri
			else:
				cover_resolver = lambda p: get_cover_art_uri(p, state_ref=track_or_state)
		except Exception:
			cover_resolver = None

	if isinstance(track_or_state, dict):
		track_path = track_or_state.get("path", "")
		title = track_or_state.get("title") or track_or_state.get("display_title", "Desconocido")
		artist = track_or_state.get("artist") or track_or_state.get("display_artist", "Desconocido")
		album = track_or_state.get("album", "La Rockola del Carpincho")
		dur_val = track_or_state.get("duration", 0)
		dur_usec = int(dur_val * 1000000) if dur_val else 0

		meta: dict[str, Any] = {
			"mpris:trackid": v_cls(
				"o",
				"/org/mpris/MediaPlayer2/TrackList/Track0"
				if track_path
				else "/org/mpris/MediaPlayer2/TrackList/NoTrack",
			),
			"xesam:title": v_cls("s", title),
			"xesam:artist": v_cls("as", [artist]),
			"xesam:album": v_cls("s", album),
			"mpris:length": v_cls("x", dur_usec),
		}
		if track_path:
			uri = track_path if track_path.startswith("http") else Path(track_path).resolve().as_uri()
			meta["xesam:url"] = v_cls("s", uri)
		cover_uri = track_or_state.get("cover_uri") or (
			cover_resolver(track_path) if (cover_resolver and track_path) else None
		)
		if cover_uri:
			meta["mpris:artUrl"] = v_cls("s", cover_uri)
		return meta

	state_obj = track_or_state
	current_track = getattr(state_obj, "current_track", None)
	if not current_track:
		return {"mpris:trackid": v_cls("o", "/org/mpris/MediaPlayer2/TrackList/NoTrack")}

	title = "Desconocido"
	artist = "Desconocido"
	album = "La Rockola del Carpincho"
	dur_usec = 0

	tracks_cache = getattr(state_obj, "tracks_cache", [])
	for t in tracks_cache:
		if t.get("path") == current_track:
			title = t.get("display_title", title)
			artist = t.get("display_artist", artist)
			album = t.get("album", album)
			break

	url_metadata = getattr(state_obj, "url_metadata", {})
	if current_track in url_metadata:
		meta_info = url_metadata[current_track]
		title = meta_info.get("display_title", title)
		artist = meta_info.get("display_artist", artist)
		album = meta_info.get("album", album)

	duration = getattr(state_obj, "duration", None)
	if duration:
		dur_usec = int(duration * 1000000)

	track_uri = current_track
	if track_uri and not track_uri.startswith("http"):
		try:
			track_uri = Path(track_uri).absolute().as_uri()
		except Exception:
			pass

	cover_uri = cover_resolver(current_track) if (cover_resolver and current_track) else None

	meta_dict = {
		"mpris:trackid": v_cls("o", "/org/mpris/MediaPlayer2/TrackList/Track0"),
		"xesam:title": v_cls("s", title),
		"xesam:artist": v_cls("as", [artist]),
		"xesam:album": v_cls("s", album),
		"mpris:length": v_cls("x", dur_usec),
	}
	if track_uri:
		meta_dict["xesam:url"] = v_cls("s", track_uri)
	if cover_uri:
		meta_dict["mpris:artUrl"] = v_cls("s", cover_uri)

	return meta_dict


class MPRISRoot(ServiceInterface):
	"""Nodo raíz de MPRIS org.mpris.MediaPlayer2."""

	def __init__(self) -> None:
		super().__init__("org.mpris.MediaPlayer2")

	@method()
	def Quit(self):
		pass

	@method()
	def Raise(self):
		pass

	@dbus_property(access=PropertyAccess.READ)
	def CanQuit(self) -> b:
		return False

	@dbus_property(access=PropertyAccess.READ)
	def Fullscreen(self) -> b:
		return False

	@dbus_property(access=PropertyAccess.READ)
	def CanSetFullscreen(self) -> b:
		return False

	@dbus_property(access=PropertyAccess.READ)
	def CanRaise(self) -> b:
		return False

	@dbus_property(access=PropertyAccess.READ)
	def HasTrackList(self) -> b:
		return False

	@dbus_property(access=PropertyAccess.READ)
	def Identity(self) -> s:
		return "La Rockola del Carpincho"

	@dbus_property(access=PropertyAccess.READ)
	def DesktopEntry(self) -> s:
		return "carpincho"

	@dbus_property(access=PropertyAccess.READ)
	def SupportedUriSchemes(self) -> "as":
		return ["file", "http", "https"]

	@dbus_property(access=PropertyAccess.READ)
	def SupportedMimeTypes(self) -> "as":
		return ["audio/mpeg", "audio/x-flac", "audio/ogg"]


class MPRISPlayer(ServiceInterface):
	"""Reproductor MPRIS org.mpris.MediaPlayer2.Player."""

	def __init__(self, state_ref: Any, command_handler: Any = None, cover_resolver: Any = None) -> None:
		super().__init__("org.mpris.MediaPlayer2.Player")
		self.state = state_ref
		self.command_handler = command_handler
		self.cover_resolver = cover_resolver

	def _dispatch(self, cmd: str, **kwargs: Any) -> None:
		if self.command_handler:
			asyncio.create_task(self.command_handler(cmd, **kwargs))
			return
		try:
			from app.api.commands import handle_command_endpoint
			from app.api.schemas import CommandRequest

			asyncio.create_task(handle_command_endpoint(CommandRequest(cmd=cmd, **kwargs)))
		except Exception as e:
			logger.debug(f"No se pudo despachar comando MPRIS {cmd}: {e}")

	@method()
	def Next(self):
		self._dispatch("skip")

	@method()
	def Previous(self):
		self._dispatch("prev")

	@method()
	def Pause(self):
		if not getattr(self.state, "mpv_paused", False):
			self._dispatch("pause")

	@method()
	def PlayPause(self):
		self._dispatch("pause")

	@method()
	def Stop(self):
		self._dispatch("stop")

	@method()
	def Play(self):
		if getattr(self.state, "mpv_paused", False):
			self._dispatch("pause")

	@method()
	def Seek(self, Offset: x):
		self._dispatch("seek", amount=Offset / 1000000.0)

	@method()
	def SetPosition(self, TrackId: o, Position: x):
		self._dispatch("seek_absolute", amount=Position / 1000000.0)

	@method()
	def OpenUri(self, Uri: s):
		self._dispatch("play", path=Uri)

	@dbus_property(access=PropertyAccess.READ)
	def PlaybackStatus(self) -> s:
		if not getattr(self.state, "current_track", None):
			return "Stopped"
		return "Paused" if getattr(self.state, "mpv_paused", False) else "Playing"

	@dbus_property(access=PropertyAccess.READ)
	def LoopStatus(self) -> s:
		return "None"

	@dbus_property(access=PropertyAccess.READ)
	def Rate(self) -> d:
		return 1.0

	@dbus_property(access=PropertyAccess.READ)
	def Shuffle(self) -> b:
		return False

	@dbus_property(access=PropertyAccess.READ)
	def Metadata(self) -> "a{sv}":
		return build_mpris_metadata(self.state, variant_cls=Variant, cover_resolver=self.cover_resolver)

	@dbus_property(access=PropertyAccess.READWRITE)
	def Volume(self) -> d:
		return getattr(self.state, "volume", 0) / 100.0

	@Volume.setter
	def Volume(self, val: d):
		self._dispatch("set_volume", vollevel=int(val * 100))

	@dbus_property(access=PropertyAccess.READ)
	def Position(self) -> x:
		return int(getattr(self.state, "time_pos", 0) * 1000000)

	@dbus_property(access=PropertyAccess.READ)
	def MinimumRate(self) -> d:
		return 1.0

	@dbus_property(access=PropertyAccess.READ)
	def MaximumRate(self) -> d:
		return 1.0

	@dbus_property(access=PropertyAccess.READ)
	def CanGoNext(self) -> b:
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanGoPrevious(self) -> b:
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanPlay(self) -> b:
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanPause(self) -> b:
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanSeek(self) -> b:
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanControl(self) -> b:
		return True


class MPRISService:
	"""Servicio coordinado para ciclo de vida y notificaciones de MPRIS sobre D-Bus."""

	def __init__(self, state_ref: Any, command_handler: Any = None, cover_resolver: Any = None) -> None:
		self.state_ref = state_ref
		self.command_handler = command_handler
		self.cover_resolver = cover_resolver
		self.bus: Any = None
		self.root: MPRISRoot | None = None
		self.player: MPRISPlayer | None = None
		self.registered: bool = False
		self._lock = asyncio.Lock()
		self._last_status: str | None = None
		self._last_meta: str | None = None
		self._last_vol: float | None = None

	async def ensure_registered(self) -> None:
		"""Registra MPRIS en DBus de forma perezosa al iniciar reproducción."""
		if self.registered or not DBUS_AVAILABLE or MessageBus is None:
			return
		async with self._lock:
			if self.registered or not DBUS_AVAILABLE or MessageBus is None:
				return
			try:
				ensure_display_env(os.environ)
				bus = await MessageBus().connect()
				self.root = MPRISRoot()
				self.player = MPRISPlayer(self.state_ref, self.command_handler, self.cover_resolver)
				bus.export("/org/mpris/MediaPlayer2", self.root)
				bus.export("/org/mpris/MediaPlayer2", self.player)
				await bus.request_name(f"org.mpris.MediaPlayer2.carpincho.instance{os.getpid()}")
				self.bus = bus
				self.registered = True
				logger.info("Carpincho registrado en DBus MPRIS. Podés controlarlo con las teclas multimedia.")
			except Exception as e:
				logger.warning(f"No se pudo registrar DBus MPRIS: {e}")

	def notify(self) -> None:
		"""Alias de notify_changes."""
		self.notify_changes()

	def notify_changes(self) -> None:
		"""Emite señal PropertiesChanged solo para las propiedades que variaron."""
		if not self.player:
			return
		try:
			changed: dict[str, Any] = {}
			new_status = self.player.PlaybackStatus
			new_meta = self.player.Metadata
			new_vol = self.player.Volume

			if self._last_status != new_status:
				changed["PlaybackStatus"] = new_status
				self._last_status = new_status

			meta_repr = repr(new_meta)
			if self._last_meta != meta_repr:
				changed["Metadata"] = new_meta
				self._last_meta = meta_repr

			if self._last_vol != new_vol:
				changed["Volume"] = new_vol
				self._last_vol = new_vol

			if changed:
				self.player.emit_properties_changed(changed)
		except Exception as e:
			logger.debug(f"Pifió actualizando propiedades MPRIS: {e}")

	def disconnect(self) -> None:
		"""Desconecta el bus de MPRIS de forma limpia."""
		if self.bus:
			try:
				self.bus.disconnect()
			except Exception:
				pass
			self.bus = None
			self.registered = False


def get_mpris_provider(state_ref: Any = None, command_handler: Any = None, cover_resolver: Any = None) -> MPRISService:
	"""Fábrica de servicio MPRIS vinculada al estado del reproductor."""
	return MPRISService(state_ref, command_handler=command_handler, cover_resolver=cover_resolver)
