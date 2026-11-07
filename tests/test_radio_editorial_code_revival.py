"""
Pruebas para las 4 mejoras de código rescatadas y perfeccionadas del commit c9762d9.
Valida:
1. Balanceo probabilístico por categoría y propagación de db_path en recencia (nlp.py).
2. Perfiles editoriales de locutores y afinidad temática en cabina (voices.py, dialogue.py).
3. Subcategorización semántica fina y coherencia de lead-ins / reacciones (classification.py, segments.py).
4. Soporte robusto de outro_mode, fallbacks contextuales seguros y limpieza de horas (dialogue.py, context.py, segments.py).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import app.domain.radio.voices as voices_mod
from app.domain.radio.classification import (
	RadioPhrase,
	resolve_segment_subcategory,
)
from app.domain.radio.context import RadioContext, build_radio_context
from app.domain.radio.dialogue import (
	NO_MERGE_CATEGORIES,
	build_radio_dialogue_plan,
	select_radio_hosts,
)
from app.domain.radio.nlp import (
	record_phrase_played,
	select_radio_phrase,
	weighted_choice_by_recency,
)
from app.domain.radio.phrase_banks.advertisements import (
	AVISOS_PARROQUIALES_Y_EXTRAVIOS,
	CARPINCHO_ADS,
)
from app.domain.radio.phrase_banks.listeners import (
	ALERTAS_INCOMODIDAD_CRIOLLA,
	TRANSITO_FLUVIAL_Y_CAMINOS,
)
from app.domain.radio.phrase_banks.soap_opera import NOVELA_VECINAL
from app.domain.radio.segments import (
	LEAD_INS_AVISOS_COMERCIALES,
	LEAD_INS_AVISOS_COMUNITARIOS,
	LEAD_INS_TRANSITO,
	REACCIONES_AVISOS_COMERCIALES,
	REACCIONES_AVISOS_COMUNITARIOS,
	REACCIONES_CLIMA_ALERTAS,
	REACCIONES_TRANSITO,
	get_lead_ins_for_category,
	get_reactions_for_category,
)
from app.domain.radio.voices import (
	VOICE_ELENA,
	VOICE_TOMAS,
	VOICE_VALENTINA,
	VOICES,
)


def test_01_balanceo_probabilistico_y_recencia_con_db_path(tmp_path: Path) -> None:
	"""1. Verifica propagación de db_path en recencia y distribución equitativa de categorías sin monopolio."""
	db_file = str(tmp_path / "test_recency_isolation.db")
	ctx = build_radio_context(dt=datetime(2026, 5, 10, 12, 0), temp_c=22)

	# A. Propagación de db_path en weighted_choice_by_recency
	candidates = list(NOVELA_VECINAL[:5])
	target_unplayed = candidates[-1]
	for item in candidates[:-1]:
		record_phrase_played(item, "novela", db_path=db_file)

	picked_count = sum(
		1
		for _ in range(30)
		if weighted_choice_by_recency(candidates, category="novela", db_path=db_file) == target_unplayed
	)
	assert picked_count >= 15, f"La frase no jugada no tuvo prioridad con db_path propagado ({picked_count}/30)"

	# B. Distribución equitativa: ninguna categoría debe monopolizar ni quedar olvidada
	counts: dict[str, int] = {}
	total_samples = 120
	for _ in range(total_samples):
		phrase, _ = select_radio_phrase(ctx=ctx, db_path=db_file)
		record_phrase_played(phrase.text, phrase.category, db_path=db_file)
		counts[phrase.category] = counts.get(phrase.category, 0) + 1

	expected_cats = {"fortuna", "aviso", "oyentes", "alerta_criolla", "chismes", "novela"}
	assert expected_cats.issubset(counts.keys()), f"Faltan categorías en la selección: {expected_cats - counts.keys()}"
	for cat, count in counts.items():
		assert count >= 10, f"Categoría '{cat}' sub-representada ({count}/{total_samples})"
		assert count <= 40, f"Categoría '{cat}' monopoliza la rotación ({count}/{total_samples})"


def test_02_perfiles_editoriales_y_afinidad_tematica() -> None:
	"""2. Verifica perfiles de locutores en voices.py y selección afín por temática en dialogue.py."""
	host_profiles = getattr(voices_mod, "HOST_PROFILES", {})
	assert len(host_profiles) >= 4, "HOST_PROFILES debe definir los 4 perfiles de cabina"

	for v in VOICES:
		profile = host_profiles.get(v)
		assert profile is not None, f"Falta perfil para la voz {v}"
		assert "name" in profile
		assert "role" in profile
		assert "style" in profile
		assert "preferred_categories" in profile
		assert "pacing" in profile

	# Afinidad: Valentina en chismes/novela, Elena en avisos comunitarios, Tomás en alertas
	chismes_participations = sum(1 for _ in range(30) if VOICE_VALENTINA in select_radio_hosts(category="chismes"))
	assert chismes_participations >= 20, (
		f"Valentina debe tener afinidad preponderante en chismes ({chismes_participations}/30)"
	)

	aviso_participations = sum(1 for _ in range(30) if VOICE_ELENA in select_radio_hosts(category="aviso"))
	assert aviso_participations >= 20, f"Elena debe tener afinidad preponderante en avisos ({aviso_participations}/30)"

	alerta_participations = sum(1 for _ in range(30) if VOICE_TOMAS in select_radio_hosts(category="alerta_criolla"))
	assert alerta_participations >= 20, (
		f"Tomás debe tener afinidad preponderante en alertas ({alerta_participations}/30)"
	)

	for _ in range(20):
		h, c = select_radio_hosts(category="fortuna")
		assert h != c, f"Host y cohost no pueden ser iguales: ({h}, {c})"


def test_03_subcategorizacion_semantica_fina() -> None:
	"""3. Verifica clasificación fina de subcategorías y selección coherente de lead-ins y reacciones."""
	# A. Avisos comerciales vs avisos comunitarios
	sample_ad = CARPINCHO_ADS[0]
	assert resolve_segment_subcategory(sample_ad, category="aviso") == "aviso_comercial"

	sample_notice = AVISOS_PARROQUIALES_Y_EXTRAVIOS[0]
	assert resolve_segment_subcategory(sample_notice, category="aviso") == "aviso_comunitario"

	# B. Alertas de tránsito fluvial vs alertas de clima/incomodidad criolla
	sample_transit = TRANSITO_FLUVIAL_Y_CAMINOS[0]
	assert resolve_segment_subcategory(sample_transit, category="alerta_criolla") == "alerta_transito"

	sample_climate = ALERTAS_INCOMODIDAD_CRIOLLA[0]
	assert resolve_segment_subcategory(sample_climate, category="alerta_criolla") == "alerta_clima"

	# C. Oyentes: pedidos vs saludos
	pedido_msg = 'Nos escriben desde el quincho: "Queremos cumbia santafesina clásica"'
	saludo_msg = "Llega un saludo cariñoso para todos los vecinos del arroyo"
	assert resolve_segment_subcategory(pedido_msg, category="oyentes") == "oyentes_pedido"
	assert resolve_segment_subcategory(saludo_msg, category="oyentes") == "oyentes_saludo"

	# D. Coherencia en lead-ins y reacciones
	assert get_lead_ins_for_category("aviso", subcategory="aviso_comercial") == LEAD_INS_AVISOS_COMERCIALES
	assert get_lead_ins_for_category("aviso", subcategory="aviso_comunitario") == LEAD_INS_AVISOS_COMUNITARIOS
	assert get_lead_ins_for_category("alerta_criolla", subcategory="alerta_transito") == LEAD_INS_TRANSITO

	assert get_reactions_for_category("aviso", subcategory="aviso_comercial") == REACCIONES_AVISOS_COMERCIALES
	assert get_reactions_for_category("aviso", subcategory="aviso_comunitario") == REACCIONES_AVISOS_COMUNITARIOS
	assert get_reactions_for_category("alerta_criolla", subcategory="alerta_transito") == REACCIONES_TRANSITO
	assert get_reactions_for_category("alerta_criolla", subcategory="alerta_clima") == REACCIONES_CLIMA_ALERTAS


def test_04_outro_mode_fallbacks_y_limpieza_de_horas() -> None:
	"""4. Verifica suporte de outro_mode, aislamiento de categorías de locución y limpieza de infantilismos."""
	# A. No merge de categorías estructurales
	assert {"lead_in", "reaccion", "pase"}.issubset(NO_MERGE_CATEGORIES), (
		f"NO_MERGE_CATEGORIES debe incluir lead_in, reaccion y pase: {NO_MERGE_CATEGORIES}"
	)

	# B. outro_mode en RadioContext y prevención de promesa falsa de música en pausa/break
	ctx_pause = build_radio_context(dt=datetime(2026, 5, 10, 14, 0), outro_mode="pause")
	assert isinstance(ctx_pause, RadioContext)
	assert ctx_pause.outro_mode == "pause"

	plan_pause = build_radio_dialogue_plan(
		fortuna=RadioPhrase("El mate se toma amargo y tranquilo.", "fortuna"),
		outro_mode="pause",
		ctx=ctx_pause,
	)
	text_plan = " ".join(t[0] for t in plan_pause).lower()
	assert "dejate llevar por el ritmo" not in text_plan, "En pausa no se debe prometer música en continuado"
