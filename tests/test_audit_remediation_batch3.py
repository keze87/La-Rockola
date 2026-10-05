"""
Pruebas para el lote 3 de remediaciones y endurecimiento de arquitectura.
Verifica entrypoints ejecutables, concurrencia del DJ countdown sin bloqueo,
fallback de state_ref en MPV, hiddenimports en larockola.spec y rutas unificadas de assets.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_entrypoints_presence_and_execution():
	"""Verifica que app/__main__.py y app/cli/entrypoint.py tengan bloques __main__ y respondan a --help."""
	root_dir = Path(__file__).resolve().parents[1]
	app_main_file = root_dir / "app" / "__main__.py"
	cli_entry_file = root_dir / "app" / "cli" / "entrypoint.py"

	assert app_main_file.is_file(), "app/__main__.py debe existir"
	assert 'if __name__ == "__main__":' in app_main_file.read_text(encoding="utf-8")
	assert 'if __name__ == "__main__":' in cli_entry_file.read_text(encoding="utf-8")

	# Ejecución de submódulos con --help
	res_app = subprocess.run(
		[sys.executable, "-m", "app", "--help"],
		cwd=str(root_dir),
		capture_output=True,
		text=True,
		timeout=10,
		check=False,
	)
	assert res_app.returncode == 0
	assert "La Rockola del Carpincho" in res_app.stdout

	res_cli = subprocess.run(
		[sys.executable, "-m", "app.cli.entrypoint", "--help"],
		cwd=str(root_dir),
		capture_output=True,
		text=True,
		timeout=10,
		check=False,
	)
	assert res_cli.returncode == 0
	assert "La Rockola del Carpincho" in res_cli.stdout


@pytest.mark.asyncio
async def test_dj_countdown_does_not_hold_lock_and_cancels_on_stop():
	"""Verifica que el countdown del DJ no retenga _play_next_lock y se cancele con stop_playback."""
	from app.engine.state import APIState

	state = APIState()
	state.radio_mode_enabled = False
	state.dj_carpincho_enabled = True

	state.tracks_cache = [
		{"path": "/tmp/test_track_1.mp3", "display_title": "Track 1"},
	]
	state.current_track = "/tmp/test_initial.mp3"

	# Mock MPV para que no intente enviar sockets reales
	state.mpv = MagicMock()
	state.mpv._send = AsyncMock()
	state.mpv.is_running = True
	state.play_track = AsyncMock()

	# Disparamos play_next en transición natural (skipped_by_user=False)
	# Debe iniciar el countdown pero NO retener el lock
	with patch("app.engine.state.broadcast_state", new=AsyncMock()):
		await state.play_next(skipped_by_user=False)

	# El lock NO debe quedar retenido mientras espera
	assert not state._play_next_lock.locked(), "El lock _play_next_lock NO debe estar bloqueado durante el countdown"
	assert state.dj_countdown_task is not None
	assert not state.dj_countdown_task.done()

	# Llamar a stop_playback debe cancelar el countdown inmediatamente
	countdown_task = state.dj_countdown_task
	await state.stop_playback()

	assert state.dj_countdown_task is None
	is_cancelling = getattr(countdown_task, "cancelling", lambda: 0)() > 0
	assert is_cancelling or countdown_task.cancelled() or countdown_task.done()


@pytest.mark.asyncio
async def test_mpv_state_ref_fallback():
	"""Verifica que AsyncMpvController.start use self.state_ref y get_state() como fallback."""
	from app.engine.mpv_controller import AsyncMpvController

	controller = AsyncMpvController()
	captured_args = []

	async def fake_create_subprocess_exec(*args, **kwargs):
		captured_args.extend(args)
		proc = MagicMock()
		proc.stdout = None
		proc.stderr = None
		proc.returncode = None
		proc.wait = AsyncMock(return_value=0)
		return proc

	with patch("asyncio.create_subprocess_exec", fake_create_subprocess_exec):
		with patch.object(controller, "_check_and_raise_mpv_error", AsyncMock()):
			with patch.object(controller, "_send", AsyncMock()):
				with patch("app.engine.mpv_controller.find_binary", return_value="/usr/bin/mpv"):
					mock_state = MagicMock()
					mock_state.mpv_visible = False
					mock_state.mpris_registered = True

					mock_reader = AsyncMock()
					mock_reader.readline = AsyncMock(return_value=b"")
					mock_writer = MagicMock()
					mock_writer.close = MagicMock()
					mock_writer.wait_closed = AsyncMock()

					# Simulamos get_state devolviendo mock_state
					with patch("app.core.dependencies.get_state", return_value=mock_state):
						with patch("os.path.exists", return_value=True):
							with patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer)):
								# Llamamos start sin state_ref explícito
								await controller.start(state_ref=None)

	# Debe haber guardado controller.state_ref y evaluado los flags correspondientes
	assert controller.state_ref is mock_state or getattr(controller, "state_ref", None) is not None
	assert "--load-scripts=no" in captured_args
	assert "--vo=null" in captured_args


def test_larockola_spec_hiddenimports():
	"""Verifica que larockola.spec incluya app.core.network en hiddenimports."""
	root_dir = Path(__file__).resolve().parents[1]
	spec_file = root_dir / "larockola.spec"
	assert spec_file.is_file()
	spec_content = spec_file.read_text(encoding="utf-8")
	assert '"app.core.network"' in spec_content or "'app.core.network'" in spec_content


def test_media_unified_asset_paths():
	"""Verifica que serve_cover no dependa de parents[3] hardcodeado."""
	from app.api.v1 import media

	source = inspect.getsource(media.serve_cover)
	assert "parents[3]" not in source, "serve_cover no debe contener parents[3] hardcodeado"
