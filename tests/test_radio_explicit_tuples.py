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
	"""Ensures RadioPhrase is a 2-tuple (duple) and CARPINCHO_PHRASES contains all phrases explicitly tagged."""
	sample = RadioPhrase("Vendo tele 4k", "aviso")
	assert isinstance(sample, tuple)
	assert len(sample) == 2
	text, cat = sample
	assert text == "Vendo tele 4k"
	assert cat == "aviso"
	assert sample.text == "Vendo tele 4k"
	assert sample.category == "aviso"

	# CARPINCHO_PHRASES must contain explicit RadioPhrase tuples
	assert isinstance(CARPINCHO_PHRASES, list)
	assert len(CARPINCHO_PHRASES) > 0
	for item in CARPINCHO_PHRASES:
		assert isinstance(item, RadioPhrase)
		assert item.category in {"fortuna", "aviso", "alerta_criolla", "oyentes"}

	# Every category must be correctly populated from source banks
	fortuna_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "fortuna"}
	aviso_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "aviso"}
	alerta_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "alerta_criolla"}
	oyentes_texts = {p.text for p in CARPINCHO_PHRASES if p.category == "oyentes"}

	for s in CARPINCHO_SABIDURIA:
		assert s in fortuna_texts
	for a in CARPINCHO_ADS + AVISOS_PARROQUIALES_Y_EXTRAVIOS + TRANSITO_FLUVIAL_Y_CAMINOS:
		assert a in aviso_texts
	for al in ALERTAS_INCOMODIDAD_CRIOLLA:
		assert al in alerta_texts
	for o in DEDICATORIAS_OYENTES:
		assert o in oyentes_texts

	# O(1) dictionary mapping exists
	assert isinstance(PHRASE_TO_CATEGORY, dict)
	assert len(PHRASE_TO_CATEGORY) == len(CARPINCHO_PHRASES)


def test_resolve_segment_category_with_explicit_duples():
	"""Ensures resolve_segment_category respects explicit duples directly without regex or heuristic inspection."""
	# Arbitrary text that looks like a quote but is tagged as an ad
	ad_duple = RadioPhrase("Sócrates decía: compren en el almacén de Don Tito.", "aviso")
	assert resolve_segment_category(ad_duple) == "aviso"

	# Standard tuple (duple) format
	raw_duple = ("Atención vecinos: jejenes en el muelle.", "alerta_criolla")
	assert resolve_segment_category(raw_duple) == "alerta_criolla"

	# Known bank phrase passed as plain string resolves via O(1) dictionary mapping
	known_ad = CARPINCHO_ADS[0]
	assert resolve_segment_category(known_ad) == "aviso"
	assert PHRASE_TO_CATEGORY[known_ad] == "aviso"

	known_sabiduria = CARPINCHO_SABIDURIA[0]
	assert resolve_segment_category(known_sabiduria) == "fortuna"
	assert PHRASE_TO_CATEGORY[known_sabiduria] == "fortuna"


def test_build_radio_dialogue_plan_accepts_explicit_duple():
	"""Ensures build_radio_dialogue_plan consumes an explicit RadioPhrase/tuple without string distortion."""
	phrase_duple = RadioPhrase(
		"Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor.",
		"aviso",
	)

	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		lead_in=None,  # Should auto-select matching lead_in_aviso
		fortuna=phrase_duple,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
		weather_text=None,
		dialogue_mode=True,
	)

	# The spoken text in the plan must be the clean text string, not the tuple repr
	fortuna_segment = next(t for t in plan if t[2] == "fortuna")
	assert "RadioPhrase" not in fortuna_segment[0]
	assert "Gomería El Chiche" in fortuna_segment[0]

	# Lead-in segment should be from the aviso bank
	lead_in_segment = next(t for t in plan if t[2] == "lead_in")
	assert any(lead_in_segment[0].startswith(l[:15]) for l in LEAD_INS_AVISOS)

	# Reaction segment should be from the aviso bank
	reaction_segment = next(t for t in plan if t[2] == "reaccion")
	assert any(reaction_segment[0].startswith(r[:15]) for r in REACCIONES_AVISOS)


def test_weighted_choice_and_recency_with_explicit_duples():
	"""Ensures recency tracking and weighted choice work natively with explicit duples."""
	reset_radio_memory_state()

	sample_duple = RadioPhrase("Llega mensajito de los isleños del arroyo.", "oyentes")
	now_ts = 5000.0

	# Record played using duple
	record_phrase_played(sample_duple, timestamp=now_ts)

	# Should be retrievable by duple or by string text
	assert get_phrase_last_played(sample_duple) == now_ts
	assert get_phrase_last_played(sample_duple.text, category="oyentes") == now_ts
	assert get_phrase_last_played(sample_duple.text, category="lead_in_oyentes") is None

	# weighted_choice_by_recency with candidate duples
	candidates = [
		RadioPhrase("Frase 1", "fortuna"),
		RadioPhrase("Frase 2", "fortuna"),
	]
	chosen = weighted_choice_by_recency(candidates, category="fortuna", current_time=now_ts + 10)
	assert isinstance(chosen, RadioPhrase)
	assert chosen in candidates
