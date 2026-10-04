"""
Tests TDD para app.services (library, radio, ytdlp).
"""

from app.services.library import (
	calculate_mood_scores,
	generate_smart_hash,
	parse_duration_str,
)
from app.services.radio import RadioService
from app.services.ytdlp import YtDlpService


def test_parse_duration_str():
	assert parse_duration_str("0:00") == 0.0
	assert parse_duration_str(None) == 0.0
	assert parse_duration_str("03:30") == 210.0
	assert parse_duration_str("1:00:00") == 3600.0


def test_generate_smart_hash(tmp_path):
	small_file = tmp_path / "tiny.mp3"
	small_file.write_bytes(b"DATA" * 500)
	h1 = generate_smart_hash(small_file)
	assert isinstance(h1, str)
	assert len(h1) == 32

	# Large file (>3MB)
	large_file = tmp_path / "large.mp3"
	large_file.write_bytes(b"A" * (4 * 1024 * 1024))
	h2 = generate_smart_hash(large_file)
	assert isinstance(h2, str)
	assert len(h2) == 32
	assert h1 != h2


def test_calculate_mood_scores():
	tracks = [
		{"path": "t1.mp3", "bpm": 100.0, "energy": 0.4, "spectral_centroid": 1500.0},
		{"path": "t2.mp3", "bpm": 150.0, "energy": 0.8, "spectral_centroid": 3000.0},
		{"path": "t3.mp3", "bpm": -1.0, "energy": 0.0, "spectral_centroid": 0.0},
	]
	scored = calculate_mood_scores(tracks)
	assert scored[2]["mood_score"] == 0.0
	assert scored[0]["mood_score"] <= scored[1]["mood_score"]
	assert 0.0 <= scored[0]["mood_score"] <= 1.0


def test_radio_service_initialization():
	radio = RadioService()
	assert radio is not None


def test_ytdlp_service_initialization():
	ytdlp = YtDlpService()
	assert ytdlp is not None
