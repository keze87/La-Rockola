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
	monkeypatch.setattr(
		config_mod,
		"_ANDROID_MUSIC_CANDIDATES",
		(str(tmp_path / "missing"), str(android_music)),
		raising=False,
	)
	assert config_mod.get_default_music_dir() == str(android_music)


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
	(tmp_path / "dist").mkdir()
	(tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
	stale_dist = tmp_path / "android" / "app" / "src" / "main" / "assets" / "dist"
	stale_dist.mkdir(parents=True)
	(stale_dist / "stale.txt").write_text("obsoleto", encoding="utf-8")

	py_dest = stage_android_assets(tmp_path)
	assert (py_dest / "android_entry.py").is_file()
	assert not (py_dest / "__pycache__").exists()
	assert not stale_dist.exists()


def test_retag_wheel_for_android(tmp_path: Path) -> None:
	"""retag_wheel_for_android reescribe nombre, WHEEL y RECORD a etiqueta android_24_*."""
	import zipfile

	from scripts.build_android import retag_wheel_for_android

	src_whl = tmp_path / "pydantic_core-2.46.3-cp311-cp311-linux_aarch64.whl"
	wheel_meta = "Wheel-Version: 1.0\nGenerator: maturin\nRoot-Is-Purelib: false\nTag: cp311-cp311-linux_aarch64\n"
	record_meta = "pydantic_core-2.46.3.dist-info/WHEEL,sha256=old,1\npydantic_core-2.46.3.dist-info/RECORD,,\n"
	with zipfile.ZipFile(src_whl, "w") as zf:
		zf.writestr("pydantic_core/__init__.py", "# ok\n")
		zf.writestr("pydantic_core-2.46.3.dist-info/WHEEL", wheel_meta)
		zf.writestr("pydantic_core-2.46.3.dist-info/RECORD", record_meta)

	out_dir = tmp_path / "wheels"
	out_whl = retag_wheel_for_android(src_whl, out_dir)
	assert out_whl.name == "pydantic_core-2.46.3-cp311-cp311-android_24_arm64_v8a.whl"
	assert out_whl.is_file()
	with zipfile.ZipFile(out_whl, "r") as zf:
		rewritten = zf.read("pydantic_core-2.46.3.dist-info/WHEEL").decode("utf-8")
		assert "Tag: cp311-cp311-android_24_arm64_v8a" in rewritten
		assert "linux_aarch64" not in rewritten
		rec = zf.read("pydantic_core-2.46.3.dist-info/RECORD").decode("utf-8")
		assert "pydantic_core-2.46.3.dist-info/WHEEL,sha256=" in rec
		assert "sha256=old" not in rec
