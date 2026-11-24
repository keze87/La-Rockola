"""Tests TDD para el comando clear_round (limpiar cola, historial y tema actual)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.core import config as config_mod
from app.core.container import get_container


def test_command_clear_round_clears_queue_history_and_current_track(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""POST /command con cmd='clear_round' detiene la reproducción y vacía cola, historial y tema actual."""
	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	config_mod.set_settings(config_mod.Settings(music_dir="", music_dir_configured=False))

	with TestClient(main_mod.create_app()) as client:
		state = get_container().ensure_orchestrator()
		assert state is not None
		state.queue_manager.history = ["/music/hist1.mp3"]
		state.queue_manager.current_track = "/music/current.mp3"
		state.queue_manager.queue = ["/music/next1.mp3", "/music/next2.mp3"]
		state.queue_manager.pause_after_path = "/music/current.mp3"

		stop_mock = AsyncMock()
		monkeypatch.setattr(state, "stop_playback", stop_mock)

		res = client.post("/command", json={"cmd": "clear_round"})

	assert res.status_code == 200
	assert res.json()["status"] == "ok"
	assert state.queue_manager.queue == []
	assert state.queue_manager.history == []
	assert state.queue_manager.pause_after_path is None
	stop_mock.assert_awaited_once_with(reset_ui_state=True)
