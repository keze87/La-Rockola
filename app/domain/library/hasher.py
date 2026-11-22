"""
Generación de hash inteligente (muestreo de onda al 15% y 85%) y comparación de huellas Chromaprint.
"""

from __future__ import annotations

import hashlib
import logging
import os
import struct
from pathlib import Path
from typing import BinaryIO

from app.infrastructure.storage import get_saf_name, get_storage_backend, is_saf_uri

logger = logging.getLogger("RockolaCarpincho")


def _mp3_audio_bounds(f: BinaryIO, file_size: int) -> tuple[int, int]:
	"""Calcula el rango de bytes correspondiente al stream MPEG excluyendo tags ID3v2 e ID3v1."""
	start = 0
	end = file_size
	if file_size >= 10:
		f.seek(0)
		header = f.read(10)
		if len(header) == 10 and header[:3] == b"ID3":
			flags = header[5]
			tag_size = (
				((header[6] & 0x7F) << 21) | ((header[7] & 0x7F) << 14) | ((header[8] & 0x7F) << 7) | (header[9] & 0x7F)
			)
			start = 10 + tag_size + (10 if (flags & 0x10) else 0)

	if file_size - start >= 128:
		f.seek(file_size - 128)
		if f.read(3) == b"TAG":
			end = file_size - 128

	return (start, end) if end > start else (0, file_size)


def _mp4_audio_bounds(f: BinaryIO, file_size: int) -> tuple[int, int]:
	"""Ubica el átomo mdat dentro de contenedores MP4/M4A para ignorar átomos de metadata."""
	offset = 0
	while offset + 8 <= file_size:
		f.seek(offset)
		box = f.read(8)
		if len(box) < 8:
			break
		size, tag = struct.unpack(">I4s", box)
		header_size = 8
		if size == 1 and offset + 16 <= file_size:
			size = struct.unpack(">Q", f.read(8))[0]
			header_size = 16
		elif size == 0:
			size = file_size - offset
		if size < header_size:
			break
		if tag == b"mdat":
			end = min(file_size, offset + size)
			start = offset + header_size
			if end > start:
				return start, end
		offset += size
	return 0, file_size


def _hash_byte_range(f: BinaryIO, start: int, end: int, chunk_size: int) -> str:
	"""Hashea primer, medio (si aplica) y último bloque del rango de audio [start, end) y su longitud."""
	span = end - start
	hasher = hashlib.md5()
	if span <= chunk_size * 2:
		f.seek(start)
		hasher.update(f.read(span))
		hasher.update(str(span).encode("utf-8"))
		return hasher.hexdigest()

	f.seek(start)
	hasher.update(f.read(chunk_size))
	if span > chunk_size * 2:
		mid_len = min(chunk_size, span - chunk_size * 2)
		mid_start = start + chunk_size + ((span - chunk_size * 2 - mid_len) // 2)
		f.seek(mid_start)
		hasher.update(f.read(mid_len))
	f.seek(end - chunk_size)
	hasher.update(f.read(chunk_size))
	hasher.update(str(span).encode("utf-8"))
	return hasher.hexdigest()


def _compute_audio_hash_from_stream(f: BinaryIO, suffix: str, file_size: int, chunk_size: int) -> str:
	"""Calcula audio_hash sobre un stream binario ya abierto, sin reabrir el archivo."""
	if suffix == ".flac":
		try:
			from mutagen.flac import FLAC

			f.seek(0)
			audio = FLAC(f)
			md5_sig = getattr(audio.info, "md5_signature", 0)
			if md5_sig:
				return f"flac:{md5_sig:032x}"
		except Exception:
			pass

	if suffix == ".mp3":
		start, end = _mp3_audio_bounds(f, file_size)
	elif suffix in (".m4a", ".mp4"):
		start, end = _mp4_audio_bounds(f, file_size)
	else:
		start, end = 0, file_size
	return _hash_byte_range(f, start, end, chunk_size)


def _compute_smart_hash_from_stream(f: BinaryIO, file_size: int, chunk_size: int) -> str:
	"""Calcula el smart-hash (15% y 85% del archivo) sobre un stream binario ya abierto."""
	if file_size < chunk_size * 3:
		f.seek(file_size // 2)
		data = f.read(file_size // 4)
		return hashlib.md5(data).hexdigest()

	f.seek(int(file_size * 0.15))
	chunk1 = f.read(chunk_size)

	f.seek(int(file_size * 0.85))
	chunk2 = f.read(chunk_size)

	hasher = hashlib.md5()
	hasher.update(chunk1)
	hasher.update(chunk2)
	hasher.update(str(file_size).encode("utf-8"))
	return hasher.hexdigest()


def generate_track_hashes(
	filepath: str | Path,
	file_size: int | None = None,
	chunk_size: int = 1024 * 1024,
) -> tuple[str, str]:
	"""
	Calcula (track_hash, audio_hash) en una única apertura y lectura sobre el almacenamiento
	(evitando doble I/O en tarjetas microSD / SAF).
	"""
	saf = is_saf_uri(filepath)
	ref: str | Path = str(filepath) if saf else Path(filepath)
	suffix = os.path.splitext(get_saf_name(ref))[1].lower()
	backend = get_storage_backend(ref)
	try:
		resolved_size = file_size
		if resolved_size is None:
			st = backend.stat_file(ref)
			if st is None:
				raise FileNotFoundError(ref)
			resolved_size = st[1]
		with backend.open_binary(ref) as f:
			track_hash = _compute_smart_hash_from_stream(f, resolved_size, chunk_size)
			audio_hash = _compute_audio_hash_from_stream(f, suffix, resolved_size, chunk_size)
			return track_hash, audio_hash
	except Exception as e:
		logger.debug(f"Pifió el cálculo unificado de hashes para {filepath}: {e}")
		fallback = hashlib.md5(str(ref).encode("utf-8")).hexdigest()
		return fallback, fallback


def generate_audio_hash(filepath: str | Path, chunk_size: int = 1024 * 1024) -> str:
	"""
	Genera un hash basado únicamente en el stream de audio, inmune a cambios de metadata.
	Soporta MD5 nativo de FLAC, salto de ID3 en MP3 y átomo mdat en MP4/M4A.
	"""
	_, audio_hash = generate_track_hashes(filepath, chunk_size=chunk_size)
	return audio_hash


def generate_smart_hash(filepath: str | Path, chunk_size: int = 1024 * 1024) -> str:
	"""
	Lee 1MB al 15% y 1MB al 85% del archivo evitando metadatos iniciales y finales.
	Genera un MD5 único basado puramente en los datos de la onda musical.
	"""
	saf = is_saf_uri(filepath)
	ref: str | Path = str(filepath) if saf else Path(filepath)
	backend = get_storage_backend(ref)
	try:
		st = backend.stat_file(ref)
		if st is None:
			raise FileNotFoundError(ref)
		file_size = st[1]
		with backend.open_binary(ref) as f:
			return _compute_smart_hash_from_stream(f, file_size, chunk_size)
	except Exception as e:
		logger.debug(f"Pifió el hash inteligente para {filepath}: {e}")
		return hashlib.md5(str(ref).encode("utf-8")).hexdigest()


def parse_fp(fp_str: str | None) -> list[int] | None:
	"""Convierte una cadena de enteros separados por coma en lista de hashes."""
	if not fp_str:
		return None
	try:
		return [int(x) for x in fp_str.split(",")]
	except (ValueError, TypeError, AttributeError):
		return None


def compare_fps(fp1: list[int] | None, fp2: list[int] | None) -> float:
	"""Compara dos huellas Chromaprint calculando similitud bit a bit [0.0, 1.0]."""
	if not fp1 or not fp2:
		return 0.0
	min_len = min(len(fp1), len(fp2))
	if min_len < 10:
		return 0.0

	diff_bits = sum(((fp1[i] ^ fp2[i]) & 0xFFFFFFFF).bit_count() for i in range(min_len))
	return 1.0 - (diff_bits / (min_len * 32))
