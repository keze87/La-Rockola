"""
Pruebas unitarias para la categoría radial CHISMES.
Verifica bancos de frases secretas, intros/lead-ins, reacciones, outros y clasificación semántica.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.domain.radio.banks import (
	CARPINCHO_PHRASES,
	CHISMES_CARPINCHOS,
	LEAD_INS_BY_CATEGORY,
	LEAD_INS_CHISMES,
	LEAD_INS_NOVELA,
	NOVELA_VECINAL,
	OUTROS_BY_CATEGORY,
	OUTROS_CHISMES,
	OUTROS_NOVELA,
	PHRASE_TO_CATEGORY,
	RADIO_OUTROS,
	REACCIONES_BY_CATEGORY,
	REACCIONES_CHISMES,
	REACCIONES_NOVELA,
	VOICE_ELENA,
	VOICE_TOMAS,
	RadioPhrase,
	expand_phrase_variants,
	get_lead_ins_for_category,
	get_outros_for_category,
	get_reactions_for_category,
	resolve_segment_category,
)
from app.domain.radio.dialogue import build_radio_dialogue_plan
from app.infrastructure.db.connection import init_db


class TestRadioChismesSuite:
	"""Suite de verificación para la categoría radial de Chismes."""

	def test_01_banco_chismes_cantidad_minima_y_unicidad(self) -> None:
		"""El banco de chismes debe contener al menos 20 frases únicas y sustanciosas."""
		assert len(CHISMES_CARPINCHOS) >= 20
		assert len(set(CHISMES_CARPINCHOS)) == len(CHISMES_CARPINCHOS)
		for frase in CHISMES_CARPINCHOS:
			assert isinstance(frase, str)
			assert len(frase.strip()) > 20

	def test_02_lead_ins_reacciones_y_outros_definidos(self) -> None:
		"""Deben existir intros (lead-ins), reacciones de cabina y outros específicos para chismes."""
		assert len(LEAD_INS_CHISMES) >= 5
		assert len(REACCIONES_CHISMES) >= 5
		assert len(OUTROS_CHISMES) >= 5

		assert LEAD_INS_BY_CATEGORY.get("chismes") == LEAD_INS_CHISMES
		assert REACCIONES_BY_CATEGORY.get("chismes") == REACCIONES_CHISMES
		assert OUTROS_BY_CATEGORY.get("chismes") == OUTROS_CHISMES

		assert get_lead_ins_for_category("chismes") == LEAD_INS_CHISMES
		assert get_reactions_for_category("chismes") == REACCIONES_CHISMES
		assert get_outros_for_category("chismes") == OUTROS_CHISMES

	def test_03_integracion_en_carpincho_phrases_y_mapeo(self) -> None:
		"""Todas las frases de chismes deben estar en CARPINCHO_PHRASES con categoría 'chismes'."""
		phrases_dict = {p.text: p.category for p in CARPINCHO_PHRASES}
		for frase in CHISMES_CARPINCHOS:
			assert frase in phrases_dict
			assert phrases_dict[frase] == "chismes"
			assert PHRASE_TO_CATEGORY.get(frase) == "chismes"

	def test_04_resolve_segment_category_explicit_and_heuristics(self) -> None:
		"""resolve_segment_category debe reconocer 'chismes' tanto por mapeo directo como por tuplas y heurística."""
		# Tupla explícita
		assert resolve_segment_category(RadioPhrase("Cualquier texto secreto", "chismes")) == "chismes"
		assert resolve_segment_category(("Cualquier texto", "chismes")) == "chismes"

		# Pertenencia directa al banco
		primera_frase = CHISMES_CARPINCHOS[0]
		assert resolve_segment_category(primera_frase) == "chismes"

		# Heurística por palabras clave / prefijos
		assert resolve_segment_category("Radio pasillo en la orilla: nadie se esperaba esto.") == "chismes"
		assert resolve_segment_category("Se filtró la verdad sobre los carpinchos que coparon Nordelta.") == "chismes"
		assert resolve_segment_category("El pacto de silencio de la laguna se rompió anoche.") == "chismes"

	def test_05_build_radio_dialogue_plan_con_chismes(self, tmp_path: Path) -> None:
		"""El plan estructurado de diálogo debe enlazar lead-in, chisme, reacción y outro de chismes."""
		db_path = tmp_path / "test_chismes.db"
		init_db(db_path)

		chisme_sample = RadioPhrase(CHISMES_CARPINCHOS[0], "chismes")
		plan = build_radio_dialogue_plan(
			intro="¡Al aire La Rockola!",
			hora_seg="Las cinco",
			minuto_seg="de la tarde",
			fortuna=chisme_sample,
			host_voice=VOICE_TOMAS,
			cohost_voice=VOICE_ELENA,
			dialogue_mode=True,
			db_path=db_path,
			dt=datetime(2026, 10, 23, 17, 0),
		)

		categorias = [cat for _t, _v, cat, _a in plan]
		textos = [t for t, _v, _c, _a in plan]

		assert "lead_in" in categorias
		assert "fortuna" in categorias
		assert "reaccion" in categorias
		assert "salida" in categorias

		# El lead-in debe pertenecer a LEAD_INS_CHISMES
		idx_leadin = categorias.index("lead_in")
		assert any(textos[idx_leadin].startswith(li.split("{")[0].strip()) for li in LEAD_INS_CHISMES)

		# La reacción debe pertenecer a REACCIONES_CHISMES
		idx_reaccion = categorias.index("reaccion")
		assert any(textos[idx_reaccion].startswith(r.split("{")[0].strip()) for r in REACCIONES_CHISMES)

		# El outro debe ser temático de OUTROS_CHISMES
		idx_salida = categorias.index("salida")
		assert any(textos[idx_salida].startswith(o.split("{")[0].strip()) for o in OUTROS_CHISMES)

	def test_06_outro_no_termina_con_chisme_si_no_es_chisme(self) -> None:
		"""Los outros generales de RADIO_OUTROS no deben contener frases de chismes."""
		for outro_chisme in OUTROS_CHISMES:
			assert outro_chisme not in RADIO_OUTROS

		# Para una fortuna estándar, el outro no debe pertenecer a OUTROS_CHISMES
		outros_fortuna = get_outros_for_category("fortuna", outro_mode="continue")
		assert all(o not in OUTROS_CHISMES for o in outros_fortuna)

	def test_07_dj_carpincho_outro_mode_and_phrases(self) -> None:
		"""Deben existir outros para DJ Bara y get_outros_for_mode('dj') debe devolverlos."""
		from app.domain.radio.banks import RADIO_OUTROS_DJ, get_outros_for_mode

		assert len(RADIO_OUTROS_DJ) >= 5
		for o in RADIO_OUTROS_DJ:
			assert any(
				k in o.lower() for k in ("dj", "diyei", "bara", "carpincho", "bandejas", "batea", "consola", "cabina")
			)
		assert get_outros_for_mode("dj") == RADIO_OUTROS_DJ
		assert get_outros_for_category("fortuna", outro_mode="dj") == RADIO_OUTROS_DJ

	def test_08_orchestrator_returns_dj_outro_mode_when_queue_empty_and_dj_enabled(self, tmp_path: Path) -> None:
		"""PlaybackOrchestrator debe retornar outro_mode='dj' si no hay cola pero DJ Bara está activo."""
		from app.domain.playback.orchestrator import PlaybackOrchestrator

		db_path = tmp_path / "orch_dj.db"
		init_db(db_path)
		orch = PlaybackOrchestrator(db_path=db_path)
		orch.queue = []
		orch.tracks_cache = [{"path": "/music/t1.mp3", "title": "Tema 1"}]
		orch.dj_carpincho_enabled = True

		# Sin canciones elegidas en la cola pero con DJ Bara activo
		assert orch._get_expected_radio_outro_mode() == "dj"

		# Con canciones elegidas en la cola
		orch.queue = ["/music/t2.mp3"]
		assert orch._get_expected_radio_outro_mode() == "continue"

		# Con cola vacía y sin DJ Bara
		orch.queue = []
		orch.dj_carpincho_enabled = False
		assert orch._get_expected_radio_outro_mode() == "break"

	async def test_09_radio_preparation_maintains_synthesizing_state_without_silence_gap(
		self, tmp_path: Path, monkeypatch
	) -> None:
		"""Verifica que orch.is_synthesizing_radio esté en True durante la preparación de la radio evitando silencio estampa."""
		from unittest.mock import AsyncMock

		import app.domain.radio.service as radio_service_mod
		from app.core.container import AppContainer, set_container
		from app.domain.playback.orchestrator import PlaybackOrchestrator

		db_path = tmp_path / "orch_synth.db"
		init_db(db_path)
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

		state_during_prep: dict[str, bool] = {}

		from app.domain.radio.service import RadioAnnouncementResult

		async def mock_get_or_synthesize(*args, **kwargs):
			# Durante la preparación de la radio, is_synthesizing_radio DEBE estar en True
			state_during_prep["is_synthesizing"] = orch.is_synthesizing_radio
			state_during_prep["has_current_track"] = orch.current_track is not None
			return RadioAnnouncementResult(
				ok=True,
				display_title="Locución radial",
				script="Guión de prueba",
				error=None,
				outro_mode="continue",
			)

		monkeypatch.setattr(orch.radio_service, "get_or_synthesize", mock_get_or_synthesize)

		await orch.play_next(skipped_by_user=False)

		# Durante get_or_synthesize, debió estar en True (evitando que el frontend muestre 'Silencio estampa')
		assert state_during_prep.get("is_synthesizing") is True
		# Al terminar de preparar, debe pasar a reproducir la locución
		assert orch.is_synthesizing_radio is False
		assert orch.is_playing_radio_announcement is True
		assert orch.current_track == orch.radio_announcement_path

	def test_10_categoria_novela_separada_de_chismes(self, tmp_path: Path) -> None:
		"""
		Verifica que la trama de personajes ficticios ('novela') esté completamente separada
		de los chismes ribereños estándar ('chismes'), contando con sus propios bancos
		de frases, lead-ins, reacciones, outros y enrutamiento en el plan de diálogo.
		"""
		# Los bancos de frases deben estar claramente separados
		assert len(CHISMES_CARPINCHOS) >= 20
		assert len(NOVELA_VECINAL) >= 25

		# Mapeo en CARPINCHO_PHRASES: chismes -> 'chismes', novela -> 'novela'
		phrases_dict = {p.text: p.category for p in CARPINCHO_PHRASES}
		for frase in CHISMES_CARPINCHOS:
			assert phrases_dict[frase] == "chismes"
		for frase in NOVELA_VECINAL:
			assert phrases_dict[frase] == "novela"

		# Verificamos que lead-ins, reacciones y outros estén aislados por categoría
		assert len(LEAD_INS_NOVELA) >= 5
		assert len(REACCIONES_NOVELA) >= 5
		assert len(OUTROS_NOVELA) >= 5

		assert LEAD_INS_BY_CATEGORY.get("novela") == LEAD_INS_NOVELA
		assert REACCIONES_BY_CATEGORY.get("novela") == REACCIONES_NOVELA
		assert OUTROS_BY_CATEGORY.get("novela") == OUTROS_NOVELA

		assert get_lead_ins_for_category("novela") == LEAD_INS_NOVELA
		assert get_reactions_for_category("novela") == REACCIONES_NOVELA
		assert get_outros_for_category("novela") == OUTROS_NOVELA

		# No debe haber contaminación cruzada entre reacciones/outros de chismes y de novela
		assert set(REACCIONES_CHISMES).isdisjoint(set(REACCIONES_NOVELA))
		assert set(OUTROS_CHISMES).isdisjoint(set(OUTROS_NOVELA))

		# Presencia de personajes ficticios en la novela no lineal
		novela_texto = " ".join(NOVELA_VECINAL)
		for personaje in ("Anselmo", "Gladys", "Pocho", "Romina", "Rodolfo", "Walter"):
			assert personaje in novela_texto
			conteo = sum(1 for f in NOVELA_VECINAL if personaje in f)
			assert conteo >= 3, f"Personaje {personaje} debe aparecer en al menos 3 episodios"

		# Resolución semántica: pertenencia directa y heurísticas
		assert resolve_segment_category(CHISMES_CARPINCHOS[0]) == "chismes"
		assert resolve_segment_category(NOVELA_VECINAL[0]) == "novela"
		assert resolve_segment_category(RadioPhrase("Texto cualquiera", "novela")) == "novela"
		assert resolve_segment_category("Capítulo prohibido de la esquina: Doña Gladys no lo perdona.") == "novela"
		assert resolve_segment_category("En el taller de Pocho se descubrió la verdad de Anselmo.") == "novela"

		# Plan de diálogo estructurado para novela
		db_path = tmp_path / "test_novela.db"
		init_db(db_path)
		sample_novela = RadioPhrase(NOVELA_VECINAL[0], "novela")
		plan = build_radio_dialogue_plan(
			intro="¡Al aire La Rockola!",
			hora_seg="Las cinco",
			minuto_seg="de la tarde",
			fortuna=sample_novela,
			host_voice=VOICE_TOMAS,
			cohost_voice=VOICE_ELENA,
			dialogue_mode=True,
			db_path=db_path,
			dt=datetime(2026, 10, 23, 17, 0),
		)
		categorias = [cat for _t, _v, cat, _a in plan]
		textos = [t for t, _v, _c, _a in plan]

		assert "lead_in" in categorias
		assert "reaccion" in categorias
		assert "salida" in categorias

		idx_leadin = categorias.index("lead_in")
		assert any(textos[idx_leadin].startswith(li.split("{")[0].strip()) for li in LEAD_INS_NOVELA)

		idx_reaccion = categorias.index("reaccion")
		assert any(textos[idx_reaccion].startswith(r.split("{")[0].strip()) for r in REACCIONES_NOVELA)

		idx_salida = categorias.index("salida")
		assert any(textos[idx_salida].startswith(o.split("{")[0].strip()) for o in OUTROS_NOVELA)

	def test_11_preload_tts_cache_incluye_todos_los_bancos(self) -> None:
		"""
		Verifica que el script de precarga (collect_phrases) contemple la totalidad
		de las frases de chismes y novela (frases principales, lead-ins, reacciones y outros),
		así como todos los bancos de OUTROS_BY_CATEGORY y REACCIONES_BY_CATEGORY.
		"""
		from app.domain.radio.dialogue import apply_rioplatense_tts_phonetics, format_fortune_for_speech
		from scripts.preload_tts_cache import collect_phrases

		items = collect_phrases()
		item_texts = {txt for _cat, txt in items}

		# 1. Frases principales de chismes y novela
		for phrase in CHISMES_CARPINCHOS:
			formatted = format_fortune_for_speech(phrase)
			phonetic = apply_rioplatense_tts_phonetics(formatted)
			assert phonetic in item_texts, f"Chisme faltante en preload: {phrase}"

		for phrase in NOVELA_VECINAL:
			formatted = format_fortune_for_speech(phrase)
			phonetic = apply_rioplatense_tts_phonetics(formatted)
			assert phonetic in item_texts, f"Novela faltante en preload: {phrase}"

		# 2. Lead-ins de chismes y novela
		for lead in (*LEAD_INS_CHISMES, *LEAD_INS_NOVELA):
			phonetic = apply_rioplatense_tts_phonetics(lead)
			assert phonetic in item_texts, f"Lead-in faltante en preload: {lead}"

		# 3. Outros de chismes y novela (y de todas las categorías de outros)
		for cat, outros in OUTROS_BY_CATEGORY.items():
			for outro in outros:
				phonetic = apply_rioplatense_tts_phonetics(outro)
				assert phonetic in item_texts, f"Outro de [{cat}] faltante en preload: {outro}"

		# 4. Reacciones de chismes y novela (y de todas las categorías de reacciones)
		for cat, reactions in REACCIONES_BY_CATEGORY.items():
			for reaction in reactions:
				for variant in expand_phrase_variants(reaction):
					phonetic = apply_rioplatense_tts_phonetics(variant)
					assert phonetic in item_texts, f"Reacción de [{cat}] faltante en preload: {variant}"
