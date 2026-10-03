from __future__ import annotations

from scripts.radio_announcer import (
	build_radio_dialogue_plan,
	generate_modular_radio_script,
	get_lead_ins_for_category,
	get_reactions_for_category,
	resolve_segment_category,
)
from scripts.radio_banks import (
	CARPINCHO_ADS,
	DEDICATORIAS_OYENTES,
	LEAD_INS_ALERTAS,
	LEAD_INS_AVISOS,
	LEAD_INS_OYENTES,
	REACCIONES_AVISOS,
	REACCIONES_OYENTES,
)


def test_resolve_segment_category_identifies_all_types():
	"""Ensures segments are classified into their proper domain categories."""
	# Wisdom / Fortunas
	assert resolve_segment_category("Che, no te apurés; el agua siempre llega a la orilla.") == "fortuna"
	assert resolve_segment_category("El secreto de la felicidad: buena música y cero drama.") == "fortuna"

	# Commercial ads and community notices
	assert resolve_segment_category(CARPINCHO_ADS[0]) == "aviso"
	assert resolve_segment_category("Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor.") == "aviso"
	assert resolve_segment_category("Aviso parroquial: Se extravió una reposera de caño cerca del sauce.") == "aviso"
	assert resolve_segment_category("Lancha colectiva con 30 minutos de demora por camalotes.") == "aviso"

	# Listener dedications
	assert resolve_segment_category(DEDICATORIAS_OYENTES[0]) == "oyentes"
	assert (
		resolve_segment_category('WhatsApp de los mecánicos: "Manden cumbia santafesina para el taller".') == "oyentes"
	)


def test_ad_segment_does_not_use_wisdom_lead_in_or_reaction():
	"""An ad or lost-item notice must NEVER be introduced as wisdom or reacted to as philosophical truth."""
	ad_text = "Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor. Precios populares."
	cat = resolve_segment_category(ad_text)
	assert cat == "aviso"

	lead_ins = get_lead_ins_for_category(cat)
	assert all(lead in LEAD_INS_AVISOS for lead in lead_ins)
	for forbidden in ["Sabiduría", "oráculo", "galletita de la fortuna", "reflexión"]:
		assert not any(forbidden.lower() in lead.lower() for lead in lead_ins)

	reactions = get_reactions_for_category(cat)
	assert all(r in REACCIONES_AVISOS for r in reactions)
	for forbidden in ["gran verdad", "dejaste pensando"]:
		assert not any(forbidden.lower() in r.lower() for r in reactions)


def test_listener_dedication_uses_coherent_lead_in_and_reaction():
	"""A WhatsApp dedication must use listener-specific lead-ins and reactions."""
	dedication = (
		'WhatsApp de la guardia del hospital: "Metiéndole onda a la noche con La Rockola, ¡un cuarteto por favor!".'
	)
	cat = resolve_segment_category(dedication)
	assert cat == "oyentes"

	lead_ins = get_lead_ins_for_category(cat)
	assert all(lead in LEAD_INS_OYENTES for lead in lead_ins)
	assert any(
		"mensaje" in lead.lower() or "campanita" in lead.lower() or "whatsapp" in lead.lower() for lead in lead_ins
	)

	reactions = get_reactions_for_category(cat)
	assert all(r in REACCIONES_OYENTES for r in reactions)
	assert any("saludo" in r.lower() or "abrazo" in r.lower() or "temazo" in r.lower() for r in reactions)


def test_build_radio_dialogue_plan_matches_lead_in_and_reaction_to_segment():
	"""build_radio_dialogue_plan should select coherent lead-in and reaction matching the fortune text."""
	ad_text = "Espacio publicitario: Yerba Mate El Carpincho Mimoso. El mate que te acaricia el alma."
	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		lead_in=None,  # Auto-select by segment category
		fortuna=ad_text,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
	)

	lead_in_tuple = next(t for t in plan if t[2] == "lead_in")
	reaction_tuple = next(t for t in plan if t[2] == "reaccion")

	lead_in_text = lead_in_tuple[0]
	reaction_text = reaction_tuple[0]

	# Lead-in must be an ad lead-in, not a wisdom one
	assert any(lead in lead_in_text for lead in LEAD_INS_AVISOS), f"Unexpected ad lead-in: {lead_in_text}"
	assert "sabiduría" not in lead_in_text.lower()
	assert "oráculo" not in lead_in_text.lower()

	# Reaction must be an ad reaction, not wisdom
	assert any(r in reaction_text for r in REACCIONES_AVISOS), f"Unexpected ad reaction: {reaction_text}"
	assert "gran verdad" not in reaction_text.lower()


def test_alert_segment_coherence():
	"""Satirical weather/mosquito alerts should trigger alert lead-ins and reactions."""
	alert_text = "Reporte especial de mosquitos: los jejenes están organizados en escuadrones cerca del río."
	cat = resolve_segment_category(alert_text)
	assert cat == "alerta_criolla"

	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		lead_in=None,
		fortuna=alert_text,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
	)

	lead_in_text = next(t[0] for t in plan if t[2] == "lead_in")
	reaction_text = next(t[0] for t in plan if t[2] == "reaccion")

	assert lead_in_text in LEAD_INS_ALERTAS
	assert "sabiduría" not in lead_in_text.lower()
	assert "gran verdad" not in reaction_text.lower()


def test_generate_modular_radio_script_coherent_lead_in():
	"""generate_modular_radio_script selects a lead-in that coherently matches the fortuna."""
	for _ in range(20):
		res = generate_modular_radio_script()
		lead_in = res[3]
		fortuna = res[4]
		cat = resolve_segment_category(fortuna)
		cat_lead_ins = get_lead_ins_for_category(cat)
		assert lead_in in cat_lead_ins, f"Lead-in '{lead_in}' not in category '{cat}' for fortune '{fortuna}'"
