import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts import binary_utils


def test_import_aliases():
	import binary_utils as bu

	assert bu is binary_utils
	assert hasattr(binary_utils, "resolve_platform_and_arch")
	assert hasattr(binary_utils, "get_clean_env")


def test_resolve_platform_and_arch_explicit():
	plat, arch = binary_utils.resolve_platform_and_arch("windows", "x86_64")
	assert plat == "windows"
	assert arch == "x86_64"

	plat, arch = binary_utils.resolve_platform_and_arch("darwin", "arm64")
	assert plat == "darwin"
	assert arch == "arm64"

	plat, arch = binary_utils.resolve_platform_and_arch("linux", "i686")
	assert plat == "linux"
	assert arch == "i686"


def test_resolve_platform_and_arch_detection(monkeypatch):
	monkeypatch.setattr(sys, "platform", "win32")
	monkeypatch.setattr(os, "name", "nt")
	monkeypatch.setattr(binary_utils.platform, "machine", lambda: "AMD64")

	plat, arch = binary_utils.resolve_platform_and_arch()
	assert plat == "windows"
	assert arch == "x86_64"

	monkeypatch.setattr(sys, "platform", "linux")
	monkeypatch.setattr(os, "name", "posix")
	monkeypatch.setattr(binary_utils.platform, "machine", lambda: "aarch64")

	plat, arch = binary_utils.resolve_platform_and_arch()
	assert plat == "linux"
	assert arch == "arm64"


def test_get_clean_env(monkeypatch):
	monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib:/usr/local/lib")
	monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI1234/lib:/usr/lib")
	monkeypatch.setenv("PYTHONPATH", "/tmp/_MEI1234")

	clean = binary_utils.get_clean_env()
	assert clean["LD_LIBRARY_PATH"] == "/usr/lib:/usr/local/lib"
	assert "PYTHONPATH" not in clean


def test_standalone_installer_scripts_execution():
	root_dir = Path(__file__).resolve().parent.parent
	env = os.environ.copy()
	# Ensure PYTHONPATH doesn't leak project root into the subprocess
	env.pop("PYTHONPATH", None)

	# Run mpv_installer directly from scripts/ directory
	res_mpv = subprocess.run(
		[sys.executable, str(root_dir / "scripts" / "mpv_installer.py"), "--help"],
		cwd=str(root_dir / "scripts"),
		capture_output=True,
		text=True,
		env=env,
		check=False,
	)
	assert res_mpv.returncode == 0
	assert "mpv_installer.py" in res_mpv.stdout
	assert "ModuleNotFoundError" not in res_mpv.stderr

	# Run ytdlp_installer directly from scripts/ directory
	res_ytdlp = subprocess.run(
		[sys.executable, str(root_dir / "scripts" / "ytdlp_installer.py"), "--help"],
		cwd=str(root_dir / "scripts"),
		capture_output=True,
		text=True,
		env=env,
		check=False,
	)
	assert res_ytdlp.returncode == 0
	assert "ytdlp_installer.py" in res_ytdlp.stdout
	assert "ModuleNotFoundError" not in res_ytdlp.stderr


def test_is_internet_available_success(monkeypatch):
	called = False

	def fake_conn(addr, timeout=0.8):
		nonlocal called
		called = True
		return MagicMock()

	monkeypatch.setattr(binary_utils.socket, "create_connection", fake_conn)
	assert binary_utils.is_internet_available(timeout=0.8) is True
	assert called is True


def test_is_internet_available_failure(monkeypatch):
	def fake_conn(addr, timeout=0.8):
		raise OSError("Network unreachable")

	monkeypatch.setattr(binary_utils.socket, "create_connection", fake_conn)
	assert binary_utils.is_internet_available(timeout=0.8) is False


@pytest.mark.asyncio
async def test_check_internet_async(monkeypatch):
	def fake_conn(addr, timeout=0.8):
		return MagicMock()

	monkeypatch.setattr(binary_utils.socket, "create_connection", fake_conn)
	res = await binary_utils.check_internet_async(timeout=0.8)
	assert res is True


def test_shared_download_file(tmp_path, monkeypatch):
	dest = tmp_path / "test_download.bin"
	logs = []

	class FakeResponse:
		def __init__(self):
			self.headers = {"Content-Length": "10"}
			self._read_done = False

		def read(self, size):
			if not self._read_done:
				self._read_done = True
				return b"0123456789"
			return b""

		def __enter__(self):
			return self

		def __exit__(self, exc_type, exc_val, exc_tb):
			pass

	monkeypatch.setattr(binary_utils.urllib.request, "urlopen", lambda req, timeout=30: FakeResponse())
	binary_utils.download_file("http://example.com/file", dest, log_fn=logs.append)
	assert dest.read_bytes() == b"0123456789"
	assert any("100%" in m for m in logs)


def test_shared_is_rockola_managed(tmp_path):
	marker_dir = tmp_path / "bin"
	marker_dir.mkdir()
	(marker_dir / ".rockola_managed_ffmpeg").touch()
	target_bin = marker_dir / "ffmpeg"
	target_bin.touch()

	assert binary_utils.is_rockola_managed(target_bin, "ffmpeg") is True
	assert binary_utils.is_rockola_managed(target_bin, "mpv") is False


def test_shared_get_default_install_dir(tmp_path, monkeypatch):
	# Test fallback directory resolution
	monkeypatch.setattr(sys, "frozen", False, raising=False)
	resolved = binary_utils.get_default_install_dir("ffmpeg")
	assert isinstance(resolved, Path)


def test_shared_build_frontend(tmp_path, monkeypatch):
	called = False

	def fake_run(cmd, cwd=None, check=True):
		nonlocal called
		called = True
		return MagicMock()

	monkeypatch.setattr(subprocess, "run", fake_run)
	binary_utils.build_frontend(root_dir=tmp_path, force=True)
	assert called is True


def test_shared_fetch_github_release_assets_api(monkeypatch):
	fake_data = {
		"tag_name": "v1.0.0",
		"assets": [
			{"name": "tool-linux.tar.xz", "browser_download_url": "http://test.com/tool.tar.xz", "size": 1234}
		],
	}

	class FakeResponse:
		def read(self):
			import json
			return json.dumps(fake_data).encode("utf-8")

		def __enter__(self):
			return self

		def __exit__(self, *args):
			pass

	monkeypatch.setattr(binary_utils.urllib.request, "urlopen", lambda req, timeout=10: FakeResponse())
	res = binary_utils.fetch_github_release_assets(
		api_url="http://api.github.com/test",
		html_url="http://github.com/test",
		user_agent="TestAgent",
	)
	assert res["tag"] == "v1.0.0"
	assert len(res["assets"]) == 1
	assert res["assets"][0]["name"] == "tool-linux.tar.xz"


def test_shared_fetch_github_release_assets_fallback(monkeypatch):
	logs = []

	class FakeHtmlResponse:
		def geturl(self):
			return "https://github.com/owner/repo/releases/tag/v2.1.0"

		def __enter__(self):
			return self

		def __exit__(self, *args):
			pass

	def fake_urlopen(req, timeout=10):
		url = req.full_url if hasattr(req, "full_url") else str(req)
		if "api.github.com" in url:
			import urllib.error
			raise urllib.error.URLError("Rate limit")
		return FakeHtmlResponse()

	def fake_builder(tag):
		return [{"name": f"asset-{tag}.zip", "url": f"http://dl/{tag}.zip", "size": 0}]

	monkeypatch.setattr(binary_utils.urllib.request, "urlopen", fake_urlopen)
	res = binary_utils.fetch_github_release_assets(
		api_url="http://api.github.com/test",
		html_url="http://github.com/test",
		user_agent="TestAgent",
		fallback_builder=fake_builder,
		log_fn=logs.append,
	)
	assert res["tag"] == "v2.1.0"
	assert res["assets"][0]["name"] == "asset-v2.1.0.zip"
	assert any("fallback" in m.lower() or "error" in m.lower() for m in logs)


def test_shared_extract_archive_binary_zip_and_tar(tmp_path):
	import tarfile
	import zipfile
	import io

	dest_dir = tmp_path / "extracted"
	dest_dir.mkdir()

	# Create test zip with binary
	zip_file = tmp_path / "test.zip"
	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("sub/bin_tool", b"echo binary_content")
		zf.writestr("sub/other.txt", b"plain text")

	success = binary_utils.extract_archive_binary(
		archive_path=zip_file,
		dest_dir=dest_dir,
		target_names={"bin_tool", "bin_tool.exe"},
	)
	assert success is True
	extracted_bin = dest_dir / "bin_tool"
	assert extracted_bin.is_file()
	assert extracted_bin.read_bytes() == b"echo binary_content"

	# Create test tar.gz
	tar_dest = tmp_path / "extracted_tar"
	tar_dest.mkdir()
	tar_file = tmp_path / "test.tar.gz"
	with tarfile.open(tar_file, "w:gz") as tf:
		data = b"tar content"
		ti = tarfile.TarInfo(name="bin_tool")
		ti.size = len(data)
		tf.addfile(ti, io.BytesIO(data))

	success_tar = binary_utils.extract_archive_binary(
		archive_path=tar_file,
		dest_dir=tar_dest,
		target_names={"bin_tool"},
	)
	assert success_tar is True
	assert (tar_dest / "bin_tool").read_bytes() == b"tar content"


def test_shared_extract_archive_binary_zipslip_protection(tmp_path):
	import zipfile

	dest_dir = tmp_path / "safe_dir"
	dest_dir.mkdir()

	zip_file = tmp_path / "malicious.zip"
	with zipfile.ZipFile(zip_file, "w") as zf:
		zf.writestr("../../evil_bin", b"evil")

	success = binary_utils.extract_archive_binary(
		archive_path=zip_file,
		dest_dir=dest_dir,
		target_names={"evil_bin"},
	)
	assert success is False
	assert not (tmp_path / "evil_bin").exists()


def test_shared_mark_rockola_managed(tmp_path):
	dest_dir = tmp_path / "bin"
	dest_dir.mkdir()
	success = binary_utils.mark_rockola_managed(dest_dir, "testtool")
	assert success is True
	assert (dest_dir / ".rockola_managed_testtool").is_file()
	assert (dest_dir / ".last_testtool_update_check").is_file()

