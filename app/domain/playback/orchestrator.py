"""
Orquestador de reproducción (PlaybackOrchestrator).
Coordina la fila (QueueManager), el DJ Carpincho (DjCarpinchoSelector),
la biblioteca (LibraryService), el Modo Radio (RadioService), MPV y MPRIS
bajo el principio de responsabilidad única.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

from app.core.container import get_container
from app.domain.dj.selector import DjCarpinchoSelector
from app.domain.library.models import get_track_duration_seconds
from app.domain.library.mood import is_mood_available
from app.domain.library.service import LibraryService, get_cover_art_uri
from app.domain.queue.manager import QueueManager
from app.domain.radio import service as radio_service_mod
from app.domain.radio.banks import DEFAULT_WEATHER_LOCATION
from app.domain.radio.service import RadioService
from app.infrastructure.binaries.manager import check_internet_async
from app.infrastructure.binaries.ytdlp import YtDlpAdapter
from app.infrastructure.db.connection import get_default_db_path
from app.infrastructure.db.repositories import (
	FavoritesRepository,
	HistoryRepository,
	TrackRepository,
	UrlLogsRepository,
)
from app.infrastructure.media.tts_cache import HAS_EDGE_TTS
from app.infrastructure.mpris.adapter import MPRISService
from app.infrastructure.mpv.controller import AsyncMpvController

logger = logging.getLogger("RockolaCarpincho")


async def broadcast_state(include_library: bool = False) -> None:
	"""Envía por WebSocket el diff de estado a todos los clientes conectados."""
	container = get_container()
	state = container.ensure_orchestrator()
	ws_mgr = container.ensure_ws_manager()
	if not state or not ws_mgr:
		return
	new_state = state.get_full_state_dict(include_library=include_library)
	diff: dict[str, Any] = {"type": "state_update"}
	for k, v in new_state.items():
		if state.last_broadcast.get(k) != v:
			diff[k] = v
	if len(diff) > 1:
		state.last_broadcast.update(new_state)
		await ws_mgr.broadcast_json(diff)
		state.notify_mpris()


class PlaybackOrchestrator:
	"""Orquestador central del dominio de reproducción de La Rockola del Carpincho."""

	def __init__(
		self,
		initial_dir: str | None = None,
		secondary_dir: str | None = None,
		open_browser: bool = True,
		db_path: Path | str | None = None,
	) -> None:
		self.db_path = Path(db_path) if db_path else get_default_db_path()
		self.initial_dir = initial_dir
		self.secondary_dir = secondary_dir
		self.open_browser = open_browser

		# Componentes de dominio delegados
		self.queue_manager = QueueManager()
		self.dj_selector = DjCarpinchoSelector()

		# Repositorios de persistencia
		self.favorites_repo = FavoritesRepository(db_path=self.db_path)
		self.history_repo = HistoryRepository(db_path=self.db_path)
		self.urllogs_repo = UrlLogsRepository(db_path=self.db_path)
		self.track_repo = TrackRepository(db_path=self.db_path)

		# Servicios de dominio e infraestructura
		self.library_service = LibraryService(db_path=self.db_path, track_repo=self.track_repo)
		self.radio_service = RadioService(db_path=self.db_path, weather_location=DEFAULT_WEATHER_LOCATION)
		self.ytdlp_service = YtDlpAdapter()
		self.mpris_service = MPRISService(
			self,
			command_handler=self._dispatch_mpris_command,
			cover_resolver=lambda p: get_cover_art_uri(p, state_ref=self),
		)

		# Estado de escaneo y biblioteca en memoria
		self.id_to_current_path: dict[str, str] = {}
		self.path_to_id: dict[str, str] = {}
		self.track_cache_by_path: dict[str, dict[str, Any]] = {}
		self.tracks_cache: list[dict[str, Any]] = []
		self.url_metadata: dict[str, dict[str, Any]] = {}
		self.favorites: list[str] = self._load_favs_from_db()

		self.is_scanning: bool = False
		self.is_analyzing_mood: bool = False
		self.scan_phase: str = "idle"
		self.scan_current: int = 0
		self.scan_total: int = 0
		self.scan_message: str = ""
		self.background_mood_task: asyncio.Task[Any] | None = None

		# Estado de reproducción y sincronización
		self.mpv_paused: bool = False
		self.processing_eof: bool = False
		self.time_pos: float = 0.0
		self.duration: float = 0.0
		self.last_time_broadcast: float = 0.0
		self.last_seek_drift: float | None = None
		self.last_track_change: float = 0.0
		self.last_broadcast: dict[str, Any] = {}
		self.volume: int = 100
		self.server_muted: bool = False

		# Modo Radio
		self.radio_mode_enabled: bool = True
		self.last_radio_time: float = 0.0
		self.radio_time_until_next: float = float(random.randint(300, 900))
		self.is_playing_radio_announcement: bool = False
		self.is_synthesizing_radio: bool = False

		# Red y servidor
		self.server_host: str = "0.0.0.0"
		self.server_port: int = 1729
		self.configured_url: str | None = None
		self.subpath: str = ""
		self.local_ip: str = "127.0.0.1"
		self.server_url: str = "http://localhost:1729"

		self._play_next_lock = asyncio.Lock()

		self._mpv: Any = AsyncMpvController(
			{
				"duration_update": self.handle_duration_update,
				"mpv_restarted": self.handle_mpv_restarted,
				"mute_update": self.handle_mute_update,
				"pause_update": self.handle_pause_update,
				"song_ended": self.handle_song_ended,
				"time_update": self.handle_time_update,
				"track_stopped": self.handle_track_stopped,
				"visibility_update": self.handle_visibility_update,
				"volume_update": self.handle_volume_update,
			},
			state_ref=self,
		)
		self.mpv_visible: bool = getattr(self._mpv, "has_display", True)

	@property
	def mpv(self) -> Any:
		return self._mpv

	@mpv.setter
	def mpv(self, val: Any) -> None:
		self._mpv = val

	async def _dispatch_mpris_command(self, cmd: str, **kwargs: Any) -> None:
		"""Despacha comandos provenientes de D-Bus MPRIS hacia la tabla de comandos."""
		from app.api.commands import handle_command_endpoint
		from app.api.schemas import CommandRequest

		await handle_command_endpoint(CommandRequest(cmd=cmd, **kwargs))

	@property
	def mpris_registered(self) -> bool:
		return bool(getattr(self.mpris_service, "registered", False))

	@mpris_registered.setter
	def mpris_registered(self, val: bool) -> None:
		self.mpris_service.registered = bool(val)

	@property
	def mpris_player(self) -> Any:
		return getattr(self.mpris_service, "player", None)

	@mpris_player.setter
	def mpris_player(self, val: Any) -> None:
		self.mpris_service.player = val

	@property
	def mpris_root(self) -> Any:
		return getattr(self.mpris_service, "root", None)

	@mpris_root.setter
	def mpris_root(self, val: Any) -> None:
		self.mpris_service.root = val

	@property
	def mpris_bus(self) -> Any:
		return getattr(self.mpris_service, "bus", None)

	@mpris_bus.setter
	def mpris_bus(self, val: Any) -> None:
		self.mpris_service.bus = val

	# Propiedades delegadas a QueueManager
	@property
	def queue(self) -> list[str]:
		return self.queue_manager.queue

	@queue.setter
	def queue(self, val: list[str]) -> None:
		self.queue_manager.queue = list(val)

	@property
	def history(self) -> list[str]:
		return self.queue_manager.history

	@history.setter
	def history(self, val: list[str]) -> None:
		self.queue_manager.history = list(val)

	@property
	def current_track(self) -> str | None:
		return self.queue_manager.current_track

	@current_track.setter
	def current_track(self, val: str | None) -> None:
		self.queue_manager.current_track = val

	@property
	def pause_after_path(self) -> str | None:
		return self.queue_manager.pause_after_path

	@pause_after_path.setter
	def pause_after_path(self, val: str | None) -> None:
		self.queue_manager.pause_after_path = val

	# Propiedades delegadas a DjCarpinchoSelector
	@property
	def dj_carpincho_enabled(self) -> bool:
		return self.dj_selector.enabled

	@dj_carpincho_enabled.setter
	def dj_carpincho_enabled(self, val: bool) -> None:
		self.dj_selector.enabled = bool(val)

	@property
	def dj_safe_mode(self) -> bool:
		return self.dj_selector.safe_mode

	@dj_safe_mode.setter
	def dj_safe_mode(self, val: bool) -> None:
		self.dj_selector.safe_mode = bool(val)

	@property
	def dj_next_track(self) -> dict[str, Any] | None:
		return self.dj_selector.next_track

	@dj_next_track.setter
	def dj_next_track(self, val: dict[str, Any] | None) -> None:
		self.dj_selector.next_track = val

	@property
	def dj_countdown_task(self) -> asyncio.Task[None] | None:
		return self.dj_selector.countdown_task

	@dj_countdown_task.setter
	def dj_countdown_task(self, val: asyncio.Task[None] | None) -> None:
		self.dj_selector.countdown_task = val

	# Propiedades delegadas a RadioService
	@property
	def radio_pregeneration_task(self) -> asyncio.Task[None] | None:
		return self.radio_service.pregeneration_task

	@radio_pregeneration_task.setter
	def radio_pregeneration_task(self, task: asyncio.Task[None] | None) -> None:
		self.radio_service.pregeneration_task = task

	@property
	def pregenerated_radio_announcement(self) -> dict[str, Any] | None:
		return self.radio_service.pregenerated_announcement

	@pregenerated_radio_announcement.setter
	def pregenerated_radio_announcement(self, val: dict[str, Any] | None) -> None:
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
		return bool(self.radio_service.is_available)

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

	def _has_local_player(self) -> bool:
		ws_mgr = get_container().ws_manager
		return bool(ws_mgr and getattr(ws_mgr, "local_player_ws", None) is not None)

	def get_full_state_dict(self, include_library: bool = False) -> dict[str, Any]:
		"""Genera un diccionario con el estado completo actual."""
		active_favs = [self.id_to_current_path.get(fav_id, fav_id) for fav_id in self.favorites]
		keys_to_exclude = {"fingerprint", "bpm", "energy", "spectral_centroid"}
		clean_dj_next = (
			{k: v for k, v in self.dj_next_track.items() if k not in keys_to_exclude}
			if isinstance(self.dj_next_track, dict)
			else self.dj_next_track
		)

		d: dict[str, Any] = {
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
			"has_local_player": self._has_local_player(),
		}

		if include_library:
			d["library"] = [{k: v for k, v in track.items() if k not in keys_to_exclude} for track in self.tracks_cache]

		return d

	def notify_mpris(self) -> None:
		self.mpris_service.notify()

	async def ensure_mpris(self) -> None:
		await self.mpris_service.ensure_registered()

	def _load_favs_from_db(self) -> list[str]:
		try:
			return self.favorites_repo.list_all()
		except Exception as e:
			logger.error(f"Error cargando favoritos de la DB: {e}")
			return []

	def is_radio_announcement(self, path: str | Path | None) -> bool:
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

	def _register_play_stat(self, path: str | Path) -> None:
		str_path = str(path)
		if self.is_playing_radio_announcement or self.is_radio_announcement(str_path):
			return
		if not str_path.startswith(("http://", "https://")):
			track_id = self.path_to_id.get(str_path, str_path)
			try:
				self.history_repo.add_play(track_id, time.time())
			except Exception as e:
				logger.error(f"Error guardando stat en DB: {e}")

	def _log_url(self, url: str) -> None:
		try:
			meta = self.url_metadata.get(
				url,
				{"display_title": "Link directo", "display_artist": "Desconocido"},
			)
			title = meta.get("title", meta.get("display_title", "Link directo"))
			artist = meta.get("artist", meta.get("display_artist", "Desconocido"))
			played_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
			self.urllogs_repo.add_url(url, title, artist, played_at)
		except Exception as e:
			logger.error(f"Error guardando el log de URLs en DB: {e}")

	def recalculate_mood_scores(self) -> None:
		if self.tracks_cache:
			self.library_service.recalculate_mood(self.tracks_cache)

	def scan_directory(
		self,
		target_dirs: list[str],
		extract_mood: bool = True,
		max_workers: int | None = None,
		extract_fingerprint: bool | None = None,
	) -> list[dict[str, Any]]:
		return self.library_service.scan_directory(
			target_dirs,
			extract_mood=extract_mood,
			max_workers=max_workers,
			extract_fingerprint=extract_fingerprint,
			state=self,
		)

	def start_background_mood_analysis(self) -> asyncio.Task[Any] | None:
		if self.background_mood_task and not self.background_mood_task.done():
			return self.background_mood_task
		try:
			loop = asyncio.get_running_loop()
			self.background_mood_task = loop.create_task(self.run_background_mood_analysis())
			return self.background_mood_task
		except RuntimeError:
			return None

	async def run_background_mood_analysis(self) -> None:
		await self.library_service.run_background_mood_analysis(
			state=self,
			on_progress=lambda cur, tot, msg: broadcast_state(),
			on_finished=lambda: broadcast_state(include_library=True),
		)

	async def fetch_yt_dlp_metadata(self, url: str) -> None:
		if url in self.url_metadata:
			return
		meta = await self.ytdlp_service.fetch_metadata(url)
		if meta:
			self.url_metadata[url] = meta
			self.id_to_current_path[url] = url
			self.path_to_id[url] = url
			logger.info(f"Data fresquita conseguida: {meta.get('artist')} - {meta.get('title')}")
			await broadcast_state()

	# Handlers de eventos provenientes de MPV
	async def handle_song_ended(self, reason: str = "eof", file_error: str | None = None) -> None:
		if self._has_local_player() or self.processing_eof:
			return
		self.processing_eof = True
		try:
			is_radio = self.is_playing_radio_announcement or self.is_radio_announcement(self.current_track)
			if self.current_track and reason != "error" and not is_radio:
				self._register_play_stat(self.current_track)
			await self.play_next(skipped_by_user=False)
			await broadcast_state()
		finally:
			self.processing_eof = False

	async def handle_mpv_restarted(self) -> None:
		if self.current_track:
			logger.info("El MPV revivió. Volviéndole a cargar el temita que estaba sonando...")
			self.last_track_change = time.time()
			await self.mpv.load_file(str(self.current_track))
			await self.mpv.set_pause(self.mpv_paused)
			await self.mpv.set_volume(self.volume)
			mpv_mute = True if self._has_local_player() else self.server_muted
			await self.mpv.set_mute(mpv_mute)
			if self.time_pos > 0:
				await self.mpv.seek_absolute(self.time_pos)

	async def handle_track_stopped(self) -> None:
		if self._has_local_player():
			return
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

	async def handle_volume_update(self, vol: float) -> None:
		if self._has_local_player():
			return
		self.volume = int(vol)
		await broadcast_state()

	async def handle_pause_update(self, paused: bool) -> None:
		self.mpv_paused = paused
		await broadcast_state()

	async def handle_time_update(self, pos: float) -> None:
		if self._has_local_player():
			return
		self.time_pos = pos or 0
		now = time.time()
		if now - self.last_time_broadcast >= 5.0:
			self.last_time_broadcast = now
			await broadcast_state()

	async def handle_duration_update(self, dur: float) -> None:
		if self._has_local_player():
			return
		self.duration = dur or 0
		await broadcast_state()

	async def handle_mute_update(self, is_muted: bool) -> None:
		if self._has_local_player():
			return
		self.server_muted = is_muted
		await broadcast_state()

	async def handle_visibility_update(self, visible: bool) -> None:
		if self.mpv_visible != visible:
			self.mpv_visible = visible
			await broadcast_state()

	async def play_track(self, path: str | Path) -> None:
		self.dj_selector.cancel_countdown()

		await self.ensure_mpris()

		if not self.mpv.is_running:
			await self.mpv.start()

		str_path = str(path)
		self.current_track = str_path
		self.mpv_paused = False
		self.time_pos = 0
		self.last_track_change = time.time()

		if str_path.startswith(("http://", "https://")):
			self._log_url(str_path)

		show_win = bool(self.mpv_visible and getattr(self.mpv, "has_display", True))
		await self.mpv.set_force_window(show_win)
		await self.mpv.load_file(str_path)
		await self.mpv.set_pause(False)
		await self.mpv.set_mute(True if self._has_local_player() else self.server_muted)

		if str_path == self.radio_announcement_path and show_win:
			sub_candidate = Path(str_path).with_suffix(".srt")
			if not sub_candidate.is_file():
				sub_candidate = Path(str_path).with_suffix(".ass")
			if not sub_candidate.is_file():
				sub_candidate = Path(str_path).with_suffix(".lrc")
			if not sub_candidate.is_file() and self.radio_pregenerated_path:
				pre_sub = Path(self.radio_pregenerated_path).with_suffix(".srt")
				if not pre_sub.is_file():
					pre_sub = Path(self.radio_pregenerated_path).with_suffix(".ass")
				if not pre_sub.is_file():
					pre_sub = Path(self.radio_pregenerated_path).with_suffix(".lrc")
				if pre_sub.is_file():
					sub_candidate = pre_sub
			if sub_candidate.is_file():
				try:
					await self.mpv.add_subtitle(str(sub_candidate))
				except Exception as sub_err:
					logger.debug(f"Fallo cargando subtítulos en MPV: {sub_err}")

		if str_path != self.radio_announcement_path and self.radio_mode_enabled:
			track_duration = get_track_duration_seconds(str_path, self.tracks_cache)
			self._start_radio_pregeneration(current_track_path=str_path, track_duration=track_duration)

	def _prune_radio_archive(self, max_files: int | None = None) -> int:
		limit = max_files if max_files is not None else self.radio_archive_max_files
		return self.radio_service.prune_radio_archive(self.radio_archive_dir, max_files=limit)

	def _archive_radio_announcement(
		self,
		src_mp3_path: str | Path | None = None,
		script_text: str = "",
		display_title: str = "",
	) -> Path | None:
		return self.radio_service.archive_radio_announcement(
			archive_dir=self.radio_archive_dir,
			script_text=script_text,
			display_title=display_title,
			max_files=self.radio_archive_max_files,
		)

	def is_radio_due(self) -> bool:
		elapsed = time.time() - getattr(self, "last_radio_time", 0.0)
		time_threshold = getattr(self, "radio_time_until_next", 600.0)
		return elapsed >= time_threshold

	def is_radio_pregeneration_due(self, track_duration: float = 0.0) -> bool:
		elapsed = time.time() - getattr(self, "last_radio_time", 0.0)
		time_threshold = getattr(self, "radio_time_until_next", 600.0)
		return (elapsed + track_duration) >= time_threshold

	def _reset_radio_schedule(self) -> None:
		self.last_radio_time = time.time()
		self.radio_time_until_next = float(random.randint(300, 900))

	def _cancel_radio_pregeneration(self) -> None:
		self.radio_service.cancel_pregeneration()

	def _get_expected_radio_outro_mode(
		self,
		current_track_path: str | None = None,
		should_pause: bool = False,
	) -> str:
		if should_pause or (current_track_path is not None and self.pause_after_path == current_track_path):
			return "pause"
		has_next = bool(self.queue or (self.dj_carpincho_enabled and self.tracks_cache))
		return "continue" if has_next else "break"

	def _start_radio_pregeneration(self, current_track_path: str, track_duration: float = 0.0) -> None:
		if not self.radio_mode_enabled or not self.radio_service.is_available:
			return
		if not self.is_radio_pregeneration_due(track_duration=track_duration):
			return
		outro_mode = self._get_expected_radio_outro_mode(current_track_path=current_track_path)
		self.radio_service.start_pregeneration(track_duration=track_duration, outro_mode=outro_mode)

	def _select_candidate_dj_track(self, unplayed: list[dict[str, Any]]) -> dict[str, Any] | None:
		return self.dj_selector.select_candidate(unplayed, self.favorites, self.path_to_id)

	def _pick_dj_next(self) -> None:
		self.dj_selector.refresh_preview(
			queue=self.queue,
			history=self.history,
			current_track=self.current_track,
			tracks_cache=self.tracks_cache,
			favorites=self.favorites,
			path_to_id=self.path_to_id,
		)

	async def set_pause(self, paused: bool = True) -> None:
		self.mpv_paused = paused
		await self.mpv.set_pause(paused)

	async def set_volume(self, volume: float) -> None:
		self.volume = max(0, min(110, int(volume)))
		await self.mpv.set_volume(self.volume)

	async def stop_playback(self, reset_ui_state: bool = False) -> None:
		self.dj_selector.cancel_countdown()
		self._cancel_radio_pregeneration()
		self.dj_next_track = None
		self.current_track = None
		if reset_ui_state:
			self.mpv_paused = False
			self.dj_carpincho_enabled = False
			self.is_playing_radio_announcement = False
			self.is_synthesizing_radio = False
			self.time_pos = 0
		await self.mpv.stop_playback()
		await self.mpv.set_force_window(False)

	async def play_next(self, skipped_by_user: bool = False) -> None:
		self.dj_selector.cancel_countdown()

		async with self._play_next_lock:
			is_radio_track = self.current_track == self.radio_announcement_path
			if is_radio_track:
				self.is_playing_radio_announcement = False
			just_finished, should_pause = self.queue_manager.advance_current(exclude_from_history=is_radio_track)

			if (
				not skipped_by_user
				and self.radio_mode_enabled
				and self.radio_service.is_available
				and just_finished is not None
				and just_finished != self.radio_announcement_path
			):
				has_pregenerated = self.pregenerated_radio_announcement is not None or (
					self.radio_pregeneration_task is not None and not self.radio_pregeneration_task.done()
				)
				if self.is_radio_due() or has_pregenerated:
					check_net_fn = getattr(radio_service_mod, "check_internet_async", check_internet_async)
					if not await check_net_fn(timeout=0.8):
						self._reset_radio_schedule()
						logger.warning(
							"📻 Carpincho Locutor: no hay conexión a internet disponible. Omitiendo locución radial para no demorar la reproducción."
						)
					else:
						outro_mode = self._get_expected_radio_outro_mode(should_pause=should_pause)
						next_track_path = None
						if outro_mode == "continue":
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
								bg_offset = total_dur / 2.0
							elif total_dur > 0:
								bg_offset = total_dur * 0.4

						async def _set_synthesizing_radio(is_synth: bool) -> None:
							self.is_synthesizing_radio = is_synth
							await broadcast_state()

						ok, display_title, script, radio_err = await self.radio_service.get_or_synthesize(
							next_track_path=next_track_path,
							bg_offset=bg_offset,
							on_synthesis_status=_set_synthesizing_radio,
							outro_mode=outro_mode,
						)

						if ok:
							self._reset_radio_schedule()
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
							if should_pause:
								self.pause_after_path = self.radio_announcement_path
							await self.play_track(self.radio_announcement_path)
							await broadcast_state()
							return
						logger.warning(
							f"🎙️ Carpincho Locutor: No se pudo sintetizar la locución radial ({radio_err}). Pasando al tema siguiente..."
						)

			next_path = self.queue_manager.pop_next()
			if next_path is not None:
				self.dj_next_track = None
				await self.play_track(next_path)
				if should_pause:
					await self.set_pause(True)
			elif self.dj_carpincho_enabled and self.tracks_cache:
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
					self.dj_next_track = chosen
					await broadcast_state()

					if not skipped_by_user and just_finished != self.radio_announcement_path:

						async def _run_dj_countdown(target_track: dict[str, Any], pause_after: bool) -> None:
							try:
								await self.mpv.set_pause(True)
								await asyncio.sleep(10)
								await self.mpv.set_pause(False)
								async with self._play_next_lock:
									if self.current_track is not None:
										if self.dj_next_track == target_track:
											self.dj_next_track = None
											await broadcast_state()
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

					self.dj_next_track = None
					await self.play_track(chosen["path"])
					if should_pause:
						await self.set_pause(True)
					self._pick_dj_next()
					await broadcast_state()
					return
				else:
					logger.info("DJ Carpincho se quedó sin temas nuevos esta sesión.")
					self.dj_carpincho_enabled = False
					await self.stop_playback()
			else:
				await self.stop_playback()

			self._pick_dj_next()
			await broadcast_state()

	async def play_prev(self) -> None:
		prev_path = self.queue_manager.rewind_previous()
		if prev_path:
			await self.play_track(prev_path)
		elif self.current_track:
			await self.play_track(self.current_track)

	async def toggle_queue(self, path: str) -> None:
		added = self.queue_manager.toggle(path)
		if added and not self.current_track and not self.is_synthesizing_radio:
			await self.play_next(skipped_by_user=True)
			return
		self._pick_dj_next()

	async def jump(self, target_type: str, index: int) -> None:
		if target_type == "queue":
			self.queue_manager.jump_to_queue(index)
			await self.play_next(skipped_by_user=True)
		elif target_type == "history":
			target = self.queue_manager.jump_to_history(index)
			if target:
				await self.play_track(target)

	def get_top_played(self) -> list[dict[str, Any]]:
		now = time.time()
		two_months_ago = now - (30 * 24 * 3600 * 2)
		try:
			rows = self.history_repo.get_top_played(limit=50, since=two_months_ago)
			results = [(r["track_id"], r["count"]) for r in rows]
		except Exception as e:
			logger.error(f"Error calculando el top played: {e}")
			return []

		top_played: list[dict[str, Any]] = []
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
