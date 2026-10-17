"""
Generación de hash inteligente (muestreo de onda al 15% y 85%) y comparación de huellas Chromaprint.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

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
