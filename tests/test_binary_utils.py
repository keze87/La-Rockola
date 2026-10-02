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
