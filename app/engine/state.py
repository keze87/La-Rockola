"""
Coordinador de estado del reproductor y de la aplicación: APIState.
Maneja la cola, historial, escaneo en segundo plano, análisis de mood,
locución de DJ Carpincho e integración con MPV y MPRIS.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import gc
import json
import logging
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile

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
from app.engine.audio_analysis import (
	compare_fps,
	extract_audio_features_ffmpeg,
	find_binary,
	is_mood_available,
	parse_fp,
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

from app.engine.mpv_controller import AsyncMpvController
from app.services.library import (
	Track,
	get_track_duration_seconds,
)
from app.services.radio import (
	DEFAULT_WEATHER_LOCATION,
	HAS_EDGE_TTS,
	create_radio_announcement,
	embed_cover_art_in_mp3,
	get_carpincho_cover_path,
	is_valid_mp3_file,
	mix_announcement_with_bg_track,
)

logger = logging.getLogger("RockolaCarpincho")

RADIO_PREGENERATION_MAX_AGE_SECONDS: float = 15.0 * 60.0  # 15 minutos de caducidad tras pausa prolongada


def _is_valid_radio_mp3_file(path: Path | str) -> bool:
	"""Valida que el archivo de locución exista y su cabecera corresponda a un MP3 válido."""
	if is_valid_mp3_file is not None:
		return is_valid_mp3_file(path)
	try:
		p = Path(path)
		if not p.is_file() or p.stat().st_size < 4:
			return False
		with p.open("rb") as f:
			head = f.read(10)
		return bool(head.startswith(b"ID3") or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0))
	except Exception:
		return False


def _unpack_radio_result(res) -> tuple[bool, str, str, str]:
	"""Normaliza el resultado devuelto por create_radio_announcement."""
	ok = res.ok if hasattr(res, "ok") else bool(res[0])
	title = res.display_title if hasattr(res, "display_title") else str(res[1])
	script = res.script if hasattr(res, "script") else str(res[2])
	err = res.error if hasattr(res, "error") else (script if not ok else "")
	return ok, title, script, err or ""


def _get_active_db_path() -> Path | str:
	from app.db.database import get_default_db_path

	return get_default_db_path()


def _srv(name: str, fallback: Any = None) -> Any:
	"""Obtiene dinámicamente un atributo de server.py si está disponible, permitiendo monkeypatching en tests."""
	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, name):
		return getattr(srv, name)
	return fallback


async def broadcast_state(include_library=False):
	"""Envía por WebSocket el diff de estado a todos los clientes conectados."""
	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, "broadcast_state") and srv.broadcast_state != broadcast_state:
		res = srv.broadcast_state(include_library=include_library)
		if asyncio.iscoroutine(res):
			await res
		return
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
	def __init__(self, initial_dir=None, secondary_dir=None):
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

		self.favorites = self._load_favs_from_db()

		# Modo Radio
		self.radio_mode_enabled = True
		self.radio_track_counter = 0
		self.radio_tracks_until_next = random.randint(1, 2)
		self.is_playing_radio_announcement = False
		self.is_synthesizing_radio = False
		self.radio_announcement_path = str(Path(tempfile.gettempdir()) / "radio_announcement.mp3")
		self.radio_pregenerated_path = str(Path(tempfile.gettempdir()) / "radio_pregenerated.mp3")
		self.radio_archive_dir = Path(tempfile.gettempdir()) / "la_rockola_radio_archive"
		self.radio_archive_max_files = 60
		self.radio_pregeneration_task: asyncio.Task | None = None
		self.pregenerated_radio_announcement: dict | None = None
		self.weather_location = DEFAULT_WEATHER_LOCATION

		# Estado de red del servidor y navegador
		self.open_browser = True
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
			"has_edge_tts": bool(_srv("HAS_EDGE_TTS", HAS_EDGE_TTS)),
			"has_ffmpeg": bool(_srv("is_mood_available", is_mood_available)()),
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
			with sqlite3.connect(_get_active_db_path()) as conn:
				c = conn.cursor()
				c.execute("SELECT track_id FROM favorites")
				return [row[0] for row in c.fetchall()]
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
				with sqlite3.connect(_get_active_db_path()) as conn:
					# Agregamos la reproducción actual
					conn.execute(
						"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
						(track_id, now),
					)
					conn.commit()

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

			with sqlite3.connect(_get_active_db_path()) as conn:
				# Borramos si existía antes para no duplicar y que vuelva a aparecer arriba
				conn.execute("DELETE FROM url_logs WHERE url = ?", (url,))

				# Insertamos la entrada fresca
				conn.execute(
					"INSERT INTO url_logs (url, title, artist, played_at) VALUES (?, ?, ?, ?)",
					(url, title, artist, played_at),
				)

				# Mantenemos el log cortito (ej: máximo 200 links) para que no sea infinito
				# conn.execute("""
				# 	DELETE FROM url_logs
				# 	WHERE id NOT IN (
				# 		SELECT id FROM url_logs ORDER BY id DESC LIMIT 200
				# 	)
				# """)
				conn.commit()
		except Exception as e:
			logger.error(f"Error guardando el log de URLs en DB: {e}")

	def recalculate_mood_scores(self):
		"""Recalcula el mood_score normalizado para todos los temas en tracks_cache."""

		def _normalize(val, values):
			if val <= 0 or not values:
				return 0.5
			lo, hi = min(values), max(values)
			if hi - lo < 1e-9:
				return 0.5
			return (val - lo) / (hi - lo)

		tracks = self.tracks_cache
		if not tracks:
			return

		valid_bpms = [t.get("bpm", -1.0) for t in tracks if t.get("bpm", -1.0) > 0]
		valid_energies = [t.get("energy", -1.0) for t in tracks if t.get("energy", -1.0) > 0]
		valid_centroids = [t.get("spectral_centroid", -1.0) for t in tracks if t.get("spectral_centroid", -1.0) > 0]

		for t in tracks:
			b = t.get("bpm", -1.0)
			e = t.get("energy", -1.0)
			c = t.get("spectral_centroid", -1.0)

			if b <= 0:
				t["mood_score"] = 0.0
			else:
				nb = _normalize(b, valid_bpms)
				ne = _normalize(e, valid_energies)
				nc = _normalize(c, valid_centroids)
				t["mood_score"] = round(0.5 * nb + 0.35 * ne + 0.15 * nc, 4)

	def scan_directory(
		self,
		target_dirs: list,
		extract_mood: bool = True,
		max_workers: int = 16,
		extract_fingerprint: bool | None = None,
	):
		if extract_fingerprint is None:
			extract_fingerprint = extract_mood

		logger.info(f"Pegando una ojeada por estas carpetas: {target_dirs}")
		extensions = [
			"*.flac",
			"*.m4a",
			"*.mp3",
			"*.ogg",
			"*.wav",
			"*.mp4",
			"*.mkv",
			"*.avi",
			"*.webm",
		]
		raw_files = []

		self.scan_phase = "discovering"
		self.scan_current = 0
		self.scan_total = 0
		self.scan_message = "Buscando archivos de audio..."

		for target_dir in target_dirs:
			if not target_dir:
				continue

			music_dir = Path(target_dir).expanduser()
			if not music_dir.exists():
				logger.warning(f"Che, este lugar está más pelado que la nada misma: {music_dir}")
				continue

			for ext in extensions:
				raw_files.extend(list(music_dir.rglob(ext)))

		logger.info(f"Encontré {len(raw_files)} archivos en total. Revisando cuáles son nuevos o cambiaron...")
		self.scan_phase = "metadata"
		self.scan_total = len(raw_files)
		self.scan_current = 0
		self.scan_message = f"Encontré {len(raw_files)} archivos en total. Revisando cuáles son nuevos o cambiaron..."

		raw_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

		has_ffmpeg = is_mood_available()
		has_fpcalc = bool(shutil.which("fpcalc"))

		# --- CARGAMOS LA CACHÉ DE LA DB AL PRINCIPIO ---
		db_cache = {}
		try:
			with sqlite3.connect(_get_active_db_path()) as conn:
				c = conn.cursor()
				c.execute(
					"SELECT path, mtime, file_size, track_id, title, album, artist, duration_str, bpm, energy, spectral_centroid, fingerprint FROM tracks"
				)
				for row in c.fetchall():
					(
						db_path,
						db_mtime,
						db_size,
						db_tid,
						db_title,
						db_album,
						db_artist,
						db_dur,
						db_bpm,
						db_energy,
						db_centroid,
						db_fingerprint,
					) = row
					db_cache[db_path] = {
						"mtime": db_mtime,
						"file_size": db_size,
						"track_hash": db_tid,
						"title": db_title,
						"album": db_album,
						"artist": db_artist,
						"duration_str": db_dur,
						"bpm": db_bpm if db_bpm is not None else 0.0,
						"energy": db_energy if db_energy is not None else 0.0,
						"spectral_centroid": (db_centroid if db_centroid is not None else 0.0),
						"fingerprint": db_fingerprint,
					}
		except Exception as e:
			logger.warning(f"No pude cargar la caché de la DB (capaz está vacía): {e}")

		self.id_to_current_path.clear()
		self.path_to_id.clear()
		new_cache = {}
		tracks_to_insert = []
		seen_track_ids = set()
		new_tracks_for_reconciliation = []

		cache_hits = {}
		miss_files = []

		for f in raw_files:
			file_str = str(f)
			try:
				stat = f.stat()
				current_mtime = stat.st_mtime
				current_size = stat.st_size
			except OSError:
				continue

			# 1. Miramos si está en memoria (escaneo en caliente)
			if (
				file_str in self.track_cache_by_path
				and self.track_cache_by_path[file_str]["mtime"] == current_mtime
				and (
					self.track_cache_by_path[file_str]["data"].get("bpm", 0.0) != 0.0
					or not has_ffmpeg
					or not extract_mood
				)
			):
				td = self.track_cache_by_path[file_str]["data"]
				th = td.get("track_hash")
				cache_hits[file_str] = (current_mtime, td, th)

			# 2. Miramos si está intacto en la DB (arranque de servidor)
			elif (
				file_str in db_cache
				and db_cache[file_str]["mtime"] == current_mtime
				and db_cache[file_str]["file_size"] == current_size
				and (db_cache[file_str].get("bpm", 0.0) != 0.0 or not has_ffmpeg or not extract_mood)
				and (db_cache[file_str].get("fingerprint") is not None or not has_fpcalc or not extract_fingerprint)
			):
				cached = db_cache[file_str]
				th = cached["track_hash"]
				td = {
					"path": file_str,
					"display_title": cached["title"],
					"display_artist": cached["artist"],
					"album": cached["album"],
					"duration_str": cached["duration_str"],
					"search_string": f"{cached['artist']} {cached['title']}".lower(),
					"title": cached["title"],
					"artist": cached["artist"],
					"track_hash": th,
					"bpm": cached["bpm"],
					"energy": cached["energy"],
					"spectral_centroid": cached["spectral_centroid"],
					"fingerprint": cached.get("fingerprint"),
				}
				cache_hits[file_str] = (current_mtime, td, th)
			else:
				miss_files.append((f, current_mtime, current_size))

		# 3. Procesamos los archivos sin caché en PARALELO
		miss_results = {}
		if miss_files:

			def _process_single_file(item):
				target_f, mtime, size = item
				track_obj = Track(target_f, extract_mood=extract_mood, extract_fingerprint=extract_fingerprint)
				track_dict = track_obj.to_dict()
				track_hash = track_obj.track_hash
				db_tuple = (
					track_hash,
					str(target_f),
					track_dict["title"],
					track_dict.get("album", "Desconocido"),
					track_dict["artist"],
					track_dict["duration_str"],
					mtime,
					size,
					track_dict.get("bpm", 0.0),
					track_dict.get("energy", 0.0),
					track_dict.get("spectral_centroid", 0.0),
					track_obj.fingerprint,
				)
				return (str(target_f), mtime, track_dict, track_hash, db_tuple, track_obj.fingerprint)

			worker_count = min(max_workers, (os.cpu_count() or 4) * 2)
			with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
				futures = {executor.submit(_process_single_file, item): item for item in miss_files}
				for processed_count, future in enumerate(concurrent.futures.as_completed(futures), 1):
					res = future.result()
					if res:
						f_str, mtime, t_dict, t_hash, db_tup, fp = res
						miss_results[f_str] = (mtime, t_dict, t_hash, db_tup, fp)
					self.scan_current = len(cache_hits) + processed_count
					if processed_count % 50 == 0:
						logger.info(
							f"Ya procesé la data de {processed_count}/{len(miss_files)} joyitas nuevas/modificadas..."
						)
						gc.collect()

		# Armamos la lista ordenada de tracks conservando el orden de raw_files
		tracks = []
		for f in raw_files:
			file_str = str(f)
			if file_str in cache_hits:
				current_mtime, track_dict, track_hash = cache_hits[file_str]
				seen_track_ids.add(track_hash)
				new_cache[file_str] = {"mtime": current_mtime, "data": track_dict}
				tracks.append(track_dict)
				self.id_to_current_path[track_hash] = file_str
				self.path_to_id[file_str] = track_hash
			elif file_str in miss_results:
				current_mtime, track_dict, track_hash, db_tuple, fp = miss_results[file_str]
				tracks_to_insert.append(db_tuple)
				seen_track_ids.add(track_hash)
				if fp:
					new_tracks_for_reconciliation.append(track_dict)
				new_cache[file_str] = {"mtime": current_mtime, "data": track_dict}
				tracks.append(track_dict)
				self.id_to_current_path[track_hash] = file_str
				self.path_to_id[file_str] = track_hash

		# --- RECONCILIACIÓN DE HUELLAS ACÚSTICAS ---
		# Si un archivo se reemplazó (ej. MP3 a FLAC) o se le metió una tapa (cambió tamaño),
		# su viejo "track_hash" va a faltar y va a haber uno nuevo para la misma canción.
		missing_db_tracks = [t for t in db_cache.values() if t["track_hash"] not in seen_track_ids]
		if missing_db_tracks and new_tracks_for_reconciliation:
			logger.info(
				f"🔎 Reconciliando {len(new_tracks_for_reconciliation)} temas nuevos con {len(missing_db_tracks)} temas desaparecidos..."
			)

			for new_t in new_tracks_for_reconciliation:
				new_fp = parse_fp(new_t.get("fingerprint"))
				if not new_fp:
					continue

				best_match = None
				best_sim = 0.0

				for miss_t in missing_db_tracks:
					miss_fp = parse_fp(miss_t.get("fingerprint"))
					if not miss_fp:
						continue

					sim = compare_fps(new_fp, miss_fp)
					if sim > best_sim:
						best_sim = sim
						best_match = miss_t

				# Si hay similitud acústica del 85% o más, asumimos que es exactamente la misma canción
				if best_sim > 0.85:
					old_id = best_match["track_hash"]
					new_id = new_t["track_hash"]
					logger.info(
						f"✨ ¡Migración detectada! '{new_t['display_title']}' reemplaza a '{best_match['title']}' (Similitud: {best_sim:.2%}) -> Conservando favoritos e historial."
					)

					new_t["track_hash"] = old_id

					for trk in tracks:
						if trk["path"] == new_t["path"]:
							trk["track_hash"] = old_id
							break

					for idx, ins_tuple in enumerate(tracks_to_insert):
						if ins_tuple[1] == new_t["path"]:
							l = list(ins_tuple)
							l[0] = old_id
							tracks_to_insert[idx] = tuple(l)
							break

					self.id_to_current_path[old_id] = new_t["path"]
					self.path_to_id[new_t["path"]] = old_id
					if new_id in self.id_to_current_path:
						del self.id_to_current_path[new_id]

					seen_track_ids.add(old_id)
					missing_db_tracks.remove(best_match)

		self.tracks_cache = tracks
		self.recalculate_mood_scores()
		self.track_cache_by_path = new_cache

		if tracks_to_insert:
			try:
				with sqlite3.connect(_get_active_db_path()) as conn:
					conn.executemany(
						"""
						INSERT OR REPLACE INTO tracks (track_id, path, title, album, artist, duration_str, mtime, file_size, bpm, energy, spectral_centroid, fingerprint)
						VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
					""",
						tracks_to_insert,
					)
					conn.commit()
					logger.info(f"Guardados {len(tracks_to_insert)} metadatos frescos en la base de datos.")
			except Exception as e:
				logger.error(f"Error guardando tracks en la DB: {e}")

		self.scan_current = len(tracks)
		self.scan_total = len(tracks)
		self.scan_message = "¡Listo el escaneo, maestro!"
		logger.info("¡Listo el escaneo, maestro!")
		return tracks

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
		"""Worker que procesa de forma asíncrona BPM/mood y huella acústica en lotes pequeños."""
		finder = _srv("find_binary", find_binary)
		ffmpeg_bin = finder("ffmpeg")
		has_fpcalc = shutil.which("fpcalc") is not None

		if not ffmpeg_bin and not has_fpcalc:
			logger.info("Sin FFmpeg ni fpcalc, salteando análisis acústico de fondo.")
			self.is_analyzing_mood = False
			self.scan_phase = "idle"
			return

		pending_tracks = []
		for t in self.tracks_cache:
			need_mood = bool(ffmpeg_bin and t.get("bpm", 0.0) == 0.0)
			need_fp = bool(has_fpcalc and not t.get("fingerprint"))
			if need_mood or need_fp:
				pending_tracks.append((t, need_mood, need_fp))

		if not pending_tracks:
			self.is_analyzing_mood = False
			self.scan_phase = "idle"
			return

		self.is_analyzing_mood = True
		self.scan_phase = "mood"
		self.scan_total = len(pending_tracks)
		self.scan_current = 0
		self.scan_message = f"Sintonizando la vibra de los temas (0/{len(pending_tracks)})..."
		try:
			await broadcast_state()
		except Exception:
			pass

		logger.info(f"Comenzando análisis acústico en segundo plano para {len(pending_tracks)} temas...")

		def _process_mood_item(item):
			t_dict, need_mood, need_fp = item
			path_str = t_dict["path"]
			bpm = t_dict.get("bpm", 0.0)
			energy = t_dict.get("energy", 0.0)
			centroid = t_dict.get("spectral_centroid", 0.0)
			fp = t_dict.get("fingerprint")

			if need_mood:
				tag_bpm = None
				try:
					audio = MutagenFile(path_str, easy=True) or MutagenFile(path_str)
					if audio and getattr(audio, "tags", None):
						tags = {k.lower(): v for k, v in audio.tags.items()}
						for k in ["tbpm", "bpm", "tempo", "tmpo"]:
							if k in tags:
								val = tags[k]
								val_str = val[0] if isinstance(val, list) else str(val)
								clean_num = re.search(r"[-+]?\d*\.?\d+", str(val_str))
								if clean_num and float(clean_num.group(0)) > 0:
									tag_bpm = round(float(clean_num.group(0)), 1)
									break
				except Exception:
					pass

				extractor = _srv("extract_audio_features_ffmpeg", extract_audio_features_ffmpeg)
				b, e, c = extractor(path_str, ffmpeg_bin)
				if b < 0.0:
					bpm, energy, centroid = -1.0, -1.0, -1.0
				else:
					bpm = tag_bpm if tag_bpm is not None else b
					energy = e
					centroid = c

			if need_fp and shutil.which("fpcalc"):
				try:
					finder = _srv("find_binary", find_binary)
					fpcalc_bin = finder("fpcalc") or "fpcalc"
					proc = subprocess.run(
						[fpcalc_bin, "-raw", "-length", "60", path_str],
						capture_output=True,
						text=True,
						timeout=10,
						check=False,
					)
					for line in proc.stdout.splitlines():
						if line.startswith("FINGERPRINT="):
							fp = line.split("=", 1)[1]
							break
				except Exception as e:
					logger.debug(f"Pifió fpcalc en background para {path_str}: {e}")

			return t_dict["track_hash"], path_str, bpm, energy, centroid, fp

		batch_size = 25
		max_workers = min(4, os.cpu_count() or 2)

		try:
			for i in range(0, len(pending_tracks), batch_size):
				batch = pending_tracks[i : i + batch_size]
				loop = asyncio.get_running_loop()

				with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
					batch_results = await loop.run_in_executor(
						pool,
						lambda b: [_process_mood_item(item) for item in b],
						batch,
					)

				# Actualizamos en SQLite el lote
				try:
					with sqlite3.connect(_get_active_db_path()) as conn:
						conn.executemany(
							"UPDATE tracks SET bpm=?, energy=?, spectral_centroid=?, fingerprint=? WHERE track_id=?",
							[(r[2], r[3], r[4], r[5], r[0]) for r in batch_results],
						)
						conn.commit()
				except Exception as e:
					logger.error(f"Error actualizando mood en DB: {e}")

				# Actualizamos en memoria
				res_map = {r[0]: r for r in batch_results}
				for t in self.tracks_cache:
					tid = t.get("track_hash")
					if tid in res_map:
						_, p, b, e, c, fp = res_map[tid]
						t["bpm"] = b
						t["energy"] = e
						t["spectral_centroid"] = c
						t["fingerprint"] = fp
						if p in self.track_cache_by_path:
							self.track_cache_by_path[p]["data"].update(
								{
									"bpm": b,
									"energy": e,
									"spectral_centroid": c,
									"fingerprint": fp,
								}
							)

				self.scan_current = min(self.scan_total, i + len(batch))
				self.scan_message = f"Sintonizando la vibra ({self.scan_current}/{self.scan_total})..."
				self.recalculate_mood_scores()
				try:
					await broadcast_state()
				except Exception:
					pass
				gc.collect()

		except asyncio.CancelledError:
			logger.info("Análisis de mood en background cancelado por nueva solicitud.")
			raise
		finally:
			self.is_analyzing_mood = False
			self.scan_phase = "idle"
			self.scan_message = ""
			try:
				await broadcast_state(include_library=True)
			except Exception:
				pass
			logger.info("Análisis acústico en segundo plano finalizado.")

	async def fetch_yt_dlp_metadata(self, url):
		"""Obtiene asincrónicamente la data de yt-dlp y avisa a los clientes"""
		if url in self.url_metadata:
			return

		finder = _srv("find_binary", find_binary)
		ytdlp_bin = finder("yt-dlp")
		if not ytdlp_bin:
			try:
				import ytdlp_installer

				try:
					from scripts import ytdlp_installer
				except ImportError:
					import ytdlp_installer

				logger.info("yt-dlp no encontrado para procesar link de YouTube. Intentando instalar...")
				installed = await asyncio.to_thread(ytdlp_installer.ensure_ytdlp)
				if installed:
					ytdlp_bin = installed
			except Exception as e:
				logger.error(f"No se pudo instalar yt-dlp en tiempo de ejecución: {e}")

		if not ytdlp_bin:
			ytdlp_bin = "yt-dlp"

		try:
			logger.info(f"Che yt-dlp, averiguate la data de este link: {url}")
			proc = await asyncio.create_subprocess_exec(
				ytdlp_bin,
				"--dump-json",
				"--no-warnings",
				"--no-playlist",
				url,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.DEVNULL,
				env=get_clean_env(),
			)
			stdout, _ = await proc.communicate()

			if stdout:
				data = json.loads(stdout.decode("utf-8"))
				title = data.get("title", "Título Misterioso")
				artist = data.get("uploader", "Artista NN")
				duration = data.get("duration", 0)

				mins = int(duration // 60) if duration else 0
				secs = int(duration % 60) if duration else 0

				self.url_metadata[url] = {
					"path": url,
					"display_title": title,
					"display_artist": artist,
					"album": "Internet",
					"duration_str": f"{mins}:{secs:02d}",
					"search_string": f"{artist} {title}".lower(),
					"title": title,
					"artist": artist,
				}

				self.id_to_current_path[url] = url
				self.path_to_id[url] = url

				logger.info(f"Data fresquita conseguida: {artist} - {title}")
				await broadcast_state()
		except Exception as e:
			logger.error(f"Pifió yt-dlp sacando la info de {url}, se empacó: {e}")

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
		# Cancelar el countdown del DJ si el usuario eligió un tema manualmente
		if self.dj_countdown_task and not self.dj_countdown_task.done():
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
		"""Elimina los guiones históricos más antiguos por encima del límite configurado y limpia cualquier MP3 residual."""
		limit = max_files if max_files is not None else self.radio_archive_max_files
		if limit <= 0:
			return 0
		try:
			if not self.radio_archive_dir.is_dir():
				return 0
			# Limpiar cualquier MP3 residual en el directorio temporal de archivo
			for mp3 in self.radio_archive_dir.glob("radio_*.mp3"):
				try:
					mp3.unlink(missing_ok=True)
				except Exception:
					pass

			# Ordenar por mtime ascendente (los más antiguos primero)
			txt_files = sorted(
				self.radio_archive_dir.glob("radio_*.txt"),
				key=lambda p: (p.stat().st_mtime, p.name),
			)
			pruned = 0
			if len(txt_files) > limit:
				to_remove = txt_files[: len(txt_files) - limit]
				for txt in to_remove:
					txt.unlink(missing_ok=True)
					pruned += 1
			return pruned
		except Exception as e:
			logger.debug(f"Error podando archivo histórico de locuciones: {e}")
			return 0

	def _archive_radio_announcement(
		self,
		src_mp3_path: str | Path | None = None,
		script_text: str = "",
		display_title: str = "",
	) -> Path | None:
		"""
		Guarda el guion .txt en el directorio de archivo histórico con marca temporal.
		No almacena archivos MP3 en /tmp ya que los segmentos de audio se encuentran
		persistidos en la base de datos SQLite (tts_cache).
		"""
		try:
			self.radio_archive_dir.mkdir(parents=True, exist_ok=True)

			now = datetime.now(UTC).astimezone()
			ts_str = now.strftime("%Y-%m-%d_%H-%M-%S")
			dest_txt = self.radio_archive_dir / f"radio_{ts_str}.txt"

			# Si ya existiera en el mismo segundo, añadir sufijo con microsegundos
			if dest_txt.exists():
				dest_txt = self.radio_archive_dir / f"radio_{ts_str}_{now.microsecond:06d}.txt"

			header = f"Título: {display_title}\nFecha: {now.isoformat()}\n\n" if display_title else ""
			dest_txt.write_text(f"{header}{script_text.strip()}\n", encoding="utf-8")

			logger.debug(f"📻 Guion radial archivado en: {dest_txt.name}")

			# Poda de retención
			self._prune_radio_archive()

			return dest_txt
		except Exception as e:
			logger.debug(f"No se pudo archivar el guion radial: {e}")
			return None

	def _cancel_radio_pregeneration(self):
		"""Cancela cualquier pregeneración en curso de la locución radial y limpia archivos parciales."""
		if self.radio_pregeneration_task and not self.radio_pregeneration_task.done():
			self.radio_pregeneration_task.cancel()
		self.radio_pregeneration_task = None
		self.pregenerated_radio_announcement = None
		if self.radio_pregenerated_path:
			try:
				p = Path(self.radio_pregenerated_path)
				if p.exists():
					p.unlink(missing_ok=True)
			except Exception as e:
				logger.debug(f"Error borrando archivo parcial de pregeneración: {e}")

	def _start_radio_pregeneration(self, current_track_path: str, track_duration: float = 0.0):
		"""
		Dispara la síntesis y procesamiento de la locución radial en segundo plano
		al comienzo de la canción, calculando el cuarto horario estimado en el que terminará el tema.
		Genera la pista de voz limpia y masterizada para poder superponer la cortina musical
		en caliente sobre la canción que efectivamente toque al finalizar.
		"""
		has_edge = _srv("HAS_EDGE_TTS", HAS_EDGE_TTS)
		create_ann_fn = _srv("create_radio_announcement", create_radio_announcement)
		if not self.radio_mode_enabled or not has_edge or create_ann_fn is None:
			return

		# Solo pregenerar si el contador alcanzará el umbral al terminar este tema
		if (self.radio_track_counter + 1) < self.radio_tracks_until_next:
			return

		self._cancel_radio_pregeneration()

		async def _do_pregeneration():
			from datetime import datetime

			now = datetime.now(UTC).astimezone()
			finish_dt = now + timedelta(seconds=max(0.0, track_duration)) if track_duration > 0 else now

			try:
				logger.info("📻 Carpincho Locutor: Iniciando pregeneración anticipada al comienzo de la canción...")
				res = await create_ann_fn(
					self.radio_pregenerated_path,
					dt=finish_dt,
					bg_track_path=None,
					weather_location=self.weather_location,
				)
				res_ok, res_title, res_script, res_err = _unpack_radio_result(res)

				if res_ok:
					self.pregenerated_radio_announcement = {
						"path": self.radio_pregenerated_path,
						"display_title": res_title,
						"script": res_script,
						"created_at": time.time(),
					}
					logger.info(
						"📻 Carpincho Locutor: Pregeneración de voz lista con anticipación para el final del tema."
					)
				else:
					logger.debug(f"Pregeneración radial no completada: {res_err}")
			except asyncio.CancelledError:
				logger.debug("Pregeneración radial cancelada.")
			except Exception as e:
				logger.debug(f"Excepción en pregeneración radial: {e}")

		self.radio_pregeneration_task = asyncio.create_task(_do_pregeneration())

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
		# Si hay un countdown del DJ corriendo en otra task que no sea esta, lo matamos
		if (
			self.dj_countdown_task
			and not self.dj_countdown_task.done()
			and self.dj_countdown_task != asyncio.current_task()
		):
			self.dj_countdown_task.cancel()
			self.dj_countdown_task = None

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
		has_edge = _srv("HAS_EDGE_TTS", HAS_EDGE_TTS)
		create_ann_fn = _srv("create_radio_announcement", create_radio_announcement)
		has_next_track = bool(self.queue or (self.dj_carpincho_enabled and self.tracks_cache))
		if (
			not skipped_by_user
			and self.radio_mode_enabled
			and has_edge
			and create_ann_fn is not None
			and has_next_track
			and just_finished is not None
			and just_finished != self.radio_announcement_path
		):
			self.radio_track_counter += 1
			if self.radio_track_counter >= self.radio_tracks_until_next:
				# Preguntamos si hay internet puntualmente antes de activar la síntesis radial
				chk_internet = _srv("check_internet_async", check_internet_async)
				if not await chk_internet(timeout=0.8):
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

					async def _apply_hot_mix_to_announcement(voice_file: Path, out_file: Path, title: str) -> bool:
						"""Superpone la cortina musical en caliente sobre la voz usando la pista que efectivamente suena después."""
						mixed_ok = False
						mix_fn = _srv("mix_announcement_with_bg_track", mix_announcement_with_bg_track)
						embed_fn = _srv("embed_cover_art_in_mp3", embed_cover_art_in_mp3)
						if next_track_path and Path(next_track_path).is_file() and mix_fn is not None:
							try:
								mixed = await asyncio.to_thread(
									mix_fn,
									voice_file,
									out_file,
									next_track_path,
									bg_offset,
									0.1,
									10.0,
								)
								if mixed:
									if embed_fn is not None:
										get_cov = _srv("get_carpincho_cover_path", get_carpincho_cover_path)
										cover_p = get_cov() if get_cov else None
										await asyncio.to_thread(
											embed_fn,
											out_file,
											cover_p,
											title,
											"Carpincho Locutor 🎙️",
											"La Rockola del Carpincho",
										)
									mixed_ok = True
							except Exception as mix_err:
								logger.debug(f"Fallo en mezcla en caliente con '{next_track_path}': {mix_err}")

						# Copiar archivos de subtítulos sincronizados si existen
						for ext in (".lrc", ".srt"):
							sub_src = voice_file.with_suffix(ext)
							sub_dst = out_file.with_suffix(ext)
							if sub_src.is_file():
								try:
									shutil.copyfile(sub_src, sub_dst)
								except Exception as copy_sub_err:
									logger.debug(f"Error copiando subtítulo {sub_src} a {sub_dst}: {copy_sub_err}")

						if not mixed_ok:
							# Fallback seguro si no hay pista de fondo o falló la mezcla en caliente
							try:
								shutil.copyfile(voice_file, out_file)
							except Exception as copy_err:
								logger.error(
									f"Error copiando archivo de locución {voice_file} a {out_file}: {copy_err}"
								)
								return False
						return True

					# 1. Comprobar si ya está lista la pregeneración de fondo (0 ms de latencia)
					if self.pregenerated_radio_announcement:
						pre = self.pregenerated_radio_announcement
						pre_created_at = pre.get("created_at")
						pre_age = (time.time() - pre_created_at) if pre_created_at is not None else 0.0
						if pre_age > RADIO_PREGENERATION_MAX_AGE_SECONDS:
							logger.info(
								f"📻 Carpincho Locutor: La locución pregenerada expiró ({pre_age / 60:.1f} min > 15 min tras pausa). Descartando para sintetizar locución fresca..."
							)
						else:
							pre_p = Path(pre["path"])
							if _is_valid_radio_mp3_file(pre_p):
								if await _apply_hot_mix_to_announcement(
									pre_p, Path(self.radio_announcement_path), pre["display_title"]
								):
									ok = True
									display_title = pre["display_title"]
									script = pre.get("script", "")
									logger.info(
										"⚡ Carpincho Locutor: Transición con locución pregenerada y mezcla de cortina en caliente."
									)
							else:
								logger.warning(
									"📻 Carpincho Locutor: El archivo pregenerado está incompleto o no es un MP3 válido. Descartando..."
								)
						self.pregenerated_radio_announcement = None

					# 2. Si la tarea de pregeneración sigue corriendo, esperarla brevemente
					if not ok and self.radio_pregeneration_task and not self.radio_pregeneration_task.done():
						try:
							logger.info("📻 Carpincho Locutor: Esperando finalización de pregeneración en curso...")
							self.is_synthesizing_radio = True
							await broadcast_state()
							await asyncio.wait_for(asyncio.shield(self.radio_pregeneration_task), timeout=3.0)
							if self.pregenerated_radio_announcement:
								pre = self.pregenerated_radio_announcement
								pre_created_at = pre.get("created_at")
								pre_age = (time.time() - pre_created_at) if pre_created_at is not None else 0.0
								if pre_age > RADIO_PREGENERATION_MAX_AGE_SECONDS:
									logger.info(
										f"📻 Carpincho Locutor: La locución pregenerada expiró ({pre_age / 60:.1f} min > 15 min tras pausa). Descartando..."
									)
								else:
									pre_p = Path(pre["path"])
									if _is_valid_radio_mp3_file(pre_p):
										if await _apply_hot_mix_to_announcement(
											pre_p, Path(self.radio_announcement_path), pre["display_title"]
										):
											ok = True
											display_title = pre["display_title"]
											script = pre.get("script", "")
									else:
										logger.warning(
											"📻 Carpincho Locutor: El archivo pregenerado esperado está incompleto o no es un MP3 válido. Descartando..."
										)
								self.pregenerated_radio_announcement = None
						except Exception as wait_e:
							logger.debug(f"Espera de pregeneración agotada o falló: {wait_e}")
						finally:
							self.is_synthesizing_radio = False

					# 3. Fallback: síntesis en caliente si no hubo pregeneración
					if not ok:
						logger.info(
							f"🎙️ Carpincho Locutor: turno de locución radial (canción #{self.radio_track_counter}). Sintetizando..."
						)
						self.is_synthesizing_radio = True
						await broadcast_state()

						try:
							res = await create_ann_fn(
								self.radio_announcement_path,
								bg_track_path=next_track_path,
								bg_offset=bg_offset,
								bg_volume=0.1,
								weather_location=self.weather_location,
							)
							ok, display_title, script, radio_err = _unpack_radio_result(res)
						except Exception as e:
							ok = False
							display_title = ""
							script = ""
							radio_err = f"{type(e).__name__}: {e}"
						finally:
							self.is_synthesizing_radio = False

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
			self.dj_next_track = None  # Limpiamos (si la fila tenía temas, el DJ no pre-eligió)
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
					# Guardamos el countdown como task cancelable
					self.dj_countdown_task = asyncio.current_task()
					try:
						await self.mpv._send(json.dumps({"command": ["set_property", "pause", True]}))
						await asyncio.sleep(10)  # Pausa de 10 segundos antes de que el DJ arranque
						await self.mpv._send(json.dumps({"command": ["set_property", "pause", False]}))
					except asyncio.CancelledError:
						logger.info("Countdown del DJ cancelado, no se reproduce el tema pre-elegido.")
						if self.dj_next_track == chosen:
							self.dj_next_track = None
						return
					finally:
						self.dj_countdown_task = None

				self.dj_next_track = None  # Ahora sí borramos: el tema está por arrancar

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
			with sqlite3.connect(_get_active_db_path()) as conn:
				c = conn.cursor()
				# SQL hace todo el trabajo pesado: cuenta y ordena los más escuchados
				c.execute(
					"""
					SELECT track_id, COUNT(*) as count
					FROM play_history
					WHERE played_at >= ?
					  AND (track_id NOT LIKE '%radio_announcement.mp3%' OR track_id IN (SELECT track_id FROM tracks))
					GROUP BY track_id
					ORDER BY count DESC
					LIMIT 50
				""",
					(two_months_ago,),
				)
				results = c.fetchall()
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
