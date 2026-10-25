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
	OUTROS_BY_CATEGORY,
	OUTROS_CHISMES,
	PHRASE_TO_CATEGORY,
	RADIO_OUTROS,
	REACCIONES_BY_CATEGORY,
	REACCIONES_CHISMES,
	VOICE_ELENA,
	VOICE_TOMAS,
	RadioPhrase,
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
			assert any(k in o.lower() for k in ("dj", "dijei", "bara", "carpincho", "bandejas", "batea", "consola", "cabina"))
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
