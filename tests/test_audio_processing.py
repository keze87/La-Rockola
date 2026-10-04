from unittest.mock import MagicMock, patch

import server


def test_generate_smart_hash_small_file(small_audio_file):
	"""Test smart hash generation on files smaller than 3MB."""
	hash1 = server.generate_smart_hash(str(small_audio_file))
	assert isinstance(hash1, str)
	assert len(hash1) == 32

	# Hash must be deterministic
	hash2 = server.generate_smart_hash(str(small_audio_file))
	assert hash1 == hash2


def test_generate_smart_hash_large_file(dummy_audio_file):
	"""Test smart hash generation on files larger than 3MB (sampling 15% and 85%)."""
	hash1 = server.generate_smart_hash(str(dummy_audio_file))
	assert isinstance(hash1, str)
	assert len(hash1) == 32

	hash2 = server.generate_smart_hash(str(dummy_audio_file))
	assert hash1 == hash2


def test_generate_smart_hash_nonexistent_file(tmp_path):
	"""Test smart hash returns fallback md5 on nonexistent files."""
	non_existent = str(tmp_path / "ghost.mp3")
	h = server.generate_smart_hash(non_existent)
	assert isinstance(h, str)
	assert len(h) == 32


def test_get_cover_art_uri(tmp_path):
	"""Test cover art extraction returns empty string on missing or invalid files."""
	# HTTP tracks return empty
	assert server.get_cover_art_uri("http://example.com/stream.mp3") == ""
	assert server.get_cover_art_uri("") == ""

	# File with no cover returns empty
	dummy_file = tmp_path / "plain.mp3"
	dummy_file.write_bytes(b"DATA" * 100)
	uri = server.get_cover_art_uri(str(dummy_file))
	assert uri == ""


def test_track_class_metadata_extraction(tmp_path):
	"""Test Track metadata parsing and display formatting fallbacks."""
	test_file = tmp_path / "Queen - Bohemian Rhapsody.mp3"
	test_file.write_bytes(b"TEST_AUDIO_CONTENT")

	# Mock MutagenFile to return customized tags
	mock_audio = MagicMock()
	mock_audio.info.length = 354.5  # 5:54
	mock_audio.tags = {
		"title": ["Bohemian Rhapsody"],
		"artist": ["Queen"],
		"album": ["A Night at the Opera"],
	}

	with (
		patch("app.services.library.MutagenFile", return_value=mock_audio),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch.object(server.Track, "_extract_mood", return_value=None),
	):
		track = server.Track(test_file)
		data = track.to_dict()

		assert data["title"] == "Bohemian Rhapsody"
		assert data["artist"] == "Queen"
		assert data["album"] == "A Night at the Opera"
		assert data["duration_str"] == "5:54"
		assert data["display_title"] == "Bohemian Rhapsody"
		assert data["display_artist"] == "Queen"
		assert "queen" in data["search_string"]
		assert "bohemian" in data["search_string"]


def test_track_class_fallback_filename(tmp_path):
	"""Test Track parsing when audio tags are missing (fallback to filename)."""
	test_file = tmp_path / "Soda Stereo - De Música Ligera.flac"
	test_file.write_bytes(b"TEST_AUDIO_CONTENT")

	with (
		patch("app.services.library.MutagenFile", return_value=None),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch.object(server.Track, "_extract_mood", return_value=None),
	):
		track = server.Track(test_file)
		data = track.to_dict()

		assert data["display_title"] == "Soda Stereo - De Música Ligera"
		assert data["display_artist"] == "Desconocido"
		assert data["album"] == "Desconocido"
		assert data["duration_str"] == "0:00"


def test_parse_fp():
	"""Test parse_fp converts fingerprint strings to integer arrays or None."""
	assert server.parse_fp(None) is None
	assert server.parse_fp("") is None
	# Valid fingerprint string
	fp_str = "123,456,789"
	parsed = server.parse_fp(fp_str)
	assert parsed == [123, 456, 789]


def test_compare_fps():
	"""Test compare_fps acoustID similarity calculations."""
	assert server.compare_fps(None, None) == 0.0
	assert server.compare_fps([1, 2], [1, 2]) == 0.0  # <10 elements returns 0.0

	# 100% identical fingerprints (length >= 10)
	fp1 = [1000 + i for i in range(20)]
	assert server.compare_fps(fp1, fp1) == 1.0

	# Completely different bitwise inverted fingerprints
	fp2 = [~x & 0xFFFFFFFF for x in fp1]
	assert server.compare_fps(fp1, fp2) == 0.0


def test_is_mood_available():
	"""Test is_mood_available detects presence of ffmpeg binary."""
	with patch("app.engine.audio_analysis.find_binary", return_value="/usr/bin/ffmpeg"):
		assert server.is_mood_available() is True

	with patch("app.engine.audio_analysis.find_binary", return_value=None):
		assert server.is_mood_available() is False


def test_extract_audio_features_ffmpeg_success(tmp_path):
	"""Test extract_audio_features_ffmpeg computes bpm, energy and centroid from raw PCM."""
	import array
	import math

	test_file = tmp_path / "test.mp3"
	test_file.write_bytes(b"dummy")

	# Generate 12 seconds of synthetic audio at 11025 Hz with 2 Hz beat (120 BPM)
	sr = 11025
	duration_sec = 12
	total_samples = sr * duration_sec
	raw_samples = array.array("h")
	for i in range(total_samples):
		t = i / sr
		# Carrier 440 Hz modulated by 2 Hz envelope (120 BPM)
		env = 0.5 * (1.0 + math.cos(2 * math.pi * 2.0 * t))
		val = int(env * 10000.0 * math.sin(2 * math.pi * 440.0 * t))
		raw_samples.append(val)

	pcm_bytes = raw_samples.tobytes()
	mock_proc = MagicMock()
	mock_proc.returncode = 0
	mock_proc.stdout = pcm_bytes

	with patch("subprocess.run", return_value=mock_proc):
		bpm, energy, centroid = server.extract_audio_features_ffmpeg(test_file, ffmpeg_bin="/usr/bin/ffmpeg")
		assert 110.0 <= bpm <= 130.0
		assert energy > 0.0
		assert centroid > 0.0


def test_extract_audio_features_ffmpeg_timeout(tmp_path):
	"""Test extract_audio_features_ffmpeg returns (-1.0, -1.0, -1.0) on subprocess timeout."""
	import subprocess

	test_file = tmp_path / "timeout.mp3"
	test_file.write_bytes(b"dummy")

	with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=5.0)):
		bpm, energy, centroid = server.extract_audio_features_ffmpeg(test_file, ffmpeg_bin="/usr/bin/ffmpeg")
		assert bpm == -1.0
		assert energy == -1.0
		assert centroid == -1.0


def test_extract_audio_features_ffmpeg_failure(tmp_path):
	"""Test extract_audio_features_ffmpeg returns (-1.0, -1.0, -1.0) on error or non-zero exit."""
	test_file = tmp_path / "error.mp3"
	test_file.write_bytes(b"dummy")

	mock_proc = MagicMock()
	mock_proc.returncode = 1
	mock_proc.stdout = b""

	with patch("subprocess.run", return_value=mock_proc):
		bpm, energy, centroid = server.extract_audio_features_ffmpeg(test_file, ffmpeg_bin="/usr/bin/ffmpeg")
		assert bpm == -1.0
		assert energy == -1.0
		assert centroid == -1.0


def test_track_mood_ffmpeg_success(tmp_path):
	"""Test Track mood extraction via ffmpeg."""
	test_file = tmp_path / "song.mp3"
	test_file.write_bytes(b"dummy")

	with (
		patch("app.services.library.MutagenFile", return_value=None),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch("app.engine.audio_analysis.find_binary", return_value="/usr/bin/ffmpeg"),
		patch("app.engine.audio_analysis.extract_audio_features_ffmpeg", return_value=(128.0, 0.65, 1850.0)),
	):
		track = server.Track(test_file)
		assert track.bpm == 128.0
		assert track.energy == 0.65
		assert track.spectral_centroid == 1850.0


def test_track_mood_tag_priority_over_ffmpeg(tmp_path):
	"""When tags contain BPM, tag BPM takes priority while energy and centroid come from ffmpeg."""
	test_file = tmp_path / "song_tagged.mp3"
	test_file.write_bytes(b"dummy")

	mock_audio = MagicMock()
	mock_audio.info.length = 180.0
	mock_audio.tags = {"TBPM": ["140"]}

	with (
		patch("app.services.library.MutagenFile", return_value=mock_audio),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch("app.engine.audio_analysis.find_binary", return_value="/usr/bin/ffmpeg"),
		patch("app.engine.audio_analysis.extract_audio_features_ffmpeg", return_value=(138.5, 0.72, 2100.0)),
	):
		track = server.Track(test_file)
		assert track.bpm == 140.0
		assert track.energy == 0.72
		assert track.spectral_centroid == 2100.0


def test_track_mood_tags_fallback_without_ffmpeg(tmp_path):
	"""When ffmpeg is missing but tags have BPM, uses tag BPM and leaves energy/centroid at 0.0."""
	test_file = tmp_path / "song_tag_fallback.mp3"
	test_file.write_bytes(b"dummy")

	mock_audio = MagicMock()
	mock_audio.info.length = 180.0
	mock_audio.tags = {"bpm": ["125.5"]}

	with (
		patch("app.services.library.MutagenFile", return_value=mock_audio),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch("app.engine.audio_analysis.find_binary", return_value=None),
	):
		track = server.Track(test_file)
		assert track.bpm == 125.5
		assert track.energy == 0.0
		assert track.spectral_centroid == 0.0


def test_track_mood_clean_degradation(tmp_path):
	"""When neither ffmpeg nor tags are available, leaves bpm, energy, centroid at 0.0."""
	test_file = tmp_path / "song_clean_deg.mp3"
	test_file.write_bytes(b"dummy")

	with (
		patch("app.services.library.MutagenFile", return_value=None),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch("app.engine.audio_analysis.find_binary", return_value=None),
	):
		track = server.Track(test_file)
		assert track.bpm == 0.0
		assert track.energy == 0.0
		assert track.spectral_centroid == 0.0


def test_track_mood_ffmpeg_error(tmp_path):
	"""When ffmpeg fails/errors, assigns -1.0 to avoid retrying corrupt tracks."""
	test_file = tmp_path / "song_corrupt.mp3"
	test_file.write_bytes(b"dummy")

	with (
		patch("app.services.library.MutagenFile", return_value=None),
		patch.object(server.Track, "_extract_fingerprint", return_value=None),
		patch("app.engine.audio_analysis.find_binary", return_value="/usr/bin/ffmpeg"),
		patch("app.engine.audio_analysis.extract_audio_features_ffmpeg", return_value=(-1.0, -1.0, -1.0)),
	):
		track = server.Track(test_file)
		assert track.bpm == -1.0
		assert track.energy == -1.0
		assert track.spectral_centroid == -1.0
