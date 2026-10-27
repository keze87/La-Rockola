"""
Tests de Etapa 5: Cadena de audio de estudio radial (room tone, acrossfade, solape de reacciones,
dynaudnorm, masterización broadcast), desbloqueo de .gitignore para app/infrastructure/mpv,
desempaquetado de ExceptionGroup, logging de diagnósticos, suite contextual de radio (12+ tests)
y compilación automática del frontend en el arranque CLI.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import server
from app.cli import entrypoint as cli_entrypoint
from app.core.container import AppContainer, get_container, set_container
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.domain.radio import service as radio_service_mod
from app.domain.radio.banks import (
	CARPINCHO_PHRASES,
	RADIO_INTROS,
	VOICE_ELENA,
	VOICE_TOMAS,
	RadioPhrase,
	build_radio_context,
	expand_phrase_variants,
	filter_by_context,
	phrase_fits_context,
	render_phrase,
)
from app.domain.radio.dialogue import build_radio_dialogue_plan, get_modular_time_segments
from app.infrastructure.db.connection import init_db
from app.infrastructure.media import mixer as mixer_mod


def test_mpv_controller_is_not_git_ignored() -> None:
	"""Verifica que .gitignore no ignore app/infrastructure/mpv/controller.py."""
	res = subprocess.run(
		["git", "check-ignore", "-q", "app/infrastructure/mpv/controller.py"],
		capture_output=True,
		check=False,
	)
	assert res.returncode != 0, "app/infrastructure/mpv/controller.py sigue ignorado por .gitignore"


def test_assemble_announcement_audio_full_studio_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""
	Verifica que assemble_announcement_audio ejecute:
	1. dynaudnorm por segmento
	2. acrossfade entre hora y minuto de la misma voz
	3. adelay + amix para solapar reacción corta
	4. room tone (anoisesrc) inicial y entre bloques
	5. concat filter_complex
	6. masterización final (highpass + acompressor + loudnorm)
	"""
	recorded_cmds: list[list[str]] = []

	def fake_run(cmd, *args, **kwargs):
		cmd_list = [str(c) for c in cmd]
		recorded_cmds.append(cmd_list)
		out_arg = Path(cmd_list[-1])
		if out_arg.suffix == ".mp3":
			out_arg.parent.mkdir(parents=True, exist_ok=True)
			out_arg.write_bytes(b"ID3" + b"\x00" * 128)
		res = MagicMock()
		res.returncode = 0
		res.stdout = b""
		res.stderr = b""
		return res

	monkeypatch.setattr(radio_service_mod, "find_binary", lambda name: f"/usr/bin/{name}")
	monkeypatch.setattr(radio_service_mod.subprocess, "run", fake_run)
	monkeypatch.setattr(radio_service_mod, "get_audio_duration", lambda _p, **_kw: 1.2)
	monkeypatch.setattr(radio_service_mod, "embed_cover_art_in_mp3", lambda *_a, **_kw: True)

	fake_mp3 = b"ID3" + b"\x00" * 64
	segments = [
		(fake_mp3, "intro", VOICE_TOMAS, "Buenas tardes", [(0.0, 1.2, "Buenas tardes")]),
		(fake_mp3, "hora", VOICE_TOMAS, "Son las cinco", [(0.0, 1.2, "Son las cinco")]),
		(fake_mp3, "minuto", VOICE_TOMAS, "y media", [(0.0, 1.2, "y media")]),
		(fake_mp3, "fortuna", VOICE_ELENA, "Al que madruga Dios lo ayuda", [(0.0, 1.2, "Al que madruga")]),
		(fake_mp3, "reaccion", VOICE_TOMAS, "Tal cual che", [(0.0, 0.8, "Tal cual che")]),
		(fake_mp3, "salida", VOICE_TOMAS, "Sigue la música", [(0.0, 1.2, "Sigue la música")]),
	]
	out_mp3 = tmp_path / "out_studio.mp3"
	ok = radio_service_mod.assemble_announcement_audio(segments, out_mp3)
	assert ok is True
	assert out_mp3.is_file()

	all_cmds_str = "\n".join(" ".join(c) for c in recorded_cmds)
	assert "dynaudnorm=p=0.9:s=5" in all_cmds_str
	assert "acrossfade=d=0.05" in all_cmds_str
	assert "adelay=" in all_cmds_str and "amix=inputs=2:duration=longest" in all_cmds_str
	assert "anoisesrc=c=pink:a=0.002:r=44100" in all_cmds_str
	assert "concat=n=" in all_cmds_str
	assert "highpass=f=80,acompressor=" in all_cmds_str and "loudnorm=I=-14" in all_cmds_str


@pytest.mark.asyncio
async def test_exception_group_unpacking_and_radio_logging(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""
	Verifica que:
	1. create_radio_announcement desempaquete ExceptionGroup mostrando la causa real y registre logger.warning.
	2. play_next registre logger.warning con el detalle de radio_err cuando falla la locución.
	3. mix_announcement_with_bg_track registre logger.warning cuando ffmpeg falla.
	"""
	db_path = tmp_path / "log_test.db"
	init_db(db_path)

	async def failing_synthesize(**_kwargs):
		raise ValueError("Fallo de red simulado en edge-tts")

	monkeypatch.setattr(radio_service_mod, "HAS_EDGE_TTS", True)
	monkeypatch.setattr(radio_service_mod, "edge_tts", MagicMock())
	monkeypatch.setattr(radio_service_mod, "synthesize_segment", failing_synthesize)

	with caplog.at_level("WARNING"):
		res = await radio_service_mod.create_radio_announcement(
			tmp_path / "fail.mp3",
			db_path=db_path,
			timeout=0.5,
			max_retries=1,
		)
	assert res.ok is False
	assert "ValueError: Fallo de red simulado en edge-tts" in (res.error or "")
	assert any("ValueError: Fallo de red simulado en edge-tts" in rec.message for rec in caplog.records)

	# Verificar log de play_next cuando falla get_or_synthesize
	orch = PlaybackOrchestrator(db_path=db_path)
	orch.mpv.start = AsyncMock()
	orch.mpv.load_file = AsyncMock()
	orch.mpv.set_force_window = AsyncMock()
	orch.current_track = "/musica/tema1.mp3"
	orch.queue = ["/musica/tema2.mp3"]
	orch.radio_mode_enabled = True
	orch.last_radio_time = 0.0
	orch.radio_time_until_next = 1.0
	set_container(AppContainer(db_path=db_path, orchestrator=orch))

	monkeypatch.setattr(radio_service_mod, "check_internet_async", AsyncMock(return_value=True))
	assert orch.radio_service.is_available is True
	monkeypatch.setattr(
		orch.radio_service,
		"get_or_synthesize",
		AsyncMock(return_value=(False, "", "", "Error simulado de locutor")),
	)

	caplog.clear()
	with caplog.at_level("WARNING"):
		await orch.play_next(skipped_by_user=False)
	assert any("Error simulado de locutor" in rec.message for rec in caplog.records)

	# Verificar log de mix_announcement_with_bg_track cuando ffmpeg falla
	voice_f = tmp_path / "v.mp3"
	bg_f = tmp_path / "bg.mp3"
	voice_f.write_bytes(b"ID3" + b"\x00" * 32)
	bg_f.write_bytes(b"ID3" + b"\x00" * 32)
	monkeypatch.setattr(mixer_mod, "find_binary", lambda _n: "/usr/bin/ffmpeg")
	bad_proc = MagicMock(returncode=1, stderr=b"Error de filtro ffmpeg")
	monkeypatch.setattr(mixer_mod.subprocess, "run", lambda *_a, **_kw: bad_proc)

	caplog.clear()
	with caplog.at_level("WARNING"):
		mixed_ok = mixer_mod.mix_announcement_with_bg_track(voice_f, tmp_path / "mixed.mp3", bg_f)
	assert mixed_ok is False
	assert any("ffmpeg falló al mezclar cortina musical" in rec.message for rec in caplog.records)


def test_server_and_entrypoint_build_frontend_and_console_encoding(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""Verifica que build_frontend y configure_console_encoding estén expuestos en entrypoint y server."""
	assert hasattr(cli_entrypoint, "build_frontend")
	assert hasattr(server, "build_frontend")
	assert hasattr(server, "configure_console_encoding")
	assert hasattr(server, "enable_system_site_packages")


class TestRadioContextualAndCoherenceSuite:
	"""Suite de 12 tests contextuales de radio: franja, género, estación, placeholders, coherencia y top-played."""

	def test_01_time_slots_mapping(self) -> None:
		assert build_radio_context(datetime(2026, 3, 10, 3, 0)).franja == "madrugada"
		assert build_radio_context(datetime(2026, 3, 10, 8, 0)).franja == "mañana"
		assert build_radio_context(datetime(2026, 3, 10, 12, 30)).franja == "mediodia"
		assert build_radio_context(datetime(2026, 3, 10, 16, 0)).franja == "tarde"
		assert build_radio_context(datetime(2026, 3, 10, 22, 0)).franja == "noche"

	def test_02_southern_hemisphere_seasons(self) -> None:
		assert build_radio_context(datetime(2026, 1, 15, 12, 0)).estacion == "verano"
		assert build_radio_context(datetime(2026, 4, 15, 12, 0)).estacion == "otoño"
		assert build_radio_context(datetime(2026, 7, 15, 12, 0)).estacion == "invierno"
		assert build_radio_context(datetime(2026, 10, 15, 12, 0)).estacion == "primavera"

	def test_03_weekend_and_weekday_detection(self) -> None:
		sat_ctx = build_radio_context(datetime(2026, 10, 17, 18, 0))  # Sábado
		mon_ctx = build_radio_context(datetime(2026, 10, 19, 18, 0))  # Lunes
		assert sat_ctx.es_finde is True and sat_ctx.dia_nombre == "sábado"
		assert mon_ctx.es_finde is False and mon_ctx.dia_nombre == "lunes"

	def test_04_temperature_overrides_season_mismatch(self) -> None:
		cold_summer = build_radio_context(datetime(2026, 1, 15, 10, 0), temp_c=8)
		hot_summer = build_radio_context(datetime(2026, 1, 15, 15, 0), temp_c=32)
		assert phrase_fits_context("Qué calorón de verano", cold_summer, category="alerta_criolla") is False
		assert phrase_fits_context("Qué calorón de verano", hot_summer, category="alerta_criolla") is True

	def test_05_placeholder_rendering_by_slot_and_gender(self) -> None:
		morning_ctx = build_radio_context(datetime(2026, 10, 17, 9, 0))
		night_ctx = build_radio_context(datetime(2026, 10, 17, 22, 0))
		template = "{saludo} {vocativo}, qué linda está {momento} con {cohost}."
		rendered_m = render_phrase(template, morning_ctx, addressee_voice=VOICE_ELENA, cohost_name="Elena")
		rendered_n = render_phrase(template, night_ctx, addressee_voice=VOICE_TOMAS, cohost_name="Tomás")
		assert "Buen día" in rendered_m and "comadre" in rendered_m and "la mañana" in rendered_m
		assert "Buenas noches" in rendered_n and "compadre" in rendered_n and "la noche" in rendered_n

	def test_06_expand_phrase_variants_removes_placeholders(self) -> None:
		variants = expand_phrase_variants("{saludo} {vocativo} en {momento} con {companero}")
		assert len(variants) >= 4
		assert all("{" not in v and "}" not in v for v in variants)

	def test_07_gender_inflection_between_tomas_and_elena(self, tmp_path: Path) -> None:
		db_path = tmp_path / "gender.db"
		init_db(db_path)
		ctx = build_radio_context(datetime(2026, 10, 17, 18, 0))
		intro = "Bienvenidos"
		hora_s, min_s, _ = get_modular_time_segments(datetime(2026, 10, 17, 18, 30))
		fortuna = RadioPhrase("El mate se toma amargo.", "fortuna")
		outro = "Seguimos con más música."
		plan = build_radio_dialogue_plan(
			intro=intro,
			hora_seg=hora_s,
			minuto_seg=min_s,
			fortuna=fortuna,
			outro=outro,
			host_voice=VOICE_ELENA,
			cohost_voice=VOICE_TOMAS,
			is_system_fortune=False,
			dialogue_mode=True,
			db_path=db_path,
			ctx=ctx,
		)
		assert any(v == VOICE_ELENA for _t, v, _c, _a in plan)
		assert any(v == VOICE_TOMAS for _t, v, _c, _a in plan)

	def test_08_filter_by_context_excludes_incompatible_slots(self) -> None:
		morning_ctx = build_radio_context(datetime(2026, 10, 17, 9, 0))
		candidates = [
			"Acompañando la trasnochada y el turno noche.",
			"Arrancando con este solcito de la mañana.",
		]
		filtered = filter_by_context(candidates, morning_ctx)
		assert filtered == ["Arrancando con este solcito de la mañana."]

	def test_08b_filter_by_context_returns_empty_when_all_candidates_incompatible(self) -> None:
		"""Si ningún candidato cumple las reglas contextuales, debe retornar una lista vacía y no la lista original."""
		morning_ctx = build_radio_context(datetime(2026, 10, 17, 9, 0))
		candidates = [
			"Acompañando la trasnochada y el turno noche.",
			"Cuadrilla de la noche metiendo garra.",
		]
		filtered = filter_by_context(candidates, morning_ctx)
		assert filtered == []

	def test_08c_callers_handle_empty_filter_by_context_gracefully(
		self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""Comprueba que los generadores de diálogo y frases radiales tengan políticas de fallback si filter_by_context vacía el pool."""
		from app.domain.radio.dialogue import generate_modular_radio_script
		from app.domain.radio.nlp import select_radio_phrase

		db_path = tmp_path / "fallback.db"
		init_db(db_path)
		ctx = build_radio_context(datetime(2026, 10, 17, 9, 0))

		# Forzamos que filter_by_context retorne [] simulando incompatibilidad absoluta
		monkeypatch.setattr("app.domain.radio.dialogue.filter_by_context", lambda candidates, _ctx, _cat=None: [])
		monkeypatch.setattr("app.domain.radio.nlp.filter_by_context", lambda candidates, _ctx, _cat=None: [])

		# 1. select_radio_phrase no debe reventar con ValueError si filter_by_context da vacío
		phrase, _is_sys = select_radio_phrase(force_system_fortune=False, db_path=db_path, ctx=ctx)
		assert phrase is not None

		# 2. build_radio_dialogue_plan con clima y diálogo no debe reventar si filter_by_context da vacío
		plan = build_radio_dialogue_plan(
			intro=None,
			hora_seg="Son las nueve",
			minuto_seg="y cinco",
			fortuna=CARPINCHO_PHRASES[0],
			outro=None,
			weather_text="Día soleado",
			weather_condition="soleado",
			dialogue_mode=True,
			db_path=db_path,
			ctx=ctx,
		)
		assert len(plan) >= 5

		# 3. generate_modular_radio_script no debe fallar con IndexError
		script_parts = generate_modular_radio_script(dt=datetime(2026, 10, 17, 9, 0))
		assert len(script_parts) == 9

	def test_08d_carpincho_fortunes_contains_only_wisdom_and_not_other_categories(self) -> None:
		"""Verifica que CARPINCHO_FORTUNES contenga exclusivamente sabiduría y no mute con avisos, alertas ni chismes."""
		from app.domain.radio.banks import (
			ALERTAS_INCOMODIDAD_CRIOLLA,
			CARPINCHO_ADS,
			CARPINCHO_FORTUNES,
			CARPINCHO_SABIDURIA,
			CHISMES_CARPINCHOS,
			NOVELA_VECINAL,
			TRANSITO_FLUVIAL_Y_CAMINOS,
		)

		assert CARPINCHO_FORTUNES == CARPINCHO_SABIDURIA
		# Ninguna frase de otras categorías debe estar en CARPINCHO_FORTUNES
		for category_bank in (
			ALERTAS_INCOMODIDAD_CRIOLLA,
			CARPINCHO_ADS,
			CHISMES_CARPINCHOS,
			NOVELA_VECINAL,
			TRANSITO_FLUVIAL_Y_CAMINOS,
		):
			for phrase in category_bank:
				assert phrase not in CARPINCHO_FORTUNES

	def test_09_lead_in_and_reaction_coherence_for_fortune(self, tmp_path: Path) -> None:
		db_path = tmp_path / "coherence.db"
		init_db(db_path)
		ctx = build_radio_context(datetime(2026, 10, 17, 19, 0))
		hora_s, min_s, _ = get_modular_time_segments(datetime(2026, 10, 17, 19, 15))
		plan = build_radio_dialogue_plan(
			intro=RADIO_INTROS[0],
			hora_seg=hora_s,
			minuto_seg=min_s,
			fortuna=CARPINCHO_PHRASES[0],
			outro="Sigue sonando.",
			host_voice=VOICE_TOMAS,
			cohost_voice=VOICE_ELENA,
			is_system_fortune=True,
			dialogue_mode=True,
			db_path=db_path,
			ctx=ctx,
		)
		cats = [cat for _t, _v, cat, _a in plan]
		assert "lead_in" in cats
		assert "fortuna" in cats
		assert cats.index("lead_in") < cats.index("fortuna")

	def test_10_modular_time_segments_exact_and_quarter_hours(self) -> None:
		h0, m0, full0 = get_modular_time_segments(datetime(2026, 10, 17, 13, 0))
		h15, m15, _ = get_modular_time_segments(datetime(2026, 10, 17, 14, 15))
		_h30, m30, _ = get_modular_time_segments(datetime(2026, 10, 17, 14, 30))
		assert "una" in h0.lower() and m0 is None and "una" in full0.lower()
		assert "dos" in h15.lower() and m15 is not None and "cuarto" in m15.lower()
		assert m30 is not None and "media" in m30.lower()

	def test_11_radio_announcement_excluded_from_top_played_and_history(self, tmp_path: Path) -> None:
		db_path = tmp_path / "top_excl.db"
		init_db(db_path)
		orch = PlaybackOrchestrator(db_path=db_path)
		ann_path = orch.radio_announcement_path
		orch._register_play_stat(ann_path)
		orch.history_repo.add_play("/tmp/radio_announcement.mp3", 100.0)
		top = orch.history_repo.get_top_played()
		assert all("radio_announcement.mp3" not in r["track_id"] for r in top)

	def test_12_coverage_config_includes_app_and_server(self) -> None:
		ini_text = Path("pytest.ini").read_text(encoding="utf-8")
		assert "--cov=app" in ini_text
		assert "--cov=server" in ini_text


def test_build_frontend_skips_when_dist_exists_and_uses_clean_env(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""
	Verifica que build_frontend en entrypoint.py no recompile si dist/index.html ya existe
	(a menos que force=True), y que pase env=get_clean_env() a subprocess.run.
	"""
	pkg = tmp_path / "package.json"
	pkg.write_text("{}", encoding="utf-8")
	(tmp_path / "node_modules").mkdir()
	dist_dir = tmp_path / "dist"
	dist_dir.mkdir()
	(dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")

	calls: list[tuple[list[str], dict]] = []

	def fake_run(cmd, **kwargs):
		calls.append((list(cmd), kwargs))
		return MagicMock(returncode=0)

	monkeypatch.setattr(cli_entrypoint.subprocess, "run", fake_run)
	monkeypatch.setattr(cli_entrypoint.sys, "argv", ["larockola"])

	# Con dist/index.html presente y force=False, no debe invocar npm run build
	cli_entrypoint.build_frontend(frontend_dir=tmp_path)
	assert len(calls) == 0

	# Con force=True (o sin dist/index.html), debe invocar npm pasando env
	cli_entrypoint.build_frontend(frontend_dir=tmp_path, force=True)
	assert len(calls) == 1
	assert calls[0][1].get("env") is not None


@pytest.mark.asyncio
async def test_mpv_start_falls_back_to_container_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""
	Verifica que AsyncMpvController.start() obtenga el estado del contenedor activo
	cuando self.state_ref es None.
	"""
	import app.infrastructure.mpv.controller as mpv_mod
	from app.infrastructure.mpv.controller import AsyncMpvController

	db_path = tmp_path / "mpv_fallback.db"
	init_db(db_path)
	orch = PlaybackOrchestrator(db_path=db_path)
	orch.mpv_visible = False
	orch.mpris_service.registered = True
	set_container(AppContainer(db_path=db_path, orchestrator=orch))

	captured_args: list[str] = []

	class DummyProc:
		returncode = None
		stdout = None
		stderr = None

		async def wait(self):
			return 0

	async def fake_subproc(*args, **_kwargs):
		captured_args.extend(args)
		return DummyProc()

	monkeypatch.setattr(mpv_mod.asyncio, "create_subprocess_exec", fake_subproc)
	monkeypatch.setattr(mpv_mod.os.path, "exists", lambda _p: True)
	monkeypatch.setattr(mpv_mod.asyncio, "open_unix_connection", AsyncMock(return_value=(AsyncMock(), AsyncMock())))

	standalone_mpv = AsyncMpvController(state_ref=None)
	monkeypatch.setattr(standalone_mpv, "command", AsyncMock())
	await standalone_mpv.start()

	assert standalone_mpv.state_ref is orch
	assert "--force-window=no" in captured_args
	assert "--load-scripts=no" in captured_args


@pytest.mark.asyncio
async def test_orchestrator_manager_proxy_and_dummy_mpv_send_fallback(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""
	Verifica:
	1. Que _has_local_player consulte limpiamente container.ws_manager sin instanciarlo de prepo.
	2. Que un objeto dummy adaptado con ensure_mpv_methods en test funcione correctamente.
	"""
	from types import SimpleNamespace

	from app.api.commands import handle_command_endpoint
	from app.api.schemas import CommandRequest
	from app.infrastructure.mpv.controller import ensure_mpv_methods

	db_path = tmp_path / "proxy_mpv.db"
	init_db(db_path)
	orch = PlaybackOrchestrator(db_path=db_path)
	container = get_container()
	container.orchestrator = orch

	# 1. Sin ws_manager en container, no hay local player
	container.ws_manager = None
	assert orch._has_local_player() is False

	# 2. Con ws_manager en container
	fake_mgr = SimpleNamespace(local_player_ws=MagicMock(send_json=AsyncMock()), broadcast_json=AsyncMock())
	container.ws_manager = fake_mgr
	assert orch._has_local_player() is True

	container.ws_manager = SimpleNamespace(local_player_ws=None, broadcast_json=AsyncMock())
	assert orch._has_local_player() is False

	sent_payloads: list[str] = []

	async def dummy_send(payload: str) -> None:
		sent_payloads.append(payload)

	raw_dummy_mpv = SimpleNamespace(
		_send=dummy_send,
		start=AsyncMock(),
		is_running=True,
		has_display=True,
	)
	dummy_mpv = ensure_mpv_methods(raw_dummy_mpv)
	orch.mpv = dummy_mpv

	await orch.play_track("/musica/cancion.mp3")
	assert any("loadfile" in p for p in sent_payloads)

	await handle_command_endpoint(CommandRequest(cmd="fullscreen"))
	assert any("fullscreen" in p for p in sent_payloads)

	await handle_command_endpoint(CommandRequest(cmd="seek", amount=15.0))
	assert any('"seek"' in p for p in sent_payloads)


def test_cli_dependency_error_messages_and_arg_parser_epilog(
	monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
	"""
	Verifica que check_dependencies imprima los encabezados y saludo criollo al faltar
	requisitos, y que build_arg_parser conserve el epilog completo con --host y --debug.
	"""
	parser = cli_entrypoint.build_arg_parser()
	assert parser.epilog is not None
	assert "--host 127.0.0.1" in parser.epilog
	assert "--debug" in parser.epilog

	monkeypatch.setattr(cli_entrypoint.sys, "argv", ["larockola"])
	monkeypatch.setattr(
		cli_entrypoint,
		"_check_python_packages",
		lambda **_kw: ([("fastapi", "pip install fastapi")], []),
	)
	monkeypatch.setattr(cli_entrypoint, "_check_mpv", lambda **_kw: ("mpv", "sudo apt install mpv"))
	monkeypatch.setattr(cli_entrypoint, "_check_ytdlp", lambda **_kw: None)
	monkeypatch.setattr(cli_entrypoint, "_check_ffmpeg", lambda **_kw: None)
	monkeypatch.setattr(cli_entrypoint, "_check_fpcalc", lambda **_kw: None)

	with pytest.raises(SystemExit):
		cli_entrypoint.check_dependencies(force=True)

	err = capsys.readouterr().err
	assert "📦 Paquetes de Python que faltan en la ronda:" in err
	assert "🛠️ Herramientas del sistema (sin esto el carpincho no canta):" in err
	assert "Tranqui, instalá eso, cambiale la yerba al mate y volvé a correr el script. ¡Te espero! 🦦🧉🎶" in err


@pytest.mark.asyncio
async def test_restored_diagnostic_logs_in_orchestrator_commands_and_library(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""
	Verifica los logs restaurados enPlaybackOrchestrator, commands.py y LibraryService.
	"""
	import time

	from app.api.commands import handle_command_endpoint, mpv_hide, mpv_show
	from app.api.schemas import CommandRequest

	db_path = tmp_path / "diag_logs.db"
	init_db(db_path)
	orch = PlaybackOrchestrator(db_path=db_path)
	orch.mpv.start = AsyncMock()
	orch.mpv.load_file = AsyncMock()
	orch.mpv.set_pause = AsyncMock()
	orch.mpv.set_volume = AsyncMock()
	orch.mpv.set_mute = AsyncMock()
	orch.mpv.seek_absolute = AsyncMock()
	orch.mpv.stop_playback = AsyncMock()
	orch.mpv.set_force_window = AsyncMock()
	orch.mpv.is_running = True
	orch.mpv.has_display = True
	set_container(AppContainer(db_path=db_path, orchestrator=orch))

	with caplog.at_level("INFO"):
		orch.current_track = "/musica/tema.mp3"
		await orch.handle_mpv_restarted()
		assert any("El MPV revivió" in r.message for r in caplog.records)

		caplog.clear()
		orch.last_track_change = time.time()
		await orch.handle_track_stopped()
		assert any("Recibí un 'stop' pero el tema cambió hace menos de 1.5s" in r.message for r in caplog.records)

		caplog.clear()
		orch.current_track = "/musica/tema.mp3"
		orch.queue = []
		orch.tracks_cache = [{"path": "/musica/tema.mp3", "display_title": "Tema"}]
		orch.history = ["/musica/tema.mp3"]
		orch.dj_carpincho_enabled = True
		await orch.play_next(skipped_by_user=True)
		assert any("DJ Bara se quedó sin temas nuevos esta sesión." in r.message for r in caplog.records)

		caplog.clear()
		await handle_command_endpoint(CommandRequest(cmd="toggle_dj_carpincho"))
		assert any("DJ Bara cambiado a:" in r.message for r in caplog.records)

		caplog.clear()
		monkeypatch.setattr("app.core.config.get_config_path", lambda *_a: tmp_path / "cfg.json")
		await handle_command_endpoint(CommandRequest(cmd="set_weather_location", location="Rosario"))
		assert any("Ubicación del clima actualizada a: Rosario" in r.message for r in caplog.records)

		caplog.clear()
		await mpv_hide()
		assert any("Reiniciando MPV para ocultar la ventana..." in r.message for r in caplog.records)

		caplog.clear()
		await mpv_show()
		assert any("Reiniciando MPV para mostrar la ventana..." in r.message for r in caplog.records)

		caplog.clear()
		orch.library_service.scan_directory([tmp_path], extract_mood=False)
		assert any("¡Listo el escaneo, maestro!" in r.message for r in caplog.records)

	caplog.clear()
	monkeypatch.setattr(orch.favorites_repo, "add", MagicMock(side_effect=RuntimeError("DB bloqueada")))
	with caplog.at_level("ERROR"):
		await handle_command_endpoint(CommandRequest(cmd="toggle_favorite", path="/musica/fav.mp3"))
	assert any("Error guardando favorito:" in r.message and r.levelname == "ERROR" for r in caplog.records)
