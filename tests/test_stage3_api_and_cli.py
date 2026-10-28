"""
Tests de integración y entrega (TDD) para la capa API REST, WebSocket, Middleware y CLI (Stage 3).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.commands import COMMAND_HANDLERS
from app.api.commands import router as commands_router
from app.api.library import router as library_router
from app.api.media import router as media_router
from app.api.router import api_router
from app.api.system import router as system_router
from app.api.websocket import ConnectionManager
from app.cli.entrypoint import build_arg_parser, print_startup_banner
from app.cli.wizard import _parse_selected_dir, run_interactive_wizard
from app.core.container import AppContainer, set_container
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.infrastructure.db.connection import init_db
from app.main import create_app


def _setup_test_container(tmp_path: Path, dummy_audio_file: Path) -> tuple[AppContainer, PlaybackOrchestrator]:
	db_path = tmp_path / "stage3.db"
	init_db(db_path)

	orch = PlaybackOrchestrator(
		initial_dir=str(dummy_audio_file.parent),
		open_browser=False,
		db_path=db_path,
	)
	orch.mpv = MagicMock()
	orch.mpv.is_running = True
	orch.mpv.has_display = True
	orch.mpv.start = AsyncMock()
	orch.mpv.stop = AsyncMock()
	orch.mpv.load_file = AsyncMock()
	orch.mpv.set_pause = AsyncMock()
	orch.mpv.set_volume = AsyncMock()
	orch.mpv.set_mute = AsyncMock()
	orch.mpv.seek_relative = AsyncMock()
	orch.mpv.seek_absolute = AsyncMock()
	orch.mpv.toggle_fullscreen = AsyncMock()
	orch.mpv.set_force_window = AsyncMock()
	orch.mpv.add_subtitle = AsyncMock()
	orch.mpv.stop_playback = AsyncMock()

	ws_mgr = ConnectionManager()
	container = AppContainer(
		db_path=db_path,
		orchestrator=orch,
		ws_manager=ws_mgr,
	)
	set_container(container)
	return container, orch


def test_declarative_command_dispatch_and_endpoints(tmp_path: Path, dummy_audio_file: Path) -> None:
	"""Verifica que la tabla declarativa COMMAND_HANDLERS despache todos los comandos sin if/elif gigantes."""
	assert "play" in COMMAND_HANDLERS
	assert "pause" in COMMAND_HANDLERS
	assert "move_in_playlist" in COMMAND_HANDLERS
	assert commands_router is not None
	assert library_router is not None
	assert media_router is not None
	assert system_router is not None
	assert api_router is not None

	_container, orch = _setup_test_container(tmp_path, dummy_audio_file)
	app = create_app()
	client = TestClient(app)

	track_str = str(dummy_audio_file)
	orch.tracks_cache = [
		{
			"path": track_str,
			"display_title": "Chacarera del Carpincho",
			"display_artist": "Los Carpinchos",
			"album": "Esteros",
			"duration_str": "02:30",
		}
	]
	orch.path_to_id[track_str] = "hash_1"
	orch.id_to_current_path["hash_1"] = track_str

	# Play
	res = client.post("/api/v1/command", json={"cmd": "play", "path": track_str})
	assert res.status_code == 200
	assert orch.current_track == track_str

	# Pause toggle
	res = client.post("/api/v1/command", json={"cmd": "pause"})
	assert res.status_code == 200
	assert orch.mpv_paused is True

	# Volume y mute
	client.post("/api/v1/command", json={"cmd": "set_volume", "vollevel": 75})
	assert orch.volume == 75
	client.post("/api/v1/command", json={"cmd": "vol_up"})
	assert orch.volume == 80
	client.post("/api/v1/command", json={"cmd": "set_mute", "state": True})
	assert orch.server_muted is True

	# Queue e historial
	client.post("/api/v1/command", json={"cmd": "insert_queue_item", "path": "/music/b.mp3", "index": 0})
	client.post("/api/v1/command", json={"cmd": "insert_queue_item", "path": "/music/c.mp3", "index": 1})
	assert orch.queue == ["/music/b.mp3", "/music/c.mp3"]

	client.post("/api/v1/command", json={"cmd": "move_queue_item", "index": 0, "new_index": 1})
	assert orch.queue == ["/music/c.mp3", "/music/b.mp3"]

	# Add URL esperando metadatos cuando no hay tema sonando
	orch.current_track = None
	with patch.object(orch, "fetch_yt_dlp_metadata", new=AsyncMock()) as mock_fetch:
		client.post("/api/v1/command", json={"cmd": "add_url", "path": "https://www.youtube.com/watch?v=xyz"})
		mock_fetch.assert_awaited_once_with("https://www.youtube.com/watch?v=xyz")

	# Favoritos, DJ y Radio
	client.post("/api/v1/command", json={"cmd": "toggle_favorite", "path": track_str})
	assert "hash_1" in orch.favorites
	client.post("/api/v1/command", json={"cmd": "toggle_dj_carpincho"})
	assert orch.dj_carpincho_enabled is True
	client.post("/api/v1/command", json={"cmd": "toggle_dj_safe_mode", "state": True})
	assert orch.dj_safe_mode is True
	client.post("/api/v1/command", json={"cmd": "toggle_radio_mode", "state": False})
	assert orch.radio_mode_enabled is False

	# MPV window endpoints
	res_hide = client.post("/api/v1/mpv/hide")
	assert res_hide.status_code == 200
	assert orch.mpv_visible is False
	res_show = client.post("/api/v1/mpv/show")
	assert res_show.status_code == 200
	assert orch.mpv_visible is True


def test_library_media_system_and_websocket_routes(tmp_path: Path, dummy_audio_file: Path) -> None:
	"""Verifica endpoints de biblioteca, streaming, letras, capacidades y ciclo WebSocket."""
	_container, orch = _setup_test_container(tmp_path, dummy_audio_file)
	app = create_app()
	client = TestClient(app)

	# Scan y library
	scan_res = client.get("/api/v1/scan", params={"dir": str(dummy_audio_file.parent)})
	assert scan_res.status_code == 200
	assert len(scan_res.json()["data"]) == 1

	lib_res = client.get("/api/v1/library")
	assert lib_res.status_code == 200
	assert len(lib_res.json()["data"]) == 1

	# Stream y Letras (.ass prioritario con respaldo en .lrc)
	lrc_file = dummy_audio_file.with_suffix(".lrc")
	lrc_file.write_text("[00:01.00] Cantando en el fogón\n", encoding="utf-8")

	stream_res = client.get("/api/v1/stream", params={"path": str(dummy_audio_file)})
	assert stream_res.status_code == 200

	# Stream de URL remota con yt-dlp: debe retornar 307 Temporary Redirect a la URL directa
	sample_yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
	fake_stream = "https://rr2---sn-googlevideo.com/videoplayback?expire=99999"
	# Registramos la URL en el orquestador
	orch.path_to_id[sample_yt] = sample_yt

	with patch.object(orch.ytdlp_service, "get_stream_url", new=AsyncMock(return_value=fake_stream)):
		url_stream_res = client.get("/api/v1/stream", params={"path": sample_yt}, follow_redirects=False)
		assert url_stream_res.status_code == 307
		assert url_stream_res.headers.get("location") == fake_stream

	with patch.object(orch.ytdlp_service, "get_stream_url", new=AsyncMock(return_value=None)):
		fail_stream_res = client.get("/api/v1/stream", params={"path": sample_yt}, follow_redirects=False)
		assert fail_stream_res.status_code == 502

	# Solo con .lrc presente
	lrc_res = client.get("/api/v1/lrc", params={"path": str(dummy_audio_file)})
	assert lrc_res.status_code == 200
	assert "Cantando en el fogón" in lrc_res.text

	# Con .ass presente (debe priorizar .ass sobre .lrc)
	ass_file = dummy_audio_file.with_suffix(".ass")
	ass_file.write_text(
		"[Events]\nDialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\kf10}Letra {\\kf20}ASS\n", encoding="utf-8"
	)
	ass_res = client.get("/api/v1/lrc", params={"path": str(dummy_audio_file)})
	assert ass_res.status_code == 200
	assert "Letra" in ass_res.text
	assert "ASS" in ass_res.text

	# Capabilities
	cap_res = client.get("/api/v1/system/capabilities")
	assert cap_res.status_code == 200
	assert "has_ffmpeg" in cap_res.json()

	# SubpathMiddleware
	orch.subpath = "/rockola"
	redir = client.get("/rockola", follow_redirects=False)
	assert redir.status_code == 307
	sub_cap = client.get("/rockola/api/v1/system/capabilities")
	assert sub_cap.status_code == 200
	orch.subpath = ""

	# WebSocket
	with client.websocket_connect("/ws") as ws:
		initial = ws.receive_json()
		assert initial["type"] == "state_update"

		ws.send_json({"type": "local_player_claim"})
		claim_msg = ws.receive_json()
		assert claim_msg["type"] in ("local_player_claim_result", "state_update")

		ws.send_json({"type": "local_player_update", "time_pos": 12.5, "duration": 180.0, "paused": False})
		upd_msg = ws.receive_json()
		assert upd_msg["type"] in ("state_update", "local_player_claim_result")
		assert orch.time_pos == 12.5
		assert orch.duration == 180.0

		ws.send_json({"type": "local_player_release"})


def test_frontend_routes_served_cleanly(tmp_path: Path, dummy_audio_file: Path) -> None:
	"""Verifica que las rutas de frontend (/vibra, /fogon, /queue, etc.) sirvan el index sin 404."""
	_container, _orch = _setup_test_container(tmp_path, dummy_audio_file)
	app = create_app()
	client = TestClient(app)

	routes = [
		"/",
		"/vibra",
		"/fogon",
		"/queue",
		"/ronda",
		"/top",
		"/clasicos",
		"/controls",
		"/perillas",
		"/temazos",
	]
	for route in routes:
		res = client.get(route)
		assert res.status_code == 200
		assert "no-cache" in res.headers.get("cache-control", "")
		assert "text/html" in res.headers.get("content-type", "")


def test_cli_and_wizard_helpers(tmp_path: Path, monkeypatch) -> None:
	"""Verifica el parser CLI, banner, chequeo de dependencias y wizard interactivo."""
	parser = build_arg_parser()
	args = parser.parse_args(["--port", "1800", "--no-browser", "--dir", str(tmp_path)])
	assert args.port == 1800
	assert args.open_browser is False
	assert args.dir == str(tmp_path)

	print_startup_banner(
		host="127.0.0.1",
		port=1800,
		music_dir=str(tmp_path),
		music_dir2=None,
		open_browser=False,
		weather_location="Tucumán",
		log_level="INFO",
	)

	assert _parse_selected_dir(str(tmp_path)) == str(tmp_path)

	inputs = iter(["2", "San Miguel de Tucumán"])
	monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
	cfg_path = tmp_path / "rockola_config.json"
	cfg = run_interactive_wizard(cfg_path, {"music_dir": str(tmp_path)})
	assert cfg["music_dir"] == str(tmp_path.resolve())
	assert cfg["weather_location"] == "San Miguel de Tucumán"


def test_packaging_and_preload_scripts(tmp_path: Path) -> None:
	"""Verifica que los scripts de empaquetado, precarga TTS y server.py utilicen la nueva arquitectura."""
	import server
	from scripts.build_appimage import create_appdir
	from scripts.preload_tts_cache import collect_phrases

	assert server.app is not None
	assert callable(server.main)
	assert not hasattr(server, "_StateProxy")
	assert not hasattr(server, "_ManagerProxy")

	phrases = collect_phrases()
	assert len(phrases) > 50

	dummy_bin = tmp_path / "larockola"
	dummy_bin.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
	appdir = create_appdir(dummy_bin, appdir=tmp_path / "LaRockola.AppDir")
	assert (appdir / "AppRun").is_file()
	assert (appdir / "usr" / "bin" / "larockola").is_file()
