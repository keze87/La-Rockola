"""Tests para detección de archivos duplicados de música (inmune a cambios de metadata)."""

from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import patch

from app.domain.library.service import LibraryService
from app.infrastructure.db.migrations import apply_migrations


def _build_id3v2_tag(payload: bytes) -> bytes:
	"""Construye un bloque ID3v2.3 sintético con tamaño synchsafe."""
	size = len(payload)
	synchsafe = bytes(
		[
			(size >> 21) & 0x7F,
			(size >> 14) & 0x7F,
			(size >> 7) & 0x7F,
			size & 0x7F,
		]
	)
	return b"ID3\x03\x00\x00" + synchsafe + payload


def _write_synthetic_mp3(
	path: Path, audio_payload: bytes, id3v2_payload: bytes = b"", with_id3v1: bool = False
) -> None:
	data = bytearray()
	if id3v2_payload:
		data.extend(_build_id3v2_tag(id3v2_payload))
	data.extend(audio_payload)
	if with_id3v1:
		data.extend(b"TAG" + b"\x00" * 125)
	path.write_bytes(bytes(data))


def test_audio_hash_ignores_mp3_metadata_changes(tmp_path: Path) -> None:
	"""Dos MP3 con el mismo audio pero distinta metadata/carátula deben producir el mismo audio_hash."""
	from app.domain.library.hasher import generate_audio_hash

	audio_stream = b"\xff\xfb\x90\x64" + (b"\x12\x34\x56\x78" * 50000)
	f1 = tmp_path / "tema_a.mp3"
	f2 = tmp_path / "tema_b.mp3"
	f3 = tmp_path / "otro_tema.mp3"

	_write_synthetic_mp3(f1, audio_stream, id3v2_payload=b"TIT2\x00\x00\x00\x05\x00\x00Hola")
	_write_synthetic_mp3(f2, audio_stream, id3v2_payload=b"APIC" + (b"\xaa" * 12000), with_id3v1=True)
	_write_synthetic_mp3(
		f3, b"\xff\xfb\x90\x64" + (b"\x99\x88\x77\x66" * 50000), id3v2_payload=b"TIT2\x00\x00\x00\x05\x00\x00Hola"
	)

	assert generate_audio_hash(f1) == generate_audio_hash(f2)
	assert generate_audio_hash(f1) != generate_audio_hash(f3)


def test_audio_hash_hashes_first_and_last_mb(tmp_path: Path) -> None:
	"""Verifica que generate_audio_hash hashee el primer y último MB del stream de audio."""
	from app.domain.library.hasher import generate_audio_hash

	mb = 1024 * 1024
	first_mb = b"A" * mb
	mid_a = b"M" * mb
	mid_b = b"N" * mb
	last_mb = b"Z" * mb

	f1 = tmp_path / "a.mp3"
	f2 = tmp_path / "b.mp3"
	f3 = tmp_path / "c.mp3"

	_write_synthetic_mp3(f1, first_mb + mid_a + last_mb, id3v2_payload=b"TIT2\x00\x00\x00\x02\x00\x00A")
	_write_synthetic_mp3(f2, first_mb + mid_b + last_mb, id3v2_payload=b"APIC" + (b"\x01" * 5000))
	_write_synthetic_mp3(f3, first_mb + mid_a + (b"X" * mb), id3v2_payload=b"TIT2\x00\x00\x00\x02\x00\x00A")

	# Mismo primer y último MB -> mismo hash
	assert generate_audio_hash(f1) == generate_audio_hash(f2)
	# Distinto último MB -> distinto hash
	assert generate_audio_hash(f1) != generate_audio_hash(f3)


def test_audio_hash_ignores_mp4_metadata_atoms(tmp_path: Path) -> None:
	"""Dos M4A con idéntico átomo mdat y distinto átomo moov/udta deben tener el mismo audio_hash."""
	from app.domain.library.hasher import generate_audio_hash

	def _atom(tag: bytes, content: bytes) -> bytes:
		return struct.pack(">I", 8 + len(content)) + tag + content

	mdat_data = b"\xde\xad\xbe\xef" * 10000
	f1 = tmp_path / "uno.m4a"
	f2 = tmp_path / "dos.m4a"

	f1.write_bytes(_atom(b"ftyp", b"M4A ") + _atom(b"moov", b"small_meta") + _atom(b"mdat", mdat_data))
	f2.write_bytes(_atom(b"ftyp", b"M4A ") + _atom(b"moov", b"huge_meta_" + (b"Z" * 8000)) + _atom(b"mdat", mdat_data))

	assert generate_audio_hash(f1) == generate_audio_hash(f2)


def test_scan_directory_marks_duplicate_tracks_and_clears_when_removed(tmp_path: Path) -> None:
	"""scan_directory marca is_duplicate=True en archivos con el mismo audio aunque cambie la metadata."""
	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)

	music_dir = tmp_path / "music"
	music_dir.mkdir()

	audio_stream = b"\xff\xfb\x90\x64" + (b"\x11\x22\x33\x44" * 20000)
	dup1 = music_dir / "zamba.mp3"
	dup2 = music_dir / "zamba_copia.mp3"
	unique = music_dir / "chacarera.mp3"

	_write_synthetic_mp3(dup1, audio_stream, id3v2_payload=b"TIT2\x00\x00\x00\x05\x00\x00Zamba")
	_write_synthetic_mp3(dup2, audio_stream, id3v2_payload=b"APIC" + (b"\xff" * 4096), with_id3v1=True)
	_write_synthetic_mp3(unique, b"\xff\xfb\x90\x64" + (b"\xaa\xbb\xcc\xdd" * 20000))

	service = LibraryService(db_path=db_path)
	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
	):
		tracks = service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)

	by_path = {t["path"]: t for t in tracks}
	assert by_path[str(dup1)]["is_duplicate"] is True
	assert by_path[str(dup1)]["duplicate_count"] == 2
	assert by_path[str(dup2)]["is_duplicate"] is True
	assert by_path[str(dup2)]["duplicate_count"] == 2
	assert by_path[str(unique)]["is_duplicate"] is False

	# Al borrar la copia duplicada y reescanear, desaparece la advertencia
	dup2.unlink()
	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
	):
		tracks_after = service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)

	by_path_after = {t["path"]: t for t in tracks_after}
	assert by_path_after[str(dup1)]["is_duplicate"] is False
	assert by_path_after[str(unique)]["is_duplicate"] is False
