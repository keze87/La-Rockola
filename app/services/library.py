"""
Servicio de biblioteca musical: escaneo, hashing inteligente y cálculo de mood.
"""

import asyncio
import concurrent.futures
import gc
import hashlib
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile

from app.db.repositories import TrackRepository
from app.engine import audio_analysis
from app.engine.audio_analysis import (
	compare_fps,
	is_mood_available,
	parse_fp,
)

logger = logging.getLogger("RockolaCarpincho")


def generate_smart_hash(filepath: str | Path, chunk_size: int = 1024 * 1024) -> str:
	"""
	Lee 1MB al 15% y 1MB al 85% del archivo evitando metadatos iniciales y finales.
	Genera un MD5 único basado puramente en los datos de la onda musical.
	"""
	p = Path(filepath)
	try:
		file_size = p.stat().st_size
		if file_size < chunk_size * 3:
			with open(p, "rb") as f:
				f.seek(file_size // 2)
				data = f.read(file_size // 4)
				return hashlib.md5(data).hexdigest()

		with open(p, "rb") as f:
			f.seek(int(file_size * 0.15))
			chunk1 = f.read(chunk_size)

			f.seek(int(file_size * 0.85))
			chunk2 = f.read(chunk_size)

			hasher = hashlib.md5()
			hasher.update(chunk1)
			hasher.update(chunk2)
			hasher.update(str(file_size).encode("utf-8"))
			return hasher.hexdigest()
	except Exception as e:
		logger.debug(f"Pifió el hash inteligente para {filepath}: {e}")
		return hashlib.md5(str(p).encode("utf-8")).hexdigest()


def parse_duration_str(duration_str: str | None) -> float:
	"""Convierte cadenas de duración ('03:45', '1:02:15') a segundos en float."""
	if not duration_str or duration_str == "0:00":
		return 0.0
	try:
		parts = [float(p) for p in str(duration_str).split(":")]
		if len(parts) == 1:
			return parts[0]
		elif len(parts) == 2:
			return parts[0] * 60 + parts[1]
		elif len(parts) == 3:
			return parts[0] * 3600 + parts[1] * 60 + parts[2]
	except Exception:
		pass
	return 0.0


def calculate_mood_scores(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Calcula y asigna el mood_score normalizado [0.0, 1.0] para una lista de pistas."""
	if not tracks:
		return tracks

	def _normalize(val: float, values: list[float]) -> float:
		if val <= 0 or not values:
			return 0.5
		lo, hi = min(values), max(values)
		if hi - lo < 1e-9:
			return 0.5
		return (val - lo) / (hi - lo)

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

	return tracks


class Track:
	"""Representa una pista musical con sus metadatos y análisis acústico."""

	def __init__(self, path: Path | str, extract_mood: bool = True, extract_fingerprint: bool = True):
		self.path = Path(path)
		self.title = self.path.stem
		self.artist = "Desconocido"
		self.album = "Desconocido"
		self.duration_str = "0:00"
		self.tag_bpm: float | None = None
		self.bpm = 0.0
		self.energy = 0.0
		self.spectral_centroid = 0.0
		self.fingerprint: str | None = None

		self._extract_metadata()
		if extract_mood:
			self._extract_mood()
		else:
			self.bpm = self.tag_bpm if self.tag_bpm is not None else 0.0
			self.energy = 0.0
			self.spectral_centroid = 0.0

		if extract_fingerprint:
			self._extract_fingerprint()
		else:
			self.fingerprint = None

		self.search_string = f"{self.artist} {self.title}".lower()
		self.track_hash = str(generate_smart_hash(self.path))

	def _extract_metadata(self) -> None:
		try:
			audio = MutagenFile(self.path, easy=True)
			if audio is None:
				audio = MutagenFile(self.path)
			if audio and getattr(audio, "tags", None):
				tags = {k.lower(): v for k, v in audio.tags.items()}
				for k in ["title", "©nam", "tit2"]:
					if k in tags:
						val = tags[k]
						self.title = val[0] if isinstance(val, list) else str(val)
						break
				for k in ["artist", "©art", "tpe1"]:
					if k in tags:
						val = tags[k]
						self.artist = val[0] if isinstance(val, list) else str(val)
						break
				for k in ["album", "©alb", "talb"]:
					if k in tags:
						val = tags[k]
						self.album = val[0] if isinstance(val, list) else str(val)
						break
				for k in ["tbpm", "bpm", "tempo", "tmpo"]:
					if k in tags:
						val = tags[k]
						val_str = val[0] if isinstance(val, list) else str(val)
						try:
							clean_num = re.search(r"[-+]?\d*\.?\d+", str(val_str))
							if clean_num:
								parsed_bpm = float(clean_num.group(0))
								if parsed_bpm > 0:
									self.tag_bpm = round(parsed_bpm, 1)
									break
						except (ValueError, TypeError):
							pass
			if audio and hasattr(audio, "info") and hasattr(audio.info, "length"):
				length = audio.info.length
				if length:
					mins = int(length // 60)
					secs = int(length % 60)
					self.duration_str = f"{mins}:{secs:02d}"
		except Exception as e:
			logger.warning(f"No le pude leer la mente (metadata) a {self.path}: {e}")

	def _extract_fingerprint(self) -> None:
		fpcalc_bin = audio_analysis.find_binary("fpcalc")
		if fpcalc_bin:
			try:
				proc = subprocess.run(
					[fpcalc_bin, "-raw", "-length", "60", str(self.path)],
					capture_output=True,
					text=True,
					timeout=10,
					check=False,
				)
				for line in proc.stdout.splitlines():
					if line.startswith("FINGERPRINT="):
						self.fingerprint = line.split("=", 1)[1]
			except Exception as e:
				logger.debug(f"Pifió fpcalc sacando la huella a {self.path}: {e}")

	def analyze_fingerprint(self) -> str | None:
		"""Saca la huella acústica con fpcalc."""
		self._extract_fingerprint()
		return self.fingerprint

	def analyze_mood(self, ffmpeg_bin: str | None = None) -> tuple[float, float, float]:
		bin_to_use = ffmpeg_bin or audio_analysis.find_binary("ffmpeg")
		if bin_to_use:
			b, e, c = audio_analysis.extract_audio_features_ffmpeg(self.path, bin_to_use)
			if b < 0.0:
				self.bpm, self.energy, self.spectral_centroid = -1.0, -1.0, -1.0
			else:
				self.bpm = self.tag_bpm if self.tag_bpm is not None else b
				self.energy = e
				self.spectral_centroid = c
			return (self.bpm, self.energy, self.spectral_centroid)

		if self.tag_bpm is not None:
			self.bpm = self.tag_bpm
			self.energy = 0.0
			self.spectral_centroid = 0.0
			return (self.bpm, self.energy, self.spectral_centroid)

		self.bpm, self.energy, self.spectral_centroid = 0.0, 0.0, 0.0
		return (self.bpm, self.energy, self.spectral_centroid)

	def _extract_mood(self) -> None:
		self.analyze_mood()

	def to_dict(self) -> dict[str, Any]:
		return {
			"path": str(self.path),
			"display_title": self.title,
			"display_artist": self.artist,
			"album": self.album,
			"duration_str": self.duration_str,
			"search_string": self.search_string,
			"title": self.title,
			"artist": self.artist,
			"track_hash": self.track_hash,
			"bpm": self.bpm,
			"energy": self.energy,
			"spectral_centroid": self.spectral_centroid,
			"fingerprint": self.fingerprint,
		}


class LibraryService:
	"""Gestor de biblioteca musical para escaneo y consultas."""

	def __init__(self, db_path: Path | str | None = None, track_repo: TrackRepository | None = None) -> None:
		self.db_path = db_path
		self.track_repo = track_repo or TrackRepository(db_path)

	def recalculate_mood(self, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
		return calculate_mood_scores(tracks)

	def reconcile_chromaprint(
		self,
		new_tracks_for_reconciliation: list[dict[str, Any]],
		missing_db_tracks: list[dict[str, Any]],
		tracks_to_insert: list[tuple[Any, ...]],
		tracks: list[dict[str, Any]],
		id_to_current_path: dict[str, str],
		path_to_id: dict[str, str],
		seen_track_ids: set[str],
	) -> None:
		"""Reconcilia huellas Chromaprint cuando un archivo cambió de formato o tamaño."""
		if not (missing_db_tracks and new_tracks_for_reconciliation):
			return

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

				id_to_current_path[old_id] = new_t["path"]
				path_to_id[new_t["path"]] = old_id
				id_to_current_path.pop(new_id, None)

				seen_track_ids.add(old_id)
				missing_db_tracks.remove(best_match)

	def scan_directory(
		self,
		target_dirs: list,
		extract_mood: bool = True,
		max_workers: int = 16,
		extract_fingerprint: bool | None = None,
		state: Any = None,
	) -> list[dict[str, Any]]:
		"""Escanea directorios en búsqueda de archivos de audio, reconciliando caché y huellas."""
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

		if state:
			state.scan_phase = "discovering"
			state.scan_current = 0
			state.scan_total = 0
			state.scan_message = "Buscando archivos de audio..."

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
		if state:
			state.scan_phase = "metadata"
			state.scan_total = len(raw_files)
			state.scan_current = 0
			state.scan_message = (
				f"Encontré {len(raw_files)} archivos en total. Revisando cuáles son nuevos o cambiaron..."
			)

		raw_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
		has_ffmpeg = is_mood_available()
		has_fpcalc = bool(shutil.which("fpcalc"))

		db_cache = {}
		try:
			cached_rows = self.track_repo.list_for_scan_cache()
			for row in cached_rows:
				db_cache[row["path"]] = {
					"mtime": row["mtime"],
					"file_size": row["file_size"],
					"track_hash": row["track_id"],
					"title": row["title"],
					"album": row["album"],
					"artist": row["artist"],
					"duration_str": row["duration_str"],
					"bpm": row["bpm"] if row["bpm"] is not None else 0.0,
					"energy": row["energy"] if row["energy"] is not None else 0.0,
					"spectral_centroid": row["spectral_centroid"] if row["spectral_centroid"] is not None else 0.0,
					"fingerprint": row["fingerprint"],
				}
		except Exception as e:
			logger.warning(f"No pude cargar la caché de la DB (capaz está vacía): {e}")

		track_cache_by_path = getattr(state, "track_cache_by_path", {}) if state else {}
		id_to_current_path = getattr(state, "id_to_current_path", {}) if state else {}
		path_to_id = getattr(state, "path_to_id", {}) if state else {}

		id_to_current_path.clear()
		path_to_id.clear()
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

			if (
				file_str in track_cache_by_path
				and track_cache_by_path[file_str]["mtime"] == current_mtime
				and (track_cache_by_path[file_str]["data"].get("bpm", 0.0) != 0.0 or not has_ffmpeg or not extract_mood)
			):
				td = track_cache_by_path[file_str]["data"]
				th = td.get("track_hash")
				cache_hits[file_str] = (current_mtime, td, th)
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
					if state:
						state.scan_current = len(cache_hits) + processed_count
					if processed_count % 50 == 0:
						logger.info(
							f"Ya procesé la data de {processed_count}/{len(miss_files)} joyitas nuevas/modificadas..."
						)
						gc.collect()

		tracks = []
		for f in raw_files:
			file_str = str(f)
			if file_str in cache_hits:
				current_mtime, track_dict, track_hash = cache_hits[file_str]
				seen_track_ids.add(track_hash)
				new_cache[file_str] = {"mtime": current_mtime, "data": track_dict}
				tracks.append(track_dict)
				id_to_current_path[track_hash] = file_str
				path_to_id[file_str] = track_hash
			elif file_str in miss_results:
				current_mtime, track_dict, track_hash, db_tuple, fp = miss_results[file_str]
				tracks_to_insert.append(db_tuple)
				seen_track_ids.add(track_hash)
				if fp:
					new_tracks_for_reconciliation.append(track_dict)
				new_cache[file_str] = {"mtime": current_mtime, "data": track_dict}
				tracks.append(track_dict)
				id_to_current_path[track_hash] = file_str
				path_to_id[file_str] = track_hash

		missing_db_tracks = [t for t in db_cache.values() if t["track_hash"] not in seen_track_ids]
		self.reconcile_chromaprint(
			new_tracks_for_reconciliation=new_tracks_for_reconciliation,
			missing_db_tracks=missing_db_tracks,
			tracks_to_insert=tracks_to_insert,
			tracks=tracks,
			id_to_current_path=id_to_current_path,
			path_to_id=path_to_id,
			seen_track_ids=seen_track_ids,
		)

		calculate_mood_scores(tracks)
		if state:
			state.tracks_cache = tracks
			state.track_cache_by_path = new_cache

		if tracks_to_insert:
			try:
				self.track_repo.save_many(tracks_to_insert)
				logger.info(f"Guardados {len(tracks_to_insert)} metadatos frescos en la base de datos.")
			except Exception as e:
				logger.error(f"Error guardando tracks en la DB: {e}")

		if state:
			state.scan_current = len(tracks)
			state.scan_total = len(tracks)
			state.scan_message = "¡Listo el escaneo, maestro!"
		logger.info("¡Listo el escaneo, maestro!")
		return tracks

	async def run_background_mood_analysis(self, state: Any = None, max_workers: int | None = None) -> None:
		"""Worker que procesa de forma asíncrona BPM/mood y huella acústica en lotes pequeños."""
		ffmpeg_bin = audio_analysis.find_binary("ffmpeg")
		has_fpcalc = shutil.which("fpcalc") is not None

		if not ffmpeg_bin and not has_fpcalc:
			logger.info("Sin FFmpeg ni fpcalc, salteando análisis acústico de fondo.")
			if state:
				state.is_analyzing_mood = False
				state.scan_phase = "idle"
			return

		tracks_cache = getattr(state, "tracks_cache", []) if state else []
		pending_tracks = []
		for t in tracks_cache:
			need_mood = bool(ffmpeg_bin and t.get("bpm", 0.0) == 0.0)
			need_fp = bool(has_fpcalc and not t.get("fingerprint"))
			if need_mood or need_fp:
				pending_tracks.append((t, need_mood, need_fp))

		if not pending_tracks:
			if state:
				state.is_analyzing_mood = False
				state.scan_phase = "idle"
			return

		if state:
			state.is_analyzing_mood = True
			state.scan_phase = "mood"
			state.scan_total = len(pending_tracks)
			state.scan_current = 0
			state.scan_message = f"Sintonizando la vibra de los temas (0/{len(pending_tracks)})..."
			if hasattr(state, "broadcast_state"):
				try:
					bc = state.broadcast_state
					res = bc()
					if asyncio.iscoroutine(res):
						await res
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

				b, e, c = audio_analysis.extract_audio_features_ffmpeg(path_str, ffmpeg_bin)
				if b < 0.0:
					bpm, energy, centroid = -1.0, -1.0, -1.0
				else:
					bpm = tag_bpm if tag_bpm is not None else b
					energy = e
					centroid = c

			if need_fp and shutil.which("fpcalc"):
				try:
					fpcalc_bin = audio_analysis.find_binary("fpcalc") or "fpcalc"
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
		workers = max_workers or min(4, os.cpu_count() or 2)

		try:
			for i in range(0, len(pending_tracks), batch_size):
				batch = pending_tracks[i : i + batch_size]
				loop = asyncio.get_running_loop()

				with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
					batch_results = await loop.run_in_executor(
						pool,
						lambda b: [_process_mood_item(item) for item in b],
						batch,
					)

				try:
					self.track_repo.update_mood_batch([(r[2], r[3], r[4], r[5], r[0]) for r in batch_results])
				except Exception as e:
					logger.error(f"Error actualizando mood en DB: {e}")

				res_map = {r[0]: r for r in batch_results}
				if state:
					track_cache_by_path = getattr(state, "track_cache_by_path", {})
					for t in state.tracks_cache:
						tid = t.get("track_hash")
						if tid in res_map:
							_, p, b, e, c, fp = res_map[tid]
							t["bpm"] = b
							t["energy"] = e
							t["spectral_centroid"] = c
							t["fingerprint"] = fp
							if p in track_cache_by_path:
								track_cache_by_path[p]["data"].update(
									{
										"bpm": b,
										"energy": e,
										"spectral_centroid": c,
										"fingerprint": fp,
									}
								)

					state.scan_current = min(state.scan_total, i + len(batch))
					state.scan_message = f"Sintonizando la vibra ({state.scan_current}/{state.scan_total})..."
					calculate_mood_scores(state.tracks_cache)
					try:
						from app.engine.state import broadcast_state

						await broadcast_state()
					except Exception:
						pass
				gc.collect()

		except asyncio.CancelledError:
			logger.info("Análisis de mood en background cancelado por nueva solicitud.")
			raise
		finally:
			if state:
				state.is_analyzing_mood = False
				state.scan_phase = "idle"
				state.scan_message = ""
				try:
					from app.engine.state import broadcast_state

					await broadcast_state(include_library=True)
				except Exception:
					pass


def get_track_duration_seconds(path: str | Path | None, tracks_cache: list[dict] | None = None) -> float:
	"""Obtiene la duración en segundos de una pista consultando el cache, mutagen o ffprobe."""
	if not path:
		return 0.0
	if tracks_cache:
		for t in tracks_cache:
			if t.get("path") == str(path):
				dur = parse_duration_str(t.get("duration_str"))
				if dur > 0:
					return dur
	p = Path(path)
	if p.is_file():
		try:
			audio = MutagenFile(p)
			if audio and audio.info and getattr(audio.info, "length", None) is not None:
				dur = float(audio.info.length)
				if dur > 0.0:
					return dur
		except Exception:
			pass

		ffprobe_bin = audio_analysis.find_binary("ffprobe")
		if ffprobe_bin:
			try:
				res = subprocess.run(
					[
						ffprobe_bin,
						"-v",
						"error",
						"-show_entries",
						"format=duration",
						"-of",
						"default=noprint_wrappers=1:nokey=1",
						str(p),
					],
					capture_output=True,
					text=True,
					timeout=2.0,
					check=False,
				)
				if res.returncode == 0 and res.stdout.strip():
					return float(res.stdout.strip())
			except Exception:
				pass
	return 0.0


def get_cover_art_uri(path: str, state_ref: Any = None) -> str:
	"""Extrae la tapa a la carpeta temporal y devuelve la URI para MPRIS."""
	import os
	import tempfile

	from app.core.dependencies import get_state
	from app.services.radio import get_carpincho_cover_path

	if not path or path.startswith("http"):
		return ""
	try:
		st = state_ref or get_state()
		is_announcement = st is not None and hasattr(st, "is_radio_announcement") and st.is_radio_announcement(path)
		if is_announcement:
			if get_carpincho_cover_path:
				carpincho_p = get_carpincho_cover_path()
				if carpincho_p and carpincho_p.is_file():
					return f"file://{carpincho_p.resolve()}"
			root_dir = Path(__file__).resolve().parents[2]
			fav_p = root_dir / "public" / "favicon.png"
			if fav_p.is_file():
				return f"file://{fav_p.resolve()}"

		path_hash = hashlib.md5(path.encode("utf-8")).hexdigest()
		tmp_dir = os.path.join(tempfile.gettempdir(), "carpincho_covers")
		os.makedirs(tmp_dir, exist_ok=True)

		try:
			covers = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)]
			if len(covers) > 50:
				covers.sort(key=os.path.getmtime)
				for old_cover in covers[:-30]:
					os.remove(old_cover)
		except Exception as e:
			logger.debug(f"Pifió pasando la escoba por las tapas: {e}")

		tmp_cover = os.path.join(tmp_dir, f"{path_hash}.jpg")

		if os.path.exists(tmp_cover):
			return f"file://{tmp_cover}"

		audio = MutagenFile(path)
		if not audio:
			return ""
		cover_data = None

		if hasattr(audio, "pictures") and audio.pictures:
			cover_data = audio.pictures[0].data
		elif hasattr(audio, "tags") and audio.tags:
			for key, tag in audio.tags.items():
				if key.startswith("APIC"):
					cover_data = tag.data
					break
			if not cover_data and "covr" in audio.tags:
				cover_data = audio.tags["covr"][0]

		if cover_data:
			with open(tmp_cover, "wb") as f:
				f.write(cover_data)
			return f"file://{tmp_cover}"
	except Exception as e:
		logger.debug(f"Pifió extrayendo la portada: {e}")
	return ""
