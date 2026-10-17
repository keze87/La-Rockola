"""
Caché SQLite y motor de síntesis con Edge-TTS para locuciones radiales.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import logging
import sqlite3
import tempfile
import time
from pathlib import Path

from app.core.config import get_carpincho_data_dir
from app.domain.radio.banks import DEFAULT_TTS_RETRIES, DEFAULT_TTS_TIMEOUT, VOICE_PROSODY

logger = logging.getLogger("rockola.radio")

try:
	import edge_tts

	HAS_EDGE_TTS = True
except ImportError:
	edge_tts = None
	HAS_EDGE_TTS = False


def is_valid_mp3_stream(data: bytes) -> bool:
	"""Determina si un bloque de bytes corresponde a un stream MP3 válido."""
	if len(data) < 4:
		return False
	if data.startswith(b"ID3"):
		return True
	return bool(data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


def estimate_mp3_duration(data: bytes) -> float | None:
	"""Estima la duración en segundos de un stream MP3 en memoria usando mutagen."""
	if not data or not is_valid_mp3_stream(data):
		return None
	try:
		from mutagen.mp3 import MP3

		audio = MP3(io.BytesIO(data))
		if audio.info and getattr(audio.info, "length", None) is not None:
			return float(audio.info.length)
	except Exception:
		pass
	return None


def init_tts_cache_db(db_path: Path | str | None = None) -> Path:
	"""Inicializa la base de datos SQLite para la caché de audios de TTS."""
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	target_path.parent.mkdir(parents=True, exist_ok=True)
	with contextlib.closing(sqlite3.connect(target_path, timeout=5.0)) as conn:
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS tts_cache (
				cache_key TEXT PRIMARY KEY,
				category TEXT NOT NULL,
				voice TEXT NOT NULL,
				text TEXT NOT NULL,
				audio_blob BLOB NOT NULL,
				duration REAL,
				created_at REAL NOT NULL,
				last_used REAL NOT NULL,
				use_count INTEGER DEFAULT 1
			)
			"""
		)
		conn.execute("CREATE INDEX IF NOT EXISTS idx_tts_cache_cat_voice ON tts_cache (category, voice)")
		conn.commit()
	return target_path


def get_cache_key(category: str, voice: str, text: str = "") -> str:
	"""Calcula la clave SHA-256 única para una tupla (categoría, voz, texto normalizado)."""
	norm_text = text.strip().lower()
	raw = f"{voice}:{category}:{norm_text}".encode()
	return hashlib.sha256(raw).hexdigest()


def get_cached_audio(
	category_or_key: str,
	voice: str = "",
	text: str = "",
	db_path: Path | str | None = None,
) -> bytes | None:
	"""Recupera el segmento de audio MP3 desde la base SQLite si existe."""
	cache_key = (
		category_or_key
		if (not voice and not text and len(category_or_key) == 64)
		else get_cache_key(category_or_key, voice, text)
	)
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	if not target_path.exists():
		return None
	try:
		with contextlib.closing(sqlite3.connect(target_path, timeout=5.0)) as conn:
			cur = conn.cursor()
			cur.execute("SELECT audio_blob FROM tts_cache WHERE cache_key = ?", (cache_key,))
			row = cur.fetchone()
			if row and row[0]:
				now = time.time()
				cur.execute(
					"UPDATE tts_cache SET last_used = ?, use_count = use_count + 1 WHERE cache_key = ?",
					(now, cache_key),
				)
				conn.commit()
				return row[0]
	except Exception as e:
		logger.debug(f"Error consultando caché TTS: {e}")
	return None


def save_cached_audio(
	category: str,
	voice: str,
	text: str,
	audio_bytes: bytes,
	duration: float | None = None,
	db_path: Path | str | None = None,
) -> None:
	"""Almacena o actualiza un segmento de audio MP3 en la caché SQLite."""
	if not audio_bytes:
		return
	if duration is None:
		duration = estimate_mp3_duration(audio_bytes)
	cache_key = (
		category
		if (len(category) == 64 and all(c in "0123456789abcdef" for c in category.lower()))
		else get_cache_key(category, voice, text)
	)
	target_path = init_tts_cache_db(db_path)
	now = time.time()
	try:
		with contextlib.closing(sqlite3.connect(target_path, timeout=5.0)) as conn:
			conn.execute(
				"""
				INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
				ON CONFLICT(cache_key) DO UPDATE SET
					audio_blob = excluded.audio_blob,
					duration = coalesce(excluded.duration, duration),
					last_used = excluded.last_used,
					use_count = use_count + 1
				""",
				(cache_key, category, voice, text, audio_bytes, duration, now, now),
			)
			conn.commit()
	except Exception as e:
		logger.debug(f"Error guardando audio en caché TTS: {e}")


def prune_tts_cache_db(
	max_entries: int = 500,
	max_age_days: float = 30.0,
	db_path: Path | str | None = None,
) -> int:
	"""Poda entradas obsoletas o excedentes de la caché SQLite de TTS."""
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	if not target_path.exists():
		return 0

	deleted_count = 0
	try:
		with contextlib.closing(sqlite3.connect(target_path, timeout=5.0)) as conn:
			cur = conn.cursor()
			cutoff = time.time() - (max_age_days * 86400.0)
			cur.execute("DELETE FROM tts_cache WHERE last_used < ?", (cutoff,))
			deleted_count += cur.rowcount

			cur.execute("SELECT count(*) FROM tts_cache")
			row = cur.fetchone()
			total_entries = row[0] if row else 0
			if total_entries > max_entries:
				excess = total_entries - max_entries
				cur.execute(
					"""
					DELETE FROM tts_cache
					WHERE cache_key IN (
						SELECT cache_key FROM tts_cache
						ORDER BY last_used ASC
						LIMIT ?
					)
					""",
					(excess,),
				)
				deleted_count += cur.rowcount

			conn.commit()
			if deleted_count > 0:
				conn.execute("VACUUM")
				conn.commit()
	except Exception as e:
		logger.warning(f"Error podando la base de datos de caché TTS ({target_path}): {e}")

	return deleted_count


async def synthesize_segment(
	text: str,
	voice: str,
	category: str,
	allow_cache: bool = True,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
	db_path: Path | str | None = None,
	boundary: str = "SentenceBoundary",
	return_cues: bool = False,
) -> bytes | tuple[bytes, list[tuple[float, float, str]]]:
	"""Sintetiza un parlamento radial mediante Edge-TTS con respaldo en caché SQLite."""
	captured_cues: list[tuple[float, float, str]] = []

	async def _stream_or_save(comm: object) -> bytes:
		nonlocal captured_cues
		captured_cues = []
		data = bytearray()
		if hasattr(comm, "stream"):
			try:
				async for chunk in comm.stream():  # type: ignore[attr-defined]
					if isinstance(chunk, dict):
						chunk_type = chunk.get("type")
						if chunk_type == "audio":
							data.extend(chunk.get("data", b""))
						elif chunk_type in ("SentenceBoundary", "WordBoundary"):
							offset_sec = chunk["offset"] / 10_000_000.0
							duration_sec = chunk["duration"] / 10_000_000.0
							chunk_text = str(chunk.get("text", "")).strip()
							if chunk_text:
								captured_cues.append((offset_sec, offset_sec + duration_sec, chunk_text))
			except Exception:
				pass
		if not data and hasattr(comm, "save"):
			with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_f:
				tmp_p = Path(tmp_f.name)
			try:
				res = comm.save(str(tmp_p))  # type: ignore[attr-defined]
				if asyncio.iscoroutine(res):
					await res
				if tmp_p.exists() and tmp_p.stat().st_size > 0:
					data = bytearray(tmp_p.read_bytes())
			except Exception:
				pass
			finally:
				tmp_p.unlink(missing_ok=True)
		return bytes(data)

	last_err: Exception | None = None
	if HAS_EDGE_TTS and edge_tts is not None:
		prosody = VOICE_PROSODY.get(voice, {})
		rate = prosody.get("rate", "+0%")
		pitch = prosody.get("pitch", "+0Hz")
		volume = prosody.get("volume", "+0%")

		attempt_timeout = max(4.0, timeout)
		audio_bytes = b""

		for attempt in range(max_retries + 1):
			try:
				try:
					communicate = edge_tts.Communicate(
						text, voice, rate=rate, pitch=pitch, volume=volume, boundary=boundary
					)
				except TypeError:
					communicate = edge_tts.Communicate(text, voice)
				audio_bytes = await asyncio.wait_for(_stream_or_save(communicate), timeout=attempt_timeout)
				if not audio_bytes:
					raise RuntimeError(f"edge-tts no produjo bytes de audio para '{text}'")
				last_err = None
				break
			except Exception as e:
				last_err = e
				if attempt < max_retries:
					await asyncio.sleep(min(0.3 * (attempt + 1), max(0.01, timeout * 0.2)))

		if audio_bytes:
			if allow_cache:
				clip_dur = estimate_mp3_duration(audio_bytes)
				save_cached_audio(category, voice, text, audio_bytes, duration=clip_dur, db_path=db_path)
			if return_cues:
				if not captured_cues:
					clip_dur = estimate_mp3_duration(audio_bytes) or 1.0
					captured_cues = [(0.0, clip_dur, text.strip())]
				return audio_bytes, captured_cues
			return audio_bytes

	if allow_cache:
		cached_blob = get_cached_audio(category, voice, text, db_path=db_path)
		if cached_blob:
			if return_cues:
				clip_dur = estimate_mp3_duration(cached_blob) or 1.0
				return cached_blob, [(0.0, clip_dur, text.strip())]
			return cached_blob

	err_suffix = f": {last_err}" if last_err else ""
	raise RuntimeError(
		f"No se pudo sintetizar ni recuperar de caché el segmento '{category}' ({voice}): '{text}'{err_suffix}"
	)
