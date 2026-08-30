import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


def test_scan_directory_fresh_and_cached(clean_state, temp_db, tmp_path):
	"""Test scan_directory scanning files from scratch and using DB cache on subsequent scans."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	file1 = music_dir / "track1.mp3"
	file1.write_bytes(b"AAA_TRACK_ONE_UNIQUE_DATA_LONG")
	file2 = music_dir / "track2.flac"
	file2.write_bytes(b"ZZZ_TRACK_TWO_DIFFERENT_DATA_LONG")

	state = clean_state

	def mock_mood(self):
		self.bpm = 120.0
		self.energy = 0.5
		self.spectral_centroid = 1500.0

	def mock_fp(self):
		self.fingerprint = "1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011"

	with (
		patch.object(server.Track, "_extract_mood", mock_mood),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		# 1. Fresh scan
		tracks = state.scan_directory([str(music_dir)])
		assert len(tracks) == 2
		assert str(file1) in state.path_to_id
		assert str(file2) in state.path_to_id

		# Verify DB insertion
		with sqlite3.connect(temp_db) as conn:
			cursor = conn.cursor()
			cursor.execute("SELECT COUNT(*) FROM tracks")
			count = cursor.fetchone()[0]
			assert count == 2

		# 2. Secondary scan (hits DB cache)
		cached_tracks = state.scan_directory([str(music_dir)])
		assert len(cached_tracks) == 2


def test_scan_directory_reconciliation(clean_state, temp_db, tmp_path):
	"""Test fingerprint reconciliation migrating metadata when a track is moved/renamed."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	old_file = music_dir / "old_name.mp3"
	old_file.write_bytes(b"ACOUSTIC_DATA_SAME")

	state = clean_state
	# Fingerprint with 15 values to pass length >= 10 check
	shared_fp = ",".join(str(1000 + i) for i in range(15))

	def mock_mood(self):
		self.bpm = 120.0
		self.energy = 0.5
		self.spectral_centroid = 1500.0

	def mock_fp(self):
		self.fingerprint = shared_fp

	with (
		patch.object(server.Track, "_extract_mood", mock_mood),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		# First scan
		tracks = state.scan_directory([str(music_dir)])
		assert len(tracks) == 1

		# Mark this track as a favorite in DB
		track_hash = tracks[0]["track_hash"]
		with sqlite3.connect(temp_db) as conn:
			conn.execute("INSERT INTO favorites (track_id) VALUES (?)", (track_hash,))
			conn.commit()

		# Rename the file on disk
		new_file = music_dir / "new_name.mp3"
		old_file.rename(new_file)

		# Second scan should reconcile the new file with old favorite track_hash
		reconciled_tracks = state.scan_directory([str(music_dir)])
		assert len(reconciled_tracks) == 1
		assert reconciled_tracks[0]["path"] == str(new_file)
