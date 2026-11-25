"""
Pruebas unitarias y de integración (TDD) para soporte Android, modo --no-mpv,
NullMpvController, rutas PWA, cambio dinámico de carpeta de música y android_entry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.websocket import ConnectionManager
from app.cli import entrypoint
from app.core import config as config_mod
from app.core import container as container_mod
from app.core.container import AppContainer, set_container
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.infrastructure.binaries import manager as bin_manager
from app.infrastructure.db.connection import init_db
from app.infrastructure.media.mixer import get_static_asset_path
from app.main import create_app


def test_is_android_detection(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Detecta entorno Android mediante variables de entorno o sys.platform."""
	monkeypatch.delenv("ANDROID_ROOT", raising=False)
	monkeypatch.delenv("TERMUX_VERSION", raising=False)
	monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
	monkeypatch.setattr(sys, "platform", "linux")
	assert bin_manager.is_android() is False

	monkeypatch.setenv("ANDROID_ROOT", "/system")
	assert bin_manager.is_android() is True

	monkeypatch.delenv("ANDROID_ROOT", raising=False)
	monkeypatch.setenv("TERMUX_VERSION", "0.118.0")
	assert bin_manager.is_android() is True

	monkeypatch.delenv("TERMUX_VERSION", raising=False)
	monkeypatch.setattr(sys, "platform", "android")
	assert bin_manager.is_android() is True


def test_resolve_platform_and_ensure_display_on_android(monkeypatch: pytest.MonkeyPatch) -> None:
	"""En Android devuelve 'android' y omite el escaneo de DISPLAY/WAYLAND_DISPLAY."""
	monkeypatch.setenv("ANDROID_ROOT", "/system")
	plat, _arch = bin_manager.resolve_platform_and_arch()
	assert plat == "android"

	env: dict[str, str] = {}
	with patch("glob.glob", side_effect=AssertionError("No debe buscar sockets X11/Wayland en Android")):
		bin_manager.ensure_display_env(env)
	assert "DISPLAY" not in env
	assert "WAYLAND_DISPLAY" not in env


@pytest.mark.asyncio
async def test_null_mpv_controller_interface() -> None:
	"""NullMpvController expone la interfaz asíncrona de AsyncMpvController sin lanzar procesos."""
	from app.infrastructure.mpv.null_controller import NullMpvController

	ctrl = NullMpvController()
	assert ctrl.is_running is False
	assert ctrl.has_display is False
	assert ctrl.is_windows is False
	assert ctrl.socket_path is None
	assert ctrl.ipc_path is None

	await ctrl.start()
	await ctrl.command("loadfile", "x.mp3")
	await ctrl.set_property("pause", True)
	await ctrl.load_file("/music/tema.mp3")
	await ctrl.set_pause(True)
	await ctrl.set_volume(80)
	await ctrl.set_mute(True)
	await ctrl.seek_relative(5.0)
	await ctrl.seek_absolute(12.0)
	await ctrl.toggle_fullscreen()
	await ctrl.set_force_window(False)
	await ctrl.add_subtitle("/music/tema.lrc")
	await ctrl.stop_playback()
	await ctrl.stop()


@pytest.mark.asyncio
async def test_orchestrator_without_mpv(tmp_path: Path) -> None:
	"""PlaybackOrchestrator(use_mpv=False) usa NullMpvController y expone has_mpv=False."""
	from app.infrastructure.mpv.null_controller import NullMpvController

	db_path = tmp_path / "no_mpv.db"
	init_db(db_path)

	orch = PlaybackOrchestrator(db_path=db_path, open_browser=False, use_mpv=False)
	assert isinstance(orch.mpv, NullMpvController)
	assert orch.has_mpv is False
	assert orch.mpv_visible is False
	assert orch.get_full_state_dict()["has_mpv"] is False

	await orch.play_track("/fake/song.mp3")
	assert orch.current_track == "/fake/song.mp3"
	await orch.set_pause(True)
	assert orch.mpv_paused is True
	await orch.set_volume(50)
	assert orch.volume == 50
	await orch.stop_playback(reset_ui_state=True)
	assert orch.current_track is None

	default_orch = PlaybackOrchestrator(db_path=db_path, open_browser=False)
	assert default_orch.has_mpv is True
	assert default_orch.get_full_state_dict()["has_mpv"] is True


def test_no_mpv_config_and_cli_parsing() -> None:
	"""Settings y el parser CLI soportan --no-mpv manteniendo default False."""
	assert config_mod.DEFAULT_CONFIG["no_mpv"] is False
	settings = config_mod.Settings()
	assert settings.no_mpv is False

	args = entrypoint.build_arg_parser().parse_args(["--no-mpv"])
	assert args.no_mpv is True

	merged = settings.merge_cli_args(args)
	assert merged.no_mpv is True


def test_check_dependencies_no_mpv_and_android(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
	"""check_dependencies no falla sin mpv cuando no_mpv=True o en Android."""
	monkeypatch.setattr(entrypoint, "find_binary", lambda name: None)
	monkeypatch.setattr(entrypoint, "is_mood_available", lambda: True)
	monkeypatch.setattr(sys, "argv", ["server.py"])

	# Con no_mpv=True no debe salir con sys.exit(1)
	entrypoint.check_dependencies(force=True, no_mpv=True)

	# En Android tampoco debe exigir mpv ni advertir por dbus_next
	monkeypatch.setenv("ANDROID_ROOT", "/system")
	monkeypatch.setattr(sys, "platform", "linux")
	entrypoint.check_dependencies(force=True, no_mpv=False)
	captured = capsys.readouterr()
	assert "dbus_next" not in captured.err


def test_dist_dirs_and_static_assets_respect_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""ROCKOLA_DIST_DIR redirige get_dist_dirs y get_static_asset_path."""
	custom_dist = tmp_path / "android_dist"
	(custom_dist / "assets").mkdir(parents=True)
	(custom_dist / "index.html").write_text("<html></html>", encoding="utf-8")
	(custom_dist / "manifest.webmanifest").write_text('{"name":"Rockola"}', encoding="utf-8")

	monkeypatch.setenv("ROCKOLA_DIST_DIR", str(custom_dist))
	_frontend_dir, dist_dir, assets_dir = config_mod.get_dist_dirs()
	assert dist_dir == custom_dist.resolve()
	assert assets_dir == (custom_dist / "assets").resolve()

	manifest_path = get_static_asset_path("manifest.webmanifest")
	assert manifest_path == (custom_dist / "manifest.webmanifest").resolve()


def test_get_default_music_dir_android(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""En Android usa la primera ruta existente del teléfono antes de caer en ~/Music."""
	monkeypatch.delenv("ANDROID_ROOT", raising=False)
	monkeypatch.delenv("TERMUX_VERSION", raising=False)
	monkeypatch.setattr(sys, "platform", "linux")
	assert config_mod.get_default_music_dir() == "~/Music"

	android_music = tmp_path / "sdcard_music"
	android_music.mkdir()
	monkeypatch.setenv("ANDROID_ROOT", "/system")
	assert config_mod.get_default_music_dir() == ""


def test_system_capabilities_music_dir_and_pwa_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Verifica has_mpv en capabilities, POST /system/music-dir y rutas PWA."""
	db_path = tmp_path / "api_android.db"
	init_db(db_path)

	music_dir = tmp_path / "microsd_music"
	music_dir.mkdir()
	config_file = tmp_path / "rockola_config.json"
	monkeypatch.setattr(config_mod, "get_config_path", lambda: config_file)

	dist_dir = tmp_path / "dist"
	(dist_dir / "assets").mkdir(parents=True)
	(dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
	(dist_dir / "manifest.webmanifest").write_text(json.dumps({"name": "La Rockola"}), encoding="utf-8")
	(dist_dir / "sw.js").write_text("self.addEventListener('fetch', () => {});", encoding="utf-8")
	monkeypatch.setenv("ROCKOLA_DIST_DIR", str(dist_dir))

	orch = PlaybackOrchestrator(db_path=db_path, open_browser=False, use_mpv=False)
	orch.scan_directory = MagicMock(return_value=[])
	container = AppContainer(db_path=db_path, orchestrator=orch, ws_manager=ConnectionManager())
	set_container(container)

	app = create_app()
	client = TestClient(app)

	# Capabilities incluye has_mpv
	caps = client.get("/system/capabilities")
	assert caps.status_code == 200
	assert caps.json()["has_mpv"] is False

	# POST /system/music-dir rechaza carpeta inexistente
	bad_res = client.post("/system/music-dir", json={"dir": str(tmp_path / "no_existe")})
	assert bad_res.status_code == 400

	# POST /system/music-dir actualiza estado y config cuando existe
	with patch("app.api.system.scan_library", new_callable=AsyncMock):
		ok_res = client.post("/api/v1/system/music-dir", json={"dir": str(music_dir)})
	assert ok_res.status_code == 200
	body = ok_res.json()
	assert body["status"] == "ok"
	assert body["music_dir"] == str(music_dir.resolve())
	assert orch.initial_dir == str(music_dir.resolve())
	saved_cfg = json.loads(config_file.read_text(encoding="utf-8"))
	assert saved_cfg["music_dir"] == str(music_dir.resolve())

	# Rutas PWA
	manifest_res = client.get("/manifest.webmanifest")
	assert manifest_res.status_code == 200
	assert "application/manifest+json" in manifest_res.headers["content-type"]

	sw_res = client.get("/sw.js")
	assert sw_res.status_code == 200
	assert "javascript" in sw_res.headers["content-type"]
	assert "no-cache" in sw_res.headers.get("cache-control", "")


def test_android_entry_configuration_and_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""android_entry configura el entorno embebido y gestiona inicio/parada de Uvicorn sin señales."""
	from app import android_entry

	data_dir = tmp_path / "android_data"
	dist_dir = tmp_path / "android_dist"
	music_dir = tmp_path / "android_music"
	(dist_dir / "assets").mkdir(parents=True)
	music_dir.mkdir()
	data_dir.mkdir(parents=True)
	(data_dir / "rockola_config.json").write_text(
		json.dumps(
			{
				"default_sort": "shuffle",
				"dj_carpincho_enabled": True,
				"dj_mode": "favorites",
				"volume": 65,
			}
		),
		encoding="utf-8",
	)

	info = android_entry.configure_android_environment(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir=str(music_dir),
		port=1829,
		host="0.0.0.0",
	)
	assert info["port"] == 1829
	assert info["music_dir"] == str(music_dir.resolve())
	assert config_mod.get_settings().no_mpv is True
	assert config_mod.get_settings().open_browser is False
	orch = container_mod.get_container().ensure_orchestrator()
	assert orch.default_sort == "shuffle"
	assert orch.dj_carpincho_enabled is False
	assert orch.dj_mode == "favorites"
	assert orch.volume == 65

	created_servers: list[SimpleNamespace] = []

	orig_signal_handler = MagicMock()

	class DummyServer:
		def __init__(self, config: object) -> None:
			self.config = config
			self.should_exit = False
			self.ran = False
			self.install_signal_handlers = orig_signal_handler
			created_servers.append(self)  # type: ignore[arg-type]

		def run(self) -> None:
			self.ran = True
			running_info = android_entry.get_server_info()
			assert running_info["running"] is True
			assert running_info["port"] == 1829
			android_entry.stop_embedded_server()

	monkeypatch.setattr("uvicorn.Server", DummyServer)
	android_entry.start_embedded_server(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir=str(music_dir),
		port=1829,
	)
	assert len(created_servers) == 1
	assert created_servers[0].ran is True
	assert created_servers[0].should_exit is True
	# Verifica que se desactivaron los signal handlers para hilos en segundo plano de Android
	assert created_servers[0].install_signal_handlers is not orig_signal_handler
	assert created_servers[0].install_signal_handlers() is None
	assert android_entry.get_server_info()["running"] is False

	# Verifica que already_configured=True evita la doble inicialización de entorno/DB
	with monkeypatch.context() as m:
		cfg_mock = MagicMock(side_effect=AssertionError("no debe reconfigurar"))
		m.setattr(android_entry, "configure_android_environment", cfg_mock)
		android_entry.start_embedded_server(
			data_dir=str(data_dir),
			dist_dir=str(dist_dir),
			music_dir=str(music_dir),
			port=1829,
			already_configured=True,
		)
		assert cfg_mock.call_count == 0


def test_build_android_stage_assets(tmp_path: Path) -> None:
	"""stage_android_assets copia app/ excluyendo cachés y elimina assets/dist redundante."""
	from scripts.build_android import stage_android_assets

	(tmp_path / "app" / "__pycache__").mkdir(parents=True)
	(tmp_path / "app" / "__pycache__" / "x.pyc").write_bytes(b"pyc")
	(tmp_path / "app" / "android_entry.py").write_text("# entry\n", encoding="utf-8")
	(tmp_path / "scripts" / "fortune-es").mkdir(parents=True)
	(tmp_path / "scripts" / "fortune-es" / "rockola.fortunes").write_text("Tomate un mate\n%\n", encoding="utf-8")
	(tmp_path / "dist").mkdir()
	(tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
	stale_dist = tmp_path / "android" / "app" / "src" / "main" / "assets" / "dist"
	stale_dist.mkdir(parents=True)
	(stale_dist / "stale.txt").write_text("obsoleto", encoding="utf-8")

	py_dest = stage_android_assets(tmp_path)
	assert (py_dest / "android_entry.py").is_file()
	assert (py_dest / "domain" / "radio" / "fortune-es" / "rockola.fortunes").is_file()
	assert not (py_dest / "__pycache__").exists()
	assert not stale_dist.exists()


def test_staged_android_python_imports_app_main_without_cli_or_installers(tmp_path: Path) -> None:
	"""El paquete Python staged para Android (sin cli/ ni instaladores) debe importar app.main y android_entry."""
	import os
	import shutil
	import subprocess
	import sys

	from scripts.build_android import stage_android_assets

	repo_root = Path(__file__).resolve().parent.parent
	shutil.copytree(repo_root / "app", tmp_path / "app")
	(tmp_path / "android").mkdir()
	(tmp_path / "dist").mkdir()
	(tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

	py_dest = stage_android_assets(tmp_path)
	assert not (py_dest / "cli").exists()
	assert not (py_dest / "infrastructure" / "binaries" / "ffmpeg.py").exists()
	assert not (py_dest / "infrastructure" / "binaries" / "fpcalc.py").exists()
	assert not (py_dest / "infrastructure" / "binaries" / "mpv.py").exists()

	env = dict(os.environ)
	env["PYTHONPATH"] = str(py_dest.parent)
	proc = subprocess.run(
		[sys.executable, "-c", "import app.main, app.android_entry"],
		cwd=tmp_path,
		env=env,
		capture_output=True,
		text=True,
		check=False,
	)
	assert proc.returncode == 0, f"Falló import en staging Android: {proc.stderr}"


def _build_synthetic_elf64(p_align: int = 0x4000, runpath: bytes | None = None) -> bytes:
	"""Construye un ELF64 minimalista con segmentos PT_LOAD y opcional PT_DYNAMIC (DT_RUNPATH)."""
	import struct

	ehdr_size = 64
	phdr_size = 56
	num_phdrs = 2 if runpath is not None else 1
	header_end = ehdr_size + phdr_size * num_phdrs

	dynstr = b"\x00" + (runpath + b"\x00" if runpath is not None else b"")
	# DT_RUNPATH = 29, DT_STRTAB = 5, DT_STRSZ = 10, DT_NULL = 0
	strtab_vaddr = 0x2000
	dyn_offset = 0x1000
	strtab_offset = 0x2000

	dyn_entries = b""
	if runpath is not None:
		dyn_entries = (
			struct.pack("<qQ", 5, strtab_vaddr)
			+ struct.pack("<qQ", 10, len(dynstr))
			+ struct.pack("<qQ", 29, 1)
			+ struct.pack("<qQ", 0, 0)
		)

	total_size = 0x2100 if runpath is not None else 0x1000
	buf = bytearray(total_size)

	# Elf64_Ehdr: e_ident(16), e_type(H=3 ET_DYN), e_machine(H=183 aarch64), e_version(I=1),
	# e_entry(Q), e_phoff(Q=64), e_shoff(Q=0), e_flags(I=0), e_ehsize(H=64),
	# e_phentsize(H=56), e_phnum(H), e_shentsize(H=64), e_shnum(H=0), e_shstrndx(H=0)
	e_ident = b"\x7fELF\x02\x01\x01" + (b"\x00" * 9)
	struct.pack_into(
		"<16sHHIQQQIHHHHHH",
		buf,
		0,
		e_ident,
		3,
		183,
		1,
		0,
		ehdr_size,
		0,
		0,
		ehdr_size,
		phdr_size,
		num_phdrs,
		64,
		0,
		0,
	)

	# PT_LOAD (1): flags=5 (R|X)
	struct.pack_into(
		"<IIQQQQQQ",
		buf,
		ehdr_size,
		1,
		5,
		0,
		0,
		0,
		total_size,
		total_size,
		p_align,
	)

	if runpath is not None:
		# PT_DYNAMIC (2)
		struct.pack_into(
			"<IIQQQQQQ",
			buf,
			ehdr_size + phdr_size,
			2,
			6,
			dyn_offset,
			dyn_offset,
			dyn_offset,
			len(dyn_entries),
			len(dyn_entries),
			8,
		)
		buf[dyn_offset : dyn_offset + len(dyn_entries)] = dyn_entries
		buf[strtab_offset : strtab_offset + len(dynstr)] = dynstr

	assert len(buf) >= header_end
	return bytes(buf)


def test_verify_android_apk_elf_page_alignment_and_termux_runpath(tmp_path: Path) -> None:
	"""verify_android_apk detecta segmentos 4KB y RUNPATH de Termux incluso dentro de .imy."""
	import zipfile

	from scripts.verify_android_apk import inspect_elf_bytes, verify_android_archive

	good_elf = _build_synthetic_elf64(p_align=0x4000, runpath=None)
	assert inspect_elf_bytes("libgood.so", good_elf) == []

	bad_align_elf = _build_synthetic_elf64(p_align=0x1000, runpath=None)
	align_issues = inspect_elf_bytes("libbad_align.so", bad_align_elf)
	assert any("0x4000" in issue or "16 KB" in issue for issue in align_issues)

	termux_elf = _build_synthetic_elf64(p_align=0x4000, runpath=b"/data/data/com.termux/files/usr/lib")
	runpath_issues = inspect_elf_bytes("libtermux.so", termux_elf)
	assert any("com.termux" in issue for issue in runpath_issues)

	# Empaquetamos un APK con un .so 4KB escondido dentro del archivo .imy de Chaquopy
	imy_bad = tmp_path / "req.imy"
	with zipfile.ZipFile(imy_bad, "w") as zf:
		zf.writestr("_bad.so", bad_align_elf)

	apk_bad = tmp_path / "bad.apk"
	with zipfile.ZipFile(apk_bad, "w") as zf:
		zf.writestr("lib/arm64-v8a/libok.so", good_elf)
		zf.writestr("assets/chaquopy/requirements-arm64-v8a.imy", imy_bad.read_bytes())

	res_bad = verify_android_archive(apk_bad)
	assert res_bad.ok is False
	assert any("_bad.so" in msg for msg in res_bad.errors)

	imy_good = tmp_path / "req_ok.imy"
	with zipfile.ZipFile(imy_good, "w") as zf:
		zf.writestr("_ok.so", good_elf)

	apk_good = tmp_path / "good.apk"
	with zipfile.ZipFile(apk_good, "w") as zf:
		import struct

		info = zipfile.ZipInfo("lib/arm64-v8a/libok.so")
		pad_needed = (0x4000 - (30 + len(info.filename.encode("utf-8")) + 4)) % 0x4000
		info.extra = struct.pack("<HH", 0xFFFF, pad_needed) + (b"\x00" * pad_needed)
		zf.writestr(info, good_elf)
		zf.writestr("assets/chaquopy/requirements-arm64-v8a.imy", imy_good.read_bytes())

	res_good = verify_android_archive(apk_good)
	assert res_good.ok is True
	assert res_good.errors == []
	assert res_good.inspected_so_count >= 2


def test_android_smoke_check_runs_fastapi_endpoints(tmp_path: Path) -> None:
	"""android_smoke valida imports críticos y endpoints /api/v1/health y /api/v1/system/info."""
	from app.android_smoke import run_embedded_smoke_check

	result = run_embedded_smoke_check(work_dir=tmp_path)
	assert result["ok"] is True
	assert result["health_status"] == 200
	assert result["system_info_status"] == 200
	assert "fastapi" in result["checked_modules"]
	assert "pydantic_core" in result["checked_modules"]


def test_resize_cover_uses_android_image_resizer_when_pillow_missing(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Si no existe Pillow en Android, _resize_cover delega al helper Kotlin AndroidImageResizer."""
	from app.api import media as media_mod

	class _FakeResizer:
		@staticmethod
		def resizeJpeg(data: bytes, max_size: int) -> bytes:
			assert data == b"ORIG_COVER"
			assert max_size == 128
			return b"KOTLIN_RESIZED"

	monkeypatch.setattr(media_mod, "HAS_PIL", False)
	monkeypatch.setattr("app.infrastructure.binaries.manager.is_android", lambda: True)
	monkeypatch.setattr(media_mod, "_get_android_image_resizer", lambda: _FakeResizer)

	resized, mime = media_mod._resize_cover(b"ORIG_COVER", 128)
	assert resized == b"KOTLIN_RESIZED"
	assert mime == "image/jpeg"

	# Si el helper nativo falla o devuelve None, degrada devolviendo los bytes originales
	class _NullResizer:
		@staticmethod
		def resizeJpeg(_data: bytes, _max_size: int) -> None:
			return None

	monkeypatch.setattr(media_mod, "_get_android_image_resizer", lambda: _NullResizer)
	fallback, mime_fb = media_mod._resize_cover(b"ORIG_COVER", 128)
	assert fallback == b"ORIG_COVER"
	assert mime_fb == "image/jpeg"


def test_build_android_no_retagging_and_writes_sha256(tmp_path: Path) -> None:
	"""build_android elimina el reetiquetado de wheels Linux y genera .sha256 para artefactos."""
	from scripts import build_android as build_mod

	assert not hasattr(build_mod, "retag_wheel_for_android")
	assert not hasattr(build_mod, "ensure_android_pydantic_wheels")

	artifact = tmp_path / "app-arm64-release.apk"
	artifact.write_bytes(b"apk-content-123")
	sha_path = build_mod.write_sha256_file(artifact)
	assert sha_path == tmp_path / "app-arm64-release.apk.sha256"
	assert sha_path.read_text(encoding="utf-8").strip().endswith("app-arm64-release.apk")


def test_start_embedded_server_prevents_duplicate_instances_and_reports_state(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""start_embedded_server ignora inicios duplicados concurrentes y reporta host_state."""
	import threading

	from app import android_entry

	android_entry.stop_embedded_server()

	data_dir = tmp_path / "data"
	dist_dir = tmp_path / "dist"
	music_dir = tmp_path / "music"
	data_dir.mkdir()
	dist_dir.mkdir()
	(dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
	music_dir.mkdir()

	entered = threading.Event()
	release = threading.Event()
	constructed: list[object] = []

	class BlockingServer:
		def __init__(self, config: object) -> None:
			self.config = config
			self.should_exit = False
			self.install_signal_handlers = lambda: None
			constructed.append(self)

		def run(self) -> None:
			entered.set()
			while not self.should_exit and not release.is_set():
				release.wait(0.05)

	monkeypatch.setattr("uvicorn.Server", BlockingServer)
	android_entry.configure_android_environment(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir=str(music_dir),
		port=1829,
		host="0.0.0.0",
	)

	t1 = threading.Thread(
		target=lambda: android_entry.start_embedded_server(
			data_dir=str(data_dir),
			dist_dir=str(dist_dir),
			music_dir=str(music_dir),
			port=1829,
			already_configured=True,
		),
		daemon=True,
	)
	t1.start()
	assert entered.wait(2.0)

	mid_info = android_entry.get_server_info()
	assert mid_info["running"] is True
	assert mid_info["host_state"] == "ready"
	assert mid_info["last_error"] is None

	# Segundo arranque simultáneo no debe instanciar otro uvicorn.Server
	dup_result = android_entry.start_embedded_server(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir=str(music_dir),
		port=1829,
		already_configured=True,
	)
	assert dup_result is False
	assert len(constructed) == 1

	android_entry.stop_embedded_server()
	stopping_info = android_entry.get_server_info()
	assert stopping_info["host_state"] == "stopping"
	release.set()
	t1.join(timeout=2.0)
	assert not t1.is_alive()

	end_info = android_entry.get_server_info()
	assert end_info["running"] is False
	assert end_info["host_state"] == "stopped"


def test_start_embedded_server_marks_ready_only_after_uvicorn_startup_and_rejects_while_stopping(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""host_state permanece en starting hasta completar startup() y rechaza un segundo start en stopping."""
	import asyncio
	import threading

	from app import android_entry

	android_entry.stop_embedded_server()

	data_dir = tmp_path / "data"
	dist_dir = tmp_path / "dist"
	music_dir = tmp_path / "music"
	data_dir.mkdir()
	dist_dir.mkdir()
	(dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
	music_dir.mkdir()

	startup_entered = threading.Event()
	allow_startup_finish = threading.Event()
	allow_exit = threading.Event()
	on_ready_calls: list[bool] = []
	constructed: list[object] = []

	class StartupAwareServer:
		def __init__(self, config: object) -> None:
			self.config = config
			self.should_exit = False
			self.started = False
			self.install_signal_handlers = lambda: None
			constructed.append(self)

		async def startup(self, sockets: object = None) -> None:
			startup_entered.set()
			while not allow_startup_finish.is_set() and not self.should_exit:
				await asyncio.sleep(0.01)
			self.started = True

		def run(self) -> None:
			asyncio.run(self.startup())
			while not self.should_exit and not allow_exit.is_set():
				allow_exit.wait(0.02)

	monkeypatch.setattr("uvicorn.Server", StartupAwareServer)
	android_entry.configure_android_environment(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir=str(music_dir),
		port=1830,
		host="0.0.0.0",
	)

	t1 = threading.Thread(
		target=lambda: android_entry.start_embedded_server(
			data_dir=str(data_dir),
			dist_dir=str(dist_dir),
			music_dir=str(music_dir),
			port=1830,
			already_configured=True,
			on_ready=lambda: on_ready_calls.append(True),
		),
		daemon=True,
	)
	t1.start()
	assert startup_entered.wait(2.0)

	# Mientras startup() no terminó, sigue en starting y on_ready todavía no se disparó
	assert android_entry.get_server_info()["host_state"] == "starting"
	assert on_ready_calls == []

	allow_startup_finish.set()
	import time

	deadline = time.monotonic() + 2.0
	while android_entry.get_server_info()["host_state"] != "ready" and time.monotonic() < deadline:
		time.sleep(0.01)
	assert android_entry.get_server_info()["host_state"] == "ready"
	assert on_ready_calls == [True]

	# Pasamos a stopping y probamos un segundo start mientras el primero aún no salió
	android_entry.stop_embedded_server()
	assert android_entry.get_server_info()["host_state"] == "stopping"
	second_while_stopping = android_entry.start_embedded_server(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir=str(music_dir),
		port=1830,
		already_configured=True,
	)
	assert second_while_stopping is False
	assert len(constructed) == 1

	allow_exit.set()
	t1.join(timeout=2.0)
	assert not t1.is_alive()
	assert android_entry.get_server_info()["host_state"] == "stopped"


def test_stage_android_assets_excludes_desktop_cli_and_binary_installers(tmp_path: Path) -> None:
	"""stage_android_assets no debe empaquetar app/cli ni instaladores CLI de escritorio en el APK."""
	import shutil

	from scripts.build_android import stage_android_assets

	root = tmp_path / "repo"
	(root / "android").mkdir(parents=True)
	(root / "dist").mkdir(parents=True)
	(root / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
	shutil.copytree(Path("app"), root / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

	py_dest = stage_android_assets(root)
	assert not (py_dest / "cli").exists()
	assert not (py_dest / "infrastructure" / "binaries" / "ffmpeg.py").exists()
	assert not (py_dest / "infrastructure" / "binaries" / "fpcalc.py").exists()
	assert not (py_dest / "infrastructure" / "binaries" / "mpv.py").exists()
	assert (py_dest / "android_entry.py").is_file()


def test_isolate_container_fixture_restores_env_and_settings(tmp_path: Path) -> None:
	"""Verifica en dos fases que el fixture autouse de conftest restaure os.environ y _settings entre tests."""
	import os
	import shutil
	import subprocess
	import sys
	import textwrap

	repo_root = Path(__file__).resolve().parent.parent
	shutil.copy2(repo_root / "tests" / "conftest.py", tmp_path / "conftest.py")
	probe_test = tmp_path / "test_isolation_probe.py"
	probe_test.write_text(
		textwrap.dedent(
			"""
			import os
			from app.core import config as config_mod

			def test_phase_1_mutates_env_and_settings(tmp_path):
				os.environ["ROCKOLA_DATA_DIR"] = str(tmp_path / "dirty_data")
				os.environ["ROCKOLA_SKIP_FRONTEND_BUILD"] = "1"
				config_mod.set_settings(config_mod.Settings(port=9999))
				assert config_mod.get_settings().port == 9999

			def test_phase_2_sees_clean_restored_state():
				assert "ROCKOLA_SKIP_FRONTEND_BUILD" not in os.environ
				assert config_mod.get_settings().port != 9999
			"""
		).lstrip(),
		encoding="utf-8",
	)

	env = dict(os.environ)
	env["PYTHONPATH"] = str(repo_root)
	env.pop("ROCKOLA_SKIP_FRONTEND_BUILD", None)
	proc = subprocess.run(
		[sys.executable, "-m", "pytest", str(probe_test), "--no-cov", "-p", "no:cacheprovider", "-o", "addopts="],
		cwd=tmp_path,
		env=env,
		capture_output=True,
		text=True,
		check=False,
	)
	assert proc.returncode == 0, f"Falló aislamiento de conftest:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.asyncio
async def test_dispatch_native_command_executes_handler_without_http(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""dispatch_native_command debe encolar comandos directo en el event loop sin vuelta HTTP."""
	import asyncio

	from app import android_entry
	from app.api import commands as commands_mod
	from app.core.container import get_container

	orch = MagicMock()
	called: list[tuple[str, dict[str, object]]] = []

	async def fake_skip(_state: object, req: object, _mgr: object) -> None:
		called.append((req.cmd, {"amount": req.amount}))  # type: ignore[attr-defined]

	monkeypatch.setitem(commands_mod.COMMAND_HANDLERS, "skip", fake_skip)
	container = get_container()
	container.orchestrator = orch
	android_entry.set_server_event_loop(asyncio.get_running_loop())

	try:
		res = await asyncio.to_thread(android_entry.dispatch_native_command, "skip", '{"amount": 1}')
		assert res == "ok"
		assert called == [("skip", {"amount": 1})]
	finally:
		android_entry.set_server_event_loop(None)


@pytest.mark.asyncio
async def test_dispatch_native_command_returns_error_when_handler_raises(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Un handler que lanza excepción debe devolver 'error' en vez de éxito silencioso."""
	import asyncio

	from app import android_entry
	from app.api import commands as commands_mod
	from app.core.container import get_container

	async def _boom(_state: object, _req: object, _mgr: object) -> None:
		raise RuntimeError("fallo simulado")

	monkeypatch.setitem(commands_mod.COMMAND_HANDLERS, "skip", _boom)
	get_container().orchestrator = MagicMock()
	android_entry.set_server_event_loop(asyncio.get_running_loop())
	try:
		res = await asyncio.to_thread(android_entry.dispatch_native_command, "skip", "{}")
		assert res == "error"
	finally:
		android_entry.set_server_event_loop(None)


@pytest.mark.asyncio
async def test_dispatch_native_command_returns_timeout_when_handler_hangs(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Un handler que tarda más que el timeout debe devolver 'timeout'."""
	import asyncio

	from app import android_entry
	from app.api import commands as commands_mod
	from app.core.container import get_container

	async def _slow(_state: object, _req: object, _mgr: object) -> None:
		await asyncio.sleep(0.3)

	monkeypatch.setitem(commands_mod.COMMAND_HANDLERS, "skip", _slow)
	get_container().orchestrator = MagicMock()
	android_entry.set_server_event_loop(asyncio.get_running_loop())
	try:
		res = await asyncio.to_thread(android_entry.dispatch_native_command, "skip", "{}", 0.05)
		assert res == "timeout"
	finally:
		android_entry.set_server_event_loop(None)


def test_start_embedded_server_converts_port_bind_system_exit_into_failed_state(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""Si el puerto ya está ocupado y Uvicorn hace sys.exit(1), debe pasar a failed con last_error."""
	import socket

	from app import android_entry

	dist_dir = tmp_path / "dist"
	dist_dir.mkdir()
	(dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
	data_dir = tmp_path / "data"
	data_dir.mkdir()
	empty_music = tmp_path / "music"
	empty_music.mkdir()

	# Ocupamos un puerto libre en 127.0.0.1
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.bind(("127.0.0.1", 0))
	sock.listen(1)
	busy_port = sock.getsockname()[1]

	monkeypatch.setattr(android_entry, "_host_state", "stopped")
	monkeypatch.setattr(android_entry, "_last_error", None)
	monkeypatch.setattr(android_entry, "_active_server", None)
	monkeypatch.setattr(android_entry, "_active_thread", None)
	monkeypatch.setattr(android_entry, "_stop_requested", False)

	try:
		with pytest.raises(RuntimeError, match=str(busy_port)):
			android_entry.start_embedded_server(
				data_dir=str(data_dir),
				dist_dir=str(dist_dir),
				music_dir=str(empty_music),
				port=busy_port,
				host="127.0.0.1",
			)

		state = android_entry.get_server_info()
		assert state["host_state"] == "failed"
		assert state["last_error"]
		assert str(busy_port) in str(state["last_error"])
	finally:
		sock.close()
		monkeypatch.setattr(android_entry, "_host_state", "stopped")
		monkeypatch.setattr(android_entry, "_last_error", None)
		monkeypatch.setattr(android_entry, "_active_server", None)
		monkeypatch.setattr(android_entry, "_active_thread", None)


def test_stop_persistence_coalesces_updates_isolates_generations_and_handles_errors(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Persistencia en shutdown coalescea estados nuevos sin perder cambios ni pisar generaciones futuras."""
	import threading

	from app import android_entry

	android_entry.wait_for_stop_persistence(timeout_sec=2.0)

	vol_calls: list[int] = []
	saved_sessions: list[tuple[int, str | None]] = []
	first_entered = threading.Event()
	release_first = threading.Event()
	call_idx = 0

	def fake_flush_volume() -> None:
		nonlocal call_idx
		call_idx += 1
		vol_calls.append(call_idx)
		if call_idx == 1:
			first_entered.set()
			release_first.wait(2.0)

	class FakeOrch:
		def __init__(self, track: str) -> None:
			self.track = track

		def save_playback_session(self, force: bool = False) -> None:
			assert force is True
			saved_sessions.append((len(saved_sessions) + 1, self.track))

	monkeypatch.setattr("app.api.commands.flush_pending_volume_persist", fake_flush_volume)
	container = container_mod.get_container()
	container.orchestrator = FakeOrch("track_1.mp3")
	monkeypatch.setattr(android_entry, "_server_generation", 10)

	# 1. Primer stop queda bloqueado en flush_volume
	android_entry.stop_embedded_server()
	assert first_entered.wait(2.0)

	# 2. Mientras el primero está en vuelo, cambia el estado y llega otro stop -> debe coalescerse y NO perderse
	container.orchestrator = FakeOrch("track_2_final.mp3")
	android_entry.stop_embedded_server()
	release_first.set()
	assert android_entry.wait_for_stop_persistence(timeout_sec=2.0) is True
	assert any(track == "track_2_final.mp3" for _, track in saved_sessions)

	# 3. Si una generación nueva arrancó antes de drenar el snapshot anterior, el viejo NO debe pisar al nuevo
	saved_sessions.clear()
	call_idx = 0
	first_entered.clear()
	release_first.clear()
	container.orchestrator = FakeOrch("old_gen_track.mp3")
	android_entry.stop_embedded_server()
	assert first_entered.wait(2.0)
	container.orchestrator = FakeOrch("new_gen_track.mp3")
	monkeypatch.setattr(android_entry, "_server_generation", 11)
	android_entry.stop_embedded_server()  # encola gen 11
	release_first.set()
	assert android_entry.wait_for_stop_persistence(timeout_sec=2.0) is True
	assert saved_sessions[-1][1] == "new_gen_track.mp3"

	# 4. Errores en volumen y sesión no impiden completar ni rompen wait_for_stop_persistence
	def boom_vol() -> None:
		raise OSError("disk full")

	class BoomOrch:
		def save_playback_session(self, force: bool = False) -> None:
			raise RuntimeError("sqlite busy")

	monkeypatch.setattr("app.api.commands.flush_pending_volume_persist", boom_vol)
	container.orchestrator = BoomOrch()
	android_entry.stop_embedded_server()
	assert android_entry.wait_for_stop_persistence(timeout_sec=2.0) is True


def test_is_radio_synthesizing(monkeypatch) -> None:
	from types import SimpleNamespace

	from app import android_entry

	class FakeContainer:
		def __init__(self, orchestrator: object | None) -> None:
			self.orchestrator = orchestrator

	monkeypatch.setattr(android_entry, "get_container", lambda: FakeContainer(None))
	assert android_entry.is_radio_synthesizing() is False

	monkeypatch.setattr(
		android_entry, "get_container", lambda: FakeContainer(SimpleNamespace(is_synthesizing_radio=False))
	)
	assert android_entry.is_radio_synthesizing() is False

	monkeypatch.setattr(
		android_entry, "get_container", lambda: FakeContainer(SimpleNamespace(is_synthesizing_radio=True))
	)
	assert android_entry.is_radio_synthesizing() is True
