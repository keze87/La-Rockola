import os
import subprocess
import sys
from pathlib import Path

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
