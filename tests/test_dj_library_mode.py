"""
Pruebas para los 3 modos de DJ Bara: shuffle, favorites y library.
"""

from __future__ import annotations

import pytest

from app.api.commands import COMMAND_HANDLERS
from app.api.schemas import CommandRequest
from app.domain.dj.selector import DjBaraSelector
from app.domain.playback.orchestrator import PlaybackOrchestrator


def _create_mock_tracks() -> list[dict[str, str]]:
	return [
		{"path": "/music/a.mp3", "display_title": "Tema A", "display_artist": "Artista 1"},
		{"path": "/music/b.mp3", "display_title": "Tema B", "display_artist": "Artista 2"},
		{"path": "/music/c.mp3", "display_title": "Tema C", "display_artist": "Artista 3"},
	]


def test_dj_selector_default_mode_and_modes_transition() -> None:
	selector = DjBaraSelector()
	assert selector.mode == "shuffle"
	assert selector.safe_mode is False

	selector.mode = "favorites"
	assert selector.safe_mode is True

	selector.mode = "library"
	assert selector.mode == "library"
	assert selector.safe_mode is False

	selector.safe_mode = True
	assert selector.mode == "favorites"
	selector.safe_mode = False
	assert selector.mode == "shuffle"


def test_dj_selector_library_mode_order_and_wrap_around() -> None:
	selector = DjBaraSelector()
	selector.enabled = True
	selector.mode = "library"
	selector.library_order = ["/music/a.mp3", "/music/b.mp3", "/music/c.mp3"]

	tracks = _create_mock_tracks()

	# 1. Sin tema actual -> primer tema de la lista
	candidate = selector.select_candidate(
		unplayed=tracks,
		favorites=[],
		path_to_id={},
		current_track=None,
		tracks_cache=tracks,
	)
	assert candidate is not None
	assert candidate["path"] == "/music/a.mp3"

	# 2. Tema actual es 'a' -> siguiente es 'b'
	candidate_b = selector.select_candidate(
		unplayed=tracks,
		favorites=[],
		path_to_id={},
		current_track="/music/a.mp3",
		tracks_cache=tracks,
	)
	assert candidate_b is not None
	assert candidate_b["path"] == "/music/b.mp3"

	# 3. Tema actual es 'b' -> siguiente es 'c'
	candidate_c = selector.select_candidate(
		unplayed=tracks,
		favorites=[],
		path_to_id={},
		current_track="/music/b.mp3",
		tracks_cache=tracks,
	)
	assert candidate_c is not None
	assert candidate_c["path"] == "/music/c.mp3"

	# 4. Tema actual es el último ('c') -> vuelve al principio ('a')
	candidate_wrap = selector.select_candidate(
		unplayed=tracks,
		favorites=[],
		path_to_id={},
		current_track="/music/c.mp3",
		tracks_cache=tracks,
	)
	assert candidate_wrap is not None
	assert candidate_wrap["path"] == "/music/a.mp3"


def test_dj_selector_library_mode_remembers_last_library_track_when_external_plays() -> None:
	selector = DjBaraSelector()
	selector.enabled = True
	selector.mode = "library"
	selector.library_order = ["/music/a.mp3", "/music/b.mp3", "/music/c.mp3"]
	tracks = _create_mock_tracks()

	# Suena 'b'
	_ = selector.select_candidate(
		unplayed=tracks,
		favorites=[],
		path_to_id={},
		current_track="/music/b.mp3",
		tracks_cache=tracks,
	)

	# Ahora suena un tema externo que no está en la biblioteca filtrada
	candidate = selector.select_candidate(
		unplayed=tracks,
		favorites=[],
		path_to_id={},
		current_track="/youtube/video123.mp3",
		tracks_cache=tracks,
	)
	# Debe continuar a partir del último tema de la biblioteca que sonó ('b'), o sea 'c'
	assert candidate is not None
	assert candidate["path"] == "/music/c.mp3"


def test_dj_selector_refresh_preview_in_library_mode() -> None:
	selector = DjBaraSelector()
	selector.enabled = True
	selector.mode = "library"
	selector.library_order = ["/music/a.mp3", "/music/b.mp3", "/music/c.mp3"]
	tracks = _create_mock_tracks()

	# Aunque 'b' esté en el historial, en modo biblioteca debe seleccionarlo si es el siguiente
	preview = selector.refresh_preview(
		queue=[],
		history=["/music/a.mp3", "/music/b.mp3"],
		current_track="/music/a.mp3",
		tracks_cache=tracks,
		favorites=[],
		path_to_id={},
	)
	assert preview is not None
	assert preview["path"] == "/music/b.mp3"
	assert selector.next_track == preview


@pytest.mark.asyncio
async def test_commands_set_dj_mode_and_sync_library(tmp_path) -> None:
	orch = PlaybackOrchestrator(db_path=tmp_path / "test.db")
	orch.tracks_cache = _create_mock_tracks()
	orch.dj_carpincho_enabled = True

	# Comando set_dj_mode
	req_mode = CommandRequest(cmd="set_dj_mode", mode="library", paths=["/music/b.mp3", "/music/c.mp3"])
	await COMMAND_HANDLERS["set_dj_mode"](orch, req_mode, None)

	assert orch.dj_mode == "library"
	assert orch.dj_library_order == ["/music/b.mp3", "/music/c.mp3"]
	assert orch.dj_next_track is not None
	assert orch.dj_next_track["path"] == "/music/b.mp3"

	# Comando sync_dj_library
	req_sync = CommandRequest(cmd="sync_dj_library", paths=["/music/c.mp3", "/music/a.mp3"])
	await COMMAND_HANDLERS["sync_dj_library"](orch, req_sync, None)

	assert orch.dj_library_order == ["/music/c.mp3", "/music/a.mp3"]
	assert orch.dj_next_track is not None
	assert orch.dj_next_track["path"] == "/music/c.mp3"
