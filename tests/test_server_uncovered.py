import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from starlette.requests import Request

import scripts.mpv_installer
import scripts.ytdlp_installer
import server

# ==========================================
# 1. Environment & Dependency Checks
# ==========================================


def test_enable_system_site_packages():
	"""Verify enable_system_site_packages behaves correctly in frozen and unfrozen modes."""
	# Unfrozen: should do nothing
	with patch.object(sys, "frozen", False, create=True):
		orig_len = len(sys.path)
		server.enable_system_site_packages()
		assert len(sys.path) == orig_len

	# Frozen mode: adds existing site-packages directories
	with patch.object(sys, "frozen", True, create=True):
		with tempfile.TemporaryDirectory() as u_dir, tempfile.TemporaryDirectory() as s_dir:
			with patch("site.getusersitepackages", return_value=u_dir):
				with patch("site.getsitepackages", return_value=[s_dir]):
					server.enable_system_site_packages()
					assert u_dir in sys.path
					assert s_dir in sys.path
					sys.path.remove(u_dir)
					sys.path.remove(s_dir)


def test_is_mood_available_with_ffmpeg():
	"""Verify is_mood_available checks for ffmpeg binary."""
	with patch("server.find_binary", return_value="/usr/bin/ffmpeg"):
		assert server.is_mood_available() is True
	with patch("server.find_binary", return_value=None):
		assert server.is_mood_available() is False


def test_find_binary_python_scripts(tmp_path):
	"""Verify find_binary checks Python Scripts/bin directories."""
	is_win = sys.platform == "win32" or os.name == "nt"
	scripts_dir_name = "Scripts" if is_win else "bin"
	bin_dir = tmp_path.parent / scripts_dir_name
	bin_dir.mkdir(parents=True, exist_ok=True)
	ext = ".exe" if is_win else ""
	target = bin_dir / f"custom_test_tool{ext}"
	target.write_text("")
	target.chmod(0o755)

	with patch("shutil.which", return_value=None), patch("sys.prefix", str(tmp_path.parent)):
		found = server.find_binary("custom_test_tool")
		assert found is not None
		assert "custom_test_tool" in found
	target.unlink()


def test_check_python_packages():
	"""Verify _check_python_packages detects missing required and optional packages."""
	with patch("importlib.util.find_spec") as mock_find:
		mock_find.return_value = None
		with patch("server.find_binary", return_value=None):
			missing_req, missing_opt = server._check_python_packages(is_frozen=False, force=True)
			req_names = [m[0] for m in missing_req]
			assert "fastapi" in req_names
			assert "uvicorn" in req_names
			assert any("ffmpeg" in m[0] for m in missing_opt)


def test_check_mpv_portable():
	"""Verify _check_mpv behaves correctly when portable and mpv is missing/installed."""
	with patch("server.find_binary", return_value=None):
		with patch.object(scripts.mpv_installer, "install_mpv", return_value=True):
			with patch("server.find_binary", side_effect=[None, "/path/to/mpv"]):
				result = server._check_mpv(is_win=True, is_mac=False, is_frozen=True)
				assert result is None

		with patch.object(scripts.mpv_installer, "install_mpv", side_effect=RuntimeError("Download error")):
			with patch("server.find_binary", return_value=None):
				result = server._check_mpv(is_win=True, is_mac=False, is_frozen=True)
				assert result is not None
				assert result[0] == "mpv"
				assert "winget" in result[1]


def test_check_ytdlp_portable():
	"""Verify _check_ytdlp behaves correctly when missing and installs or fails."""
	with patch("server.find_binary", return_value=None):
		with patch.object(scripts.ytdlp_installer, "install_ytdlp", return_value=True):
			with patch("server.find_binary", side_effect=[None, "/path/to/yt-dlp"]):
				result = server._check_ytdlp(is_win=False, is_mac=False, is_frozen=True)
				assert result is None

		with patch.object(scripts.ytdlp_installer, "install_ytdlp", side_effect=RuntimeError("Network error")):
			with patch("server.find_binary", return_value=None):
				result = server._check_ytdlp(is_win=False, is_mac=False, is_frozen=False)
				assert result is not None
				assert result[0] == "yt-dlp"


def test_check_dependencies_exit():
	"""Verify check_dependencies halts execution when required dependencies are missing."""
	with patch("server._check_python_packages", return_value=([("fastapi", "pip install fastapi")], [])):
		with patch("server._check_mpv", return_value=None):
			with patch("server._check_ytdlp", return_value=None):
				with pytest.raises(SystemExit) as exc_info:
					server.check_dependencies(force=True)
				assert exc_info.value.code == 1


# ==========================================
# 2. DBUS Fallback Classes
# ==========================================


def test_dbus_fallback_classes():
	"""Verify Variant, PropertyAccess, dbus_property, method, and ServiceInterface."""
	var1 = server.Variant("s", "tango")
	var2 = server.Variant("s", "tango")
	var3 = server.Variant("i", 42)

	assert var1 == var2
	assert var1 != var3
	assert var1 != "not-a-variant"

	prop_read = server.PropertyAccess.READ
	assert getattr(prop_read, "value", prop_read) == "read"

	class SampleDbus:
		@server.dbus_property(access=server.PropertyAccess.READ)
		def volume(self) -> "d":  # noqa: F821
			return 80.0

	obj = SampleDbus()
	assert obj.volume == 80.0

	method_dec = server.method()
	assert callable(method_dec)

	svc = server.ServiceInterface("org.mpris.MediaPlayer2.Player")
	assert svc.name == "org.mpris.MediaPlayer2.Player"


# ==========================================
# 3. Browser Opening
# ==========================================


def test_open_browser_platforms():
	"""Verify open_browser_url handles win32, darwin, and linux/xdg-open with fallback."""
	# 1. win32: os.startfile
	with patch("sys.platform", "win32"):
		mock_startfile = MagicMock()
		with patch("os.startfile", mock_startfile, create=True):
			server.open_browser_url("http://localhost:1729")
			mock_startfile.assert_called_once_with("http://localhost:1729")

	# 2. darwin: open command
	with patch("sys.platform", "darwin"):
		with patch("server.get_clean_env", return_value={}):
			with patch("subprocess.Popen") as mock_popen:
				server.open_browser_url("http://localhost:1729")
				mock_popen.assert_called_once()
				assert mock_popen.call_args[0][0][0] == "open"

	# 3. linux: xdg-open command
	with patch("sys.platform", "linux"):
		with patch("server.get_clean_env", return_value={}):
			with patch("shutil.which", return_value="/usr/bin/xdg-open"):
				with patch("subprocess.Popen") as mock_popen:
					server.open_browser_url("http://localhost:1729")
					mock_popen.assert_called_once()
					assert mock_popen.call_args[0][0][0] == "xdg-open"

	# 4. Fallback to webbrowser.open
	with patch("sys.platform", "linux"):
		with patch("shutil.which", return_value=None):
			with patch("webbrowser.open") as mock_wb:
				server.open_browser_url("http://localhost:1729")
				mock_wb.assert_called_once_with("http://localhost:1729")


# ==========================================
# 4. Folder Pickers
# ==========================================


def test_select_folder_tkinter(tmp_path):
	"""Verify _select_folder_tkinter handles GUI dialog."""
	mock_tk = MagicMock()
	mock_root = MagicMock()
	mock_tk.Tk.return_value = mock_root
	mock_filedialog = MagicMock()
	mock_filedialog.askdirectory.return_value = str(tmp_path)

	mock_tk.filedialog = mock_filedialog

	with patch.dict(sys.modules, {"tkinter": mock_tk, "tkinter.filedialog": mock_filedialog}):
		res = server._select_folder_tkinter("Seleccioná carpeta", str(tmp_path))
		assert res == str(tmp_path)
		mock_root.destroy.assert_called_once()


def test_select_folder_macos(tmp_path):
	"""Verify _select_folder_macos executes osascript."""
	with patch("subprocess.run") as mock_run:
		mock_run.return_value = subprocess.CompletedProcess(
			args=[], returncode=0, stdout=str(tmp_path) + "\n", stderr=""
		)
		res = server._select_folder_macos("Título", str(tmp_path))
		assert res == str(tmp_path)


def test_select_folder_linux(tmp_path):
	"""Verify _select_folder_linux tries zenity, kdialog, yad."""
	# 1. zenity success
	with patch("shutil.which", side_effect=lambda name: "/usr/bin/zenity" if name == "zenity" else None):
		with patch("subprocess.run") as mock_run:
			mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout=str(tmp_path) + "\n")
			res = server._select_folder_linux("Elegir", str(tmp_path))
			assert res == str(tmp_path)

	# 2. kdialog success
	with patch("shutil.which", side_effect=lambda name: "/usr/bin/kdialog" if name == "kdialog" else None):
		with patch("subprocess.run") as mock_run:
			mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout=str(tmp_path) + "\n")
			res = server._select_folder_linux("Elegir", str(tmp_path))
			assert res == str(tmp_path)

	# 3. yad success
	with patch("shutil.which", side_effect=lambda name: "/usr/bin/yad" if name == "yad" else None):
		with patch("subprocess.run") as mock_run:
			mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout=str(tmp_path) + "\n")
			res = server._select_folder_linux("Elegir", str(tmp_path))
			assert res == str(tmp_path)


def test_select_folder_dialog_dispatch(tmp_path):
	"""Verify select_folder_dialog delegates by platform."""
	with patch("sys.platform", "darwin"):
		with patch("server._select_folder_macos", return_value=str(tmp_path)):
			assert server.select_folder_dialog() == str(tmp_path)

	with patch("sys.platform", "linux"):
		with patch("server._select_folder_linux", return_value=str(tmp_path)):
			assert server.select_folder_dialog() == str(tmp_path)


# ==========================================
# 5. Readline Completion
# ==========================================


def test_setup_readline_completion():
	"""Verify setup_readline_completion configures path completer without throwing."""
	mock_readline = MagicMock()
	with patch.dict(sys.modules, {"readline": mock_readline}):
		server.setup_readline_completion()
		assert mock_readline.set_completer.called
		completer = mock_readline.set_completer.call_args[0][0]
		# Test completer function
		with patch("glob.glob", return_value=["/home/user/Music", "/home/user/Movies"]):
			assert completer("/home/user/M", 0) is not None
			assert completer("/home/user/M", 5) is None


# ==========================================
# 6. Interactive Setup Wizard
# ==========================================


def test_run_interactive_wizard(tmp_path):
	"""Verify run_interactive_wizard handles option 1, option 3, and directory creation."""
	config_path = tmp_path / "rockola_config.json"
	default_folder = tmp_path / "default_music"
	default_folder.mkdir()
	initial_cfg = {"music_dir": str(default_folder)}

	# Option 1: default directory
	with patch("builtins.input", side_effect=["1"]):
		cfg = server.run_interactive_wizard(config_path, initial_cfg.copy())
		assert cfg["music_dir"] == str(default_folder)

	# Option 3: manual directory with create prompt 's'
	new_dir = tmp_path / "fresh_music"
	with patch("builtins.input", side_effect=["3", str(new_dir), "s"]):
		cfg = server.run_interactive_wizard(config_path, initial_cfg.copy())
		assert cfg["music_dir"] == str(new_dir.resolve())
		assert new_dir.is_dir()


# ==========================================
# 7. Cover Art Extraction & Cache Sweeping
# ==========================================


def test_extract_cover_art_file(tmp_path):
	"""Verify get_cover_art_uri cleans old covers and extracts pictures/tags."""
	cover_dir = Path(tempfile.gettempdir()) / "carpincho_covers"
	cover_dir.mkdir(parents=True, exist_ok=True)

	# Pre-create >50 dummy covers to test sweeping
	for i in range(55):
		dummy = cover_dir / f"dummy_cover_{i:02d}.jpg"
		dummy.write_text("data")

	# Extract cover on non-existent track
	res = server.get_cover_art_uri(str(tmp_path / "nonexistent.mp3"))
	assert res == ""
	# Sweeping should have pruned down to ~30 files
	remaining = list(cover_dir.glob("dummy_cover_*.jpg"))
	assert len(remaining) <= 35
	# Cleanup
	for f in remaining:
		try:
			f.unlink()
		except Exception:
			pass

	# Extract cover with MutagenFile mock containing pictures
	mock_audio = MagicMock()
	mock_pic = MagicMock()
	mock_pic.data = b"JPEG_IMAGE_DATA_123"
	mock_audio.pictures = [mock_pic]

	with patch("server.MutagenFile", return_value=mock_audio):
		audio_file = tmp_path / "song.flac"
		audio_file.write_bytes(b"FLAC_DATA")
		cover_res = server.get_cover_art_uri(str(audio_file))
		assert cover_res.startswith("file://")
		assert cover_res.endswith(".jpg")

		# Calling again should hit existing file check
		assert server.get_cover_art_uri(str(audio_file)) == cover_res


# ==========================================
# 8. Track Fingerprint & Mood Extraction
# ==========================================


def test_track_extract_fingerprint(small_audio_file):
	"""Verify Track._extract_fingerprint parses output from fpcalc."""
	track = server.Track(small_audio_file)
	with patch("shutil.which", return_value="/usr/bin/fpcalc"):
		with patch("subprocess.run") as mock_run:
			mock_run.return_value = subprocess.CompletedProcess(
				args=[], returncode=0, stdout="DURATION=180\nFINGERPRINT=AQADtHKUZEmiJA0e\n"
			)
			track._extract_fingerprint()
			assert track.fingerprint == "AQADtHKUZEmiJA0e"


def test_track_extract_mood_exceptions(small_audio_file):
	"""Verify Track._extract_mood assigns -1.0 on analysis errors or timeouts."""
	track = server.Track(small_audio_file)
	with (
		patch("server.find_binary", return_value="/usr/bin/ffmpeg"),
		patch("server.extract_audio_features_ffmpeg", return_value=(-1.0, -1.0, -1.0)),
	):
		track._extract_mood()
		assert track.bpm == -1.0
		assert track.energy == -1.0
		assert track.spectral_centroid == -1.0


# ==========================================
# 9. AsyncMpvController Windows IPC & Retry
# ==========================================


async def test_mpv_controller_windows_ipc(tmp_path):
	"""Verify _read_ipc_events_windows and _send on Windows named pipes."""
	pipe_path = tmp_path / "test_mpv_pipe"
	pipe_path.write_bytes(b'{"event": "pause", "data": true}\n')

	controller = server.AsyncMpvController(callbacks={})
	controller.socket_path = str(pipe_path)
	controller.is_windows = True
	proc_mock = MagicMock()
	proc_mock.returncode = None
	controller.process = proc_mock
	assert controller.is_running is True

	# Test _read_ipc_events_windows
	with patch("builtins.open", return_value=io.BytesIO(b'{"event": "pause", "data": true}\n')):
		with patch.object(controller, "_process_event_line"):
			await controller._read_ipc_events_windows()

	# Test _send with Windows pipe write and retry
	with patch("server.asyncio.to_thread") as mock_to_thread:
		mock_to_thread.side_effect = [OSError("Broken pipe"), None]
		with patch.object(controller, "start", AsyncMock()) as mock_start:
			await controller._send('{"command": ["get_property", "volume"]}')
			assert mock_start.called


# ==========================================
# 10. Library Scan with DB Cache
# ==========================================


def test_scan_music_library_uses_cached_entries(temp_db, tmp_path):
	"""Verify scan_music_library reuses cached entries with fingerprint & bpm."""
	music_folder = tmp_path / "music"
	music_folder.mkdir()
	track_file = music_folder / "cached_song.mp3"
	track_file.write_bytes(b"AUDIO_DATA" * 50)

	file_str = str(track_file.resolve())
	stat = track_file.stat()

	# Seed DB with cached metadata
	import sqlite3

	conn = sqlite3.connect(temp_db)
	cur = conn.cursor()
	cur.execute(
		"""
		INSERT INTO tracks (
			track_id, path, title, album, artist,
			duration_str, mtime, file_size, bpm, energy,
			spectral_centroid, fingerprint
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			"track_hash_123",
			file_str,
			"Cached Title",
			"Cached Album",
			"Cached Artist",
			"3:00",
			stat.st_mtime,
			stat.st_size,
			120.0,
			0.75,
			2200.0,
			"fingerprint123",
		),
	)
	conn.commit()
	conn.close()

	with patch("server.find_binary", return_value=None):
		tracks = server.state.scan_directory([str(music_folder)])
		assert len(tracks) == 1
		assert tracks[0]["title"] == "Cached Title"
		assert tracks[0]["bpm"] == 120.0


# ==========================================
# 11. Endpoints & Favicon
# ==========================================


async def test_serve_favicon_etag_and_caching(tmp_path):
	"""Verify serve_favicon returns 304 when ETag matches if-none-match header."""
	fav_file = tmp_path / "favicon.png"
	fav_file.write_bytes(b"PNG_DATA")

	with patch.object(server, "dist_dir", tmp_path):
		# Normal 200 response
		res200 = await server.serve_favicon(None)
		assert res200.status_code == 200

		# Request with matching ETag
		stat = fav_file.stat()
		etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
		req = Request(
			scope={
				"type": "http",
				"method": "GET",
				"headers": [(b"if-none-match", etag.encode("utf-8"))],
			}
		)
		res304 = await server.serve_favicon(req)
		assert res304.status_code == 304


async def test_mpv_hide_and_show_endpoints():
	"""Verify mpv_hide and mpv_show endpoints update state and restart MPV if running."""
	with patch.object(server.AsyncMpvController, "is_running", new_callable=PropertyMock, return_value=True):
		with patch.object(server.state.mpv, "start", AsyncMock()) as mock_start:
			with patch("server.broadcast_state", AsyncMock()):
				hide_res = await server.mpv_hide()
				assert hide_res == {"status": "ok"}
				assert server.state.mpv_visible is False
				assert mock_start.called

				show_res = await server.mpv_show()
				assert show_res == {"status": "ok"}
				assert server.state.mpv_visible is True


async def test_serve_cover_variations(tmp_path):
	"""Verify serve_cover handles APIC, covr, memory caching, and ETag."""
	song_file = tmp_path / "song.mp3"
	song_file.write_bytes(b"DUMMY_MP3")

	stat = song_file.stat()
	path_str = str(song_file)
	etag = f'"{hashlib.md5(f"{path_str}:{int(stat.st_mtime)}:{stat.st_size}".encode()).hexdigest()}"'

	# 1. 304 response with matching If-None-Match
	req = Request(
		scope={
			"type": "http",
			"method": "GET",
			"headers": [(b"if-none-match", etag.encode("utf-8"))],
		}
	)
	res304 = await server.serve_cover(path=str(song_file), request=req)
	assert res304.status_code == 304

	# 2. MutagenFile with APIC tag
	mock_audio = MagicMock()
	mock_tag = MagicMock()
	mock_tag.data = b"\xff\xd8\xffJPEG"
	mock_tag.mime = "image/jpeg"
	mock_audio.tags = {"APIC:Front": mock_tag}
	mock_audio.pictures = []

	server._COVER_MEM_CACHE.clear()
	with patch("server.MutagenFile", return_value=mock_audio):
		res = await server.serve_cover(path=str(song_file), request=None)
		assert res.status_code == 200
		assert res.body == b"\xff\xd8\xffJPEG"

		# Second call hits memory cache
		res_cache = await server.serve_cover(path=str(song_file), request=None)
		assert res_cache.status_code == 200
		assert res_cache.body == b"\xff\xd8\xffJPEG"

	# 3. MutagenFile with covr tag
	mock_audio_covr = MagicMock()
	mock_audio_covr.tags = {"covr": [b"\x89PNG_DATA"]}
	mock_audio_covr.pictures = []
	server._COVER_MEM_CACHE.clear()

	with patch("server.MutagenFile", return_value=mock_audio_covr):
		res_covr = await server.serve_cover(path=str(song_file), request=None)
		assert res_covr.status_code == 200
		assert res_covr.headers["content-type"] == "image/png"


async def test_serve_cover_resizing(tmp_path):
	"""Verify serve_cover resizes images when size is specified and caches them."""
	from PIL import Image

	song_file = tmp_path / "song_resized.mp3"
	song_file.write_bytes(b"DUMMY_AUDIO")

	# Create a 1000x1000 test image
	test_img = Image.new("RGB", (1000, 1000), color=(255, 0, 0))
	buf = io.BytesIO()
	test_img.save(buf, format="JPEG")
	orig_bytes = buf.getvalue()

	mock_audio = MagicMock()
	mock_tag = MagicMock()
	mock_tag.data = orig_bytes
	mock_tag.mime = "image/jpeg"
	mock_audio.tags = {"APIC:Front": mock_tag}
	mock_audio.pictures = []

	server._COVER_MEM_CACHE.clear()
	with patch("server.MutagenFile", return_value=mock_audio):
		# 1. Request resized cover (256px)
		res_256 = await server.serve_cover(path=str(song_file), size=256, request=None)
		assert res_256.status_code == 200
		with Image.open(io.BytesIO(res_256.body)) as im:
			assert im.size == (256, 256)

		# 2. Resized version is cached under path:s=256 and original under path
		assert f"{song_file!s}:s=256" in server._COVER_MEM_CACHE
		assert str(song_file) in server._COVER_MEM_CACHE

		# 3. Request original cover (highest quality, no size)
		res_orig = await server.serve_cover(path=str(song_file), size=None, request=None)
		assert res_orig.status_code == 200
		assert res_orig.body == orig_bytes

		# 4. Request 512px cover - uses the in-memory original
		res_512 = await server.serve_cover(path=str(song_file), size=512, request=None)
		assert res_512.status_code == 200
		with Image.open(io.BytesIO(res_512.body)) as im:
			assert im.size == (512, 512)


async def test_fetch_yt_dlp_metadata(temp_db):
	"""Verify fetch_yt_dlp_metadata runs yt-dlp, parses metadata and saves to DB."""
	state = server.state
	state.url_metadata.clear()
	url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

	# 1. Early return if already cached
	state.url_metadata[url] = {"title": "Cached Song"}
	await state.fetch_yt_dlp_metadata(url)
	assert state.url_metadata[url]["title"] == "Cached Song"

	# 2. Run subprocess and parse JSON
	state.url_metadata.clear()
	mock_proc = AsyncMock()
	fake_dump = json.dumps({"title": "Never Gonna Give You Up", "uploader": "Rick Astley"}).encode("utf-8")
	mock_proc.communicate.return_value = (fake_dump, b"")
	mock_proc.returncode = 0

	with patch("server.find_binary", return_value="/usr/bin/yt-dlp"):
		with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
			with patch("server.broadcast_state", AsyncMock()):
				await state.fetch_yt_dlp_metadata(url)
				assert url in state.url_metadata
				assert state.url_metadata[url]["title"] == "Never Gonna Give You Up"
				assert state.url_metadata[url]["artist"] == "Rick Astley"


async def test_dj_safe_mode_selection_and_pause_after():
	"""Verify DJ safe mode candidate selection and play_next pause_after handling."""
	state = server.state
	state.dj_safe_mode = True
	state.favorites = ["fav1"]
	state.path_to_id = {"/music/fav.mp3": "fav1", "/music/normal.mp3": "norm1"}

	candidates = [
		{"path": "/music/fav.mp3", "title": "Fav"},
		{"path": "/music/normal.mp3", "title": "Normal"},
	]

	# Both favs and normals exist
	chosen = state._select_candidate_dj_track(candidates)
	assert chosen in candidates

	# Only favs exist
	chosen_fav = state._select_candidate_dj_track([candidates[0]])
	assert chosen_fav["path"] == "/music/fav.mp3"

	# Only normals exist
	chosen_norm = state._select_candidate_dj_track([candidates[1]])
	assert chosen_norm["path"] == "/music/normal.mp3"

	# play_next with pause_after_path
	state.current_track = "/music/song1.mp3"
	state.pause_after_path = "/music/song1.mp3"
	state.queue = ["/music/song2.mp3"]

	with patch.object(state, "play_track", AsyncMock()) as mock_play:
		with patch.object(state.mpv, "_send", AsyncMock()) as mock_send:
			await state.play_next()
			assert mock_play.called
			assert state.pause_after_path is None
			assert state.mpv_paused is True
			assert mock_send.called
