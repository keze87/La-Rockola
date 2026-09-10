import sys
from pathlib import Path
from unittest.mock import patch

import server


def test_find_binary_in_script_or_app_dir(tmp_path, monkeypatch):
	"""Test finding a binary next to the executable / script or in subfolders."""
	exe_dir = tmp_path / "app"
	exe_dir.mkdir()
	bin_dir = exe_dir / "bin"
	bin_dir.mkdir()

	# Create a dummy binary in bin/
	dummy_bin = bin_dir / "mpv"
	dummy_bin.write_text("dummy")

	monkeypatch.setattr(sys, "executable", str(exe_dir / "larockola.exe"))
	monkeypatch.setattr(sys, "frozen", True, raising=False)

	found = server.find_binary("mpv")
	assert found is not None
	assert Path(found).resolve() == dummy_bin.resolve()


def test_find_binary_fallback_to_which(monkeypatch):
	"""Test find_binary falling back to shutil.which."""
	monkeypatch.setattr(sys, "frozen", False, raising=False)
	with patch("shutil.which", return_value="/usr/bin/mpv"):
		assert server.find_binary("mpv") == "/usr/bin/mpv"


def test_build_frontend_when_frozen(monkeypatch):
	"""Test build_frontend immediately returns without subprocess calls when frozen."""
	monkeypatch.setattr(sys, "frozen", True, raising=False)
	with patch("subprocess.run") as mock_run:
		server.build_frontend()
		mock_run.assert_not_called()


def test_get_carpincho_data_dir_frozen_writable(tmp_path, monkeypatch):
	"""Test portable DB path next to executable when writable."""
	exe_dir = tmp_path / "portable_app"
	exe_dir.mkdir()
	fake_exe = exe_dir / "larockola.exe"
	fake_exe.write_text("fake")

	monkeypatch.setattr(sys, "frozen", True, raising=False)
	monkeypatch.setattr(sys, "executable", str(fake_exe))

	data_dir = server.get_carpincho_data_dir()
	assert data_dir == exe_dir / "DB"
	assert data_dir.is_dir()


def test_get_carpincho_data_dir_frozen_readonly_fallback(tmp_path, monkeypatch):
	"""Test fallback to user data dir when executable directory is not writable."""
	exe_dir = tmp_path / "readonly_app"
	exe_dir.mkdir()
	fake_exe = exe_dir / "larockola.exe"

	monkeypatch.setattr(sys, "frozen", True, raising=False)
	monkeypatch.setattr(sys, "executable", str(fake_exe))

	# Simulate write error on exe directory
	with patch.object(Path, "touch", side_effect=OSError("Read-only file system")):
		data_dir = server.get_carpincho_data_dir()
		assert "DB" in str(data_dir)
		assert str(data_dir) != str(exe_dir / "DB")


def test_check_dependencies_bypasses_on_help():
	"""Verify check_dependencies does not exit if --help is present in argv."""
	with patch("sys.argv", ["server.py", "--help"]), patch("sys.exit") as mock_exit:
		server.check_dependencies()
		mock_exit.assert_not_called()
