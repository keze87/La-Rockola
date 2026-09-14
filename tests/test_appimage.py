import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import server
from scripts import build_appimage


def test_larockola_desktop_file_syntax():
	desktop_file = Path(__file__).resolve().parent.parent / "scripts" / "larockola.desktop"
	assert desktop_file.is_file()

	content = desktop_file.read_text(encoding="utf-8")
	assert "[Desktop Entry]" in content
	assert "Type=Application" in content
	assert "Name=La Rockola del Carpincho" in content
	assert "Exec=larockola %F" in content
	assert "Icon=larockola" in content
	assert "Categories=" in content
	assert "AudioVideo" in content


def test_create_appdir_structure(tmp_path):
	fake_bin = tmp_path / "larockola_compiled"
	fake_bin.write_text("elf_binary_content")

	appdir = tmp_path / "LaRockola.AppDir"
	result = build_appimage.create_appdir(fake_bin, appdir=appdir)

	assert result == appdir
	assert (appdir / "AppRun").is_file()
	assert (appdir / "larockola.desktop").is_file()
	assert (appdir / "larockola.png").is_file()

	# Executable binary in usr/bin
	dest_bin = appdir / "usr" / "bin" / "larockola"
	assert dest_bin.is_file()
	assert dest_bin.read_text() == "elf_binary_content"
	assert dest_bin.stat().st_mode & stat.S_IXUSR

	# AppRun permissions and content
	apprun = appdir / "AppRun"
	assert apprun.stat().st_mode & stat.S_IXUSR
	apprun_text = apprun.read_text(encoding="utf-8")
	assert "exec \"${HERE}/usr/bin/larockola\" \"$@\"" in apprun_text
	assert "LD_LIBRARY_PATH" in apprun_text

	# Standard desktop file location
	assert (appdir / "usr" / "share" / "applications" / "larockola.desktop").is_file()

	# Icon in hicolor theme
	assert (appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "larockola.png").is_file()


def test_get_carpincho_data_dir_appimage_portable_db(tmp_path, monkeypatch):
	"""Verify that running from an AppImage with a DB folder alongside uses that DB."""
	appimage_file = tmp_path / "LaRockola-x86_64.AppImage"
	appimage_file.touch()

	portable_db = tmp_path / "DB"
	portable_db.mkdir()

	fake_exe = tmp_path / "squashfs-root" / "usr" / "bin" / "larockola"
	fake_exe.parent.mkdir(parents=True)
	fake_exe.touch()

	monkeypatch.setattr(sys, "frozen", True, raising=False)
	monkeypatch.setattr(sys, "executable", str(fake_exe))
	monkeypatch.setenv("APPIMAGE", str(appimage_file))

	data_dir = server.get_carpincho_data_dir()
	assert data_dir == portable_db


def test_get_carpincho_data_dir_appimage_fallback_to_xdg(tmp_path, monkeypatch):
	"""Verify that running from an AppImage without DB folder falls back to XDG user data dir."""
	appimage_file = tmp_path / "LaRockola-x86_64.AppImage"
	appimage_file.touch()

	fake_exe = tmp_path / "squashfs-root" / "usr" / "bin" / "larockola"
	fake_exe.parent.mkdir(parents=True)
	fake_exe.touch()

	monkeypatch.setattr(sys, "frozen", True, raising=False)
	monkeypatch.setattr(sys, "executable", str(fake_exe))
	monkeypatch.setenv("APPIMAGE", str(appimage_file))

	# Simulate read-only squashfs on exe_dir
	with patch.object(Path, "touch", side_effect=OSError("Read-only file system")):
		data_dir = server.get_carpincho_data_dir()
		assert "DB" in str(data_dir)
		assert "carpincho" in str(data_dir)
		assert str(data_dir) != str(tmp_path / "DB")


def test_ensure_appimagetool_found_in_path(monkeypatch):
	monkeypatch.setattr(build_appimage.shutil, "which", lambda cmd: "/usr/bin/appimagetool" if cmd == "appimagetool" else None)
	tool = build_appimage.ensure_appimagetool()
	assert tool == Path("/usr/bin/appimagetool")


def test_ensure_appimagetool_download(tmp_path, monkeypatch):
	monkeypatch.setattr(build_appimage.shutil, "which", lambda cmd: None)
	fake_build = tmp_path / "build"
	monkeypatch.setattr(build_appimage, "BUILD_DIR", fake_build)

	fake_content = b"x" * (2 * 1024 * 1024)

	mock_resp = MagicMock()
	mock_resp.__enter__.return_value = mock_resp
	mock_resp.read.side_effect = [fake_content, b""]

	with patch("urllib.request.urlopen", return_value=mock_resp), patch(
		"shutil.copyfileobj", side_effect=lambda src, dst: dst.write(fake_content)
	):
		tool = build_appimage.ensure_appimagetool()
		assert tool == fake_build / "tools" / "appimagetool"
		assert tool.is_file()
		assert tool.stat().st_mode & stat.S_IXUSR


def test_build_appimage_success(tmp_path, monkeypatch):
	fake_release = tmp_path / "release"
	monkeypatch.setattr(build_appimage, "RELEASE_DIR", fake_release)

	fake_tool = tmp_path / "appimagetool"
	fake_tool.touch()
	monkeypatch.setattr(build_appimage, "ensure_appimagetool", lambda: fake_tool)

	fake_appdir = tmp_path / "LaRockola.AppDir"
	fake_appdir.mkdir()

	out_appimage = fake_release / "LaRockola-x86_64.AppImage"

	def fake_run(cmd, env=None, check=False):
		# Simulate appimagetool writing output
		out_appimage.write_text("appimage_content")
		res = MagicMock()
		res.returncode = 0
		return res

	with patch("subprocess.run", side_effect=fake_run):
		res_path = build_appimage.build_appimage(appdir=fake_appdir)
		assert res_path == out_appimage
		assert res_path.is_file()
		assert res_path.stat().st_mode & stat.S_IXUSR


def test_build_frontend_skips_when_not_forced(tmp_path, monkeypatch):
	fake_dist = tmp_path / "dist"
	fake_dist.mkdir()
	(fake_dist / "index.html").touch()
	monkeypatch.setattr(build_appimage, "DIST_DIR", fake_dist)

	with patch("subprocess.run") as mock_run:
		build_appimage.build_frontend(force=False)
		mock_run.assert_not_called()


def test_run_pyinstaller_skip(tmp_path, monkeypatch):
	fake_dist_bin = tmp_path / "dist_bin"
	fake_dist_bin.mkdir()
	fake_exe = fake_dist_bin / "larockola"
	fake_exe.touch()
	monkeypatch.setattr(build_appimage, "DIST_BIN_DIR", fake_dist_bin)

	with patch("subprocess.run") as mock_run:
		res = build_appimage.run_pyinstaller(skip=True)
		assert res == fake_exe
		mock_run.assert_not_called()


