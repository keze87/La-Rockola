import io
import json
import os
import sys
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

from scripts import mpv_installer
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
			{
				"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip",
				"browser_download_url": "http://test.com/mpv.zip",
				"size": 100,
			}
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

	with patch("scripts.mpv_installer.install_mpv") as mock_install:
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
		"assets": [{"name": "mpv-v0.41.0-x86_64-w64-mingw32.zip", "url": "http://fake.url/mpv.zip", "size": 100}],
	}

	def fake_download(url, dest_path, log_fn=None):
		with zipfile.ZipFile(dest_path, "w") as zf:
			zf.writestr("mpv.exe", "fake_binary")
			zf.writestr("avutil.dll", "dll_binary")

	with (
		patch("scripts.mpv_installer.fetch_release_info", return_value=fake_info),
		patch("scripts.mpv_installer.download_asset", side_effect=fake_download),
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

	with (
		patch("scripts.mpv_installer.install_mpv", return_value=fake_mpv.parent) as mock_install,
		patch("sys.exit") as mock_exit,
	):
		server.check_dependencies(force=True)
		mock_install.assert_called_once()
		mock_exit.assert_not_called()


def test_parse_version():
	assert mpv_installer._parse_version("v0.41.0") == (0, 41, 0)
	assert mpv_installer._parse_version("0.38.1") == (0, 38, 1)
	assert mpv_installer._parse_version("v0.42") == (0, 42)
	assert mpv_installer._parse_version("") == (0,)
	assert mpv_installer._parse_version(None) == (0,)


def test_get_installed_mpv_version_success(tmp_path):
	fake_bin = tmp_path / "mpv"
	fake_bin.write_text("binary")

	mock_proc = MagicMock()
	mock_proc.stdout = "mpv v0.41.0-w64 Copyright (C) 2000-2025 mpv/MPlayer/mplayer2 projects"
	mock_proc.stderr = ""
	mock_proc.returncode = 0

	with patch("subprocess.run", return_value=mock_proc):
		ver = mpv_installer.get_installed_mpv_version(fake_bin)
		assert ver == "0.41.0"


def test_get_installed_mpv_version_missing_or_error(tmp_path):
	assert mpv_installer.get_installed_mpv_version(tmp_path / "nonexistent") is None

	fake_bin = tmp_path / "mpv"
	fake_bin.write_text("binary")
	with patch("subprocess.run", side_effect=OSError("Exec error")):
		assert mpv_installer.get_installed_mpv_version(fake_bin) is None


def test_is_rockola_managed(tmp_path):
	# Path with .rockola_managed_mpv
	managed_dir = tmp_path / "my_rockola_mpv"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_mpv").touch()
	bin_path = managed_dir / "mpv.exe"
	bin_path.touch()

	assert mpv_installer.is_rockola_managed(bin_path) is True
	assert mpv_installer.is_rockola_managed(managed_dir) is True

	# External path without marker
	external_dir = tmp_path / "external_bin"
	external_dir.mkdir()
	external_bin = external_dir / "mpv"
	external_bin.touch()
	assert mpv_installer.is_rockola_managed(external_bin) is False


def test_update_mpv_skips_unmanaged(tmp_path):
	external_bin = tmp_path / "system_mpv" / "mpv"
	external_bin.parent.mkdir()
	external_bin.touch()

	logged = []
	res = mpv_installer.update_mpv(bin_path=external_bin, log_fn=logged.append)
	assert res is False
	assert any("externa" in m for m in logged)


def test_update_mpv_cooldown(tmp_path, monkeypatch):
	monkeypatch.setattr(mpv_installer, "resolve_platform_and_arch", lambda *a: ("windows", "x86_64"))
	managed_dir = tmp_path / "mpv"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_mpv").touch()
	fake_bin = managed_dir / "mpv.exe"
	fake_bin.touch()

	import time

	(managed_dir / ".last_mpv_update_check").write_text(str(time.time()))

	with patch("scripts.mpv_installer.fetch_release_info") as mock_fetch:
		# Within cooldown, force=False -> returns True immediately without network call
		assert mpv_installer.update_mpv(bin_path=fake_bin, force=False) is True
		mock_fetch.assert_not_called()

		# force=True -> bypasses cooldown and calls fetch_release_info
		mock_fetch.return_value = {"tag": "v0.41.0", "assets": []}
		with patch("scripts.mpv_installer.get_installed_mpv_version", return_value="0.41.0"):
			assert mpv_installer.update_mpv(bin_path=fake_bin, force=True) is True
			mock_fetch.assert_called_once()


def test_update_mpv_already_up_to_date(tmp_path, monkeypatch):
	monkeypatch.setattr(mpv_installer, "resolve_platform_and_arch", lambda *a: ("windows", "x86_64"))
	managed_dir = tmp_path / "mpv"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_mpv").touch()
	fake_bin = managed_dir / "mpv.exe"
	fake_bin.touch()

	with (
		patch("scripts.mpv_installer.get_installed_mpv_version", return_value="0.41.0"),
		patch("scripts.mpv_installer.fetch_release_info", return_value={"tag": "v0.41.0", "assets": []}),
		patch("scripts.mpv_installer.install_mpv") as mock_install,
	):
		res = mpv_installer.update_mpv(bin_path=fake_bin, force=True)
		assert res is True
		mock_install.assert_not_called()


def test_update_mpv_triggers_install_on_newer_version(tmp_path, monkeypatch):
	monkeypatch.setattr(mpv_installer, "resolve_platform_and_arch", lambda *a: ("windows", "x86_64"))
	managed_dir = tmp_path / "mpv"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_mpv").touch()
	fake_bin = managed_dir / "mpv.exe"
	fake_bin.touch()

	with (
		patch("scripts.mpv_installer.get_installed_mpv_version", return_value="0.40.0"),
		patch("scripts.mpv_installer.fetch_release_info", return_value={"tag": "v0.41.0", "assets": []}),
		patch("scripts.mpv_installer.install_mpv", return_value=managed_dir) as mock_install,
	):
		res = mpv_installer.update_mpv(bin_path=fake_bin, force=True)
		assert res is True
		mock_install.assert_called_once_with(target_dir=managed_dir, log_fn=mpv_installer.default_logger)


def test_server_check_dependencies_triggers_mpv_update(monkeypatch, tmp_path):
	monkeypatch.setattr(server, "_dependencies_checked", False)
	monkeypatch.setattr(sys, "platform", "win32")

	managed_dir = tmp_path / "mpv"
	managed_dir.mkdir()
	(managed_dir / ".rockola_managed_mpv").touch()
	fake_mpv = managed_dir / "mpv.exe"
	fake_mpv.touch()

	monkeypatch.setattr(server, "find_binary", lambda b: str(fake_mpv) if b == "mpv" else None)
	monkeypatch.setattr("server.importlib.util.find_spec", lambda mod: True)

	with patch("scripts.mpv_installer.update_mpv") as mock_update:
		server.check_dependencies(force=True)
		mock_update.assert_called_once()
