"""
Tests unitarios TDD para app.db (database, migrations, repositories).
"""

import pytest

from app.db.database import backup_db, get_db_connection
from app.db.migrations import apply_migrations, get_current_schema_version
from app.db.repositories import FavoritesRepository, HistoryRepository, TrackRepository, UrlLogsRepository


@pytest.fixture
def clean_db(tmp_path):
	db_file = tmp_path / "test_modular.db"
	apply_migrations(db_file)
	return db_file


def test_migrations_create_tables_and_versions(clean_db):
	version = get_current_schema_version(clean_db)
	assert version >= 5

	# Verificamos que las tablas existan
	with get_db_connection(clean_db) as conn:
		cursor = conn.cursor()
		cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
		tables = {row[0] for row in cursor.fetchall()}
		assert "tracks" in tables
		assert "play_history" in tables
		assert "favorites" in tables
		assert "url_logs" in tables
		assert "schema_version" in tables

		# Verificamos columnas de tracks
		cursor.execute("PRAGMA table_info(tracks)")
		cols = {row[1] for row in cursor.fetchall()}
		assert {
			"track_id",
			"path",
			"title",
			"artist",
			"album",
			"duration_str",
			"mtime",
			"file_size",
			"bpm",
			"energy",
			"spectral_centroid",
			"fingerprint",
		}.issubset(cols)


def test_track_repository(clean_db):
	repo = TrackRepository(clean_db)

	track_data = {
		"track_id": "hash123",
		"path": "/music/rock.mp3",
		"title": "Jijiji",
		"album": "Oktubre",
		"artist": "Patricio Rey",
		"duration_str": "05:20",
		"mtime": 1700000000.0,
		"file_size": 5000000,
		"bpm": 130.0,
		"energy": 0.85,
		"spectral_centroid": 2500.0,
		"fingerprint": "AQAA...",
	}

	repo.save(track_data)
	retrieved = repo.get_by_id("hash123")
	assert retrieved is not None
	assert retrieved["title"] == "Jijiji"
	assert retrieved["artist"] == "Patricio Rey"
	assert retrieved["bpm"] == 130.0

	# Test get_by_path
	by_path = repo.get_by_path("/music/rock.mp3")
	assert by_path["track_id"] == "hash123"

	# Test update mood
	repo.update_mood("hash123", bpm=132.5, energy=0.90, spectral_centroid=2600.0)
	updated = repo.get_by_id("hash123")
	assert updated["bpm"] == 132.5
	assert updated["energy"] == 0.90

	# Test count & list_all
	assert repo.count() == 1
	all_tracks = repo.list_all()
	assert len(all_tracks) == 1


def test_favorites_repository(clean_db):
	repo = FavoritesRepository(clean_db)
	assert repo.list_all() == []

	repo.add("hash123")
	assert repo.is_favorite("hash123") is True
	assert repo.list_all() == ["hash123"]

	# Toggle off
	repo.remove("hash123")
	assert repo.is_favorite("hash123") is False
	assert repo.list_all() == []


def test_history_repository(clean_db):
	repo = HistoryRepository(clean_db)
	repo.add_play("hash123", played_at=1700000000.0)
	repo.add_play("hash123", played_at=1700000010.0)
	repo.add_play("hash456", played_at=1700000020.0)

	history = repo.get_recent(limit=10)
	assert len(history) == 3
	assert history[0]["track_id"] == "hash456"

	top = repo.get_top_played(limit=5)
	assert len(top) == 2
	assert top[0]["track_id"] == "hash123"
	assert top[0]["count"] == 2

	# Test purge radio announcements
	repo.add_play("/tmp/radio_announcement.mp3", played_at=1700000030.0)
	purged = repo.purge_radio_announcements()
	assert purged >= 1


def test_url_logs_repository(clean_db):
	repo = UrlLogsRepository(clean_db)
	repo.add_url("https://youtube.com/watch?v=123", title="Video Copado", artist="Artista")
	logs = repo.get_recent(limit=5)
	assert len(logs) == 1
	assert logs[0]["title"] == "Video Copado"


def test_backup_db(tmp_path, clean_db):
	data_dir = tmp_path / "data"
	data_dir.mkdir()
	backup_path = backup_db(clean_db, data_dir)
	assert backup_path is not None
	assert backup_path.exists()
