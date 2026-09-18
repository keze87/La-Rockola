import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server
from scripts import ytdlp_installer


def test_get_ytdlp_asset_name():
	assert ytdlp_installer.get_ytdlp_asset_name("windows", "x86_64") == "yt-dlp.exe"
	assert ytdlp_installer.get_ytdlp_asset_name("windows", "arm64") == "yt-dlp_arm64.exe"
	assert ytdlp_installer.get_ytdlp_asset_name("windows", "i686") == "yt-dlp_x86.exe"
	assert ytdlp_installer.get_ytdlp_asset_name("macos", "arm64") == "yt-dlp_macos"
	assert ytdlp_installer.get_ytdlp_asset_name("linux", "x86_64") == "yt-dlp"


def test_get_ytdlp_download_url():
	url = ytdlp_installer.get_ytdlp_download_url("windows", "x86_64")
	assert url == "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


def test_install_ytdlp(tmp_path):
	dest_dir = tmp_path / "bin"

	def fake_download(url, dest_path, log_fn=None):
		dest_path.parent.mkdir(parents=True, exist_ok=True)
		dest_path.write_text("fake yt-dlp binary")

	with patch("scripts.ytdlp_installer.download_file", side_effect=fake_download):
		res = ytdlp_installer.install_ytdlp(target_dir=dest_dir, platform_name="windows", arch="x86_64")
		assert res is not None
		assert res.name == "yt-dlp.exe"
		assert res.is_file()


def test_install_ytdlp_skips_when_already_installed(tmp_path):
	dest_dir = tmp_path / "bin"
	dest_dir.mkdir(parents=True, exist_ok=True)
	existing_bin = dest_dir / "yt-dlp.exe"
	existing_bin.write_text("existing binary content")

	with patch("scripts.ytdlp_installer.download_file") as mock_download:
		res = ytdlp_installer.install_ytdlp(target_dir=dest_dir, platform_name="windows", arch="x86_64", force=False)
		assert res == existing_bin
		mock_download.assert_not_called()


def test_install_ytdlp_reinstalls_when_force(tmp_path):
	dest_dir = tmp_path / "bin"
	dest_dir.mkdir(parents=True, exist_ok=True)
	existing_bin = dest_dir / "yt-dlp.exe"
	existing_bin.write_text("old content")

	def fake_download(url, dest_path, log_fn=None):
		dest_path.write_text("new content")

	with patch("scripts.ytdlp_installer.download_file", side_effect=fake_download) as mock_download:
		res = ytdlp_installer.install_ytdlp(target_dir=dest_dir, platform_name="windows", arch="x86_64", force=True)
		assert res == existing_bin
		mock_download.assert_called_once()
		assert existing_bin.read_text() == "new content"


def test_ensure_ytdlp_existing():
	with patch("server.find_binary", return_value="/usr/bin/yt-dlp"):
		res = ytdlp_installer.ensure_ytdlp()
		assert res == "/usr/bin/yt-dlp"


def test_ensure_ytdlp_installs_when_missing(tmp_path):
	fake_bin = tmp_path / "yt-dlp.exe"
	fake_bin.write_text("dummy")

	with (
		patch("server.find_binary", return_value=None),
		patch("shutil.which", return_value=None),
		patch("scripts.ytdlp_installer.install_ytdlp", return_value=fake_bin),
	):
		res = ytdlp_installer.ensure_ytdlp()
		assert res == str(fake_bin)


def test_get_default_install_dir_uses_mpv_dir(tmp_path):
	fake_mpv = tmp_path / "mpv_folder" / "mpv.exe"
	fake_mpv.parent.mkdir(parents=True, exist_ok=True)
	fake_mpv.write_text("mpv")

	with patch("server.find_binary", return_value=str(fake_mpv)):
		target_dir = ytdlp_installer.get_default_install_dir()
		assert target_dir == fake_mpv.parent


def test_is_rockola_managed(tmp_path):
	# Case 1: Has explicit marker
	managed_dir = tmp_path / "managed"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_ytdlp").touch()
	bin1 = managed_dir / "yt-dlp"
	bin1.touch()
	assert ytdlp_installer.is_rockola_managed(bin1) is True

	# Case 2: External system binary without marker
	sys_dir = tmp_path / "usr" / "bin"
	sys_dir.mkdir(parents=True)
	bin2 = sys_dir / "yt-dlp"
	bin2.touch()
	assert ytdlp_installer.is_rockola_managed(bin2) is False


def test_update_ytdlp_success(tmp_path):
	fake_bin = tmp_path / "yt-dlp"
	fake_bin.write_text("dummy")
	# Mark as managed by Rockola
	(tmp_path / ".rockola_managed_ytdlp").touch()

	with patch("subprocess.run") as mock_run:
		mock_run.return_value = MagicMock(returncode=0, stdout="Updated", stderr="")
		ok = ytdlp_installer.update_ytdlp(bin_path=str(fake_bin))
		assert ok is True
		mock_run.assert_called_once()
		assert mock_run.call_args[0][0] == [str(fake_bin), "-U"]


def test_update_ytdlp_skips_unmanaged(tmp_path):
	fake_bin = tmp_path / "system_bin" / "yt-dlp"
	fake_bin.parent.mkdir()
	fake_bin.write_text("system binary")

	with patch("subprocess.run") as mock_run:
		ok = ytdlp_installer.update_ytdlp(bin_path=str(fake_bin))
		assert ok is False
		mock_run.assert_not_called()


def test_update_ytdlp_not_found():
	with patch("server.find_binary", return_value=None), patch("shutil.which", return_value=None):
		ok = ytdlp_installer.update_ytdlp(bin_path=None)
		assert ok is False


@pytest.mark.asyncio
async def test_fetch_yt_dlp_metadata_invokes_ensure_ytdlp(tmp_path):
	"""Test fetch_yt_dlp_metadata triggers ensure_ytdlp when binary is missing."""
	app_state = server.APIState()
	fake_bin = str(tmp_path / "yt-dlp")

	# find_binary returns None first
	with (
		patch("server.find_binary", return_value=None),
		patch("scripts.ytdlp_installer.ensure_ytdlp", return_value=fake_bin) as mock_ensure,
		patch("asyncio.create_subprocess_exec") as mock_exec,
	):
		mock_proc = AsyncMock()
		mock_proc.communicate.return_value = (
			b'{"title": "Test Song", "uploader": "Test Artist", "duration": 180}',
			b"",
		)
		mock_exec.return_value = mock_proc

		await app_state.fetch_yt_dlp_metadata("https://www.youtube.com/watch?v=12345")
		mock_ensure.assert_called_once()
		assert mock_exec.call_args[0][0] == fake_bin


def test_check_dependencies_installs_ytdlp_on_windows(monkeypatch, tmp_path):
	"""Test check_dependencies triggers ytdlp installation when missing on Windows."""
	monkeypatch.setattr(server, "_dependencies_checked", False)
	monkeypatch.setattr(sys, "platform", "win32")

	fake_bin = tmp_path / "yt-dlp.exe"

	def fake_find(bin_name):
		if bin_name == "mpv":
			return "/usr/bin/mpv"
		if bin_name == "yt-dlp":
			return None
		return None

	monkeypatch.setattr(server, "find_binary", fake_find)
	monkeypatch.setattr("server.importlib.util.find_spec", lambda mod: True)

	with patch("scripts.ytdlp_installer.install_ytdlp", return_value=fake_bin) as mock_install:
		server.check_dependencies(force=True)
		mock_install.assert_called_once()


def test_find_binary_in_python_scripts(monkeypatch, tmp_path):
	"""Test find_binary discovers binaries located in Python's Scripts/ directory."""
	fake_scripts = tmp_path / "Scripts"
	fake_scripts.mkdir()
	fake_ytdlp = fake_scripts / "yt-dlp.exe"
	fake_ytdlp.touch()

	monkeypatch.setattr(sys, "prefix", str(tmp_path))
	monkeypatch.setattr(sys, "platform", "win32")
	monkeypatch.setattr("shutil.which", lambda name: None)

	found = server.find_binary("yt-dlp")
	assert found == str(fake_ytdlp)


def test_find_binary_in_scoop_shims(monkeypatch, tmp_path):
	"""Test find_binary discovers binaries located in Scoop shims."""
	fake_env = tmp_path / "dummy_env"
	fake_env.mkdir()
	monkeypatch.setattr(sys, "prefix", str(fake_env))
	monkeypatch.setattr(sys, "exec_prefix", str(fake_env))
	monkeypatch.setattr(sys, "executable", str(fake_env / "python.exe"))

	fake_shims = tmp_path / "scoop" / "shims"
	fake_shims.mkdir(parents=True)
	fake_ytdlp = fake_shims / "yt-dlp.exe"
	fake_ytdlp.touch()

	monkeypatch.setattr(Path, "home", lambda: tmp_path)
	monkeypatch.setattr(sys, "platform", "win32")
	monkeypatch.setattr("shutil.which", lambda name: None)

	found = server.find_binary("yt-dlp")
	assert found == str(fake_ytdlp)


def test_find_binary_next_to_mpv(monkeypatch, tmp_path):
	"""Test find_binary discovers yt-dlp in the same directory as mpv."""
	fake_env = tmp_path / "dummy_env"
	fake_env.mkdir()
	monkeypatch.setattr(sys, "prefix", str(fake_env))
	monkeypatch.setattr(sys, "exec_prefix", str(fake_env))
	monkeypatch.setattr(sys, "executable", str(fake_env / "python.exe"))
	monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")

	fake_mpv_dir = tmp_path / "custom_mpv"
	fake_mpv_dir.mkdir()
	fake_mpv = fake_mpv_dir / "mpv.exe"
	fake_mpv.touch()
	fake_ytdlp = fake_mpv_dir / "yt-dlp.exe"
	fake_ytdlp.touch()

	monkeypatch.setattr(sys, "platform", "win32")
	# shutil.which finds mpv, but not yt-dlp
	monkeypatch.setattr("shutil.which", lambda name: str(fake_mpv) if "mpv" in name else None)

	found = server.find_binary("yt-dlp")
	assert found == str(fake_ytdlp)

