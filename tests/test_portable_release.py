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


def test_get_config_path_custom(tmp_path):
	"""Test get_config_path with a custom path."""
	custom = tmp_path / "my_custom_config.json"
	assert server.get_config_path(str(custom)) == custom.resolve()


def test_get_config_path_frozen_writable(tmp_path, monkeypatch):
	"""Test get_config_path in frozen mode when exe dir is writable."""
	exe_dir = tmp_path / "app_dir"
	exe_dir.mkdir()
	fake_exe = exe_dir / "larockola.exe"
	fake_exe.write_text("fake")

	monkeypatch.setattr(sys, "frozen", True, raising=False)
	monkeypatch.setattr(sys, "executable", str(fake_exe))

	config_path = server.get_config_path()
	assert config_path == exe_dir / "rockola_config.json"


def test_load_and_save_config(tmp_path):
	"""Test loading default config, saving modified config, and reloading."""
	cfg_file = tmp_path / "test_config.json"
	# Initial load when not exists
	initial = server.load_config(cfg_file)
	assert initial["port"] == 1729
	assert initial["host"] == "0.0.0.0"

	# Save custom config
	custom = {
		"music_dir": str(tmp_path / "my_music"),
		"music_dir2": None,
		"port": 8080,
		"host": "127.0.0.1",
	}
	server.save_config(cfg_file, custom)
	assert cfg_file.is_file()

	loaded = server.load_config(cfg_file)
	assert loaded["port"] == 8080
	assert loaded["host"] == "127.0.0.1"
	assert loaded["music_dir"] == str(tmp_path / "my_music")


def test_run_interactive_wizard(tmp_path):
	"""Test standard interactive wizard flow with valid inputs."""
	cfg_file = tmp_path / "rockola_config.json"
	music_folder = tmp_path / "RockolaMusic"
	music_folder.mkdir()

	# Inputs: primary dir, empty secondary, port 9000, empty host (default)
	inputs = [str(music_folder), "", "9000", ""]

	with patch("builtins.input", side_effect=inputs):
		cfg = server.run_interactive_wizard(cfg_file)

	assert cfg["port"] == 9000
	assert cfg["music_dir"] == str(music_folder.resolve())
	assert cfg["music_dir2"] is None
	assert cfg["host"] == "0.0.0.0"
	assert cfg_file.is_file()


def test_run_interactive_wizard_create_dir_and_invalid_port(tmp_path):
	"""Test wizard creating a non-existent directory and handling invalid port retries."""
	cfg_file = tmp_path / "rockola_config.json"
	new_music_folder = tmp_path / "BrandNewMusic"

	inputs = [str(new_music_folder), "s", "", "invalid", "999999", "1800", "192.168.1.50"]

	with patch("builtins.input", side_effect=inputs):
		cfg = server.run_interactive_wizard(cfg_file)

	assert cfg["port"] == 1800
	assert cfg["host"] == "192.168.1.50"
	assert new_music_folder.is_dir()
	assert cfg["music_dir"] == str(new_music_folder.resolve())

