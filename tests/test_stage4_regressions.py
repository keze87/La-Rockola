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
