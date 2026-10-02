import sqlite3
from unittest.mock import patch

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


def test_scan_directory_reanalyzes_untested_bpm(clean_state, temp_db, tmp_path):
	"""Test that tracks with bpm == 0.0 (untested) are re-analyzed only when mood analysis is available."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	file1 = music_dir / "track_mood_retry.mp3"
	file1.write_bytes(b"TRACK_FOR_MOOD_RETRY_TEST_BYTES")

	state = clean_state

	# Step 1: Scan with no ffmpeg available -> bpm remains 0.0
	def mock_mood_untested(self):
		self.bpm = 0.0
		self.energy = 0.0
		self.spectral_centroid = 0.0

	def mock_fp(self):
		self.fingerprint = "1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011"

	with (
		patch("server.find_binary", return_value=None),
		patch.object(server.Track, "_extract_mood", mock_mood_untested),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		tracks = state.scan_directory([str(music_dir)])
		assert len(tracks) == 1
		assert tracks[0]["bpm"] == 0.0

		with sqlite3.connect(temp_db) as conn:
			row = conn.execute(
				"SELECT bpm, energy, spectral_centroid FROM tracks WHERE path = ?", (str(file1),)
			).fetchone()
			assert row is not None
			assert row[0] == 0.0

	# Step 2: Scan without ffmpeg -> should hit cache without reanalyzing
	mood_called = False

	def mock_mood_should_not_run(self):
		nonlocal mood_called
		mood_called = True

	with (
		patch("server.find_binary", return_value=None),
		patch.object(server.Track, "_extract_mood", mock_mood_should_not_run),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		tracks_cached = state.scan_directory([str(music_dir)])
		assert len(tracks_cached) == 1
		assert tracks_cached[0]["bpm"] == 0.0
		assert not mood_called

	# Step 3: Scan with ffmpeg available -> should re-analyze and update DB
	def mock_mood_success(self):
		self.bpm = 124.0
		self.energy = 0.8
		self.spectral_centroid = 2200.0

	with (
		patch("server.find_binary", return_value="/usr/bin/ffmpeg"),
		patch.object(server.Track, "_extract_mood", mock_mood_success),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		tracks_after = state.scan_directory([str(music_dir)])
		assert len(tracks_after) == 1
		assert tracks_after[0]["bpm"] == 124.0
		assert tracks_after[0]["energy"] == 0.8
		assert tracks_after[0]["spectral_centroid"] == 2200.0

		with sqlite3.connect(temp_db) as conn:
			row = conn.execute(
				"SELECT bpm, energy, spectral_centroid FROM tracks WHERE path = ?", (str(file1),)
			).fetchone()
			assert row is not None
			assert row[0] == 124.0
			assert row[1] == 0.8
			assert row[2] == 2200.0


def test_scan_directory_skips_failed_mood(clean_state, temp_db, tmp_path):
	"""Test that tracks with bpm == -1.0 (mood analysis failed/error) are cached and NOT re-tested."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	file1 = music_dir / "track_corrupt.mp3"
	file1.write_bytes(b"CORRUPT_AUDIO_FILE_BYTES")

	state = clean_state

	# Step 1: First scan with ffmpeg running but failing -> bpm set to -1.0
	def mock_mood_error(self):
		self.bpm = -1.0
		self.energy = -1.0
		self.spectral_centroid = -1.0

	def mock_fp(self):
		self.fingerprint = "1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011"

	with (
		patch("server.find_binary", return_value="/usr/bin/ffmpeg"),
		patch.object(server.Track, "_extract_mood", mock_mood_error),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		tracks = state.scan_directory([str(music_dir)])
		assert len(tracks) == 1
		assert tracks[0]["bpm"] == -1.0

		with sqlite3.connect(temp_db) as conn:
			row = conn.execute(
				"SELECT bpm, energy, spectral_centroid FROM tracks WHERE path = ?", (str(file1),)
			).fetchone()
			assert row is not None
			assert row[0] == -1.0

	# Step 2: Next scan with ffmpeg available -> should hit cache and NOT re-run _extract_mood
	mood_retested = False

	def mock_mood_unexpected(self):
		nonlocal mood_retested
		mood_retested = True

	with (
		patch("server.find_binary", return_value="/usr/bin/ffmpeg"),
		patch.object(server.Track, "_extract_mood", mock_mood_unexpected),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		tracks_cached = state.scan_directory([str(music_dir)])
		assert len(tracks_cached) == 1
		assert tracks_cached[0]["bpm"] == -1.0
		assert not mood_retested


def test_track_explicit_methods(tmp_path):
	"""Test Track constructor flags (extract_mood=False, extract_fingerprint=False) and explicit analyze methods."""
	test_file = tmp_path / "song.mp3"
	test_file.write_bytes(b"DUMMY_AUDIO_BYTES_TEST")

	# When flags are False, mood and fingerprint extraction are deferred
	t = server.Track(test_file, extract_mood=False, extract_fingerprint=False)
	assert t.bpm == 0.0
	assert t.energy == 0.0
	assert t.spectral_centroid == 0.0
	assert t.fingerprint is None

	# Explicit analyze_mood
	with patch("server.extract_audio_features_ffmpeg", return_value=(128.0, 0.7, 1800.0)):
		t.analyze_mood(ffmpeg_bin="/usr/bin/ffmpeg")
		assert t.bpm == 128.0
		assert t.energy == 0.7
		assert t.spectral_centroid == 1800.0

	# Explicit analyze_fingerprint
	with patch("shutil.which", return_value="/usr/bin/fpcalc"), patch("subprocess.run") as mock_subproc:
		mock_subproc.return_value.stdout = "FINGERPRINT=123,456,789\nDURATION=120\n"
		t.analyze_fingerprint()
		assert t.fingerprint == "123,456,789"


def test_scan_directory_parallel_fast_pass(clean_state, temp_db, tmp_path):
	"""Test scan_directory with extract_mood=False performs fast parallel scan without acoustic analysis."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	files = []
	for i in range(10):
		f = music_dir / f"track_{i}.mp3"
		f.write_bytes(f"{i}".encode() * (50 + i * 10))
		files.append(f)

	state = clean_state

	mood_called = False
	fp_called = False

	def mock_mood(self):
		nonlocal mood_called
		mood_called = True

	def mock_fp(self):
		nonlocal fp_called
		fp_called = True

	with (
		patch.object(server.Track, "_extract_mood", mock_mood),
		patch.object(server.Track, "_extract_fingerprint", mock_fp),
	):
		tracks = state.scan_directory([str(music_dir)], extract_mood=False)
		assert len(tracks) == 10
		assert not mood_called
		assert not fp_called

		for t in tracks:
			assert t["bpm"] == 0.0
			assert t["energy"] == 0.0
			assert t["fingerprint"] is None

		# Check SQLite DB insertion
		with sqlite3.connect(temp_db) as conn:
			count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
			assert count == 10


def test_scan_status_progress_reporting(clean_state):
	"""Test APIState scan_status dict exposed in get_full_state_dict."""
	state = clean_state
	state.is_scanning = True
	state.scan_phase = "metadata"
	state.scan_current = 42
	state.scan_total = 100
	state.scan_message = "Procesando metadatos..."

	full_state = state.get_full_state_dict()
	assert full_state["is_scanning"] is True
	assert "scan_status" in full_state
	status = full_state["scan_status"]
	assert status["is_scanning"] is True
	assert status["is_analyzing_mood"] is False
	assert status["phase"] == "metadata"
	assert status["current"] == 42
	assert status["total"] == 100
	assert status["message"] == "Procesando metadatos..."


import pytest


@pytest.mark.asyncio
async def test_background_mood_analysis(clean_state, temp_db, tmp_path):
	"""Test background mood worker processes pending tracks and updates state and DB."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	f1 = music_dir / "song1.mp3"
	f1.write_bytes(b"A" * 50)
	f2 = music_dir / "song2.mp3"
	f2.write_bytes(b"B" * 60)

	state = clean_state

	# Step 1: Fast scan without mood
	tracks = state.scan_directory([str(music_dir)], extract_mood=False)
	assert len(tracks) == 2
	assert tracks[0]["bpm"] == 0.0
	assert tracks[1]["bpm"] == 0.0
	state.tracks_cache = tracks

	# Step 2: Run background mood worker
	def mock_extract_audio(path, ffmpeg_bin):
		return (130.0, 0.6, 2000.0)

	with (
		patch("server.find_binary", return_value="/usr/bin/ffmpeg"),
		patch("server.extract_audio_features_ffmpeg", side_effect=mock_extract_audio),
		patch("shutil.which", return_value=None),  # No fpcalc in this test
	):
		await state.run_background_mood_analysis()

	assert state.is_analyzing_mood is False
	assert state.scan_phase == "idle"

	# Verify tracks_cache updated with new BPM and recalculated mood_score
	for t in state.tracks_cache:
		assert t["bpm"] == 130.0
		assert t["energy"] == 0.6
		assert t["spectral_centroid"] == 2000.0
		assert t["mood_score"] > 0.0

	# Verify SQLite DB updated
	with sqlite3.connect(temp_db) as conn:
		rows = conn.execute("SELECT bpm, energy, spectral_centroid FROM tracks").fetchall()
		assert len(rows) == 2
		for row in rows:
			assert row[0] == 130.0
			assert row[1] == 0.6
			assert row[2] == 2000.0


@pytest.mark.asyncio
async def test_scan_library_resets_is_scanning_on_error(clean_state, tmp_path):
	"""Test that scan_library resets is_scanning to False and scan_phase to idle even if scan_directory fails."""
	with (
		patch.object(server.state, "scan_directory", side_effect=RuntimeError("Disk failure")),
		patch("server.broadcast_state", return_value=None),
	):
		with pytest.raises(RuntimeError):
			await server.scan_library(str(tmp_path))

	assert server.state.is_scanning is False
	assert server.state.scan_phase == "idle"


def test_scan_directory_without_fpcalc_uses_cache(clean_state, temp_db, tmp_path):
	"""Test that when fpcalc is unavailable, DB cache entries with fingerprint=None are still valid hits."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()

	f1 = music_dir / "track_no_fp.mp3"
	f1.write_bytes(b"DATA_FOR_NO_FPCALC_TEST")

	state = clean_state

	# Pre-insert track into SQLite DB with bpm > 0 but fingerprint = None
	mtime = f1.stat().st_mtime
	size = f1.stat().st_size
	tid = "test_tid_no_fp"
	with sqlite3.connect(temp_db) as conn:
		conn.execute(
			"""
			INSERT INTO tracks (track_id, path, title, album, artist, duration_str, mtime, file_size, bpm, energy, spectral_centroid, fingerprint)
			VALUES (?, ?, 'Title', 'Album', 'Artist', '3:00', ?, ?, 120.0, 0.5, 1500.0, NULL)
		""",
			(tid, str(f1), mtime, size),
		)
		conn.commit()

	track_instantiated = False

	def mock_track_init(self, *args, **kwargs):
		nonlocal track_instantiated
		track_instantiated = True

	with (
		patch("shutil.which", return_value=None),  # fpcalc is not installed
		patch("server.is_mood_available", return_value=True),
		patch.object(server.Track, "__init__", mock_track_init),
	):
		tracks = state.scan_directory([str(music_dir)], extract_mood=True)
		assert len(tracks) == 1
		assert tracks[0]["track_hash"] == tid
		# Should have hit DB cache without instantiating a fresh Track
		assert not track_instantiated


@pytest.mark.asyncio
async def test_background_mood_broadcasts_library(clean_state, tmp_path):
	"""Test that background mood analysis worker broadcasts state with include_library=True upon completion."""
	music_dir = tmp_path / "Music"
	music_dir.mkdir()
	f = music_dir / "test.mp3"
	f.write_bytes(b"TEST_BROADCAST_AUDIO")

	state = clean_state
	state.tracks_cache = [{"path": str(f), "track_hash": "th1", "bpm": 0.0, "energy": 0.0, "spectral_centroid": 0.0}]

	broadcast_calls = []

	async def mock_broadcast(**kwargs):
		broadcast_calls.append(kwargs)

	with (
		patch("server.find_binary", return_value="/usr/bin/ffmpeg"),
		patch("server.extract_audio_features_ffmpeg", return_value=(120.0, 0.5, 1500.0)),
		patch("shutil.which", return_value=None),
		patch("server.broadcast_state", side_effect=mock_broadcast),
	):
		await state.run_background_mood_analysis()

	assert any(c.get("include_library") is True for c in broadcast_calls)
