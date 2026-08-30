import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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

	with patch("server.MutagenFile", return_value=mock_audio):
		with patch.object(server.Track, "_extract_fingerprint", return_value=None):
			with patch.object(server.Track, "_extract_mood", return_value=None):
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

	with patch("server.MutagenFile", return_value=None):
		with patch.object(server.Track, "_extract_fingerprint", return_value=None):
			with patch.object(server.Track, "_extract_mood", return_value=None):
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
