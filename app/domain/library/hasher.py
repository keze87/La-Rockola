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


VIDEO_CONTAINER_SUFFIXES = frozenset({".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".3gp"})


def _mp3_audio_bounds(f: BinaryIO, file_size: int) -> tuple[int, int]:
	"""Calcula el rango de bytes correspondiente al stream MPEG excluyendo tags ID3v2 e ID3v1."""
	start = 0
	end = file_size
	if file_size >= 10:
		f.seek(0)
		header = _read_exact(f, 10)
		if header[:3] == b"ID3":
			flags = header[5]
			tag_size = (
				((header[6] & 0x7F) << 21) | ((header[7] & 0x7F) << 14) | ((header[8] & 0x7F) << 7) | (header[9] & 0x7F)
			)
			start = min(file_size, 10 + tag_size + (10 if (flags & 0x10) else 0))

	if file_size - start >= 128:
		f.seek(file_size - 128)
		if _read_exact(f, 3) == b"TAG":
			end = file_size - 128

	return (start, end) if end > start else (0, file_size)


def _read_exact(f: BinaryIO, length: int) -> bytes:
	"""Lee exactamente `length` bytes del stream o falla si ocurre una lectura corta."""
	if length <= 0:
		return b""
	chunks: list[bytes] = []
	remaining = length
	while remaining > 0:
		data = f.read(remaining)
		if not data:
			raise EOFError(f"Lectura corta: faltaron {remaining} de {length} bytes")
		chunks.append(data)
		remaining -= len(data)
	return b"".join(chunks)


def _iter_iso_boxes(f: BinaryIO, start: int, limit_end: int) -> list[tuple[bytes, int, int]]:
	"""Enumera átomos ISO BMFF dentro de [start, limit_end) tolerando lecturas fragmentadas."""
	boxes: list[tuple[bytes, int, int]] = []
	offset = start
	while offset + 8 <= limit_end:
		f.seek(offset)
		box = _read_exact(f, 8)
		size, tag = struct.unpack(">I4s", box)
		header_size = 8
		if size == 1:
			if offset + 16 > limit_end:
				break
			size = struct.unpack(">Q", _read_exact(f, 8))[0]
			header_size = 16
		elif size == 0:
			size = limit_end - offset
		if size < header_size or offset + size > limit_end:
			break
		boxes.append((tag, offset + header_size, offset + size))
		offset += size
	return boxes


def _moov_has_video_track(f: BinaryIO, moov_start: int, moov_end: int) -> bool:
	"""Detecta si un átomo moov declara al menos un track con handler 'vide'."""
	for tag, p_start, p_end in _iter_iso_boxes(f, moov_start, moov_end):
		if tag == b"trak":
			for sub_tag, sub_start, sub_end in _iter_iso_boxes(f, p_start, p_end):
				if sub_tag == b"mdia":
					for md_tag, md_start, md_end in _iter_iso_boxes(f, sub_start, sub_end):
						if md_tag == b"hdlr" and (md_end - md_start) >= 12:
							f.seek(md_start)
							hdlr_head = _read_exact(f, 12)
							if hdlr_head[8:12] == b"vide":
								return True
	return False


def _mp4_audio_ranges(f: BinaryIO, file_size: int) -> list[tuple[int, int]] | None:
	"""
	Ubica átomos mdat de un contenedor M4A únicamente si no contiene tracks de video.
	Si el átomo moov declara un track 'vide', devuelve None para no mezclar audio y video.
	"""
	ranges: list[tuple[int, int]] = []
	for tag, start, end in _iter_iso_boxes(f, 0, file_size):
		if tag == b"moov" and _moov_has_video_track(f, start, end):
			return None
		if tag == b"mdat" and end > start:
			ranges.append((start, end))
	return ranges or [(0, file_size)]


def _hash_byte_range(f: BinaryIO, start: int, end: int, chunk_size: int) -> str:
	"""Hashea primer, medio (si aplica) y último bloque del rango de audio [start, end) y su longitud."""
	span = end - start
	if span <= 0:
		raise ValueError("Rango de audio vacío")
	hasher = hashlib.md5()
	if span <= chunk_size * 2:
		f.seek(start)
		hasher.update(_read_exact(f, span))
		hasher.update(str(span).encode("utf-8"))
		return hasher.hexdigest()

	f.seek(start)
	hasher.update(_read_exact(f, chunk_size))
	mid_len = min(chunk_size, span - chunk_size * 2)
	mid_start = start + chunk_size + ((span - chunk_size * 2 - mid_len) // 2)
	f.seek(mid_start)
	hasher.update(_read_exact(f, mid_len))
	f.seek(end - chunk_size)
	hasher.update(_read_exact(f, chunk_size))
	hasher.update(str(span).encode("utf-8"))
	return hasher.hexdigest()


def _hash_byte_ranges(f: BinaryIO, ranges: list[tuple[int, int]], chunk_size: int) -> str:
	"""Hashea uno o múltiples rangos de audio en el stream."""
	if len(ranges) == 1:
		return _hash_byte_range(f, ranges[0][0], ranges[0][1], chunk_size)
	hasher = hashlib.md5()
	total_span = 0
	for start, end in ranges:
		total_span += max(0, end - start)
		hasher.update(_hash_byte_range(f, start, end, chunk_size).encode("utf-8"))
	hasher.update(str(total_span).encode("utf-8"))
	return hasher.hexdigest()


def _compute_audio_hash_from_stream(f: BinaryIO, suffix: str, file_size: int, chunk_size: int) -> str | None:
	"""
	Calcula `audio_hash` sobre un stream binario seekable ya abierto, sin reabrir el archivo.

	Semántica soportada por formato:
	- `.flac`: firma MD5 nativa del stream de audio FLAC (`flac:<md5>`).
	- `.mp3`: stream MPEG excluyendo cabeceras ID3v2 e ID3v1.
	- `.m4a`: payloads de átomos `mdat` únicamente si el contenedor no declara tracks de video (`vide`).
	- Contenedores de video (`.mp4`, `.m4v`, `.mov`, `.mkv`, `.avi`, `.webm`, `.3gp`) o `.m4a` con video:
	  devuelven `None` explícitamente porque no garantizan identidad exclusiva de audio sin demux completo.
	- Otros formatos de solo audio (`.ogg`, `.opus`, `.wav`, `.aac`, `.wma`, etc.): bytes completos del stream.
	"""
	if file_size <= 0 or not f.seekable() or suffix in VIDEO_CONTAINER_SUFFIXES:
		return None

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

	try:
		if suffix == ".mp3":
			ranges = [_mp3_audio_bounds(f, file_size)]
		elif suffix == ".m4a":
			maybe_ranges = _mp4_audio_ranges(f, file_size)
			if maybe_ranges is None:
				return None
			ranges = maybe_ranges
		else:
			ranges = [(0, file_size)]
		return _hash_byte_ranges(f, ranges, chunk_size)
	except (EOFError, OSError, ValueError):
		return None


def _compute_smart_hash_from_stream(f: BinaryIO, file_size: int, chunk_size: int) -> str:
	"""
	Calcula el smart-hash (15% y 85% del archivo) sobre un stream seekable tolerando lecturas parciales.
	"""
	if file_size <= 0 or not f.seekable():
		raise ValueError(f"Stream inválido o tamaño nulo para smart-hash ({file_size})")

	if file_size < chunk_size * 3:
		pos = file_size // 2
		f.seek(pos)
		data = _read_exact(f, min(file_size // 4, max(0, file_size - pos)))
		return hashlib.md5(data).hexdigest()

	pos1 = int(file_size * 0.15)
	f.seek(pos1)
	chunk1 = _read_exact(f, min(chunk_size, max(0, file_size - pos1)))

	pos2 = int(file_size * 0.85)
	f.seek(pos2)
	chunk2 = _read_exact(f, min(chunk_size, max(0, file_size - pos2)))

	hasher = hashlib.md5()
	hasher.update(chunk1)
	hasher.update(chunk2)
	hasher.update(str(file_size).encode("utf-8"))
	return hasher.hexdigest()


def generate_track_hashes(
	filepath: str | Path,
	file_size: int | None = None,
	chunk_size: int = 1024 * 1024,
) -> tuple[str, str | None]:
	"""
	Calcula (track_hash, audio_hash) en una única apertura y lectura sobre el almacenamiento
	(evitando doble I/O en tarjetas microSD / SAF). Si no se puede calcular un hash de audio
	confiable, devuelve `None` en lugar de fabricar un hash a partir de la ruta/URI.
	"""
	saf = is_saf_uri(filepath)
	ref: str | Path = str(filepath) if saf else Path(filepath)
	suffix = os.path.splitext(get_saf_name(ref))[1].lower()
	backend = get_storage_backend(ref)
	fallback = hashlib.md5(str(ref).encode("utf-8")).hexdigest()
	try:
		resolved_size = file_size
		if resolved_size is None:
			st = backend.stat_file(ref)
			if st is None:
				raise FileNotFoundError(ref)
			resolved_size = st[1]
		with backend.open_binary(ref) as f:
			if not f.seekable():
				return fallback, None
			if resolved_size is None:
				resolved_size = f.seek(0, os.SEEK_END)
			if resolved_size is None or resolved_size <= 0:
				return fallback, None
			track_hash = _compute_smart_hash_from_stream(f, resolved_size, chunk_size)
			audio_hash = _compute_audio_hash_from_stream(f, suffix, resolved_size, chunk_size)
			return track_hash, audio_hash
	except Exception as e:
		logger.debug(f"Pifió el cálculo unificado de hashes para {filepath}: {e}")
		return fallback, None


def generate_audio_hash(filepath: str | Path, chunk_size: int = 1024 * 1024) -> str | None:
	"""
	Genera un hash basado únicamente en el stream de audio, inmune a cambios de metadata.
	Soporta MD5 nativo de FLAC, salto de ID3 en MP3 y átomos mdat en M4A sin video; devuelve `None`
	en contenedores de video o streams no seekables / con lectura incompleta.
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
