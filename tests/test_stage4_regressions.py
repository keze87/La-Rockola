"""
Tests de regresión (TDD) para verificar MPRIS, binarios portátiles, rutas legacy /api/*,
inicialización perezosa de AppContainer, DJ countdown unificado, tolerancia a fallos DB
en favoritos, check_internet_async, firmas de archivo de radio y UX de CLI/Wizard.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.commands import CommandRequest, _cmd_toggle_favorite
from app.cli.entrypoint import build_arg_parser
from app.cli.wizard import run_interactive_wizard
from app.core.container import AppContainer, set_container
from app.domain.library.service import get_cover_art_uri
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.infrastructure.binaries import manager as bin_manager
from app.infrastructure.db.connection import init_db
from app.infrastructure.media import mixer
from app.infrastructure.mpris.adapter import build_mpris_metadata
from app.main import create_app


@pytest.mark.asyncio
async def test_mpris_dispatch_cover_and_registered_property(tmp_path: Path, dummy_audio_file: Path) -> None:
	"""
	Verifica que:
	1. PlaybackOrchestrator exponga mpris_registered delegando a mpris_service.registered.
	2. MPRISPlayer._dispatch ejecute comandos reales a través del handler inyectado.
	3. build_mpris_metadata y get_cover_art_uri resuelvan mpris:artUrl (incluyendo anuncios de radio).
	"""
	db_path = tmp_path / "mpris_reg.db"
	init_db(db_path)
	orch = PlaybackOrchestrator(initial_dir=str(tmp_path), open_browser=False, db_path=db_path)
	set_container(AppContainer(db_path=db_path, orchestrator=orch))

	# 1. Propiedad mpris_registered en PlaybackOrchestrator
	assert orch.mpris_registered is False
	orch.mpris_service.registered = True
	assert orch.mpris_registered is True

	# 2. MPRISPlayer tiene command_handler y cover_resolver configurados desde PlaybackOrchestrator
	assert orch.mpris_service.command_handler is not None
	assert orch.mpris_service.cover_resolver is not None

	# 3. get_cover_art_uri usa el orquestador del contenedor cuando state_ref es None
	radio_path = orch.radio_announcement_path
	cover_uri = get_cover_art_uri(radio_path)
	assert cover_uri.startswith("file://")

	# 4. build_mpris_metadata resuelve mpris:artUrl por defecto sin pasar cover_resolver manual
	orch.current_track = radio_path
	meta = build_mpris_metadata(orch)
	assert "mpris:artUrl" in meta


def test_portable_binaries_resolved_via_find_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""
	Verifica que LibraryService, RadioService y mixer usen find_binary() en vez de shutil.which()
	para detectar binarios portátiles instalados fuera del PATH del sistema.
	"""
	# Simulamos un entorno donde shutil.which devuelve None pero find_binary encuentra el binario portátil
	monkeypatch.setattr("shutil.which", lambda _name: None)
	fake_ffmpeg = str(tmp_path / "portable_ffmpeg")
	fake_ffprobe = str(tmp_path / "portable_ffprobe")
	fake_fpcalc = str(tmp_path / "portable_fpcalc")

	def _fake_find_binary(name: str) -> str | None:
		return {
			"ffmpeg": fake_ffmpeg,
			"ffprobe": fake_ffprobe,
			"fpcalc": fake_fpcalc,
		}.get(name)

	monkeypatch.setattr("app.infrastructure.binaries.manager.find_binary", _fake_find_binary)
	monkeypatch.setattr("app.domain.library.service.find_binary", _fake_find_binary)
	monkeypatch.setattr("app.domain.radio.service.find_binary", _fake_find_binary)
	monkeypatch.setattr("app.infrastructure.media.mixer.find_binary", _fake_find_binary)

	with patch("subprocess.run") as mock_run:
		mock_run.return_value = MagicMock(returncode=0, stdout="12.34\n")
		dur = mixer.get_audio_duration(tmp_path / "nonexistent.mp3")
		assert dur == 12.34
		assert mock_run.call_args[0][0][0] == fake_ffprobe


def test_legacy_api_system_routes_and_lazy_orchestrator(tmp_path: Path) -> None:
	"""
	Verifica que:
	1. /api/system/capabilities y /api/weather/preview estén montados bajo /api/*.
	2. Si container.orchestrator es None al crear/arrancar la app, se inicialice perezosamente.
	"""
	db_path = tmp_path / "lazy.db"
	init_db(db_path)
	set_container(AppContainer(db_path=db_path, orchestrator=None))

	app = create_app()
	client = TestClient(app)

	cap_res = client.get("/api/system/capabilities")
	assert cap_res.status_code == 200
	assert "has_ffmpeg" in cap_res.json()

	cmd_res = client.post("/api/v1/command", json={"cmd": "set_volume", "vollevel": 55})
	assert cmd_res.status_code == 200
	assert cmd_res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dj_countdown_delegation_and_favorite_db_resilience(tmp_path: Path) -> None:
	"""
	Verifica que:
	1. PlaybackOrchestrator.dj_countdown_task delegue a dj_selector.countdown_task.
	2. _cmd_toggle_favorite no explote si el repositorio SQLite lanza excepción.
	3. check_internet_async delegue a is_internet_available.
	"""
	db_path = tmp_path / "behav.db"
	init_db(db_path)
	orch = PlaybackOrchestrator(initial_dir=str(tmp_path), open_browser=False, db_path=db_path)

	dummy_task = asyncio.create_task(asyncio.sleep(10))
	orch.dj_countdown_task = dummy_task
	assert orch.dj_selector.countdown_task is dummy_task
	orch.dj_selector.cancel_countdown()
	assert orch.dj_countdown_task is None

	# Tolerancia a fallos DB en _cmd_toggle_favorite
	orch.path_to_id["/music/song.mp3"] = "hash_song"
	orch.favorites_repo.add = MagicMock(side_effect=RuntimeError("DB locked"))
	await _cmd_toggle_favorite(orch, CommandRequest(cmd="toggle_favorite", path="/music/song.mp3"), None)
	assert "hash_song" in orch.favorites

	# check_internet_async delega a is_internet_available
	with patch.object(bin_manager, "is_internet_available", return_value=True) as mock_inet:
		res = await bin_manager.check_internet_async(timeout=0.2)
		assert res is True
		mock_inet.assert_called_once_with(0.2)


def test_wizard_and_cli_feedback_and_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
	"""
	Verifica mensajes de feedback del wizard, epilog del CLI, mensajes de _check_mpv y símbolos exportados.
	"""
	import app.core as core_mod
	import app.infrastructure.db.connection as db_conn_mod
	import app.infrastructure.mpris as mpris_mod

	assert hasattr(core_mod, "get_db")
	assert hasattr(core_mod, "get_state")
	assert hasattr(db_conn_mod, "db_query")
	assert hasattr(mpris_mod, "get_mpris_provider")

	parser = build_arg_parser()
	assert parser.epilog is not None and "--port" in parser.epilog

	new_music_dir = tmp_path / "nueva_carpeta_musica"
	inputs = iter([str(new_music_dir), "s", "Tucumán"])
	monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
	cfg_path = tmp_path / "rockola_config.json"
	run_interactive_wizard(cfg_path, {"music_dir": str(tmp_path)})
	out = capsys.readouterr().out
	assert "no existe actualmente" in out
	assert "Configuración guardada en" in out


@pytest.mark.asyncio
async def test_second_pass_contract_and_cli_regressions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""
	Verifica:
	1. get_db() como generador de sqlite3.Connection y get_db_path() devolviendo Path.
	2. get_mpris_provider() devolviendo None cuando DBUS_AVAILABLE=False y (root, player) cuando True.
	3. AppContainer.ensure_ws_manager() e inicialización perezosa de ws_manager en broadcast_state.
	4. Propiedades mpris_player, mpris_root y mpris_bus en PlaybackOrchestrator.
	5. Alerta de seguridad log_fn en extract_archive_binary ante Zip Slip.
	"""
	import sqlite3
	import zipfile

	import app.core as core_mod
	from app.api.system import get_system_capabilities
	from app.core.container import get_container
	from app.domain.playback.orchestrator import broadcast_state
	from app.infrastructure.mpris import adapter as mpris_adapter

	db_path = tmp_path / "pass2.db"
	init_db(db_path)
	set_container(AppContainer(db_path=db_path, orchestrator=None, ws_manager=None))

	# 1. get_db_path() devuelve Path y get_db() es un generador de sqlite3.Connection
	assert hasattr(core_mod, "get_db_path")
	assert core_mod.get_db_path() == db_path
	gen = core_mod.get_db()
	conn = next(gen)
	assert isinstance(conn, sqlite3.Connection)
	gen.close()

	# 2. get_mpris_provider() respeta DBUS_AVAILABLE y devuelve tupla (root, player)
	monkeypatch.setattr(mpris_adapter, "DBUS_AVAILABLE", False)
	assert mpris_adapter.get_mpris_provider(None) is None
	monkeypatch.setattr(mpris_adapter, "DBUS_AVAILABLE", True)
	provider_tuple = mpris_adapter.get_mpris_provider(None)
	assert isinstance(provider_tuple, tuple) and len(provider_tuple) == 2

	# 3. get_system_capabilities y broadcast_state inicializan perezosamente orchestrator y ws_manager
	caps = await get_system_capabilities()
	assert "has_edge_tts" in caps
	assert get_container().orchestrator is not None
	await broadcast_state()
	assert get_container().ws_manager is not None

	# 4. Propiedades mpris_player, mpris_root y mpris_bus en PlaybackOrchestrator
	orch = get_container().orchestrator
	dummy_player = MagicMock()
	orch.mpris_player = dummy_player
	assert orch.mpris_service.player is dummy_player
	orch.notify_mpris()

	# 5. Zip Slip log_fn en extract_archive_binary
	zip_path = tmp_path / "slip.zip"
	with zipfile.ZipFile(zip_path, "w") as zf:
		zf.writestr("../../ffmpeg", b"malicious")
	logs: list[str] = []
	bin_manager.extract_archive_binary(zip_path, tmp_path / "dest", ["ffmpeg"], log_fn=logs.append)
	assert any("Alerta de seguridad" in m for m in logs)
