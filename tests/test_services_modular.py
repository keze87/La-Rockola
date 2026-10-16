"""
Tests TDD para app.services (library, radio, ytdlp).
"""

import pytest

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
	assert radio.weather_location is not None


def test_radio_service_is_valid_radio_mp3_file(tmp_path):
	from app.services.radio import _is_valid_radio_mp3_file

	# Nonexistent
	assert _is_valid_radio_mp3_file(tmp_path / "ghost.mp3") is False

	# Tiny file (< 4 bytes)
	tiny = tmp_path / "tiny.mp3"
	tiny.write_bytes(b"12")
	assert _is_valid_radio_mp3_file(tiny) is False

	# ID3 valid header
	id3_file = tmp_path / "id3.mp3"
	id3_file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00dummy")
	assert _is_valid_radio_mp3_file(id3_file) is True

	# Sync word valid header
	sync_file = tmp_path / "sync.mp3"
	sync_file.write_bytes(b"\xff\xfb\x90\x00dummy")
	assert _is_valid_radio_mp3_file(sync_file) is True

	# Invalid audio
	bad_file = tmp_path / "bad.mp3"
	bad_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
	assert _is_valid_radio_mp3_file(bad_file) is False


def test_radio_service_archive_and_prune(tmp_path):
	radio = RadioService()
	archive_dir = tmp_path / "radio_archive"

	# Non-existent or max_files <= 0
	assert radio.prune_radio_archive(tmp_path / "non_existent", max_files=10) == 0
	assert radio.prune_radio_archive(archive_dir, max_files=0) == 0

	# Archive script
	txt_path = radio.archive_radio_announcement(
		archive_dir,
		script_text="Buenas tardes chamigo",
		display_title="Locución de la Tarde",
		max_files=2,
	)
	assert txt_path is not None
	assert txt_path.is_file()
	content = txt_path.read_text(encoding="utf-8")
	assert "Buenas tardes chamigo" in content
	assert "Locución de la Tarde" in content

	# Collision handling
	txt_path2 = radio.archive_radio_announcement(
		archive_dir,
		script_text="Segunda locución",
		display_title="Locución 2",
		max_files=2,
	)
	assert txt_path2 is not None
	assert txt_path2.is_file()

	# Create a dummy residual mp3 in archive
	dummy_mp3 = archive_dir / "radio_dummy.mp3"
	dummy_mp3.write_bytes(b"mp3data")

	# Add 2 more text files to trigger pruning (max_files=2)
	(archive_dir / "radio_2026-01-01_10-00-00.txt").write_text("old1")
	(archive_dir / "radio_2026-01-01_11-00-00.txt").write_text("old2")

	pruned = radio.prune_radio_archive(archive_dir, max_files=2)
	assert pruned > 0
	assert not dummy_mp3.exists()


@pytest.mark.asyncio
async def test_radio_service_apply_hot_mix(tmp_path):
	radio = RadioService()
	voice_file = tmp_path / "voice.mp3"
	voice_file.write_bytes(b"VOICE_DATA")
	out_file = tmp_path / "out.mp3"

	# Create subtitles
	lrc_file = tmp_path / "voice.lrc"
	lrc_file.write_text("[00:01.00] Hola", encoding="utf-8")
	srt_file = tmp_path / "voice.srt"
	srt_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nHola", encoding="utf-8")

	# Fallback (without next_track_path) -> direct copy
	ok = await radio.apply_hot_mix_to_announcement(
		voice_file,
		out_file,
		title="Test Mix",
		next_track_path=None,
	)
	assert ok is True
	assert out_file.read_bytes() == b"VOICE_DATA"
	assert (tmp_path / "out.lrc").is_file()
	assert (tmp_path / "out.srt").is_file()


@pytest.mark.asyncio
async def test_radio_service_get_or_synthesize_scenarios(tmp_path):
	import asyncio
	from unittest.mock import AsyncMock, PropertyMock, patch

	radio = RadioService()

	# 1. Unavailable scenario
	with patch("app.services.radio.RadioService.is_available", new_callable=PropertyMock, return_value=False):
		ok, title, script, err = await radio.get_or_synthesize()
		assert ok is False
		assert err == "Servicio de radio no disponible"

	# Test cancel_pregeneration
	dummy_pregen_file = tmp_path / "part_pregen.mp3"
	dummy_pregen_file.write_bytes(b"data")
	radio.pregenerated_path = dummy_pregen_file
	radio.pregenerated_announcement = {"dummy": 1}
	radio.cancel_pregeneration()
	assert not dummy_pregen_file.exists()
	assert radio.pregenerated_announcement is None

	# 2. Consume pregenerated
	ann_file = tmp_path / "pregen.mp3"
	ann_file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00dummy")
	radio.pregenerated_announcement = {
		"path": str(ann_file),
		"display_title": "Pregenerado",
		"script": "Texto pregenerado",
		"created_at": 9999999999.0,  # future -> not expired
	}

	with patch.object(radio, "apply_hot_mix_to_announcement", AsyncMock(return_value=True)):
		ok, title, script, err = await radio.get_or_synthesize(announcement_path=tmp_path / "out_ann.mp3")
		assert ok is True
		assert title == "Pregenerado"
		assert script == "Texto pregenerado"
		assert err is None

	# 3. Wait for pregeneration task with callback
	callback_states = []

	def on_status(is_synthesizing):
		callback_states.append(is_synthesizing)

	async def fake_pregen():
		await asyncio.sleep(0.01)
		radio.pregenerated_announcement = {
			"path": str(ann_file),
			"display_title": "Task Done",
			"script": "Texto task",
			"created_at": 9999999999.0,
		}

	radio.pregeneration_task = asyncio.create_task(fake_pregen())
	with patch.object(radio, "apply_hot_mix_to_announcement", AsyncMock(return_value=True)):
		ok, title, script, err = await radio.get_or_synthesize(
			on_synthesis_status=on_status,
			announcement_path=tmp_path / "out_task.mp3",
		)
		assert ok is True
		assert title == "Task Done"
		assert callback_states == [True, False]

	# 4. Fallback synthesis exception handling
	with patch("app.services.radio.create_radio_announcement", side_effect=RuntimeError("Synthesis crashed")):
		ok, title, script, err = await radio.get_or_synthesize(announcement_path=tmp_path / "err.mp3")
		assert ok is False
		assert "Synthesis crashed" in str(err)

	# 5. Expired pregenerated announcement
	radio.pregenerated_announcement = {
		"path": str(ann_file),
		"display_title": "Viejo",
		"script": "Texto viejo",
		"created_at": 100.0,  # Expired
	}
	with patch("app.services.radio.create_radio_announcement", AsyncMock(return_value={"ok": False, "error": "none"})):
		ok, title, script, err = await radio.get_or_synthesize(announcement_path=tmp_path / "exp.mp3")
		assert ok is False


@pytest.mark.asyncio
async def test_radio_service_consume_pregenerated_outro_change(tmp_path):
	from unittest.mock import AsyncMock, patch

	radio = RadioService()
	ann_file = tmp_path / "pregen_outro.mp3"
	ann_file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00dummy")
	pre = {
		"path": str(ann_file),
		"display_title": "Con Cierre",
		"script": "Texto",
		"created_at": 9999999999.0,
		"outro_mode": "continue",
		"host_voice": "tomas",
		"stem_segments": [("intro", "hola")],
	}
	with (
		patch(
			"app.services.radio.replace_announcement_outro",
			AsyncMock(return_value=(True, "Con Cierre", "Texto", None)),
		) as mock_replace,
		patch.object(radio, "apply_hot_mix_to_announcement", AsyncMock(return_value=True)),
	):
		ok, title, _script = await radio._consume_pregenerated(
			pre,
			target_ann_path=tmp_path / "target.mp3",
			next_track_path=None,
			bg_offset=0.0,
			outro_mode="stop",  # Different outro mode!
		)
		assert ok is True
		assert title == "Con Cierre"
		mock_replace.assert_awaited_once()


@pytest.mark.asyncio
async def test_radio_service_hot_mix_with_bg_track(tmp_path):
	from unittest.mock import patch

	radio = RadioService()
	voice_file = tmp_path / "voice_bg.mp3"
	voice_file.write_bytes(b"VOICE")
	out_file = tmp_path / "out_bg.mp3"
	bg_track = tmp_path / "bg.mp3"
	bg_track.write_bytes(b"BG_TRACK")

	with (
		patch("app.services.radio.mix_announcement_with_bg_track", return_value=True) as mock_mix,
		patch("app.services.radio.embed_cover_art_in_mp3") as mock_embed,
	):
		ok = await radio.apply_hot_mix_to_announcement(
			voice_file,
			out_file,
			title="Hot Mix Test",
			next_track_path=str(bg_track),
			bg_offset=5.0,
		)
		assert ok is True
		mock_mix.assert_called_once()
		mock_embed.assert_called_once()


def test_radio_service_archive_and_prune_errors(tmp_path):
	from unittest.mock import patch

	radio = RadioService()

	# Prune error handling
	with patch("pathlib.Path.glob", side_effect=PermissionError("Permission denied")):
		assert radio.prune_radio_archive(tmp_path, max_files=10) == 0

	# Archive error handling
	with patch("pathlib.Path.mkdir", side_effect=OSError("Read-only filesystem")):
		assert radio.archive_radio_announcement(tmp_path / "bad_archive", "script") is None


@pytest.mark.asyncio
async def test_radio_service_synthesize_announcement():
	from unittest.mock import AsyncMock, patch

	radio = RadioService()
	with patch("app.services.radio.create_radio_announcement", AsyncMock(return_value={"ok": True})) as mock_synth:
		res = await radio.synthesize_announcement(
			current_track={"title": "Song 1"},
			next_track={"title": "Song 2"},
		)
		assert res == {"ok": True}
		mock_synth.assert_awaited_once()


def test_ytdlp_service_initialization():
	ytdlp = YtDlpService()
	assert ytdlp is not None
