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


def test_get_config_path_in_data_dir(tmp_path, monkeypatch):
	"""Test get_config_path resolves to rockola_config.json inside DATA_DIR."""
	data_dir = tmp_path / "my_db_dir"
	data_dir.mkdir()
	monkeypatch.setattr(server, "DATA_DIR", data_dir)

	config_path = server.get_config_path()
	assert config_path == data_dir / "rockola_config.json"


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

	# Input: primary dir only
	inputs = [str(music_folder)]

	with patch("builtins.input", side_effect=inputs):
		cfg = server.run_interactive_wizard(cfg_file)

	assert cfg["port"] == 1729
	assert cfg["music_dir"] == str(music_folder.resolve())
	assert cfg["music_dir2"] is None
	assert cfg["host"] == "0.0.0.0"
	assert cfg_file.is_file()


def test_run_interactive_wizard_create_dir(tmp_path):
	"""Test wizard creating a non-existent directory."""
	cfg_file = tmp_path / "rockola_config.json"
	new_music_folder = tmp_path / "BrandNewMusic"

	inputs = [str(new_music_folder), "s"]

	with patch("builtins.input", side_effect=inputs):
		cfg = server.run_interactive_wizard(cfg_file)

	assert cfg["port"] == 1729
	assert cfg["host"] == "0.0.0.0"
	assert new_music_folder.is_dir()
	assert cfg["music_dir"] == str(new_music_folder.resolve())


def test_check_dependencies_no_duplicate_warning():
	"""Test that check_dependencies only executes once when _dependencies_checked is True."""
	server._dependencies_checked = True
	with patch("server.importlib.util.find_spec") as mock_find:
		server.check_dependencies(force=False)
		mock_find.assert_not_called()

	# When force=True, it should execute
	with patch("server.importlib.util.find_spec", return_value=True) as mock_find2, patch(
		"server.find_binary", return_value="/usr/bin/dummy"
	):
		server.check_dependencies(force=True)
		assert mock_find2.called


def test_select_folder_dialog_powershell(tmp_path):
	"""Test select_folder_dialog with PowerShell provider on Windows."""
	target_folder = tmp_path / "MyMusicFolder"
	target_folder.mkdir()

	with patch("sys.platform", "win32"):
		with patch("subprocess.run") as mock_run:
			mock_run.return_value.stdout = f"{str(target_folder)}\n"
			mock_run.return_value.return_code = 0
			res = server.select_folder_dialog(title="Test", initial_dir=str(tmp_path))
			assert res == str(target_folder)


def test_select_folder_dialog_cancel(tmp_path):
	"""Test select_folder_dialog returns None when user cancels the dialog."""
	with patch("sys.platform", "win32"):
		with patch("server._select_folder_powershell", return_value=None), patch(
			"server._select_folder_tkinter", return_value=None
		):
			res = server.select_folder_dialog(title="Test", initial_dir=str(tmp_path))
			assert res is None


def test_run_interactive_wizard_using_selector_dialog(tmp_path):
	"""Test choosing option 2 (folder selector dialog) in the wizard."""
	cfg_file = tmp_path / "rockola_config.json"
	picked_folder = tmp_path / "PickedMusic"
	picked_folder.mkdir()

	# Choice 2 for primary folder dialog
	inputs = ["2"]

	with patch("server.select_folder_dialog", return_value=str(picked_folder)):
		with patch("builtins.input", side_effect=inputs):
			cfg = server.run_interactive_wizard(cfg_file)

	assert cfg["music_dir"] == str(picked_folder.resolve())
	assert cfg["music_dir2"] is None
	assert cfg["port"] == 1729
	assert cfg["host"] == "0.0.0.0"


def test_run_interactive_wizard_using_default_option(tmp_path):
	"""Test choosing option 1 (or pressing Enter) to use the default ~/Music."""
	cfg_file = tmp_path / "rockola_config.json"
	default_folder = tmp_path / "DefaultMusic"
	default_folder.mkdir()

	initial_cfg = {"music_dir": str(default_folder)}

	# Enter (option 1 default)
	inputs = [""]

	with patch("builtins.input", side_effect=inputs):
		cfg = server.run_interactive_wizard(cfg_file, current_config=initial_cfg)

	assert cfg["music_dir"] == str(default_folder.resolve())
	assert cfg["music_dir2"] is None


def test_build_windows_zip_structure(tmp_path, monkeypatch):
	"""Test that build_windows.py creates a ZIP with files at root (relative to package_dir)."""
	import zipfile
	from scripts import build_windows

	fake_release = tmp_path / "release"
	monkeypatch.setattr(build_windows, "RELEASE_DIR", fake_release)

	fake_exe = tmp_path / "larockola.exe"
	fake_exe.write_text("fake binary")

	build_windows.create_release_package(fake_exe)

	zip_path = fake_release / "larockola-windows-x86_64.zip"
	assert zip_path.is_file()

	with zipfile.ZipFile(zip_path, "r") as zf:
		names = zf.namelist()
		# Files must be at root of zip, NOT starting with 'larockola-windows-x86_64/'
		assert "larockola.exe" in names
		assert "LEEME.txt" in names
		assert "iniciar_rockola.bat" in names
		assert not any(name.startswith("larockola-windows-x86_64/") for name in names)


