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
	"""Test fingerprint reconciliation migrating metadata when file content hash changes but acoustic fingerprint matches (>85%)."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	old_file = music_dir / "old_name.mp3"
	old_file.write_bytes(b"INITIAL_AUDIO_BYTES_FOR_OLD_FILE_V1")

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
		old_id = tracks[0]["track_hash"]

		# Add favorite and history entries for old_id in DB
		with sqlite3.connect(temp_db) as conn:
			conn.execute("INSERT INTO favorites (track_id) VALUES (?)", (old_id,))
			conn.execute("INSERT INTO play_history (track_id, played_at) VALUES (?, ?)", (old_id, 1700000000.0))
			conn.commit()

		# Replace file with different audio content (different content hash)
		old_file.unlink()
		new_file = music_dir / "reencoded_song.flac"
		new_file.write_bytes(b"DIFFERENT_AUDIO_BYTES_FOR_REENCODED_FILE_V2")

		# Clear in-memory cache to simulate fresh server scan reading from DB
		state.track_cache_by_path.clear()

		# Second scan should reconcile new_file (acoustically identical) to old_id
		reconciled_tracks = state.scan_directory([str(music_dir)])
		assert len(reconciled_tracks) == 1
		assert reconciled_tracks[0]["path"] == str(new_file)
		assert reconciled_tracks[0]["track_hash"] == old_id

		# Verify state mappings point to old_id
		assert state.path_to_id[str(new_file)] == old_id
		assert state.id_to_current_path[old_id] == str(new_file)

		# Verify favorites and history still link to old_id
		with sqlite3.connect(temp_db) as conn:
			fav_count = conn.execute("SELECT COUNT(*) FROM favorites WHERE track_id = ?", (old_id,)).fetchone()[0]
			hist_count = conn.execute("SELECT COUNT(*) FROM play_history WHERE track_id = ?", (old_id,)).fetchone()[0]
			assert fav_count == 1
			assert hist_count == 1

			# Verify track record in DB updated with new path under the old_id
			row = conn.execute("SELECT path FROM tracks WHERE track_id = ?", (old_id,)).fetchone()
			assert row is not None
			assert row[0] == str(new_file)


def test_scan_directory_reconciliation_negative_dissimilar(clean_state, temp_db, tmp_path):
	"""Test that fingerprint reconciliation does NOT occur when acoustic similarity is <= 85%."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	old_file = music_dir / "song_a.mp3"
	old_file.write_bytes(b"SONG_A_AUDIO_BYTES_ORIGINAL")

	state = clean_state
	fp_a = ",".join(str(1000 + i) for i in range(15))
	# fp_b with completely inverted bit values (similarity ~ 0.0)
	fp_b = ",".join(str(0xFFFFFFFF ^ (1000 + i)) for i in range(15))

	current_fp = fp_a

	def mock_mood(self):
		self.bpm = 120.0
		self.energy = 0.5
		self.spectral_centroid = 1500.0

	def mock_fp(self):
		self.fingerprint = current_fp

	with (
		patch.object(server.Track, "_extract_mood", mock_mood),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		# First scan
		tracks = state.scan_directory([str(music_dir)])
		assert len(tracks) == 1
		old_id = tracks[0]["track_hash"]

		# Add favorite for old_id
		with sqlite3.connect(temp_db) as conn:
			conn.execute("INSERT INTO favorites (track_id) VALUES (?)", (old_id,))
			conn.commit()

		# Replace file with an entirely different song
		old_file.unlink()
		new_file = music_dir / "song_b.mp3"
		new_file.write_bytes(b"SONG_B_AUDIO_BYTES_COMPLETELY_DIFFERENT")
		current_fp = fp_b

		state.track_cache_by_path.clear()

		# Second scan should NOT reconcile because fingerprints are dissimilar
		second_tracks = state.scan_directory([str(music_dir)])
		assert len(second_tracks) == 1
		new_id = second_tracks[0]["track_hash"]
		assert new_id != old_id
		assert second_tracks[0]["path"] == str(new_file)
		assert state.path_to_id[str(new_file)] == new_id
		assert state.id_to_current_path[new_id] == str(new_file)
		assert old_id not in state.id_to_current_path
