"""
Coordinador de estado del reproductor y de la aplicación: APIState.
Maneja la cola, historial, escaneo en segundo plano, análisis de mood,
locución de DJ Carpincho e integración con MPV y MPRIS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

try:
	from scripts.binary_utils import check_internet_async, ensure_display_env, get_clean_env
except ImportError:
	try:
		from binary_utils import check_internet_async, ensure_display_env, get_clean_env
	except ImportError:

		async def check_internet_async(timeout: float = 0.8) -> bool:
			return True

		def ensure_display_env(env):
			pass

		def get_clean_env():
			return os.environ.copy()


try:
	from scripts.ytdlp_installer import ensure_ytdlp
except ImportError:
	try:
		from ytdlp_installer import ensure_ytdlp
	except ImportError:

		def ensure_ytdlp():
			return None


from app.core.dependencies import get_manager, get_state
from app.db.repositories import (
	FavoritesRepository,
	HistoryRepository,
	TrackRepository,
	UrlLogsRepository,
)
from app.engine.audio_analysis import (
	is_mood_available,
)
from app.engine.mpris import (
	DBUS_AVAILABLE,
	MPRISPlayer,
	MPRISRoot,
)

if DBUS_AVAILABLE:
	from dbus_next.aio import MessageBus
else:
	MessageBus = None

import app.services.radio as radio_service_mod
from app.engine.mpv_controller import AsyncMpvController
from app.services.library import (
	LibraryService,
	get_track_duration_seconds,
)
from app.services.radio import (
	DEFAULT_WEATHER_LOCATION,
	HAS_EDGE_TTS,
	RadioService,
)
from app.services.ytdlp import YtDlpService

logger = logging.getLogger("RockolaCarpincho")

RADIO_PREGENERATION_MAX_AGE_SECONDS: float = 15.0 * 60.0  # 15 minutos de caducidad tras pausa prolongada


def _get_active_db_path() -> Path | str:
	from app.db.database import get_default_db_path

	return get_default_db_path()


async def broadcast_state(include_library=False):
	"""Envía por WebSocket el diff de estado a todos los clientes conectados."""
	state = get_state()
	if not state:
		return
	manager = get_manager()
	if not manager:
		return
	new_state = state.get_full_state_dict(include_library=include_library)
	diff = {"type": "state_update"}
	for k, v in new_state.items():
		if state.last_broadcast.get(k) != v:
			diff[k] = v
	if len(diff) > 1:
		state.last_broadcast.update(new_state)
		await manager.broadcast_json(diff)
		if hasattr(state, "notify_mpris"):
			state.notify_mpris()


class _ManagerProxy:
	"""Proxy dinámico para acceder a ConnectionManager incluso cuando es monkeypatcheado."""

	def __getattr__(self, name: str) -> Any:
		return getattr(get_manager(), name)


manager = _ManagerProxy()


class APIState:
	def __init__(self, initial_dir=None, secondary_dir=None, open_browser: bool = True):
		self.current_track = None
		self.dj_carpincho_enabled = False
		self.dj_safe_mode = False
		self.history = []
		self.id_to_current_path = {}
		self.initial_dir = initial_dir
		self.is_scanning = False
		self.is_analyzing_mood = False
		self.scan_phase = "idle"  # Estados: "idle", "discovering", "metadata", "mood"
		self.scan_current = 0
		self.scan_total = 0
		self.scan_message = ""
		self.background_mood_task: asyncio.Task | None = None
		self.last_broadcast = {}
		self.mpv_paused = False
		self.path_to_id = {}
		self.pause_after_path = None
		self.processing_eof = False
		self.queue = []
		self.secondary_dir = secondary_dir

		# Estado de reproducción
		self.time_pos = 0
		self.duration = 0
		self.last_time_broadcast = 0
		self.last_seek_drift: float | None = None  # Última deriva con la que sincronizamos MPV

		# Archivos y caché
		self.track_cache_by_path = {}
		self.tracks_cache = []

		self.url_metadata = {}
		self.volume = 100
		self.server_muted = False
		self.dj_next_track = None  # El tema que el DJ eligió para sonar después
		self.dj_countdown_task = None  # Task del countdown de 10s del DJ (cancelable)
		self.mpv_visible = True

		# Repositorios y Servicios delegados
		self.favorites_repo = FavoritesRepository()
		self.history_repo = HistoryRepository()
		self.urllogs_repo = UrlLogsRepository()
		self.track_repo = TrackRepository()
		self.library_service = LibraryService(track_repo=self.track_repo)
		self.radio_service = RadioService(weather_location=DEFAULT_WEATHER_LOCATION)
		self.ytdlp_service = YtDlpService()

		self.favorites = self._load_favs_from_db()

		# Modo Radio
		self.radio_mode_enabled = True
		self.radio_track_counter = 0
		self.radio_tracks_until_next = random.randint(1, 2)
		self.is_playing_radio_announcement = False
		self.is_synthesizing_radio = False

		# Estado de red del servidor y navegador
		self.open_browser = open_browser
		self.server_host = "0.0.0.0"
		self.server_port = 1729
		self.configured_url = None
		self.subpath = ""
		self.local_ip = "127.0.0.1"
		self.server_url = "http://localhost:1729"

		self.mpris_bus = None
		self.mpris_root = None
		self.mpris_player = None
		self.mpris_registered = False
		self._mpris_lock = asyncio.Lock()
		self._play_next_lock = asyncio.Lock()

		self.mpv = AsyncMpvController(
			{
				"duration_update": self.handle_duration_update,
				"mpv_restarted": self.handle_mpv_restarted,
				"mute_update": self.handle_mute_update,
				"pause_update": self.handle_pause_update,
				"song_ended": self.handle_song_ended,
				"time_update": self.handle_time_update,
				"track_stopped": self.handle_track_stopped,
				"volume_update": self.handle_volume_update,
			}
		)

	@property
	def radio_pregeneration_task(self) -> asyncio.Task | None:
		return self.radio_service.pregeneration_task

	@radio_pregeneration_task.setter
	def radio_pregeneration_task(self, task: asyncio.Task | None) -> None:
		self.radio_service.pregeneration_task = task

	@property
	def pregenerated_radio_announcement(self) -> dict | None:
		return self.radio_service.pregenerated_announcement

	@pregenerated_radio_announcement.setter
	def pregenerated_radio_announcement(self, val: dict | None) -> None:
		self.radio_service.pregenerated_announcement = val

	@property
	def weather_location(self) -> str:
		return self.radio_service.weather_location

	@weather_location.setter
	def weather_location(self, val: str) -> None:
		self.radio_service.weather_location = val

	@property
	def radio_announcement_path(self) -> str:
		return str(self.radio_service.announcement_path)

	@radio_announcement_path.setter
	def radio_announcement_path(self, val: str | Path) -> None:
		self.radio_service.announcement_path = Path(val)

	@property
	def radio_pregenerated_path(self) -> str:
		return str(self.radio_service.pregenerated_path)

	@radio_pregenerated_path.setter
	def radio_pregenerated_path(self, val: str | Path) -> None:
		self.radio_service.pregenerated_path = Path(val)

	@property
	def has_edge_tts(self) -> bool:
		"""Indica si el servicio de Edge-TTS para locución radial está disponible."""
		return bool(self.radio_service.is_available if hasattr(self, "radio_service") else False)

	@property
	def radio_archive_dir(self) -> Path:
		return self.radio_service.archive_dir

	@radio_archive_dir.setter
	def radio_archive_dir(self, val: Path | str) -> None:
		self.radio_service.archive_dir = Path(val)

	@property
	def radio_archive_max_files(self) -> int:
		return self.radio_service.archive_max_files

	@radio_archive_max_files.setter
	def radio_archive_max_files(self, val: int) -> None:
		self.radio_service.archive_max_files = val

	def get_full_state_dict(self, include_library=False):
		"""Genera un diccionario con el estado completo actual (creando copias listas/diccionarios)"""
		active_favs = []
		for fav_id in self.favorites:
			if fav_id in self.id_to_current_path:
				active_favs.append(self.id_to_current_path[fav_id])
			else:
				active_favs.append(fav_id)

		keys_to_exclude = {"fingerprint", "bpm", "energy", "spectral_centroid"}
		clean_dj_next = (
			{k: v for k, v in self.dj_next_track.items() if k not in keys_to_exclude}
			if isinstance(self.dj_next_track, dict)
			else self.dj_next_track
		)

		d = {
			"current_track": self.current_track,
			"dj_carpincho_enabled": self.dj_carpincho_enabled,
			"dj_safe_mode": self.dj_safe_mode,
			"dj_next_track": clean_dj_next,
			"duration": self.duration,
			"favorites": active_favs,
			"has_edge_tts": bool(self.radio_service.is_available if hasattr(self, "radio_service") else HAS_EDGE_TTS),
			"has_ffmpeg": bool(is_mood_available()),
			"history": list(self.history),
			"is_scanning": self.is_scanning,
			"scan_status": {
				"is_scanning": self.is_scanning,
				"is_analyzing_mood": self.is_analyzing_mood,
				"phase": self.scan_phase,
				"current": self.scan_current,
				"total": self.scan_total,
				"message": self.scan_message,
			},
			"local_ip": self.local_ip,
			"mpv_visible": self.mpv_visible,
			"pause_after_path": self.pause_after_path,
			"paused": self.mpv_paused,
			"queue": list(self.queue),
			"radio_mode_enabled": self.radio_mode_enabled,
			"is_playing_radio_announcement": self.is_playing_radio_announcement,
			"is_synthesizing_radio": self.is_synthesizing_radio,
			"server_muted": self.server_muted,
			"server_url": self.server_url,
			"time_pos": self.time_pos,
			"top_played": self.get_top_played(),
			"url_metadata": dict(self.url_metadata),
			"volume": self.volume,
			"weather_location": self.weather_location,
		}

		if include_library:
			# Lista limpia filtrando fingerprints y métricas de mood
			d["library"] = [{k: v for k, v in track.items() if k not in keys_to_exclude} for track in self.tracks_cache]

		return d

	def notify_mpris(self):
		if self.mpris_player:
			try:
				changed = {}
				new_status = self.mpris_player.PlaybackStatus
				new_meta = self.mpris_player.Metadata
				new_vol = self.mpris_player.Volume

				if getattr(self, "_last_mpris_status", None) != new_status:
					changed["PlaybackStatus"] = new_status
					self._last_mpris_status = new_status

				meta_repr = repr(new_meta)
				if getattr(self, "_last_mpris_meta", None) != meta_repr:
					changed["Metadata"] = new_meta
					self._last_mpris_meta = meta_repr

				if getattr(self, "_last_mpris_vol", None) != new_vol:
					changed["Volume"] = new_vol
					self._last_mpris_vol = new_vol

				if changed:
					self.mpris_player.emit_properties_changed(changed)
			except Exception as e:
				logger.debug(f"Pifió actualizando propiedades MPRIS: {e}")

	async def ensure_mpris(self):
		"""Registra MPRIS en DBus al reproducir el primer tema."""
		if self.mpris_registered or not DBUS_AVAILABLE:
			return
		async with self._mpris_lock:
			if self.mpris_registered or not DBUS_AVAILABLE:
				return
			try:
				ensure_display_env(os.environ)
				bus = await MessageBus().connect()
				self.mpris_root = MPRISRoot()
				self.mpris_player = MPRISPlayer(self)
				bus.export("/org/mpris/MediaPlayer2", self.mpris_root)
				bus.export("/org/mpris/MediaPlayer2", self.mpris_player)
				await bus.request_name(f"org.mpris.MediaPlayer2.carpincho.instance{os.getpid()}")
				self.mpris_bus = bus
				self.mpris_registered = True
				logger.info("Carpincho registrado en DBus MPRIS. Podés controlarlo con las teclas multimedia.")
			except Exception as e:
				logger.warning(
					f"No se pudo registrar DBus MPRIS (quizás corrés sin entorno de escritorio). MPV usará su sistema nativo. Error: {e}"
				)

	def _load_favs_from_db(self):
		try:
			return self.favorites_repo.list_all()
		except Exception as e:
			logger.error(f"Error cargando favoritos de la DB: {e}")
			return []

	def is_radio_announcement(self, path: str | Path | None) -> bool:
		"""
		Verifica si un path corresponde a la locución radial sintética generada por la aplicación.
		Si la ruta está registrada en la biblioteca del usuario (path_to_id), se trata de una pista legítima.
		"""
		if not path:
			return False
		str_path = str(path)
		if str_path in self.path_to_id:
			return False
		try:
			announcement_p = getattr(self, "radio_announcement_path", None)
			if announcement_p and Path(str_path).resolve() == Path(announcement_p).resolve():
				return True
			pregenerated_p = getattr(self, "radio_pregenerated_path", None)
			if pregenerated_p and Path(str_path).resolve() == Path(pregenerated_p).resolve():
				return True
			p = Path(str_path)
			if (
				p.name in ("radio_announcement.mp3", "radio_pregenerated.mp3")
				and p.parent.resolve() == Path(tempfile.gettempdir()).resolve()
			):
				return True
		except Exception:
			pass
		return False

	def _register_play_stat(self, path):
		str_path = str(path)
		if getattr(self, "is_playing_radio_announcement", False) or self.is_radio_announcement(str_path):
			return

		if not str_path.startswith(("http://", "https://")):
			track_id = self.path_to_id.get(str_path, str_path)
			now = time.time()
			try:
				self.history_repo.add_play(track_id, now)
				logger.debug(f"Tema completado, sumando +1 al top: {str_path}")
			except Exception as e:
				logger.error(f"Error guardando stat en DB: {e}")

	def _log_url(self, url):
		"""Guarda un registro de los links que sonaron, con su metadata si existe."""
		try:
			meta = self.url_metadata.get(
				url,
				{"display_title": "Link directo", "display_artist": "Desconocido"},
			)
			title = meta.get("title", meta.get("display_title"))
			artist = meta.get("artist", meta.get("display_artist"))
			played_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
			self.urllogs_repo.add_url(url, title, artist, played_at)
		except Exception as e:
			logger.error(f"Error guardando el log de URLs en DB: {e}")

	def recalculate_mood_scores(self):
		"""Recalcula el mood_score normalizado para todos los temas en tracks_cache delegando en LibraryService."""
		if self.tracks_cache:
			self.library_service.recalculate_mood(self.tracks_cache)

	def scan_directory(
		self,
		target_dirs: list,
		extract_mood: bool = True,
		max_workers: int = 16,
		extract_fingerprint: bool | None = None,
	):
		"""Escanea directorios delegando en LibraryService."""
		return self.library_service.scan_directory(
			target_dirs,
			extract_mood=extract_mood,
			max_workers=max_workers,
			extract_fingerprint=extract_fingerprint,
			state=self,
		)

	def start_background_mood_analysis(self):
		"""Lanza la tarea en segundo plano para analizar BPM y fingerprints sin bloquear."""
		if self.background_mood_task and not self.background_mood_task.done():
			return self.background_mood_task
		try:
			loop = asyncio.get_running_loop()
			self.background_mood_task = loop.create_task(self.run_background_mood_analysis())
			return self.background_mood_task
		except RuntimeError:
			return None

	async def run_background_mood_analysis(self):
		"""Worker que procesa de forma asíncrona BPM/mood y huella acústica delegando en LibraryService."""
		return await self.library_service.run_background_mood_analysis(
			state=self,
			on_progress=lambda cur, tot, msg: broadcast_state(),
			on_finished=lambda: broadcast_state(include_library=True),
		)

	async def fetch_yt_dlp_metadata(self, url):
		"""Obtiene asincrónicamente la data de yt-dlp y avisa a los clientes delegando en YtDlpService."""
		if url in self.url_metadata:
			return

		meta = await self.ytdlp_service.fetch_metadata(url)
		if meta:
			self.url_metadata[url] = meta
			self.id_to_current_path[url] = url
			self.path_to_id[url] = url
			logger.info(f"Data fresquita conseguida: {meta.get('artist')} - {meta.get('title')}")
			await broadcast_state()

	# Los handlers de eventos actualizan el estado, que los clientes reciben en su próxima sincronización
	async def handle_song_ended(self, reason: str = "eof", file_error: str | None = None):
		# Si hay un reproductor local activo, ÉL es quien manda el evento de canción terminada.
		# Ignoramos el EOF de MPV para no avanzar la cola dos veces.
		if manager.local_player_ws is not None:
			return

		# Si MPV nos mandó múltiples "canción terminada" al mismo tiempo, los ignoramos
		if getattr(self, "processing_eof", False):
			logger.debug("Ignorando evento EOF concurrente para no sumar puntos doble.")
			return

		self.processing_eof = True
		try:
			is_radio = getattr(self, "is_playing_radio_announcement", False) or self.is_radio_announcement(
				self.current_track
			)
			if self.current_track and reason != "error" and not is_radio:
				self._register_play_stat(self.current_track)
			await self.play_next(skipped_by_user=False)
			await broadcast_state()
		finally:
			self.processing_eof = False

	async def handle_mpv_restarted(self):
		"""Si MPV se muere y revive, le devolvemos la memoria de lo que estaba sonando."""
		if self.current_track:
			logger.info("El MPV revivió. Volviéndole a cargar el temita que estaba sonando...")

			self.last_track_change = time.time()

			# Volvemos a cargar la pista sin tocar el historial
			await self.mpv._send(
				json.dumps(
					{"command": ["loadfile", str(self.current_track)]},
					ensure_ascii=False,
				)
			)
			# Le devolvemos su estado de pausa y volumen
			await self.mpv._send(json.dumps({"command": ["set_property", "pause", self.mpv_paused]}))
			await self.mpv._send(json.dumps({"command": ["set_property", "volume", self.volume]}))
			mpv_mute = True if manager.local_player_ws is not None else self.server_muted
			await self.mpv._send(json.dumps({"command": ["set_property", "mute", mpv_mute]}))
			if self.time_pos > 0:
				await self.mpv._send(json.dumps({"command": ["seek", self.time_pos, "absolute"]}))

	async def handle_track_stopped(self):
		# Si hay un reproductor local activo, el cliente maneja el ciclo de vida
		if manager.local_player_ws is not None:
			return

		# Si cambiamos de tema hace menos de 1.5 segundos,
		# este "stop" es del tema viejo muriendo. Lo ignoramos.
		if time.time() - getattr(self, "last_track_change", 0) < 1.5:
			logger.info(
				"Recibí un 'stop' pero el tema cambió hace menos de 1.5s, asumo que es el viejo muriendo, ignoro."
			)
			return
		self.current_track = None
		self.mpv_paused = False
		self.time_pos = 0
		self.duration = 0
		await broadcast_state()

	async def handle_volume_update(self, vol):
		if manager.local_player_ws is not None:
			return
		self.volume = vol
		await broadcast_state()

	async def handle_pause_update(self, paused):
		self.mpv_paused = paused
		await broadcast_state()

	async def handle_time_update(self, pos):
		# Mientras hay un reproductor local activo, el cliente es la fuente de verdad para
		# time_pos. Ignoramos los ticks del MPV para evitar que sobreescriban el valor del
		# cliente y creen jitter en todos los demás clientes.
		if manager.local_player_ws is not None:
			return
		self.time_pos = pos or 0
		now = time.time()
		# Solo triggereamos broadcast cada ~5 seg para no fundir el WebSocket
		if now - self.last_time_broadcast >= 5.0:
			self.last_time_broadcast = now
			await broadcast_state()

	async def handle_duration_update(self, dur):
		# Igual que handle_time_update: el cliente local reporta su propia duración.
		if manager.local_player_ws is not None:
			return
		self.duration = dur or 0
		await broadcast_state()

	async def handle_mute_update(self, is_muted):
		if manager.local_player_ws is not None:
			return
		self.server_muted = is_muted
		await broadcast_state()

	async def play_track(self, path):
		# Cancelar el countdown del DJ si el usuario eligió un tema manualmente (no si lo dispara el countdown mismo)
		if self.dj_countdown_task and not self.dj_countdown_task.done():
			try:
				curr_task = asyncio.current_task()
			except Exception:
				curr_task = None
			if curr_task is not self.dj_countdown_task:
				self.dj_countdown_task.cancel()
				self.dj_countdown_task = None
				logger.info("Countdown del DJ Carpincho cancelado por nueva acción del usuario.")

		# Si aún no inicializamos MPRIS, lo registramos al reproducir la primera canción
		await self.ensure_mpris()

		# Si MPV no está corriendo, lo arrancamos acá al empezar a reproducir
		if not self.mpv.is_running:
			await self.mpv.start()

		self.current_track = path
		self.mpv_paused = False
		self.time_pos = 0
		self.last_track_change = time.time()

		str_path = str(path)
		if str_path.startswith(("http://", "https://")):
			# Si es un link de YouTube o internet, lo mandamos al log especial apenas arranca
			self._log_url(str_path)

		if self.mpv_visible and getattr(self.mpv, "has_display", True):
			await self.mpv._send('{"command": ["set_property", "force-window", "yes"]}')
		else:
			await self.mpv._send('{"command": ["set_property", "force-window", "no"]}')

		# Usamos json.dumps() con ensure_ascii=False para mandar acentos (ñ, tildes) en crudo y evitar marear a MPV
		cmd_payload = json.dumps({"command": ["loadfile", str_path]}, ensure_ascii=False)
		await self.mpv._send(cmd_payload)
		await self.mpv._send(json.dumps({"command": ["set_property", "pause", False]}))
		mgr = get_manager()
		if mgr and mgr.local_player_ws is not None:
			await self.mpv._send('{"command": ["set_property", "mute", true]}')
		else:
			await self.mpv._send(json.dumps({"command": ["set_property", "mute", self.server_muted]}))

		# Si es la locución radial y tiene subtítulos generados, se los inyectamos a MPV si la ventana está activa
		if str_path == self.radio_announcement_path and self.mpv_visible and getattr(self.mpv, "has_display", True):
			sub_candidate = Path(str_path).with_suffix(".srt")
			if not sub_candidate.is_file():
				sub_candidate = Path(str_path).with_suffix(".lrc")
			if not sub_candidate.is_file() and self.radio_pregenerated_path:
				pre_sub = Path(self.radio_pregenerated_path).with_suffix(".srt")
				if not pre_sub.is_file():
					pre_sub = Path(self.radio_pregenerated_path).with_suffix(".lrc")
				if pre_sub.is_file():
					sub_candidate = pre_sub
			if sub_candidate.is_file():
				try:
					await self.mpv._send(
						json.dumps({"command": ["sub-add", str(sub_candidate), "select"]}, ensure_ascii=False)
					)
				except Exception as sub_err:
					logger.debug(f"Fallo cargando subtítulos en MPV: {sub_err}")

		# Modo Radio: Si este no es el anuncio radial y la próxima transición toca locución,
		# iniciamos el procesamiento y síntesis al comienzo de la canción para tener latencia cero.
		if str_path != self.radio_announcement_path and self.radio_mode_enabled:
			track_duration = get_track_duration_seconds(str_path, self.tracks_cache)
			self._start_radio_pregeneration(current_track_path=str_path, track_duration=track_duration)

	def _prune_radio_archive(self, max_files: int | None = None) -> int:
		"""Elimina guiones históricos viejos delegando en RadioService."""
		limit = max_files if max_files is not None else self.radio_archive_max_files
		return self.radio_service.prune_radio_archive(self.radio_archive_dir, max_files=limit)

	def _archive_radio_announcement(
		self,
		src_mp3_path: str | Path | None = None,
		script_text: str = "",
		display_title: str = "",
	) -> Path | None:
		"""Guarda el guion .txt delegando en RadioService."""
		return self.radio_service.archive_radio_announcement(
			archive_dir=self.radio_archive_dir,
			script_text=script_text,
			display_title=display_title,
			max_files=self.radio_archive_max_files,
		)

	def _cancel_radio_pregeneration(self):
		"""Cancela cualquier pregeneración en curso de la locución radial delegando en RadioService."""
		self.radio_service.cancel_pregeneration()

	def _start_radio_pregeneration(self, current_track_path: str, track_duration: float = 0.0):
		"""Dispara la síntesis y procesamiento de la locución radial en segundo plano delegando en RadioService."""
		if not self.radio_mode_enabled or not self.radio_service.is_available:
			return

		# Solo pregenerar si el contador alcanzará el umbral al terminar este tema
		if (self.radio_track_counter + 1) < self.radio_tracks_until_next:
			return

		self.radio_service.start_pregeneration(track_duration=track_duration)

	def _select_candidate_dj_track(self, unplayed: list[dict]) -> dict | None:
		"""Elige una pista de la lista de pendientes según el modo del DJ Carpincho."""
		if not unplayed:
			return None
		if self.dj_safe_mode:
			favs = [t for t in unplayed if self.path_to_id.get(t["path"]) in self.favorites]
			normals = [t for t in unplayed if self.path_to_id.get(t["path"]) not in self.favorites]

			if favs and normals:
				# ¡90% de chances clavadas de sacar un temazo!
				return random.choice(favs) if random.random() < 0.90 else random.choice(normals)
			elif favs:
				return random.choice(favs)
			else:
				return random.choice(normals)
		return random.choice(unplayed)

	async def set_pause(self, paused: bool = True):
		self.mpv_paused = paused
		await self.mpv._send(json.dumps({"command": ["set_property", "pause", paused]}))

	async def set_volume(self, volume: float):
		self.volume = max(0, min(110, int(volume)))
		await self.mpv._send(json.dumps({"command": ["set_property", "volume", self.volume]}))

	async def stop_playback(self, reset_ui_state: bool = False):
		if self.dj_countdown_task and not self.dj_countdown_task.done():
			self.dj_countdown_task.cancel()
		self.dj_countdown_task = None
		self._cancel_radio_pregeneration()
		self.dj_next_track = None
		self.current_track = None
		if reset_ui_state:
			self.mpv_paused = False
			self.dj_carpincho_enabled = False
			self.is_playing_radio_announcement = False
			self.is_synthesizing_radio = False
			self.time_pos = 0
		await self.mpv._send('{"command": ["stop"]}')
		await self.mpv._send('{"command": ["set_property", "force-window", "no"]}')

	async def play_next(self, skipped_by_user=False):
		# Cancelar countdown previo del DJ antes de pedir el lock para evitar contención
		if self.dj_countdown_task and not self.dj_countdown_task.done():
			self.dj_countdown_task.cancel()
		self.dj_countdown_task = None

		async with self._play_next_lock:
			just_finished = self.current_track

			if self.current_track:
				if self.current_track == self.radio_announcement_path:
					# Terminó la locución radial: no va al historial
					self.is_playing_radio_announcement = False
				else:
					self.history.append(self.current_track)
				self.current_track = None

			# Verificamos si tocaba pausar después del track que acaba de terminar
			should_pause = (self.pause_after_path is not None) and (just_finished == self.pause_after_path)
			if should_pause:
				self.pause_after_path = None

			# Modo Radio: Intervención de locución cada 2 o 3 canciones durante transiciones naturales
			has_next_track = bool(self.queue or (self.dj_carpincho_enabled and self.tracks_cache))
			if (
				not skipped_by_user
				and self.radio_mode_enabled
				and self.radio_service.is_available
				and has_next_track
				and just_finished is not None
				and just_finished != self.radio_announcement_path
			):
				self.radio_track_counter += 1
				if self.radio_track_counter >= self.radio_tracks_until_next:
					# Preguntamos si hay internet puntualmente antes de activar la síntesis radial
					check_net_fn = getattr(radio_service_mod, "check_internet_async", check_internet_async)
					if not await check_net_fn(timeout=0.8):
						self.radio_track_counter = 0
						self.radio_tracks_until_next = random.randint(2, 3)
						logger.warning(
							"📻 Carpincho Locutor: no hay conexión a internet disponible. Omitiendo locución radial para no demorar la reproducción."
						)
					else:
						ok = False
						display_title = ""
						script = ""
						radio_err = ""

						# Averiguamos qué tema viene realmente en este momento para superponerlo como cortina en caliente
						next_track_path = None
						if self.queue:
							next_track_path = self.queue[0]
						elif self.dj_next_track:
							next_track_path = self.dj_next_track.get("path")
						elif self.dj_carpincho_enabled and self.tracks_cache:
							self._pick_dj_next()
							if self.dj_next_track:
								next_track_path = self.dj_next_track.get("path")

						bg_offset = 0.0
						if next_track_path:
							total_dur = get_track_duration_seconds(next_track_path, self.tracks_cache)
							if total_dur > 10.0:
								bg_offset = total_dur / 2.0  # Desde la mitad de la canción
							elif total_dur > 0:
								bg_offset = total_dur * 0.4

						async def _set_synthesizing_radio(is_synth: bool):
							self.is_synthesizing_radio = is_synth
							await broadcast_state()

						ok, display_title, script, radio_err = await self.radio_service.get_or_synthesize(
							next_track_path=next_track_path,
							bg_offset=bg_offset,
							on_synthesis_status=_set_synthesizing_radio,
						)

						if ok:
							self.radio_track_counter = 0
							self.radio_tracks_until_next = random.randint(2, 3)
							self.is_playing_radio_announcement = True
							self.url_metadata[self.radio_announcement_path] = {
								"path": self.radio_announcement_path,
								"display_title": display_title,
								"display_artist": "Carpincho Locutor 🎙️",
								"album": "La Rockola del Carpincho",
								"duration_str": "0:12",
							}
							self._archive_radio_announcement(
								self.radio_announcement_path,
								script_text=script,
								display_title=display_title,
							)
							await self.play_track(self.radio_announcement_path)
							if should_pause:
								await self.set_pause(True)
							await broadcast_state()
							return
						else:
							logger.warning(
								f"🎙️ Carpincho Locutor: No se pudo sintetizar la locución radial ({radio_err}). Pasando al tema siguiente..."
							)

			if self.queue:
				next_path = self.queue.pop(0)
				self.dj_next_track = None  # Limpiamos (si la fila tenía temas, el DJ no pre-elegió)
				await self.play_track(next_path)
				if should_pause:
					await self.set_pause(True)
			elif self.dj_carpincho_enabled and self.tracks_cache:
				# Usamos la pre-elección del DJ si existe; sino elegimos ahora
				if self.dj_next_track:
					chosen = self.dj_next_track
				else:
					played_paths = set(self.history)
					unplayed = [t for t in self.tracks_cache if t["path"] not in played_paths]
					chosen = self._select_candidate_dj_track(unplayed)

				if chosen:
					logger.info(
						f"🦦 DJ Carpincho salvó las papas con un clásico: {chosen['display_title']} {'(al toque)' if skipped_by_user or just_finished == self.radio_announcement_path else '(arranca en 10 segundos...)'}"
					)

					# Durante el countdown mostramos el tema elegido en dj_next_track
					# para que todos los clientes vean qué viene — lo borramos recién cuando arranca.
					self.dj_next_track = chosen
					await broadcast_state()

					if not skipped_by_user and just_finished != self.radio_announcement_path:
						# Corremos el countdown en una tarea background para no retener el lock durante los 10 segundos
						async def _run_dj_countdown(target_track: dict, pause_after: bool):
							try:
								await self.mpv._send(json.dumps({"command": ["set_property", "pause", True]}))
								await asyncio.sleep(10)  # Pausa de 10 segundos antes de que el DJ arranque
								await self.mpv._send(json.dumps({"command": ["set_property", "pause", False]}))
								async with self._play_next_lock:
									if self.current_track is not None:
										return
									self.dj_next_track = None
									await self.play_track(target_track["path"])
									if pause_after:
										await self.set_pause(True)
									self._pick_dj_next()
									await broadcast_state()
							except asyncio.CancelledError:
								logger.info("Countdown del DJ cancelado, no se reproduce el tema pre-elegido.")
								if self.dj_next_track == target_track:
									self.dj_next_track = None
								await broadcast_state()
							finally:
								self.dj_countdown_task = None

						self.dj_countdown_task = asyncio.create_task(_run_dj_countdown(chosen, should_pause))
						return

					self.dj_next_track = None  # Ahora sí borramos: el tema arranca al toque
					await self.play_track(chosen["path"])
					if should_pause:
						await self.set_pause(True)
					# Pre-elegimos el siguiente para el front
					self._pick_dj_next()
					return

				else:
					logger.info("DJ Carpincho se quedó sin temas nuevos esta sesión.")
					self.dj_carpincho_enabled = False
					await self.stop_playback()
			else:
				# Sin fila ni DJ: frena
				await self.stop_playback()

			self._pick_dj_next()  # Actualiza la preview después de tocar la fila

	async def play_prev(self):
		if self.history:
			prev_path = self.history.pop()
			if self.current_track:
				self.queue.insert(0, self.current_track)
				self.current_track = None
			await self.play_track(prev_path)
		elif self.current_track:
			# Reiniciamos el tema actual desde el comienzo si no hay historial previo
			await self.play_track(self.current_track)

	def _pick_dj_next(self):
		"""Elige (o limpia) el próximo tema del DJ Carpincho según el estado actual."""
		if self.dj_carpincho_enabled and not self.queue and self.tracks_cache:
			played_paths = set(self.history)
			if self.current_track:
				played_paths.add(self.current_track)

			unplayed = [t for t in self.tracks_cache if t["path"] not in played_paths]
			chosen = self._select_candidate_dj_track(unplayed)

			if chosen:
				self.dj_next_track = chosen
				is_fav = self.path_to_id.get(chosen["path"]) in self.favorites
				logger.info(
					f"🦦 DJ Carpincho pre-eligió: {chosen['display_title']} (Favorito: {'Sí' if is_fav else 'No'})"
				)
				return
		self.dj_next_track = None

	async def toggle_queue(self, path):
		if path in self.queue:
			self.queue.remove(path)
		else:
			self.queue.append(path)
			if not self.current_track and not self.is_synthesizing_radio:
				await self.play_next(skipped_by_user=True)
				return
		self._pick_dj_next()  # Actualiza la pre-elección del DJ cuando cambia la fila

	async def jump(self, target_type, index):
		if target_type == "queue":
			# Avanzamos rápido hasta un tema que está en la fila
			skipped = self.queue[:index]
			if self.current_track:
				self.history.append(self.current_track)
				self.current_track = None
			self.history.extend(skipped)
			self.queue = self.queue[index:]
			await self.play_next(skipped_by_user=True)
		elif target_type == "history":
			# Rebobinamos hasta un tema del historial
			rewound = self.history[index + 1 :]
			if self.current_track:
				rewound.append(self.current_track)
				self.current_track = None
			self.queue = rewound + self.queue
			target = self.history[index]
			self.history = self.history[:index]
			await self.play_track(target)

	def get_top_played(self):
		now = time.time()
		two_months_ago = now - (30 * 24 * 3600 * 2)

		try:
			rows = self.history_repo.get_top_played(limit=50, since=two_months_ago)
			results = [(r["track_id"], r["count"]) for r in rows]
		except Exception as e:
			logger.error(f"Error calculando el top played: {e}")
			return []

		top_played = []
		for track_id, count in results:
			if "\\" in track_id or "/" in track_id or track_id.startswith("http"):
				current_path = track_id
			else:
				current_path = self.id_to_current_path.get(track_id)

			if current_path and self.is_radio_announcement(current_path):
				continue

			if current_path and os.path.exists(current_path):
				top_played.append({"path": current_path, "count": count})

		return top_played
