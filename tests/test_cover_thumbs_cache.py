"""Tests para la caché persistente en SQLite de miniaturas de carátulas (128px)."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.core.container import get_container
from app.infrastructure.db.migrations import apply_migrations
from app.infrastructure.db.repositories import CoverThumbRepository
from app.main import create_app


def _make_jpeg_bytes(size: tuple[int, int] = (400, 400), color: tuple[int, int, int] = (180, 90, 40)) -> bytes:
	buf = io.BytesIO()
	Image.new("RGB", size, color).save(buf, format="JPEG")
	return buf.getvalue()


def test_cover_thumb_repository_roundtrip_and_invalidation(tmp_path: Path) -> None:
	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)

	repo = CoverThumbRepository(db_path)
	repo.upsert("/music/a.mp3", mtime=100, file_size=2048, thumb_blob=b"THUMB128", mime_type="image/jpeg")

	assert repo.get("/music/a.mp3", mtime=100, file_size=2048) == (b"THUMB128", "image/jpeg")
	# Cambia mtime o file_size -> cache miss
	assert repo.get("/music/a.mp3", mtime=101, file_size=2048) is None
	assert repo.get("/music/a.mp3", mtime=100, file_size=2049) is None


def test_cover_endpoint_persists_and_serves_128px_thumb_from_sqlite(tmp_path: Path) -> None:
	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)

	audio_file = tmp_path / "track.mp3"
	audio_file.write_bytes(b"FAKE_MP3")
	big_cover = _make_jpeg_bytes((512, 512))

	mock_pic = MagicMock()
	mock_pic.data = big_cover
	mock_pic.mime = "image/jpeg"
	mock_audio = MagicMock()
	mock_audio.pictures = [mock_pic]
	mock_audio.tags = None

	container = get_container()
	prev_db = container.db_path
	container.db_path = db_path
	app = create_app()
	client = TestClient(app)

	try:
		with (
			patch("app.api.media._COVER_MEM_CACHE", {}),
			patch("app.api.media.MutagenFile", return_value=mock_audio) as mutagen_mock,
		):
			res1 = client.get(f"/cover?path={audio_file}&size=128")
			assert res1.status_code == 200
			assert len(res1.content) > 0
			assert mutagen_mock.call_count == 1

		# Limpiamos la caché en RAM para simular reinicio de la app;
		# la segunda llamada debe salir de SQLite sin tocar MutagenFile.
		with (
			patch("app.api.media._COVER_MEM_CACHE", {}),
			patch(
				"app.api.media.MutagenFile", side_effect=AssertionError("No debería leer el archivo")
			) as mutagen_mock2,
		):
			res2 = client.get(f"/cover?path={audio_file}&size=128")
			assert res2.status_code == 200
			assert res2.content == res1.content
			assert mutagen_mock2.call_count == 0
	finally:
		container.db_path = prev_db
