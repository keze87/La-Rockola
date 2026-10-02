import io
import json
import tarfile
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

from scripts import ffmpeg_installer


def test_select_best_asset_windows_x86_64():
	assets = [
		{"name": "ffmpeg-master-latest-win32-gpl.zip", "url": "http://example.com/win32.zip"},
		{"name": "ffmpeg-master-latest-win64-gpl.zip", "url": "http://example.com/win64.zip"},
		{"name": "ffmpeg-master-latest-linux64-gpl.tar.xz", "url": "http://example.com/linux64.tar.xz"},
	]
	chosen = ffmpeg_installer.select_best_asset(assets, "windows", "x86_64")
	assert chosen is not None
	assert chosen["name"] == "ffmpeg-master-latest-win64-gpl.zip"


def test_select_best_asset_windows_arm64():
	assets = [
		{"name": "ffmpeg-master-latest-winarm64-gpl.zip", "url": "http://example.com/winarm64.zip"},
		{"name": "ffmpeg-master-latest-win64-gpl.zip", "url": "http://example.com/win64.zip"},
	]
	chosen = ffmpeg_installer.select_best_asset(assets, "windows", "arm64")
	assert chosen is not None
	assert chosen["name"] == "ffmpeg-master-latest-winarm64-gpl.zip"


def test_select_best_asset_linux_x86_64():
	assets = [
		{"name": "ffmpeg-master-latest-linux64-gpl.tar.xz", "url": "http://example.com/linux64.tar.xz"},
		{"name": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz", "url": "http://example.com/linuxarm64.tar.xz"},
	]
	chosen = ffmpeg_installer.select_best_asset(assets, "linux", "x86_64")
	assert chosen is not None
	assert chosen["name"] == "ffmpeg-master-latest-linux64-gpl.tar.xz"


def test_select_best_asset_linux_arm64():
	assets = [
		{"name": "ffmpeg-master-latest-linux64-gpl.tar.xz", "url": "http://example.com/linux64.tar.xz"},
		{"name": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz", "url": "http://example.com/linuxarm64.tar.xz"},
	]
	chosen = ffmpeg_installer.select_best_asset(assets, "linux", "arm64")
	assert chosen is not None
	assert chosen["name"] == "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"


def test_fetch_release_info_api_success():
	fake_data = {
		"tag_name": "latest",
		"assets": [
			{
				"name": "ffmpeg-master-latest-win64-gpl.zip",
				"browser_download_url": "http://test.com/ffmpeg.zip",
				"size": 1024,
			}
		],
	}
	mock_resp = MagicMock()
	mock_resp.read.return_value = json.dumps(fake_data).encode("utf-8")
	mock_resp.__enter__.return_value = mock_resp

	with patch("urllib.request.urlopen", return_value=mock_resp):
		info = ffmpeg_installer.fetch_release_info()
		assert info["tag"] == "latest"
		assert len(info["assets"]) == 1
		assert info["assets"][0]["name"] == "ffmpeg-master-latest-win64-gpl.zip"


def test_fetch_release_info_fallback():
	mock_redirect = MagicMock()
	mock_redirect.geturl.return_value = "https://github.com/yt-dlp/FFmpeg-Builds/releases/tag/latest"
	mock_redirect.__enter__.return_value = mock_redirect

	def fake_urlopen(req, *args, **kwargs):
		if "api.github.com" in req.full_url:
			raise urllib.error.URLError("API Rate Limited")
		return mock_redirect

	with patch("urllib.request.urlopen", side_effect=fake_urlopen):
		info = ffmpeg_installer.fetch_release_info()
		assert any("win64-gpl.zip" in a["name"] for a in info["assets"])


def test_extract_ffmpeg_zip(tmp_path):
	zip_file = tmp_path / "ffmpeg_pkg.zip"
	dest_dir = tmp_path / "extracted"

	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe", b"binary_ffmpeg_exe")
		zf.writestr("ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe", b"binary_ffprobe_exe")
		zf.writestr("ffmpeg-master-latest-win64-gpl/doc/manual.txt", b"documentation")

	success = ffmpeg_installer.extract_ffmpeg_archive(zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "ffmpeg.exe").is_file()
	assert (dest_dir / "ffmpeg.exe").read_bytes() == b"binary_ffmpeg_exe"
	assert (dest_dir / "ffprobe.exe").is_file()
	assert (dest_dir / "ffprobe.exe").read_bytes() == b"binary_ffprobe_exe"


def test_extract_ffmpeg_tar(tmp_path):
	tar_file = tmp_path / "ffmpeg_pkg.tar.gz"
	dest_dir = tmp_path / "extracted_tar"

	with tarfile.open(tar_file, "w:gz") as tf:
		ffmpeg_data = b"binary_ffmpeg_posix"
		ti = tarfile.TarInfo("ffmpeg-master-latest-linux64-gpl/bin/ffmpeg")
		ti.size = len(ffmpeg_data)
		ti.mode = 0o755
		tf.addfile(ti, io.BytesIO(ffmpeg_data))

		ffprobe_data = b"binary_ffprobe_posix"
		ti2 = tarfile.TarInfo("ffmpeg-master-latest-linux64-gpl/bin/ffprobe")
		ti2.size = len(ffprobe_data)
		ti2.mode = 0o755
		tf.addfile(ti2, io.BytesIO(ffprobe_data))

	success = ffmpeg_installer.extract_ffmpeg_archive(tar_file, dest_dir)
	assert success is True
	assert (dest_dir / "ffmpeg").is_file()
	assert (dest_dir / "ffmpeg").read_bytes() == b"binary_ffmpeg_posix"
	assert (dest_dir / "ffprobe").is_file()
	assert (dest_dir / "ffprobe").read_bytes() == b"binary_ffprobe_posix"


def test_extract_ffmpeg_traversal_defense(tmp_path):
	zip_file = tmp_path / "slip.zip"
	dest_dir = tmp_path / "extracted_slip"

	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("../evil.txt", b"evil")
		zf.writestr("bin/ffmpeg.exe", b"safe")

	success = ffmpeg_installer.extract_ffmpeg_archive(zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "ffmpeg.exe").is_file()
	assert not (tmp_path / "evil.txt").exists()


def test_is_rockola_managed(tmp_path):
	managed_dir = tmp_path / "managed"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_ffmpeg").touch()
	bin1 = managed_dir / "ffmpeg"
	bin1.touch()
	assert ffmpeg_installer.is_rockola_managed(bin1) is True

	unmanaged_dir = tmp_path / "sys"
	unmanaged_dir.mkdir()
	bin2 = unmanaged_dir / "ffmpeg"
	bin2.touch()
	assert ffmpeg_installer.is_rockola_managed(bin2) is False


def test_install_ffmpeg_skips_when_exists(tmp_path):
	dest_dir = tmp_path / "bin"
	dest_dir.mkdir()
	bin_file = dest_dir / "ffmpeg.exe"
	bin_file.write_bytes(b"existing")

	with patch("scripts.ffmpeg_installer.download_file") as mock_dl:
		res = ffmpeg_installer.install_ffmpeg(target_dir=dest_dir, platform_name="windows", arch="x86_64", force=False)
		assert res is not None
		assert res == bin_file
		mock_dl.assert_not_called()


def test_install_ffmpeg_full_flow(tmp_path):
	dest_dir = tmp_path / "bin"

	fake_info = {
		"tag": "latest",
		"assets": [
			{
				"name": "ffmpeg-master-latest-win64-gpl.zip",
				"url": "http://fake.url/ffmpeg.zip",
				"size": 100,
			}
		],
	}

	def fake_download(url, dest_path, log_fn=None):
		with zipfile.ZipFile(dest_path, "w") as zf:
			zf.writestr("ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe", b"new_ffmpeg_binary")
			zf.writestr("ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe", b"new_ffprobe_binary")

	with (
		patch("scripts.ffmpeg_installer.fetch_release_info", return_value=fake_info),
		patch("scripts.ffmpeg_installer.download_file", side_effect=fake_download),
	):
		res = ffmpeg_installer.install_ffmpeg(
			target_dir=dest_dir,
			platform_name="windows",
			arch="x86_64",
			force=True,
		)
		assert res is not None
		assert (dest_dir / "ffmpeg.exe").is_file()
		assert (dest_dir / "ffprobe.exe").is_file()
		assert (dest_dir / ".rockola_managed_ffmpeg").is_file()


def test_ensure_ffmpeg_existing(tmp_path):
	fake_bin = str(tmp_path / "ffmpeg")
	with patch("server.find_binary", return_value=fake_bin):
		res = ffmpeg_installer.ensure_ffmpeg()
		assert res == fake_bin


def test_ensure_ffmpeg_installs_when_missing(tmp_path):
	fake_bin = tmp_path / "ffmpeg.exe"
	fake_bin.write_bytes(b"dummy")

	with (
		patch("server.find_binary", return_value=None),
		patch("shutil.which", return_value=None),
		patch("scripts.ffmpeg_installer.install_ffmpeg", return_value=fake_bin),
	):
		res = ffmpeg_installer.ensure_ffmpeg()
		assert res == str(fake_bin)


def test_check_dependencies_installs_ffmpeg_on_windows(monkeypatch, tmp_path):
	"""Test check_dependencies triggers ffmpeg installation when missing on Windows."""
	import sys

	import server

	monkeypatch.setattr(server, "_dependencies_checked", False)
	monkeypatch.setattr(sys, "platform", "win32")

	fake_bin = tmp_path / "ffmpeg.exe"

	def fake_find(bin_name):
		if bin_name in ("mpv", "yt-dlp", "fpcalc"):
			return f"/usr/bin/{bin_name}"
		if bin_name == "ffmpeg":
			return None
		return None

	monkeypatch.setattr(server, "find_binary", fake_find)
	monkeypatch.setattr("server.importlib.util.find_spec", lambda mod: True)

	with (
		patch("scripts.ffmpeg_installer.install_ffmpeg", return_value=fake_bin) as mock_install,
		patch("scripts.fpcalc_installer.install_fpcalc") as mock_fpcalc,
		patch("scripts.mpv_installer.install_mpv"),
		patch("scripts.ytdlp_installer.install_ytdlp"),
	):
		server.check_dependencies(force=True)
		mock_install.assert_called_once()
		mock_fpcalc.assert_not_called()
