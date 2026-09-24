import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


@pytest.mark.asyncio
async def test_mpv_process_event_line_property_changes():
	"""Test parsing of property-change IPC messages for volume, pause, time-pos, duration, mute."""
	callbacks = {
		"volume_update": AsyncMock(),
		"pause_update": AsyncMock(),
		"time_update": AsyncMock(),
		"duration_update": AsyncMock(),
		"mute_update": AsyncMock(),
	}
	mpv = server.AsyncMpvController(callbacks)

	# 1. Volume update
	line = json.dumps({"event": "property-change", "name": "volume", "data": 75}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["volume_update"].assert_called_once_with(75)

	# 2. Pause update
	line = json.dumps({"event": "property-change", "name": "pause", "data": True}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["pause_update"].assert_called_once_with(True)

	# 3. Time update
	line = json.dumps({"event": "property-change", "name": "time-pos", "data": 42.5}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["time_update"].assert_called_once_with(42.5)

	# 4. Duration update
	line = json.dumps({"event": "property-change", "name": "duration", "data": 210.0}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["duration_update"].assert_called_once_with(210.0)

	# 5. Mute update
	line = json.dumps({"event": "property-change", "name": "mute", "data": True}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["mute_update"].assert_called_once_with(True)


@pytest.mark.asyncio
async def test_mpv_process_event_line_end_file():
	"""Test parsing of end-file events with reason eof and stop."""
	callbacks = {
		"song_ended": AsyncMock(),
		"track_stopped": AsyncMock(),
	}
	mpv = server.AsyncMpvController(callbacks)

	# EOF triggers song_ended
	line = json.dumps({"event": "end-file", "reason": "eof"}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["song_ended"].assert_called_once()

	# Stop triggers track_stopped
	line = json.dumps({"event": "end-file", "reason": "stop"}).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)
	callbacks["track_stopped"].assert_called_once()


@pytest.mark.asyncio
async def test_mpv_start_is_restart_behavior():
	"""Verify that start(is_restart=False) does not invoke mpv_restarted, but start(is_restart=True) does."""
	callbacks = {
		"mpv_restarted": AsyncMock(),
	}
	mpv = server.AsyncMpvController(callbacks)

	mock_reader = MagicMock()
	mock_reader.readline = AsyncMock(return_value=b"")
	mock_writer = MagicMock()
	mock_writer.drain = AsyncMock()
	mock_writer.write = MagicMock()

	with (
		patch("asyncio.create_subprocess_exec") as mock_exec,
		patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer), create=True),
		patch("os.path.exists", return_value=True),
		patch.object(mpv, "_send", new_callable=AsyncMock),
	):
		mock_process = MagicMock()
		mock_process.returncode = None
		mock_process.wait = AsyncMock(return_value=0)
		mock_exec.return_value = mock_process

		# Initial startup (is_restart=False)
		await mpv.start(is_restart=False)
		await asyncio.sleep(0.01)
		callbacks["mpv_restarted"].assert_not_called()

		# Explicit restart (is_restart=True)
		await mpv.start(is_restart=True)
		await asyncio.sleep(0.01)
		callbacks["mpv_restarted"].assert_called_once()


def test_mpv_check_windows_pipe_success():
	"""Verify _check_windows_pipe returns True when the named pipe is successfully opened."""
	mpv = server.AsyncMpvController({})
	mpv.socket_path = r"\\.\pipe\test_pipe"

	with patch("builtins.open") as mock_open:
		assert mpv._check_windows_pipe() is True
		mock_open.assert_called_once_with(r"\\.\pipe\test_pipe", "r+b")


def test_mpv_check_windows_pipe_failure():
	"""Verify _check_windows_pipe returns False when opening the pipe raises FileNotFoundError or OSError."""
	mpv = server.AsyncMpvController({})
	mpv.socket_path = r"\\.\pipe\test_pipe"

	with patch("builtins.open", side_effect=FileNotFoundError):
		assert mpv._check_windows_pipe() is False

	with patch("builtins.open", side_effect=OSError("Pipe busy")):
		assert mpv._check_windows_pipe() is False


@pytest.mark.asyncio
async def test_mpv_start_fails_fast_on_process_exit():
	"""Verify start() raises RuntimeError immediately when MPV exits with non-zero code during startup."""
	mpv = server.AsyncMpvController({})
	mock_proc = MagicMock()
	mock_proc.returncode = 127
	mock_proc.stderr = AsyncMock()
	mock_proc.stderr.read = AsyncMock(return_value=b"/bin/bash: symbol lookup error: undefined symbol")

	with (
		patch("asyncio.create_subprocess_exec", return_value=mock_proc),
		patch("os.path.exists", return_value=False),
	):
		with pytest.raises(RuntimeError) as exc_info:
			await mpv.start()

		assert "127" in str(exc_info.value)
		assert "symbol lookup error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mpv_start_passes_clean_env():
	"""Verify start() passes clean environment to create_subprocess_exec."""
	mpv = server.AsyncMpvController({})
	mock_proc = MagicMock()
	mock_proc.returncode = None
	mock_proc.stderr = AsyncMock()

	mock_reader = MagicMock()
	mock_reader.readline = AsyncMock(return_value=b"")
	mock_writer = MagicMock()
	mock_writer.drain = AsyncMock()

	with (
		patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec,
		patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer), create=True),
		patch("os.path.exists", return_value=True),
		patch.object(mpv, "_send", new_callable=AsyncMock),
		patch("server.get_clean_env", return_value={"MOCK_CLEAN_ENV": "1"}) as mock_clean,
	):
		await mpv.start()
		mock_clean.assert_called()
		assert mock_exec.call_args[1]["env"]["MOCK_CLEAN_ENV"] == "1"


def test_ensure_display_env_from_systemctl(monkeypatch):
	"""Verify ensure_display_env extracts variables from systemctl show-environment."""
	monkeypatch.setattr(server.sys, "platform", "linux")
	env = {}
	mock_output = (
		"WAYLAND_DISPLAY=wayland-1\nDISPLAY=:1\nXAUTHORITY=/run/user/1000/xauth_test\nXDG_RUNTIME_DIR=/run/user/1000\n"
	)
	mock_res = MagicMock()
	mock_res.returncode = 0
	mock_res.stdout = mock_output

	with patch("subprocess.run", return_value=mock_res):
		server.ensure_display_env(env)

	assert env.get("WAYLAND_DISPLAY") == "wayland-1"
	assert env.get("DISPLAY") == ":1"
	assert env.get("XAUTHORITY") == "/run/user/1000/xauth_test"


def test_ensure_display_env_fallback_sockets(monkeypatch, tmp_path):
	"""Verify ensure_display_env falls back to filesystem sockets when systemctl fails."""
	monkeypatch.setattr(server.sys, "platform", "linux")
	runtime_dir = tmp_path / "run_user"
	runtime_dir.mkdir()
	(runtime_dir / "wayland-0").touch()
	(runtime_dir / "bus").touch()

	x11_dir = tmp_path / "x11"
	x11_dir.mkdir()
	(x11_dir / "X0").touch()

	env = {"XDG_RUNTIME_DIR": str(runtime_dir)}

	with (
		patch("subprocess.run", side_effect=FileNotFoundError),
		patch(
			"glob.glob",
			side_effect=lambda pattern: (
				[str(runtime_dir / "wayland-0")]
				if "wayland" in pattern
				else [str(x11_dir / "X0")]
				if "/tmp/.X11-unix" in pattern
				else []
			),
		),
	):
		server.ensure_display_env(env)

	assert env.get("WAYLAND_DISPLAY") == "wayland-0"
	assert env.get("DISPLAY") == ":0"
	assert env.get("DBUS_SESSION_BUS_ADDRESS") == f"unix:path={runtime_dir / 'bus'}"


def test_ensure_display_env_windows(monkeypatch):
	"""Verify ensure_display_env does nothing on Windows."""
	monkeypatch.setattr(server.sys, "platform", "win32")
	env = {}
	with patch("subprocess.run") as mock_sub:
		server.ensure_display_env(env)
		mock_sub.assert_not_called()
	assert env == {}


@pytest.mark.asyncio
async def test_mpv_start_display_args_with_display(monkeypatch):
	"""Verify that start() configures GPU contexts and fallback VO when a display is detected."""
	mpv = server.AsyncMpvController({})
	mpv.is_windows = False
	mock_proc = MagicMock()
	mock_proc.returncode = None
	mock_proc.stderr = AsyncMock()

	mock_reader = MagicMock()
	mock_reader.readline = AsyncMock(return_value=b"")
	mock_writer = MagicMock()
	mock_writer.drain = AsyncMock()

	clean_env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}

	with (
		patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec,
		patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer), create=True),
		patch("os.path.exists", return_value=True),
		patch.object(mpv, "_send", new_callable=AsyncMock),
		patch("server.get_clean_env", return_value=clean_env),
		patch("server.ensure_display_env"),
	):
		await mpv.start()
		args = mock_exec.call_args[0]
		assert "--gpu-context=waylandvk,wayland,x11vk,x11egl,x11" in args
		assert "--vo=gpu-next,gpu,null" in args
		assert mpv.has_display is True


@pytest.mark.asyncio
async def test_mpv_start_display_args_headless(monkeypatch):
	"""Verify that start() uses null video output and disables display in headless mode."""
	mpv = server.AsyncMpvController({})
	mpv.is_windows = False
	mock_proc = MagicMock()
	mock_proc.returncode = None
	mock_proc.stderr = AsyncMock()

	mock_reader = MagicMock()
	mock_reader.readline = AsyncMock(return_value=b"")
	mock_writer = MagicMock()
	mock_writer.drain = AsyncMock()

	clean_env = {}  # No display variables

	with (
		patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec,
		patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer), create=True),
		patch("os.path.exists", return_value=True),
		patch.object(mpv, "_send", new_callable=AsyncMock),
		patch("server.get_clean_env", return_value=clean_env),
		patch("server.ensure_display_env"),
	):
		await mpv.start()
		args = mock_exec.call_args[0]
		assert "--vo=null" in args
		assert "--no-audio-display" in args
		assert "--force-window=no" in args
		assert mpv.has_display is False


@pytest.mark.asyncio
async def test_mpv_process_event_line_end_file_error():
	"""Verify that an end-file event with reason error triggers song_ended callback with error reason."""
	callback = AsyncMock()
	mpv = server.AsyncMpvController({"song_ended": callback})

	line = json.dumps(
		{
			"event": "end-file",
			"reason": "error",
			"file_error": "video output initialization failed",
		}
	).encode("utf-8")
	await mpv._process_event_line(line)
	await asyncio.sleep(0.01)

	callback.assert_called_once_with(reason="error", file_error="video output initialization failed")


@pytest.mark.asyncio
async def test_handle_song_ended_skips_stats_on_error():
	"""Verify handle_song_ended skips _register_play_stat when ending with reason=error."""
	state = server.state
	state.current_track = "/music/song.mp3"
	with (
		patch.object(state, "_register_play_stat") as mock_stat,
		patch.object(state, "play_next", new_callable=AsyncMock) as mock_next,
		patch("server.broadcast_state", new_callable=AsyncMock),
	):
		# When reason is error, stats must not be incremented
		await state.handle_song_ended(reason="error", file_error="video output initialization failed")
		mock_stat.assert_not_called()
		mock_next.assert_called_once()

		mock_stat.reset_mock()
		mock_next.reset_mock()

		# When reason is eof, stats must be incremented
		await state.handle_song_ended(reason="eof")
		mock_stat.assert_called_once_with("/music/song.mp3")
		mock_next.assert_called_once()
