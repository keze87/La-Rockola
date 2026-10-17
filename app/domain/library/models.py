"""
Entidad de dominio Track y utilidades de parseo de duración y metadatos.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile

from app.domain.library.hasher import generate_smart_hash
from app.domain.library.mood import extract_audio_features_ffmpeg
from app.infrastructure.binaries.manager import find_binary, get_clean_env

logger = logging.getLogger("RockolaCarpincho")


def parse_duration_str(duration_str: str | None) -> float:
	"""Convierte cadenas de duración ('03:45', '1:02:15') a segundos en float."""
	if not duration_str or duration_str == "0:00":
		return 0.0
	try:
		parts = [float(p) for p in str(duration_str).split(":")]
		if len(parts) == 1:
			return parts[0]
		if len(parts) == 2:
			return parts[0] * 60 + parts[1]
		if len(parts) == 3:
			return parts[0] * 3600 + parts[1] * 60 + parts[2]
	except Exception:
		pass
	return 0.0


def get_track_duration_seconds(path: str | Path | None, tracks_cache: list[dict[str, Any]] | None = None) -> float:
	"""Obtiene la duración en segundos de una pista consultando la caché, mutagen o ffprobe."""
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

		ffprobe_bin = find_binary("ffprobe")
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
					env=get_clean_env(),
				)
				if res.returncode == 0 and res.stdout.strip():
					return float(res.stdout.strip())
			except Exception:
				pass
	return 0.0


class Track:
	"""Representa una pista musical con sus metadatos y análisis acústico."""

	def __init__(self, path: Path | str, extract_mood: bool = True, extract_fingerprint: bool = True) -> None:
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
			self.analyze_mood()
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
		fpcalc_bin = find_binary("fpcalc")
		if fpcalc_bin:
			try:
				proc = subprocess.run(
					[fpcalc_bin, "-raw", "-length", "60", str(self.path)],
					capture_output=True,
					text=True,
					timeout=10,
					check=False,
					env=get_clean_env(),
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
		"""Analiza BPM, energía y centroide espectral del archivo de audio."""
		bin_to_use = ffmpeg_bin or find_binary("ffmpeg")
		if bin_to_use:
			b, e, c = extract_audio_features_ffmpeg(self.path, bin_to_use)
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

	def to_dict(self) -> dict[str, Any]:
		"""Serializa la pista a diccionario para la caché y el frontend."""
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
