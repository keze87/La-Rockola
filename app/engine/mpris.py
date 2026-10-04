"""
Proveedor D-Bus / MPRIS para integración con controles multimedia de Linux.
Incluye fallback no-op transparente para Windows, macOS y entornos sin DBus.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("RockolaCarpincho")

try:
	from scripts.binary_utils import ensure_display_env
except ImportError:
	try:
		from binary_utils import ensure_display_env
	except ImportError:

		def ensure_display_env(env: Any = None) -> None:
			pass


DBUS_AVAILABLE = False
if sys.platform == "linux":
	try:
		from dbus_next import Variant
		from dbus_next.constants import PropertyAccess
		from dbus_next.service import ServiceInterface, dbus_property, method

		DBUS_AVAILABLE = True
	except ImportError:
		pass

if not DBUS_AVAILABLE:

	class Variant:  # type: ignore
		"""Fallback Variant para cuando dbus_next no está instalado."""

		def __init__(self, signature: str, value: object):
			self.signature = signature
			self.value = value

		def __repr__(self):
			return f"Variant('{self.signature}', {self.value!r})"

		def __eq__(self, other):
			if hasattr(other, "signature") and hasattr(other, "value"):
				return self.signature == other.signature and self.value == other.value
			return False

	class PropertyAccess:  # type: ignore
		READ = "read"
		WRITE = "write"
		READWRITE = "readwrite"

	def dbus_property(access=None):  # type: ignore
		def decorator(fn):
			if hasattr(fn, "setter"):
				return fn
			prop = property(fn)
			return prop

		return decorator

	def method():  # type: ignore
		def decorator(fn):
			return fn

		return decorator

	class ServiceInterface:  # type: ignore
		def __init__(self, name: str):
			self.name = name


b = s = d = x = o = str


def build_mpris_metadata(track_or_state: Any, server_url: str = "", variant_cls: Any = None) -> dict[str, Any]:
	"""
	Construye el diccionario de metadatos para la interfaz MPRIS (MediaPlayer2.Player.Metadata).
	Soporta tanto un objeto APIState como un diccionario plano de pista.
	"""
	v_cls = variant_cls or Variant

	import app.services.library as lib_service

	cover_art_finder = getattr(lib_service, "get_cover_art_uri", lambda p: None)

	# 1. Si es un diccionario con datos directos de pista
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
		cover_uri = track_or_state.get("cover_uri") or (cover_art_finder(track_path) if track_path else None)
		if cover_uri:
			meta["mpris:artUrl"] = v_cls("s", cover_uri)
		return meta

	# 2. Si es un objeto de estado
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
		meta = url_metadata[current_track]
		title = meta.get("display_title", title)
		artist = meta.get("display_artist", artist)
		album = meta.get("album", album)

	duration = getattr(state_obj, "duration", None)
	if duration:
		dur_usec = int(duration * 1000000)

	track_uri = current_track
	if track_uri and not track_uri.startswith("http"):
		try:
			track_uri = Path(track_uri).absolute().as_uri()
		except Exception:
			pass

	cover_uri = cover_art_finder(current_track) if current_track else None

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
	"""Implementación del nodo raíz de MPRIS org.mpris.MediaPlayer2."""

	def __init__(self):
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
	"""Implementación del reproductor MPRIS org.mpris.MediaPlayer2.Player."""

	def __init__(self, state_ref: Any, command_handler: Any = None):
		super().__init__("org.mpris.MediaPlayer2.Player")
		self.state = state_ref
		self.command_handler = command_handler

	def _dispatch(self, cmd: str, **kwargs: Any) -> None:
		if self.command_handler:
			asyncio.create_task(self.command_handler(cmd, **kwargs))
			return
		import app.api.v1.playback as playback_mod
		from app.api.schemas import CommandRequest

		handler = getattr(playback_mod, "handle_command_endpoint", None) or playback_mod.handle_command
		req = CommandRequest(cmd=cmd, **kwargs)
		asyncio.create_task(handler(req))

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
		amount = Offset / 1000000.0
		self._dispatch("seek", amount=amount)

	@method()
	def SetPosition(self, TrackId: o, Position: x):
		amount = Position / 1000000.0
		self._dispatch("seek_absolute", amount=amount)

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
		return build_mpris_metadata(self.state, variant_cls=Variant)

	@dbus_property(access=PropertyAccess.READWRITE)
	def Volume(self) -> d:
		return getattr(self.state, "volume", 0) / 100.0

	@Volume.setter
	def Volume(self, val: d):
		vollevel = int(val * 100)
		self._dispatch("set_volume", vollevel=vollevel)

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


def get_mpris_provider(state_ref: Any, command_handler: Any = None) -> tuple[MPRISRoot, MPRISPlayer] | None:
	"""Crea las interfaces MPRIS si DBus está disponible en el entorno."""
	if not DBUS_AVAILABLE:
		return None
	return MPRISRoot(), MPRISPlayer(state_ref, command_handler)
