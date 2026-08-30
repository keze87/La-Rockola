import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import server


def test_init_db_creates_tables(temp_db):
	"""Test that init_db properly creates all required tables and columns."""
	with sqlite3.connect(temp_db) as conn:
		cursor = conn.cursor()
		cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
		tables = {row[0] for row in cursor.fetchall()}
		assert {"tracks", "play_history", "favorites", "url_logs"}.issubset(tables)

		# Verify tracks table columns including migrations
		cursor.execute("PRAGMA table_info(tracks);")
		columns = {row[1] for row in cursor.fetchall()}
		expected_columns = {
			"track_id",
			"path",
			"title",
			"album",
			"artist",
			"duration_str",
			"mtime",
			"file_size",
			"bpm",
			"energy",
			"spectral_centroid",
			"fingerprint",
		}
		assert expected_columns.issubset(columns)


def test_backup_db(temp_db, tmp_path, monkeypatch):
	"""Test DB backup creation and 7-day throttling."""
	backup_dir = temp_db.parent / ".carpincho_backups"

	# Initial backup
	server.backup_db()
	backups = list(backup_dir.glob("carpincho_backup_*.db"))
	assert len(backups) == 1

	# Immediate second backup should not duplicate due to recent timestamp
	server.backup_db()
	backups = list(backup_dir.glob("carpincho_backup_*.db"))
	assert len(backups) == 1


def test_favorites_operations(clean_state, temp_db):
	"""Test adding, listing, and loading favorites from the DB."""
	state = clean_state
	track_id = "test_track_hash_123"
	track_path = "/home/music/song.mp3"
	state.path_to_id[track_path] = track_id
	state.id_to_current_path[track_id] = track_path

	with sqlite3.connect(temp_db) as conn:
		conn.execute("INSERT INTO favorites (track_id) VALUES (?)", (track_id,))
		conn.commit()

	loaded_favs = state._load_favs_from_db()
	assert track_id in loaded_favs

	# Verify full state dict maps track_id to path if available
	state.favorites = loaded_favs
	state_dict = state.get_full_state_dict()
	assert track_path in state_dict["favorites"]


def test_play_stats_and_top_played(clean_state, temp_db, tmp_path):
	"""Test registering track plays and computing top_played rankings."""
	state = clean_state
	file1 = tmp_path / "song1.mp3"
	file1.write_bytes(b"DATA1")
	file2 = tmp_path / "song2.mp3"
	file2.write_bytes(b"DATA2")

	track_path_1 = str(file1)
	track_path_2 = str(file2)
	id_1 = "hash1"
	id_2 = "hash2"

	state.path_to_id = {track_path_1: id_1, track_path_2: id_2}
	state.id_to_current_path = {id_1: track_path_1, id_2: track_path_2}

	# Register plays: song1 x3, song2 x1
	state._register_play_stat(track_path_1)
	state._register_play_stat(track_path_1)
	state._register_play_stat(track_path_1)
	state._register_play_stat(track_path_2)

	top = state.get_top_played()
	assert len(top) == 2
	assert top[0]["path"] == track_path_1
	assert top[0]["count"] == 3
	assert top[1]["path"] == track_path_2
	assert top[1]["count"] == 1


def test_log_url(clean_state, temp_db):
	"""Test logging YouTube/Internet URLs into the database."""
	state = clean_state
	url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
	state.url_metadata[url] = {
		"title": "Never Gonna Give You Up",
		"artist": "Rick Astley",
	}

	state._log_url(url)

	with sqlite3.connect(temp_db) as conn:
		cursor = conn.cursor()
		cursor.execute("SELECT url, title, artist FROM url_logs WHERE url = ?", (url,))
		row = cursor.fetchone()
		assert row is not None
		assert row[0] == url
		assert row[1] == "Never Gonna Give You Up"
		assert row[2] == "Rick Astley"
