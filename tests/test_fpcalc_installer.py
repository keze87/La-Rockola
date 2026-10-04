import io
import json
import tarfile
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

from scripts import fpcalc_installer


def test_select_best_asset_windows_x86_64():
	assets = [
		{"name": "chromaprint-fpcalc-1.6.1-linux-x86_64.tar.gz", "url": "http://example.com/linux.tar.gz"},
		{"name": "chromaprint-fpcalc-1.6.1-windows-x86_64.zip", "url": "http://example.com/win.zip"},
		{"name": "chromaprint-fpcalc-1.6.1-macos-universal.tar.gz", "url": "http://example.com/mac.tar.gz"},
	]
	chosen = fpcalc_installer.select_best_asset(assets, "windows", "x86_64")
	assert chosen is not None
	assert chosen["name"] == "chromaprint-fpcalc-1.6.1-windows-x86_64.zip"


def test_select_best_asset_linux_x86_64():
	assets = [
		{"name": "chromaprint-fpcalc-1.6.1-linux-arm64.tar.gz", "url": "http://example.com/arm64.tar.gz"},
		{"name": "chromaprint-fpcalc-1.6.1-linux-x86_64.tar.gz", "url": "http://example.com/linux64.tar.gz"},
	]
	chosen = fpcalc_installer.select_best_asset(assets, "linux", "x86_64")
	assert chosen is not None
	assert chosen["name"] == "chromaprint-fpcalc-1.6.1-linux-x86_64.tar.gz"


def test_select_best_asset_linux_arm64():
	assets = [
		{"name": "chromaprint-fpcalc-1.6.1-linux-arm64.tar.gz", "url": "http://example.com/arm64.tar.gz"},
		{"name": "chromaprint-fpcalc-1.6.1-linux-x86_64.tar.gz", "url": "http://example.com/linux64.tar.gz"},
	]
	chosen = fpcalc_installer.select_best_asset(assets, "linux", "arm64")
	assert chosen is not None
	assert chosen["name"] == "chromaprint-fpcalc-1.6.1-linux-arm64.tar.gz"


def test_select_best_asset_macos_arm64():
	assets = [
		{"name": "chromaprint-fpcalc-1.6.1-macos-x86_64.tar.gz", "url": "http://example.com/mac-x64.tar.gz"},
		{"name": "chromaprint-fpcalc-1.6.1-macos-arm64.tar.gz", "url": "http://example.com/mac-arm.tar.gz"},
	]
	chosen = fpcalc_installer.select_best_asset(assets, "macos", "arm64")
	assert chosen is not None
	assert "arm64" in chosen["name"]


def test_fetch_release_info_api_success():
	fake_data = {
		"tag_name": "v1.6.1",
		"assets": [
			{
				"name": "chromaprint-fpcalc-1.6.1-windows-x86_64.zip",
				"browser_download_url": "http://test.com/fpcalc.zip",
				"size": 1024,
			}
		],
	}
	mock_resp = MagicMock()
	mock_resp.read.return_value = json.dumps(fake_data).encode("utf-8")
	mock_resp.__enter__.return_value = mock_resp

	with patch("urllib.request.urlopen", return_value=mock_resp):
		info = fpcalc_installer.fetch_release_info()
		assert info["tag"] == "v1.6.1"
		assert len(info["assets"]) == 1
		assert info["assets"][0]["name"] == "chromaprint-fpcalc-1.6.1-windows-x86_64.zip"


def test_fetch_release_info_fallback():
	mock_redirect = MagicMock()
	mock_redirect.geturl.return_value = "https://github.com/acoustid/chromaprint/releases/tag/v1.6.1"
	mock_redirect.__enter__.return_value = mock_redirect

	def fake_urlopen(req, *args, **kwargs):
		if "api.github.com" in req.full_url:
			raise urllib.error.URLError("API Rate Limited")
		return mock_redirect

	with patch("urllib.request.urlopen", side_effect=fake_urlopen):
		info = fpcalc_installer.fetch_release_info()
		assert info["tag"] == "v1.6.1"
		assert any("windows-x86_64.zip" in a["name"] for a in info["assets"])


def test_extract_fpcalc_zip(tmp_path):
	zip_file = tmp_path / "fpcalc_pkg.zip"
	dest_dir = tmp_path / "extracted"

	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("chromaprint-fpcalc-1.6.1-windows-x86_64/fpcalc.exe", b"binary_fpcalc_exe")
		zf.writestr("chromaprint-fpcalc-1.6.1-windows-x86_64/README.txt", b"readme text")

	success = fpcalc_installer.extract_fpcalc_archive(zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "fpcalc.exe").is_file()
	assert (dest_dir / "fpcalc.exe").read_bytes() == b"binary_fpcalc_exe"


def test_extract_fpcalc_tar_gz(tmp_path):
	tar_file = tmp_path / "fpcalc_pkg.tar.gz"
	dest_dir = tmp_path / "extracted_tar"

	with tarfile.open(tar_file, "w:gz") as tf:
		data = b"binary_fpcalc_posix"
		ti = tarfile.TarInfo("chromaprint-fpcalc-1.6.1-linux-x86_64/fpcalc")
		ti.size = len(data)
		ti.mode = 0o755
		tf.addfile(ti, io.BytesIO(data))

	success = fpcalc_installer.extract_fpcalc_archive(tar_file, dest_dir)
	assert success is True
	assert (dest_dir / "fpcalc").is_file()
	assert (dest_dir / "fpcalc").read_bytes() == b"binary_fpcalc_posix"


def test_extract_fpcalc_traversal_defense(tmp_path):
	zip_file = tmp_path / "slip.zip"
	dest_dir = tmp_path / "extracted_slip"

	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("../evil.txt", b"evil")
		zf.writestr("chromaprint-fpcalc/fpcalc.exe", b"safe")

	success = fpcalc_installer.extract_fpcalc_archive(zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "fpcalc.exe").is_file()
	assert not (tmp_path / "evil.txt").exists()


def test_is_rockola_managed(tmp_path):
	managed_dir = tmp_path / "managed"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_fpcalc").touch()
	bin1 = managed_dir / "fpcalc"
	bin1.touch()
	assert fpcalc_installer.is_rockola_managed(bin1) is True

	unmanaged_dir = tmp_path / "sys"
	unmanaged_dir.mkdir()
	bin2 = unmanaged_dir / "fpcalc"
	bin2.touch()
	assert fpcalc_installer.is_rockola_managed(bin2) is False


def test_install_fpcalc_skips_when_exists(tmp_path):
	dest_dir = tmp_path / "bin"
	dest_dir.mkdir()
	bin_file = dest_dir / "fpcalc.exe"
	bin_file.write_bytes(b"existing")

	with patch("scripts.fpcalc_installer.download_file") as mock_dl:
		res = fpcalc_installer.install_fpcalc(target_dir=dest_dir, platform_name="windows", arch="x86_64", force=False)
		assert res is not None
		assert res == bin_file
		mock_dl.assert_not_called()


def test_install_fpcalc_full_flow(tmp_path):
	dest_dir = tmp_path / "bin"

	fake_info = {
		"tag": "v1.6.1",
		"assets": [
			{
				"name": "chromaprint-fpcalc-1.6.1-windows-x86_64.zip",
				"url": "http://fake.url/fpcalc.zip",
				"size": 100,
			}
		],
	}

	def fake_download(url, dest_path, log_fn=None):
		with zipfile.ZipFile(dest_path, "w") as zf:
			zf.writestr("chromaprint-fpcalc-1.6.1-windows-x86_64/fpcalc.exe", b"new_fpcalc_binary")

	with (
		patch("scripts.fpcalc_installer.fetch_release_info", return_value=fake_info),
		patch("scripts.fpcalc_installer.download_file", side_effect=fake_download),
	):
		res = fpcalc_installer.install_fpcalc(
			target_dir=dest_dir,
			platform_name="windows",
			arch="x86_64",
			force=True,
		)
		assert res is not None
		assert (dest_dir / "fpcalc.exe").is_file()
		assert (dest_dir / ".rockola_managed_fpcalc").is_file()


def test_ensure_fpcalc_existing(tmp_path):
	fake_bin = str(tmp_path / "fpcalc")
	with patch("server.find_binary", return_value=fake_bin):
		res = fpcalc_installer.ensure_fpcalc()
		assert res == fake_bin


def test_ensure_fpcalc_installs_when_missing(tmp_path):
	fake_bin = tmp_path / "fpcalc.exe"
	fake_bin.write_bytes(b"dummy")

	with (
		patch("server.find_binary", return_value=None),
		patch("shutil.which", return_value=None),
		patch("scripts.fpcalc_installer.install_fpcalc", return_value=fake_bin),
	):
		res = fpcalc_installer.ensure_fpcalc()
		assert res == str(fake_bin)


def test_check_dependencies_installs_fpcalc_on_windows(monkeypatch, tmp_path):
	"""Test check_dependencies triggers fpcalc installation when missing on Windows."""
	import sys

	import server

	monkeypatch.setattr(server, "_dependencies_checked", False)
	monkeypatch.setattr(sys, "platform", "win32")

	fake_bin = tmp_path / "fpcalc.exe"

	def fake_find(bin_name):
		if bin_name in ("mpv", "yt-dlp", "ffmpeg"):
			return f"/usr/bin/{bin_name}"
		if bin_name == "fpcalc":
			return None
		return None

	monkeypatch.setattr(server, "find_binary", fake_find)
	monkeypatch.setattr("app.engine.audio_analysis.find_binary", fake_find)
	monkeypatch.setattr("server.importlib.util.find_spec", lambda mod: True)

	with (
		patch("scripts.fpcalc_installer.install_fpcalc", return_value=fake_bin) as mock_install,
		patch("scripts.ffmpeg_installer.install_ffmpeg") as mock_ffmpeg,
		patch("scripts.mpv_installer.install_mpv"),
		patch("scripts.ytdlp_installer.install_ytdlp"),
	):
		server.check_dependencies(force=True)
		mock_install.assert_called_once()
		mock_ffmpeg.assert_not_called()
