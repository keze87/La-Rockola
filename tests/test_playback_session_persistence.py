"""Tests para persistencia y restauración con TTL de cola, orden, historial y configuraciones."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.playback.orchestrator import PlaybackOrchestrator


def test_saves_and_restores_queue_order_history_and_configs_within_ttl(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""Al reiniciar dentro del TTL se restauran cola, orden, historial, pista actual y configuraciones."""
	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	db_path = tmp_path / "rockola.db"

	orch1 = PlaybackOrchestrator(initial_dir=str(tmp_path), db_path=db_path, use_mpv=False)
	orch1.current_track = "/music/tema_actual.mp3"
	orch1.time_pos = 42.5
	orch1.queue = ["/music/b.mp3", "/music/a.mp3", "/music/c.mp3"]
	orch1.history = ["/music/prev1.mp3", "/music/prev2.mp3"]
	orch1.pause_after_path = "/music/a.mp3"
	orch1.dj_carpincho_enabled = True
	orch1.dj_safe_mode = True
	orch1.dj_mode = "favorites"
	orch1.radio_mode_enabled = False
	orch1.default_sort = "artist"
	orch1.volume = 77
	orch1.server_muted = True
	orch1.save_playback_session(force=True)

	orch2 = PlaybackOrchestrator(initial_dir=str(tmp_path), db_path=db_path, use_mpv=False)
	restored = orch2.restore_playback_session(max_age_sec=3600)

	assert restored is True
	assert orch2.current_track == "/music/tema_actual.mp3"
	assert orch2.mpv_paused is True
	assert orch2.time_pos == 42.5
	assert orch2.queue == ["/music/b.mp3", "/music/a.mp3", "/music/c.mp3"]
	assert orch2.history == ["/music/prev1.mp3", "/music/prev2.mp3"]
	assert orch2.pause_after_path == "/music/a.mp3"
	assert orch2.dj_carpincho_enabled is True
	assert orch2.dj_safe_mode is True
	assert orch2.dj_mode == "favorites"
	assert orch2.radio_mode_enabled is False
	assert orch2.default_sort == "artist"
	assert orch2.volume == 77
	assert orch2.server_muted is True


def test_expired_session_is_not_restored_and_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Si pasó el tiempo máximo desde saved_at, no se restaura la cola vieja y se limpia el archivo."""
	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	db_path = tmp_path / "rockola.db"
	session_file = tmp_path / "playback_session.json"
	session_file.write_text(
		json.dumps(
			{
				"saved_at": time.time() - 7200,
				"current_track": "/music/viejo.mp3",
				"queue": ["/music/q1.mp3"],
				"history": [],
				"dj_carpincho_enabled": True,
			}
		),
		encoding="utf-8",
	)

	orch = PlaybackOrchestrator(initial_dir=str(tmp_path), db_path=db_path, use_mpv=False)
	restored = orch.restore_playback_session(max_age_sec=3600)

	assert restored is False
	assert orch.current_track is None
	assert orch.queue == []
	assert orch.dj_carpincho_enabled is False
	assert not session_file.exists()


@pytest.mark.asyncio
async def test_broadcast_state_persists_session_when_queue_or_settings_change(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""broadcast_state debe persistir el snapshot ante cambios de cola/orden/configuración."""
	from app.core.container import get_container
	from app.domain.playback.orchestrator import broadcast_state

	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	orch = PlaybackOrchestrator(initial_dir=str(tmp_path), db_path=tmp_path / "rockola.db", use_mpv=False)
	ws_mgr = MagicMock()
	ws_mgr.broadcast_json = AsyncMock()
	container = get_container()
	container.orchestrator = orch
	container.ws_manager = ws_mgr

	orch.queue = ["/music/1.mp3", "/music/2.mp3"]
	orch.dj_carpincho_enabled = True
	await broadcast_state()

	session_file = tmp_path / "playback_session.json"
	assert session_file.is_file()
	data = json.loads(session_file.read_text(encoding="utf-8"))
	assert data["queue"] == ["/music/1.mp3", "/music/2.mp3"]
	assert data["dj_carpincho_enabled"] is True


def test_lifespan_restores_session_on_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Al iniciar FastAPI lifespan, si existe una sesión vigente se restaura automáticamente."""
	from fastapi.testclient import TestClient

	from app.core import config as config_mod
	from app.core.container import get_container
	from app.main import create_app

	music_dir = tmp_path / "music"
	music_dir.mkdir()
	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	config_mod.set_settings(config_mod.Settings(music_dir=str(music_dir), music_dir_configured=True, no_mpv=True))

	(tmp_path / "playback_session.json").write_text(
		json.dumps(
			{
				"saved_at": time.time(),
				"current_track": "/music/restaurado.mp3",
				"time_pos": 15.0,
				"queue": ["/music/sig1.mp3", "/music/sig2.mp3"],
				"history": ["/music/ant1.mp3"],
				"dj_carpincho_enabled": True,
				"dj_safe_mode": True,
				"volume": 65,
			}
		),
		encoding="utf-8",
	)

	app = create_app()
	with TestClient(app):
		orch = get_container().orchestrator
		assert orch is not None
		assert orch.current_track == "/music/restaurado.mp3"
		assert orch.queue == ["/music/sig1.mp3", "/music/sig2.mp3"]
		assert orch.history == ["/music/ant1.mp3"]
		assert orch.dj_carpincho_enabled is True
		assert orch.dj_safe_mode is True
		assert orch.volume == 65
