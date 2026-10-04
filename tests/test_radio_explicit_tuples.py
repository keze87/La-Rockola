from scripts.radio_announcer import (
	build_radio_dialogue_plan,
	get_phrase_last_played,
	record_phrase_played,
	reset_radio_memory_state,
	weighted_choice_by_recency,
)
from scripts.radio_banks import (
	ALERTAS_INCOMODIDAD_CRIOLLA,
	AVISOS_PARROQUIALES_Y_EXTRAVIOS,
	CARPINCHO_ADS,
	CARPINCHO_PHRASES,
	CARPINCHO_SABIDURIA,
	DEDICATORIAS_OYENTES,
	LEAD_INS_AVISOS,
	PHRASE_TO_CATEGORY,
	REACCIONES_AVISOS,
	TRANSITO_FLUVIAL_Y_CAMINOS,
	RadioPhrase,
	resolve_segment_category,
)


def test_radio_phrase_model_and_banks_are_explicit_tuples():
	"""Garantiza que RadioPhrase sea una 2-tupla (dupla) y que CARPINCHO_PHRASES contenga frases etiquetadas explícitamente."""
	sample = RadioPhrase("Vendo tele 4k", "aviso")
	assert isinstance(sample, tuple)
	assert len(sample) == 2
	text, cat = sample
	assert text == "Vendo tele 4k"
	assert cat == "aviso"
	assert sample.text == "Vendo tele 4k"
	assert sample.category == "aviso"

	# CARPINCHO_PHRASES debe contener tuplas RadioPhrase explícitas
	assert isinstance(CARPINCHO_PHRASES, list)
	assert len(CARPINCHO_PHRASES) > 0
	for item in CARPINCHO_PHRASES:
		assert isinstance(item, RadioPhrase)
		assert item.category in {"fortuna", "aviso", "alerta_criolla", "oyentes"}

	# Cada categoría debe estar correctamente poblada a partir de los bancos fuente
	fortuna_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "fortuna"}
	aviso_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "aviso"}
	alerta_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "alerta_criolla"}
	oyentes_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "oyentes"}

	for s in CARPINCHO_SABIDURIA:
		assert s in fortuna_texts
	for a in CARPINCHO_ADS + AVISOS_PARROQUIALES_Y_EXTRAVIOS:
		assert a in aviso_texts
	for al in ALERTAS_INCOMODIDAD_CRIOLLA + TRANSITO_FLUVIAL_Y_CAMINOS:
		assert al in alerta_texts
	for o in DEDICATORIAS_OYENTES:
		assert o in oyentes_texts

	# Mapeo de diccionario O(1) directo
	assert isinstance(PHRASE_TO_CATEGORY, dict)
	assert len(PHRASE_TO_CATEGORY) == len(CARPINCHO_PHRASES)


def test_resolve_segment_category_with_explicit_duples():
	"""Garantiza que resolve_segment_category respete las duplas explícitas directamente sin regex ni heurísticas."""
	# Texto arbitrario con pinta de cita pero categorizado como aviso comercial
	ad_duple = RadioPhrase("Sócrates decía: compren en el almacén de Don Tito.", "aviso")
	assert resolve_segment_category(ad_duple) == "aviso"

	# Formato de tupla (dupla) estándar
	raw_duple = ("Atención vecinos: jejenes en el muelle.", "alerta_criolla")
	assert resolve_segment_category(raw_duple) == "alerta_criolla"

	# Frase conocida del banco pasada como string plano se resuelve vía diccionario O(1)
	known_ad = CARPINCHO_ADS[0]
	assert resolve_segment_category(known_ad) == "aviso"
	assert PHRASE_TO_CATEGORY[known_ad] == "aviso"

	known_sabiduria = CARPINCHO_SABIDURIA[0]
	assert resolve_segment_category(known_sabiduria) == "fortuna"
	assert PHRASE_TO_CATEGORY[known_sabiduria] == "fortuna"


def test_build_radio_dialogue_plan_accepts_explicit_duple():
	"""Garantiza que build_radio_dialogue_plan consuma una RadioPhrase/tupla explícita sin distorsión de strings."""
	phrase_duple = RadioPhrase(
		"Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor.",
		"aviso",
	)

	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		lead_in=None,  # Selecciona automáticamente lead_in_aviso
		fortuna=phrase_duple,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
		weather_text=None,
		dialogue_mode=True,
	)

	# El texto hablado en el plan debe ser texto limpio, no la representación de la tupla
	fortuna_segment = next(t for t in plan if t[2] == "fortuna")
	assert "RadioPhrase" not in fortuna_segment[0]
	assert "Gomería El Chiche" in fortuna_segment[0]

	# El segmento de lead-in debe provenir del banco de avisos
	lead_in_segment = next(t for t in plan if t[2] == "lead_in")
	assert any(lead_in_segment[0].startswith(l[:15]) for l in LEAD_INS_AVISOS)

	# El segmento de reacción debe provenir del banco de avisos
	reaction_segment = next(t for t in plan if t[2] == "reaccion")
	assert any(reaction_segment[0].startswith(r[:15]) for r in REACCIONES_AVISOS)


def test_weighted_choice_and_recency_with_explicit_duples():
	"""Garantiza que el tracking de recencia y la ponderación funcionen nativamente con duplas explícitas."""
	reset_radio_memory_state()

	sample_duple = RadioPhrase("Llega mensajito de los isleños del arroyo.", "oyentes")
	now_ts = 5000.0

	# Registrar reproducción usando dupla
	record_phrase_played(sample_duple, timestamp=now_ts)

	# Debe poder consultarse tanto por dupla como por string de texto
	assert get_phrase_last_played(sample_duple) == now_ts
	assert get_phrase_last_played(sample_duple.text, category="oyentes") == now_ts
	assert get_phrase_last_played(sample_duple.text, category="lead_in_oyentes") is None

	# weighted_choice_by_recency con duplas candidatas
	candidates = [
		RadioPhrase("Frase 1", "fortuna"),
		RadioPhrase("Frase 2", "fortuna"),
	]
	chosen = weighted_choice_by_recency(candidates, category="fortuna", current_time=now_ts + 10)
	assert isinstance(chosen, RadioPhrase)
	assert chosen in candidates
