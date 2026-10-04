"""
Servicio de biblioteca musical: escaneo, hashing inteligente y cálculo de mood.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile

from app.engine.audio_analysis import extract_audio_features_ffmpeg, find_binary

logger = logging.getLogger("RockolaCarpincho")


def _srv(name: str, fallback: Any = None) -> Any:
	"""Resuelve símbolos dinámicos desde server.py para soportar monkeypatching en tests."""
	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, name):
		return getattr(srv, name)
	return fallback


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
		mutagen_cls = _srv("MutagenFile", MutagenFile)
		try:
			audio = mutagen_cls(self.path, easy=True)
			if audio is None:
				audio = mutagen_cls(self.path)
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
		finder = _srv("find_binary", find_binary)
		fpcalc_bin = finder("fpcalc")
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
		finder = _srv("find_binary", find_binary)
		extractor = _srv("extract_audio_features_ffmpeg", extract_audio_features_ffmpeg)
		bin_to_use = ffmpeg_bin or finder("ffmpeg")
		if bin_to_use:
			b, e, c = extractor(self.path, bin_to_use)
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

	def __init__(self, db_path: Path | str | None = None) -> None:
		self.db_path = db_path

	def recalculate_mood(self, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
		return calculate_mood_scores(tracks)


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
			mutagen_cls = _srv("MutagenFile", MutagenFile)
			audio = mutagen_cls(p)
			if audio and audio.info and getattr(audio.info, "length", None) is not None:
				dur = float(audio.info.length)
				if dur > 0.0:
					return dur
		except Exception:
			pass

		finder = _srv("find_binary", find_binary)
		ffprobe_bin = finder("ffprobe")
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
	import sys
	import tempfile

	from app.core.dependencies import get_state
	from app.services.radio import get_carpincho_cover_path

	if not path or path.startswith("http"):
		return ""
	try:
		st = state_ref or getattr(sys.modules.get("server"), "state", None) or get_state()
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

		mutagen_cls = _srv("MutagenFile", MutagenFile)
		audio = mutagen_cls(path)
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
