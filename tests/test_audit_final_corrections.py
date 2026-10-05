"""
Pruebas para las correcciones finales de arquitectura modular.
Verifica:
1. Punto de entrada en server.py ejecutando enable_system_site_packages y main.
2. Soporte de librerías del sistema en app/cli/entrypoint.py y su invocación en main().
3. Broadcast de estado en _run_dj_countdown al finalizar y al cancelarse.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cli import entrypoint


def test_server_entrypoint_structure():
	"""Verifica que server.py invoque enable_system_site_packages() y main() en __main__."""
	root_dir = Path(__file__).resolve().parents[1]
	server_file = root_dir / "server.py"
	content = server_file.read_text(encoding="utf-8")

	assert 'if __name__ == "__main__":' in content
	main_block = content.split('if __name__ == "__main__":')[1]
	assert "enable_system_site_packages()" in main_block
	assert "main()" in main_block


def test_entrypoint_enable_system_site_packages(monkeypatch, tmp_path):
	"""Verifica que enable_system_site_packages exista en app.cli.entrypoint y funcione en modo frozen."""
	assert hasattr(entrypoint, "enable_system_site_packages"), (
		"app.cli.entrypoint debe tener enable_system_site_packages"
	)

	fake_user_site = str(tmp_path / "user_site")
	fake_sys_site = str(tmp_path / "sys_site")
	Path(fake_user_site).mkdir()
	Path(fake_sys_site).mkdir()

	monkeypatch.setattr(sys, "frozen", True, raising=False)
	monkeypatch.setattr("site.getusersitepackages", lambda: fake_user_site)
	monkeypatch.setattr("site.getsitepackages", lambda: [fake_sys_site])

	original_path = list(sys.path)
	try:
		entrypoint.enable_system_site_packages()
		assert fake_user_site in sys.path
		assert fake_sys_site in sys.path
	finally:
		sys.path[:] = original_path


def test_main_invokes_enable_system_site_packages_before_check_dependencies():
	"""Verifica que main() invoque enable_system_site_packages() antes de check_dependencies()."""
	source = inspect.getsource(entrypoint.main)
	assert "enable_system_site_packages()" in source
	idx_site = source.index("enable_system_site_packages()")
	idx_deps = source.index("check_dependencies()")
	assert idx_site < idx_deps, "enable_system_site_packages() debe ejecutarse antes de check_dependencies()"


@pytest.mark.asyncio
async def test_dj_countdown_broadcasts_on_finish_and_cancel():
	"""Verifica que _run_dj_countdown emita broadcast_state tanto al finalizar como al cancelarse."""
	from app.engine.state import APIState

	state = APIState()
	state.radio_mode_enabled = False
	state.dj_carpincho_enabled = True
	state.tracks_cache = [
		{"path": "/tmp/test1.mp3", "display_title": "T1"},
		{"path": "/tmp/test2.mp3", "display_title": "T2"},
	]
	state.current_track = "/tmp/test1.mp3"
	state.mpv = MagicMock()
	state.mpv._send = AsyncMock()
	state.mpv.is_running = True
	state.play_track = AsyncMock()

	# Caso 1: Finalización normal de la cuenta regresiva
	with patch("app.engine.state.broadcast_state", new_callable=AsyncMock) as mock_broadcast:
		with patch("asyncio.sleep", new_callable=AsyncMock):
			await state.play_next(skipped_by_user=False)
			assert state.dj_countdown_task is not None
			await state.dj_countdown_task

			# Debe haber broadcast inicial (al elegir tema) y broadcast final (al terminar countdown)
			assert mock_broadcast.await_count >= 2

	# Caso 2: Cancelación de la cuenta regresiva
	state.current_track = "/tmp/test1.mp3"
	state.dj_countdown_task = None
	with patch("app.engine.state.broadcast_state", new_callable=AsyncMock) as mock_broadcast_cancel:
		with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
			await state.play_next(skipped_by_user=False)
			assert state.dj_countdown_task is not None
			try:
				await state.dj_countdown_task
			except asyncio.CancelledError:
				pass

			# Debe haber emitido broadcast al cancelarse
			assert mock_broadcast_cancel.await_count >= 2


@pytest.mark.asyncio
async def test_has_edge_tts_property_and_capabilities_endpoint():
	"""Verifica que APIState exponga has_edge_tts y que /system/capabilities devuelva el valor real."""
	from app.api.v1.system import get_system_capabilities
	from app.engine.state import APIState

	state = APIState()
	assert hasattr(state, "has_edge_tts"), "APIState debe tener la propiedad has_edge_tts"

	# Mockeamos radio_service.is_available como True
	state.radio_service = MagicMock()
	state.radio_service.is_available = True
	assert state.has_edge_tts is True

	with patch("app.api.v1.system.get_state", return_value=state):
		caps = await get_system_capabilities()
		assert caps.get("has_edge_tts") is True

	# Mockeamos radio_service.is_available como False
	state.radio_service.is_available = False
	assert state.has_edge_tts is False

	with patch("app.api.v1.system.get_state", return_value=state):
		caps = await get_system_capabilities()
		assert caps.get("has_edge_tts") is False


@pytest.mark.asyncio
async def test_dj_countdown_race_condition_protection():
	"""Verifica que si otro tema empezó a reproducirse durante el countdown, _run_dj_countdown no lo pise."""
	from app.engine.state import APIState

	state = APIState()
	state.radio_mode_enabled = False
	state.dj_carpincho_enabled = True
	state.tracks_cache = [
		{"path": "/tmp/t1.mp3", "display_title": "T1"},
		{"path": "/tmp/t2.mp3", "display_title": "T2"},
	]
	state.current_track = "/tmp/t1.mp3"
	state.mpv = MagicMock()
	state.mpv._send = AsyncMock()
	state.mpv.is_running = True
	state.play_track = AsyncMock()

	# Simulamos que durante el sleep de 10s, otra acción asignó un tema
	async def fake_sleep_with_interruption(seconds):
		state.current_track = "/tmp/manual_track.mp3"

	with patch("app.engine.state.broadcast_state", new_callable=AsyncMock):
		with patch("asyncio.sleep", side_effect=fake_sleep_with_interruption):
			await state.play_next(skipped_by_user=False)
			assert state.dj_countdown_task is not None
			await state.dj_countdown_task

	# Como current_track era distinto de None al despertar, play_track NO debe haberse llamado para el tema del DJ
	state.play_track.assert_not_called()
	assert state.current_track == "/tmp/manual_track.mp3"


def test_no_duplicate_get_dist_dirs_in_main():
	"""Verifica que app/main.py no redefina 'def get_dist_dirs'."""
	root_dir = Path(__file__).resolve().parents[1]
	main_file = root_dir / "app" / "main.py"
	content = main_file.read_text(encoding="utf-8")
	assert "def get_dist_dirs" not in content, "app/main.py no debe definir get_dist_dirs redundante"
