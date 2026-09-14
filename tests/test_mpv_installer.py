import io
import json
import os
import sys
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

import mpv_installer
import server


def test_resolve_platform_and_arch_explicit():
	plat, arch = mpv_installer.resolve_platform_and_arch("windows", "x86_64")
	assert plat == "windows"
	assert arch == "x86_64"

	plat2, arch2 = mpv_installer.resolve_platform_and_arch("darwin", "arm64")
	assert plat2 == "darwin"
	assert arch2 == "arm64"


def test_resolve_platform_and_arch_detected(monkeypatch):
	monkeypatch.setattr(sys, "platform", "win32")
	monkeypatch.setattr(os, "name", "nt")
	monkeypatch.setattr(mpv_installer.platform, "machine", lambda: "AMD64")

	plat, arch = mpv_installer.resolve_platform_and_arch()
	assert plat == "windows"
	assert arch == "x86_64"


def test_select_best_asset_windows_x86_64():
	assets = [
		{"name": "mpv-v0.41.0-x86_64-pc-windows-msvc.zip", "url": "http://example.com/msvc.zip"},
		{"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip", "url": "http://example.com/mingw.zip"},
		{"name": "mpv-v0.41.0-i686-w64-mingw32.zip", "url": "http://example.com/i686.zip"},
	]
	chosen = mpv_installer.select_best_asset(assets, "windows", "x86_64")
	assert chosen is not None
	assert chosen["name"] == "mpv-v0.41.0-x86_64-w64-mingw32.zip"


def test_select_best_asset_windows_arm64():
	assets = [
		{"name": "mpv-v0.41.0-aarch64-pc-windows-msvc.zip", "url": "http://example.com/arm64.zip"},
		{"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip", "url": "http://example.com/mingw.zip"},
	]
	chosen = mpv_installer.select_best_asset(assets, "windows", "arm64")
	assert chosen is not None
	assert chosen["name"] == "mpv-v0.41.0-aarch64-pc-windows-msvc.zip"


def test_select_best_asset_macos():
	assets = [
		{"name": "mpv-v0.41.0-macos-15-arm.zip", "url": "http://example.com/arm.zip"},
		{"name": "mpv-v0.41.0-macos-15-intel.zip", "url": "http://example.com/intel.zip"},
	]
	chosen_arm = mpv_installer.select_best_asset(assets, "macos", "arm64")
	assert chosen_arm is not None
	assert "arm" in chosen_arm["name"]

	chosen_intel = mpv_installer.select_best_asset(assets, "macos", "x86_64")
	assert chosen_intel is not None
	assert "intel" in chosen_intel["name"]


def test_select_best_asset_unsupported():
	assets = [{"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip", "url": "http://example.com/mingw.zip"}]
	assert mpv_installer.select_best_asset(assets, "linux", "x86_64") is None


def test_fetch_release_info_api_success():
	fake_response_data = {
		"tag_name": "v0.41.0",
		"assets": [
			{"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip", "browser_download_url": "http://test.com/mpv.zip", "size": 100}
		],
	}

	mock_resp = MagicMock()
	mock_resp.read.return_value = json.dumps(fake_response_data).encode("utf-8")
	mock_resp.__enter__.return_value = mock_resp

	with patch("urllib.request.urlopen", return_value=mock_resp):
		info = mpv_installer.fetch_release_info()
		assert info["tag"] == "v0.41.0"
		assert len(info["assets"]) == 1
		assert info["assets"][0]["name"] == "mpv-v0.41.0-x86_64-w64-mingw32.zip"


def test_fetch_release_info_fallback_redirect():
	# API call raises error, redirect fallback succeeds
	mock_redirect_resp = MagicMock()
	mock_redirect_resp.geturl.return_value = "https://github.com/mpv-player/mpv/releases/tag/v0.42.0"
	mock_redirect_resp.__enter__.return_value = mock_redirect_resp

	def fake_urlopen(req, *args, **kwargs):
		if "api.github.com" in req.full_url:
			raise urllib.error.HTTPError(req.full_url, 403, "Rate Limit", {}, None)
		return mock_redirect_resp

	with patch("urllib.request.urlopen", side_effect=fake_urlopen):
		info = mpv_installer.fetch_release_info()
		assert info["tag"] == "v0.42.0"
		assert any("mingw32" in a["name"] for a in info["assets"])


def test_extract_mpv_zip_flat(tmp_path):
	zip_file = tmp_path / "test_flat.zip"
	dest_dir = tmp_path / "extracted_flat"

	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("mpv.exe", "fake_exe_content")
		zf.writestr("mpv.pdb", "huge_pdb_content")
		zf.writestr("vulkan-1.dll", "dll_content")

	success = mpv_installer.extract_mpv_zip(zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "mpv.exe").is_file()
	assert (dest_dir / "vulkan-1.dll").is_file()
	# .pdb must be excluded
	assert not (dest_dir / "mpv.pdb").exists()


def test_extract_mpv_zip_nested(tmp_path):
	inner_zip_bytes = io.BytesIO()
	with zipfile.ZipFile(inner_zip_bytes, "w") as izf:
		izf.writestr("mpv.exe", "inner_exe_content")
		izf.writestr("avcodec-62.dll", "dll_content")
		izf.writestr("debug.pdb", "pdb_content")

	outer_zip_file = tmp_path / "test_nested.zip"
	with zipfile.ZipFile(outer_zip_file, "w") as ozf:
		ozf.writestr("mpv-git-2025-x86_64.zip", inner_zip_bytes.getvalue())

	dest_dir = tmp_path / "extracted_nested"
	success = mpv_installer.extract_mpv_zip(outer_zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "mpv.exe").is_file()
	assert (dest_dir / "avcodec-62.dll").is_file()
	assert not (dest_dir / "debug.pdb").exists()


def test_extract_mpv_zip_traversal_defense(tmp_path):
	zip_file = tmp_path / "test_slip.zip"
	dest_dir = tmp_path / "extracted_slip"

	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("../evil.txt", "evil_content")
		zf.writestr("mpv.exe", "safe_exe")

	success = mpv_installer.extract_mpv_zip(zip_file, dest_dir)
	assert success is True
	assert (dest_dir / "mpv.exe").is_file()
	assert not (tmp_path / "evil.txt").exists()


def test_ensure_mpv_already_exists(tmp_path):
	dest_dir = tmp_path / "mpv_dir"
	dest_dir.mkdir()
	(dest_dir / "mpv.exe").write_text("existing")

	with patch("mpv_installer.install_mpv") as mock_install:
		res = mpv_installer.ensure_mpv(target_dir=dest_dir)
		assert res == dest_dir
		mock_install.assert_not_called()


def test_install_mpv_unsupported_platform():
	res = mpv_installer.install_mpv(platform_name="linux")
	assert res is None


def test_install_mpv_full_flow(tmp_path):
	dest_dir = tmp_path / "mpv_install"

	# Mock release info
	fake_info = {
		"tag": "v0.41.0",
		"assets": [
			{"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip", "url": "http://fake.url/mpv.zip", "size": 100}
		],
	}

	def fake_download(url, dest_path, log_fn=None):
		with zipfile.ZipFile(dest_path, "w") as zf:
			zf.writestr("mpv.exe", "fake_binary")
			zf.writestr("avutil.dll", "dll_binary")

	with patch("mpv_installer.fetch_release_info", return_value=fake_info), patch(
		"mpv_installer.download_asset", side_effect=fake_download
	):
		res = mpv_installer.install_mpv(
			target_dir=dest_dir,
			platform_name="windows",
			arch="x86_64",
		)
		assert res == dest_dir
		assert (dest_dir / "mpv.exe").is_file()


def test_server_check_dependencies_triggers_mpv_install(monkeypatch, tmp_path):
	"""Test that check_dependencies attempts to install MPV when missing on Windows."""
	monkeypatch.setattr(server, "_dependencies_checked", False)
	monkeypatch.setattr(sys, "platform", "win32")

	# find_binary returns None first, but after install it returns the new path
	call_count = 0
	fake_mpv = tmp_path / "mpv" / "mpv.exe"

	def fake_find(bin_name):
		nonlocal call_count
		if bin_name == "mpv":
			call_count += 1
			if call_count > 1:
				return str(fake_mpv)
		return None

	monkeypatch.setattr(server, "find_binary", fake_find)
	monkeypatch.setattr("server.importlib.util.find_spec", lambda mod: True)

	with patch("mpv_installer.install_mpv", return_value=fake_mpv.parent) as mock_install, patch(
		"sys.exit"
	) as mock_exit:
		server.check_dependencies(force=True)
		mock_install.assert_called_once()
		mock_exit.assert_not_called()
