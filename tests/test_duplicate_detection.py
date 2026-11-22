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


def test_audio_hash_hashes_first_middle_and_last_mb(tmp_path: Path) -> None:
	"""Verifica que generate_audio_hash incluya primer, medio y último bloque para evitar falsos positivos."""
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

	# Distinto bloque central -> distinto hash (evita falsos duplicados)
	assert generate_audio_hash(f1) != generate_audio_hash(f2)
	# Distinto último MB -> distinto hash
	assert generate_audio_hash(f1) != generate_audio_hash(f3)


def test_generate_track_hashes_opens_file_once(tmp_path: Path, monkeypatch: object) -> None:
	"""generate_track_hashes debe calcular track_hash y audio_hash abriendo el archivo una sola vez."""
	from app.domain.library import hasher as hasher_mod
	from app.infrastructure import storage as storage_mod

	mp3 = tmp_path / "single_open.mp3"
	_write_synthetic_mp3(mp3, b"\xff\xfb\x90\x64" * 20000)

	backend = storage_mod.get_storage_backend(mp3)
	orig_open = backend.open_binary
	open_calls = 0

	def tracked_open(ref: object):
		nonlocal open_calls
		open_calls += 1
		return orig_open(ref)

	monkeypatch.setattr(backend, "open_binary", tracked_open)  # type: ignore[attr-defined]
	monkeypatch.setattr(hasher_mod, "get_storage_backend", lambda _p="": backend)  # type: ignore[attr-defined]

	track_hash, audio_hash = hasher_mod.generate_track_hashes(mp3, file_size=mp3.stat().st_size)
	assert track_hash and audio_hash
	assert open_calls == 1


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


def test_scan_directory_single_pass_extensions_and_progress(tmp_path: Path) -> None:
	"""Verifica descubrimiento case-insensitive en una sola pasada y actualización de scan_current."""
	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)

	music_dir = tmp_path / "music"
	sub = music_dir / "sub"
	sub.mkdir(parents=True)

	f1 = music_dir / "tema1.MP3"
	f2 = sub / "tema2.Flac"
	ignored = sub / "cover.jpg"
	f1.write_bytes(b"\xff\xfb\x90\x64" + b"\x01" * 4096)
	f2.write_bytes(b"fLaC" + b"\x02" * 4096)
	ignored.write_bytes(b"JPEG")

	class _State:
		def __init__(self) -> None:
			self.scan_phase = "idle"
			self.scan_current = 0
			self.scan_total = 0
			self.scan_message = ""
			self.tracks_cache: list = []
			self.track_cache_by_path: dict = {}
			self.id_to_current_path: dict = {}
			self.path_to_id: dict = {}

	state = _State()
	service = LibraryService(db_path=db_path)
	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
	):
		tracks = service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False, state=state)

	assert len(tracks) == 2
	assert state.scan_total == 2
	assert state.scan_current == 2


def test_scan_directory_persists_audio_hash_and_skips_rehash_on_cache_hit(tmp_path: Path) -> None:
	"""El segundo escaneo debe reutilizar audio_hash desde SQLite sin volver a leer el audio."""
	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)

	music_dir = tmp_path / "music"
	music_dir.mkdir()
	f1 = music_dir / "tema1.mp3"
	_write_synthetic_mp3(f1, b"\xff\xfb\x90\x64" + (b"\x55" * 8192))

	service = LibraryService(db_path=db_path)
	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
	):
		first = service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)

	assert len(first) == 1
	assert first[0].get("audio_hash")

	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
		patch(
			"app.domain.library.service.generate_audio_hash", side_effect=AssertionError("No debe rehashear")
		) as h_mock,
	):
		second = service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)

	assert len(second) == 1
	assert second[0]["audio_hash"] == first[0]["audio_hash"]
	assert h_mock.call_count == 0


def test_duplicate_mp3s_keep_distinct_track_ids_and_same_audio_hash(tmp_path: Path) -> None:
	"""Dos MP3 con mismo audio y distinto ID3 tienen track_hash distintos, mismo audio_hash y sobreviven ambos en DB."""
	from app.domain.library.hasher import generate_smart_hash, generate_track_hashes
	from app.infrastructure.db.repositories import TrackRepository

	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)

	music_dir = tmp_path / "music"
	music_dir.mkdir()
	audio_stream = b"\xff\xfb\x90\x64" + (b"\x22\x44\x66\x88" * 30000)
	f1 = music_dir / "original.mp3"
	f2 = music_dir / "copia_tag.mp3"
	_write_synthetic_mp3(f1, audio_stream, id3v2_payload=b"TIT2\x00\x00\x00\x05\x00\x00Uno")
	_write_synthetic_mp3(f2, audio_stream, id3v2_payload=b"APIC" + (b"\xcc" * 6000), with_id3v1=True)

	th1, ah1 = generate_track_hashes(f1)
	th2, ah2 = generate_track_hashes(f2)
	assert th1 != th2
	assert th1 == generate_smart_hash(f1)
	assert th2 == generate_smart_hash(f2)
	assert ah1 == ah2

	service = LibraryService(db_path=db_path)
	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
	):
		tracks = service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)

	assert len(tracks) == 2
	all_rows = TrackRepository(db_path).list_all()
	assert len(all_rows) == 2
	assert {r["track_id"] for r in all_rows} == {th1, th2}


def test_duplicate_flacs_with_same_md5_signature_keep_distinct_track_ids(tmp_path: Path) -> None:
	"""Dos FLAC con igual md5_signature y distinta metadata tienen track_hash distintos y mismo audio_hash."""
	from types import SimpleNamespace

	from app.domain.library.hasher import generate_track_hashes

	f1 = tmp_path / "uno.flac"
	f2 = tmp_path / "dos.flac"
	f1.write_bytes(b"fLaC" + (b"\x11" * 16384))
	f2.write_bytes(b"fLaC" + (b"\x22" * 24576))

	fake_flac = SimpleNamespace(info=SimpleNamespace(md5_signature=0x0123456789ABCDEF0123456789ABCDEF))
	with patch("mutagen.flac.FLAC", return_value=fake_flac):
		th1, ah1 = generate_track_hashes(f1)
		th2, ah2 = generate_track_hashes(f2)

	assert ah1 == ah2 == "flac:0123456789abcdef0123456789abcdef"
	assert th1 != th2


def test_rescan_existing_library_preserves_smart_hash_track_ids(tmp_path: Path) -> None:
	"""Reescanear una biblioteca existente no cambia ningún track_id basado en smart_hash."""
	import os

	from app.domain.library.hasher import generate_smart_hash
	from app.infrastructure.db.repositories import TrackRepository

	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)
	music_dir = tmp_path / "music"
	music_dir.mkdir()

	f1 = music_dir / "clasico.mp3"
	_write_synthetic_mp3(f1, b"\xff\xfb\x90\x64" + (b"\x77" * 20000), id3v2_payload=b"TIT2\x00\x00\x00\x04\x00\x00Ok")
	expected_id = generate_smart_hash(f1)

	service = LibraryService(db_path=db_path)
	repo = TrackRepository(db_path)
	with (
		patch("app.domain.library.service.is_mood_available", return_value=False),
		patch("app.domain.library.service.find_binary", return_value=None),
	):
		service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)
		rows_first = repo.list_all()
		# Forzamos un cambio de mtime para que se re-procese el archivo como en una migración
		st = f1.stat()
		os.utime(f1, (st.st_atime, st.st_mtime + 10))
		service.scan_directory([music_dir], extract_mood=False, extract_fingerprint=False)
		rows_second = repo.list_all()

	assert rows_first[0]["track_id"] == expected_id
	assert rows_second[0]["track_id"] == expected_id
