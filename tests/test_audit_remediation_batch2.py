"""
Pruebas para el saneamiento arquitectónico y remediación de regresiones (Lote 2).
Verifica flags de MPV, ticker de escaneo, límites POSIX, helpers de red, caché de covers,
concurrencia en play_next, PRAGMAs de SQLite y router de sistema.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _create_mock_conn():
	mock_reader = MagicMock()
	mock_reader.readline = AsyncMock(return_value=b"")
	mock_writer = MagicMock()
	mock_writer.drain = AsyncMock()
	mock_writer.write = MagicMock()
	mock_writer.close = MagicMock()
	return mock_reader, mock_writer


@pytest.mark.asyncio
async def test_mpv_flags_mpris_and_styling(monkeypatch):
	"""Verifica que AsyncMpvController inyecte los flags de subtítulos, MPRIS y wayland/x11."""
	from app.engine.mpv_controller import AsyncMpvController

	controller = AsyncMpvController()
	captured_args = []

	async def fake_create_subprocess_exec(*args, **kwargs):
		captured_args.extend(args)
		proc = MagicMock()
		proc.stdout = None
		proc.stderr = None
		proc.returncode = None
		proc.wait = AsyncMock(return_value=0)
		return proc

	monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
	monkeypatch.setattr(controller, "_check_and_raise_mpv_error", AsyncMock())
	monkeypatch.setattr(controller, "_send", AsyncMock())

	# 1. Con mpris_registered = True y display habilitado
	state_mock = MagicMock()
	state_mock.mpv_visible = True
	state_mock.mpris_registered = True

	with patch("app.engine.mpv_controller.find_binary") as mock_find_bin:

		def _find_bin(name):
			if name == "mpv":
				return "/usr/bin/mpv"
			if name == "yt-dlp":
				return "/opt/custom/bin/yt-dlp"
			return None

		mock_find_bin.side_effect = _find_bin
		monkeypatch.setattr(controller, "is_windows", False)

		env_dict = {"DISPLAY": ":0", "PATH": "/usr/bin"}
		with patch("app.engine.mpv_controller.get_clean_env", return_value=env_dict.copy()):
			with patch("os.path.exists", return_value=True):
				with patch("asyncio.open_unix_connection", return_value=_create_mock_conn()):
					await controller.start(state_ref=state_mock)

	# Verificamos flags inyectados
	assert "--load-scripts=no" in captured_args
	assert "--input-media-keys=no" in captured_args
	assert "--sub-color=#FF00FF" in captured_args
	assert "--sub-font-size=100" in captured_args
	assert "--sub-font=Pacifico" in captured_args
	assert "--wayland-app-id=mpvpip" in captured_args
	assert "--x11-name=mpvpip" in captured_args

	# 2. Con mpris_registered = False
	captured_args.clear()
	state_mock.mpris_registered = False

	with patch("app.engine.mpv_controller.find_binary") as mock_find_bin:
		mock_find_bin.side_effect = _find_bin
		with patch("app.engine.mpv_controller.get_clean_env", return_value=env_dict.copy()):
			with patch("os.path.exists", return_value=True):
				with patch("asyncio.open_unix_connection", return_value=_create_mock_conn()):
					await controller.start(state_ref=state_mock)

	assert "--load-scripts=yes" in captured_args
	assert "--input-media-keys=yes" in captured_args


@pytest.mark.asyncio
async def test_mpv_path_prepended_for_ytdlp(monkeypatch):
	"""Verifica que el directorio de yt-dlp sea antepuesto al PATH del subproceso."""
	from app.engine.mpv_controller import AsyncMpvController

	controller = AsyncMpvController()
	captured_env = {}

	async def fake_create_subprocess_exec(*args, **kwargs):
		captured_env.update(kwargs.get("env", {}))
		proc = MagicMock()
		proc.stdout = None
		proc.stderr = None
		proc.returncode = None
		proc.wait = AsyncMock(return_value=0)
		return proc

	monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
	monkeypatch.setattr(controller, "_check_and_raise_mpv_error", AsyncMock())
	monkeypatch.setattr(controller, "_send", AsyncMock())

	with patch("app.engine.mpv_controller.find_binary") as mock_find_bin:
		mock_find_bin.side_effect = lambda name: "/custom/tools/yt-dlp" if name == "yt-dlp" else "/usr/bin/mpv"
		monkeypatch.setattr(controller, "is_windows", False)
		env_dict = {"PATH": "/usr/bin:/bin"}
		with patch("app.engine.mpv_controller.get_clean_env", return_value=env_dict):
			with patch("os.path.exists", return_value=True):
				with patch("asyncio.open_unix_connection", return_value=_create_mock_conn()):
					await controller.start()

	assert captured_env["PATH"].startswith("/custom/tools")


@pytest.mark.asyncio
async def test_scan_progress_ticker():
	"""Verifica que scan_library ejecute un ticker de progreso que envíe broadcasts."""
	from app.api.v1.library import scan_library

	broadcast_mock = AsyncMock()
	mock_state = MagicMock()
	mock_state.is_scanning = False
	mock_state.initial_dir = "/tmp/music"
	mock_state.secondary_dir = None
	mock_state.tracks_cache = []

	def fake_scan_directory(target_dirs, deep):
		# Simulamos demora para que el ticker dispare al menos un tick
		import time

		time.sleep(0.5)
		return [{"path": "/tmp/music/song1.mp3"}]

	mock_state.scan_directory = fake_scan_directory
	mock_state.start_background_mood_analysis = MagicMock(return_value=None)

	with patch("app.api.v1.library.get_state", return_value=mock_state):
		with patch("app.api.v1.library.broadcast_state", broadcast_mock):
			with patch("pathlib.Path.resolve", return_value=Path("/tmp/music")):
				res = await scan_library()

	assert res["status"] == "ok"
	# El ticker corre a 400ms; con sleep de 500ms y los broadcasts inicial/final, debe haber >= 3 llamadas
	assert broadcast_mock.call_count >= 3


def test_network_module_and_no_circular_dependencies():
	"""Verifica que app.core.network provea helpers y app.core.config no use imports diferidos a entrypoint."""
	import inspect

	import app.core.config as config_mod
	import app.core.network as net_mod

	assert hasattr(net_mod, "get_local_ip")
	assert hasattr(net_mod, "normalize_url")
	assert hasattr(net_mod, "get_url_subpath")
	assert hasattr(net_mod, "get_server_urls")

	# Verificar que config re-exporta los helpers
	assert config_mod.get_local_ip is net_mod.get_local_ip
	assert config_mod.normalize_url is net_mod.normalize_url

	# Verificar que el código fuente de app.core.config no importa app.cli.entrypoint
	config_src = inspect.getsource(config_mod)
	assert "app.cli.entrypoint" not in config_src


def test_cover_mem_cache_eviction():
	"""Verifica que _COVER_MEM_CACHE no crezca indefinidamente y aplique desalojo."""
	from app.api.v1 import media

	media._COVER_MEM_CACHE.clear()
	original_max = media._MAX_COVER_MEM_CACHE
	media._MAX_COVER_MEM_CACHE = 5

	try:
		for i in range(10):
			media._set_cover_cache(f"key_{i}", (1234, 100, b"data", "image/jpeg", "etag"))

		assert len(media._COVER_MEM_CACHE) <= 5
		# Los primeros deben haber sido desalojados
		assert "key_0" not in media._COVER_MEM_CACHE
		assert "key_9" in media._COVER_MEM_CACHE
	finally:
		media._MAX_COVER_MEM_CACHE = original_max
		media._COVER_MEM_CACHE.clear()


@pytest.mark.asyncio
async def test_play_next_lock_concurrency():
	"""Verifica que play_next use un lock para serializar ejecuciones concurrentes."""
	from app.engine.state import APIState

	state = APIState()
	assert hasattr(state, "_play_next_lock")
	assert isinstance(state._play_next_lock, asyncio.Lock)

	state.tracks_cache = [
		{"path": "/tmp/a.mp3", "title": "A"},
		{"path": "/tmp/b.mp3", "title": "B"},
	]
	state.queue = ["/tmp/a.mp3", "/tmp/b.mp3"]

	played = []

	async def fake_play_track(path):
		played.append(path)
		await asyncio.sleep(0.05)

	state.play_track = fake_play_track

	# Disparar dos play_next concurrentes
	await asyncio.gather(
		state.play_next(skipped_by_user=True),
		state.play_next(skipped_by_user=True),
	)

	# Ambos deben haberse reproducido en orden secuencial sin condiciones de carrera
	assert len(played) == 2
	assert played == ["/tmp/a.mp3", "/tmp/b.mp3"]


def test_db_pragmas_on_connection(tmp_path):
	"""Verifica que get_db_connection solo ejecute busy_timeout y no WAL/synchronous en cada open."""
	from app.db import database

	db_file = tmp_path / "test_pragmas.db"
	executed_statements = []

	mock_conn = MagicMock()

	def fake_execute(sql, *args, **kwargs):
		executed_statements.append(sql.strip())
		return MagicMock()

	mock_conn.execute.side_effect = fake_execute

	with patch("app.db.database.sqlite3.connect", return_value=mock_conn):
		with database.get_db_connection(db_file) as conn:
			conn.execute("SELECT 1;")

	# busy_timeout debe estar
	assert any("busy_timeout" in s for s in executed_statements)
	# journal_mode y synchronous NO deben ejecutarse en get_db_connection
	assert not any("journal_mode" in s for s in executed_statements)
	assert not any("synchronous" in s for s in executed_statements)


def test_system_router_dual_mount():
	"""Verifica que system_router esté accesible tanto en /api como en raíz en legacy_router."""
	from app.main import app

	client = TestClient(app)
	# /system/capabilities debe responder sin 404
	resp_root = client.get("/system/capabilities")
	assert resp_root.status_code == 200

	resp_api = client.get("/api/system/capabilities")
	assert resp_api.status_code == 200

	resp_v1 = client.get("/api/v1/system/capabilities")
	assert resp_v1.status_code == 200
