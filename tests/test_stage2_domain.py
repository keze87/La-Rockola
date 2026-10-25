"""
Tests unitarios (TDD) para la capa de Dominio (Stage 2).
Verifica QueueManager, DjBaraSelector, LibraryDomain (hasher, mood, scanner),
RadioDomain (nlp, dialogue, service) y PlaybackOrchestrator.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.domain.dj.selector import DjBaraSelector
from app.domain.library.hasher import compare_fps, generate_smart_hash, parse_fp
from app.domain.library.models import parse_duration_str
from app.domain.library.mood import calculate_mood_scores
from app.domain.library.service import LibraryService
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.domain.queue.manager import QueueManager
from app.domain.radio.dialogue import (
	build_radio_dialogue_plan,
	get_modular_time_segments,
	group_plan_into_speech_turns,
)
from app.domain.radio.nlp import (
	clean_fortune_text,
	contains_blacklisted_content,
	is_spanish_text,
	is_tts_friendly_fortune,
)
from app.infrastructure.db.connection import init_db
from app.infrastructure.db.repositories import TrackRepository


def test_queue_manager_operations() -> None:
	"""Verifica todas las transiciones atómicas de fila, historial y tema actual."""
	qm = QueueManager()

	# Toggle queue
	assert qm.toggle("/music/a.mp3") is True
	assert qm.toggle("/music/b.mp3") is True
	assert qm.queue == ["/music/a.mp3", "/music/b.mp3"]
	assert qm.toggle("/music/a.mp3") is False
	assert qm.queue == ["/music/b.mp3"]

	# Insert y reordenamiento
	qm.insert("/music/a.mp3", 0)
	qm.insert("/music/c.mp3", 2)
	assert qm.queue == ["/music/a.mp3", "/music/b.mp3", "/music/c.mp3"]

	qm.move_queue_item(0, 2)
	assert qm.queue == ["/music/b.mp3", "/music/c.mp3", "/music/a.mp3"]

	# Avanzar tema y verificar pause_after
	qm.current_track = "/music/intro.mp3"
	qm.toggle_pause_after("/music/intro.mp3")
	assert qm.pause_after_path == "/music/intro.mp3"

	finished, should_pause = qm.advance_current(exclude_from_history=False)
	assert finished == "/music/intro.mp3"
	assert should_pause is True
	assert qm.pause_after_path is None
	assert qm.history == ["/music/intro.mp3"]
	assert qm.current_track is None

	# Jump en fila y en historial
	qm.current_track = "/music/now.mp3"
	qm.jump_to_queue(1)
	assert "/music/now.mp3" in qm.history
	assert "/music/b.mp3" in qm.history
	assert qm.queue == ["/music/c.mp3", "/music/a.mp3"]

	qm.current_track = "/music/c.mp3"
	target_hist = qm.jump_to_history(0)
	assert target_hist == "/music/intro.mp3"
	assert "/music/c.mp3" in qm.queue


def test_dj_carpincho_selector() -> None:
	"""Verifica la preselección del DJ Bara en modo normal y modo seguro."""
	dj = DjBaraSelector()
	dj.enabled = True
	dj.safe_mode = True

	tracks = [
		{"path": "/music/fav.mp3", "display_title": "Favorito"},
		{"path": "/music/norm.mp3", "display_title": "Normal"},
	]
	path_to_id = {"/music/fav.mp3": "id_fav", "/music/norm.mp3": "id_norm"}
	favorites = ["id_fav"]

	chosen = dj.refresh_preview(
		queue=[],
		history=[],
		current_track=None,
		tracks_cache=tracks,
		favorites=favorites,
		path_to_id=path_to_id,
	)
	assert chosen is not None
	assert dj.next_track == chosen

	# Si hay temas en la fila, el DJ limpia su preselección
	assert (
		dj.refresh_preview(
			queue=["/music/fav.mp3"],
			history=[],
			current_track=None,
			tracks_cache=tracks,
			favorites=favorites,
			path_to_id=path_to_id,
		)
		is None
	)


def test_library_hasher_mood_and_scanner(tmp_path: Path, dummy_audio_file: Path) -> None:
	"""Verifica el hash inteligente, comparación Chromaprint, cálculo de mood y escaneo SQLite."""
	h1 = generate_smart_hash(dummy_audio_file)
	h2 = generate_smart_hash(dummy_audio_file)
	assert h1 == h2 and len(h1) == 32

	fp1 = parse_fp("10,20,30,40,50,60,70,80,90,100")
	fp2 = parse_fp("10,20,30,40,50,60,70,80,90,100")
	assert compare_fps(fp1, fp2) == 1.0

	assert parse_duration_str("03:30") == 210.0

	scored = calculate_mood_scores(
		[
			{"path": "a.mp3", "bpm": 90.0, "energy": 0.3, "spectral_centroid": 1200.0},
			{"path": "b.mp3", "bpm": 150.0, "energy": 0.9, "spectral_centroid": 3200.0},
		]
	)
	assert scored[0]["mood_score"] < scored[1]["mood_score"]

	db_path = tmp_path / "lib.db"
	init_db(db_path)
	repo = TrackRepository(db_path)
	service = LibraryService(db_path=db_path, track_repo=repo)

	scanned = service.scan_directory([str(dummy_audio_file.parent)], extract_mood=False, extract_fingerprint=False)
	assert len(scanned) == 1
	assert scanned[0]["path"] == str(dummy_audio_file)


def test_radio_nlp_and_dialogue_builder() -> None:
	"""Verifica los filtros lingüísticos criollos y el planificador de diálogo radial."""
	assert is_spanish_text("Hoy es un gran día para tomar unos buenos mates con amigos en el patio.") is True
	assert is_spanish_text("The quick brown fox jumps over the lazy dog every morning.") is False
	assert contains_blacklisted_content("Como modelo de lenguaje IA no puedo responder.") is True

	cleaned = clean_fortune_text("«El que madruga encuentra el mate listo.»\n  -- José Hernández")
	assert "José Hernández" not in cleaned
	assert is_tts_friendly_fortune(cleaned) is True

	dt = datetime(2026, 10, 17, 15, 30)
	time_segs = get_modular_time_segments(dt)
	assert len(time_segs) >= 1

	plan = build_radio_dialogue_plan(
		dt=dt,
		fortune="Siempre que llovió, paró y salió el sol.",
		weather_phrase="En Tucumán hacen 25 grados con cielo despejado.",
		weather_condition="agradable",
		outro_mode="continue",
	)
	turns = group_plan_into_speech_turns(plan)
	assert len(turns) >= 2


async def test_playback_orchestrator_state_and_commands(tmp_path: Path) -> None:
	"""Verifica que PlaybackOrchestrator coordine la reproducción sin acoplamiento espagueti."""
	db_path = tmp_path / "orch.db"
	init_db(db_path)

	orch = PlaybackOrchestrator(
		initial_dir=str(tmp_path),
		open_browser=False,
		db_path=db_path,
	)
	orch.mpv = MagicMock()
	orch.mpv.is_running = True
	orch.mpv.has_display = False
	orch.mpv.start = AsyncMock()
	orch.mpv.stop = AsyncMock()
	orch.mpv.load_file = AsyncMock()
	orch.mpv.set_pause = AsyncMock()
	orch.mpv.set_volume = AsyncMock()
	orch.mpv.set_mute = AsyncMock()
	orch.mpv.set_force_window = AsyncMock()
	orch.mpv.stop_playback = AsyncMock()
	orch.mpv._send = AsyncMock()

	await orch.play_track("/music/tema1.mp3")
	assert orch.current_track == "/music/tema1.mp3"
	assert orch.mpv_paused is False

	await orch.toggle_queue("/music/tema2.mp3")
	assert "/music/tema2.mp3" in orch.queue

	await orch.play_next(skipped_by_user=True)
	assert orch.current_track == "/music/tema2.mp3"
	assert "/music/tema1.mp3" in orch.history

	state_dict = orch.get_full_state_dict(include_library=True)
	assert state_dict["current_track"] == "/music/tema2.mp3"
	assert state_dict["history"] == ["/music/tema1.mp3"]
	assert "scan_status" in state_dict
	assert isinstance(state_dict["library"], list)
