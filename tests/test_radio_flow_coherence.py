from __future__ import annotations

from scripts.radio_announcer import (
	build_radio_dialogue_plan,
	generate_modular_radio_script,
	get_lead_ins_for_category,
	get_reactions_for_category,
	resolve_segment_category,
)
from scripts.radio_banks import (
	ALERTAS_INCOMODIDAD_CRIOLLA,
	CARPINCHO_ADS,
	DEDICATORIAS_OYENTES,
	LEAD_INS_ALERTAS,
	LEAD_INS_AVISOS,
	LEAD_INS_OYENTES,
	REACCIONES_ALERTAS,
	REACCIONES_AVISOS,
	REACCIONES_OYENTES,
	TRANSITO_FLUVIAL_Y_CAMINOS,
)


def test_resolve_segment_category_identifies_all_types():
	"""Garantiza que los segmentos se clasifiquen en sus categorías de dominio adecuadas."""
	# Sabiduría / Fortunas
	assert resolve_segment_category("Che, no te apurés; el agua siempre llega a la orilla.") == "fortuna"
	assert resolve_segment_category("El secreto de la felicidad: buena música y cero drama.") == "fortuna"

	# Avisos comerciales y comunitarios
	assert resolve_segment_category(CARPINCHO_ADS[0]) == "aviso"
	assert resolve_segment_category("Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor.") == "aviso"
	assert resolve_segment_category("Aviso parroquial: Se extravió una reposera de caño cerca del sauce.") == "aviso"

	# Alertas criollas y tránsito fluvial remoto
	assert resolve_segment_category("Lancha colectiva con 30 minutos de demora por camalotes.") == "alerta_criolla"

	# Mensajes y dedicatorias de oyentes
	assert resolve_segment_category(DEDICATORIAS_OYENTES[0]) == "oyentes"
	assert (
		resolve_segment_category('WhatsApp de los mecánicos: "Manden cumbia santafesina para el taller".') == "oyentes"
	)


def test_ad_segment_does_not_use_wisdom_lead_in_or_reaction():
	"""Un aviso comercial o reporte comunitario NUNCA debe presentarse como sabiduría ni reaccionar filosóficamente."""
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
	"""Una dedicatoria de oyente por WhatsApp debe usar lead-ins y reacciones específicas de oyentes."""
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
	"""build_radio_dialogue_plan debe seleccionar lead-in y reacción coherentes con el texto del segmento."""
	ad_text = "Espacio publicitario: Yerba Mate El Carpincho Mimoso. El mate que te acaricia el alma."
	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		lead_in=None,  # Autoselección según categoría del segmento
		fortuna=ad_text,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
	)

	lead_in_tuple = next(t for t in plan if t[2] == "lead_in")
	reaction_tuple = next(t for t in plan if t[2] == "reaccion")

	lead_in_text = lead_in_tuple[0]
	reaction_text = reaction_tuple[0]

	# El lead-in debe ser del banco de avisos, nunca de sabiduría
	assert any(lead in lead_in_text for lead in LEAD_INS_AVISOS), f"Lead-in inesperado para aviso: {lead_in_text}"
	assert "sabiduría" not in lead_in_text.lower()
	assert "oráculo" not in lead_in_text.lower()

	# La reacción debe ser del banco de avisos, nunca de sabiduría
	assert any(r in reaction_text for r in REACCIONES_AVISOS), f"Reacción inesperada para aviso: {reaction_text}"
	assert "gran verdad" not in reaction_text.lower()


def test_alert_segment_coherence():
	"""Los reportes satíricos de clima y mosquitos deben disparar lead-ins y reacciones de alerta."""
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
	"""generate_modular_radio_script selecciona un lead-in coherente con la categoría de la fortuna."""
	for _ in range(20):
		res = generate_modular_radio_script()
		lead_in = res[3]
		fortuna = res[4]
		cat = resolve_segment_category(fortuna)
		cat_lead_ins = get_lead_ins_for_category(cat)
		assert lead_in in cat_lead_ins, (
			f"Lead-in '{lead_in}' no pertenece a la categoría '{cat}' para la fortuna '{fortuna}'"
		)


def test_philosophical_quotes_and_refranes_not_misclassified():
	"""Garantiza que frases de sabiduría y citas con palabras clave como 'recompensa' o 'mosquito' no se clasifiquen como avisos o alertas."""
	salk_quote = (
		"La recompensa del trabajo bien hecho es la oportunidad de hacer más trabajo bien hecho. — Jonas Edward Salk."
	)
	assert resolve_segment_category(salk_quote) == "fortuna"

	quevedo_quote = "Dijo la rana al mosquito desde una tinaja: más quiero morir en el vino que vivir en el agua... — Francisco de Quevedo."
	assert resolve_segment_category(quevedo_quote) == "fortuna"

	refran_mosquito = "Más vale carpincho en laguna que cien mosquitos en la nuca."
	assert resolve_segment_category(refran_mosquito) == "fortuna"

	# Avisos comerciales con 'mosquito' o 'jejenes' deben permanecer como 'aviso', no como 'alerta_criolla'
	ad_repelente = "Aviso parroquial: Repelente Chau Mosquito. Para que no te piquen las orejas mientras disfrutás de un buen chamamé."
	assert resolve_segment_category(ad_repelente) == "aviso"

	ad_fumigacion = "Publicidad: Fumigaciones La Garza. Control ecológico de tábanos y jejenes con sapos adiestrados. Eficacia comprobada en todo el humedal."
	assert resolve_segment_category(ad_fumigacion) == "aviso"


def test_recency_contract_records_specific_categories_matching_weighted_choice():
	"""Garantiza que las categorías registradas en el historial de frases coincidan con las consultadas por weighted_choice_by_recency."""
	from scripts.radio_announcer import (
		get_phrase_last_played,
		record_phrase_played,
		reset_radio_memory_state,
	)

	reset_radio_memory_state()

	ad_text = "Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor."
	seg_cat = resolve_segment_category(ad_text)
	assert seg_cat == "aviso"

	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		lead_in="Atención vecinos con este aviso del pueblo:",
		fortuna=ad_text,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
		weather_text="En Tucumán hacen 25 grados.",
	)

	# Simular registro tal como lo realiza create_radio_announcement
	now_ts = 1000.0
	for seg_text, _v, cat, _c in plan:
		clean_s = seg_text.strip()
		if clean_s:
			record_phrase_played(clean_s, category=cat, timestamp=now_ts)

	# La consulta de lead-in utiliza f"lead_in_{seg_cat}" (lead_in_aviso)
	lead_in_ts = get_phrase_last_played("Atención vecinos con este aviso del pueblo:", category=f"lead_in_{seg_cat}")
	assert lead_in_ts == now_ts, "El lead-in no se registró con la categoría específica f'lead_in_{seg_cat}'"

	reactions = [t[0] for t in plan if t[2] == "reaccion"]
	assert len(reactions) == 2
	weather_react = reactions[0]
	fortune_react = reactions[1]
	react_clima_ts = get_phrase_last_played(weather_react, category="reaccion_clima")
	assert react_clima_ts == now_ts, "La reacción climática no se registró con categoría 'reaccion_clima'"
	react_fortune_ts = get_phrase_last_played(fortune_react, category=f"reaccion_{seg_cat}")
	assert react_fortune_ts == now_ts, f"La reacción a la fortuna no se registró con categoría 'reaccion_{seg_cat}'"


def test_build_radio_dialogue_plan_default_lead_in_is_none():
	"""Garantiza que lead_in sea opcional en build_radio_dialogue_plan y resuelva automáticamente por categoría."""
	# Al invocar sin pasar el parámetro lead_in, debe resolver el lead-in correspondiente a la categoría del segmento
	ad_text = "Gomería El Chiche: emparchamos desde gomones hasta cámaras de tractor."
	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		fortuna=ad_text,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
	)

	lead_in_segment = next(t for t in plan if t[2] == "lead_in")
	assert any(lead in lead_in_segment[0] for lead in LEAD_INS_AVISOS), (
		f"Lead-in inesperado para aviso sin pasar lead_in explícito: {lead_in_segment[0]}"
	)


def test_alertas_and_transito_fluvial_no_local_deictics():
	"""Garantiza que ni los lead-ins, ni las reacciones, ni los partes fluviales contengan deícticos de primera persona local."""
	import re

	patrones_prohibidos = [
		r"\bacá\b",
		r"\baquí\b",
		r"\bnuestra zona\b",
		r"\bnuestro pago\b",
		r"\bnuestra tierra\b",
	]

	bancos_a_revisar = {
		"LEAD_INS_ALERTAS": LEAD_INS_ALERTAS,
		"REACCIONES_ALERTAS": REACCIONES_ALERTAS,
		"TRANSITO_FLUVIAL_Y_CAMINOS": TRANSITO_FLUVIAL_Y_CAMINOS,
		"ALERTAS_INCOMODIDAD_CRIOLLA": ALERTAS_INCOMODIDAD_CRIOLLA,
	}

	for nombre_banco, frases in bancos_a_revisar.items():
		for frase in frases:
			for patron in patrones_prohibidos:
				assert not re.search(patron, frase, re.IGNORECASE), (
					f"Deíctico prohibido '{patron}' encontrado en {nombre_banco}: '{frase}'"
				)


def test_lead_ins_alertas_remote_correspondent_markers():
	"""Garantiza que cada lead-in de alertas contenga al menos un marcador de procedencia remota / corresponsal."""
	marcadores_esperados = (
		"desde",
		"nos llega",
		"nos cuentan",
		"allá",
		"río abajo",
		"nos tira",
		"corresponsalía",
		"otra orilla",
		"cable urgente",
		"nos acerca",
		"nos envían",
	)

	for lead_in in LEAD_INS_ALERTAS:
		lead_lower = lead_in.lower()
		assert any(m in lead_lower for m in marcadores_esperados), (
			f"El lead-in '{lead_in}' no incluye ningún marcador de corresponsal remoto ({marcadores_esperados})"
		)


def test_fluvial_traffic_uses_remote_alert_pool_in_dialogue_plan():
	"""Verifica que el tránsito fluvial se clasifique como alerta_criolla y seleccione lead-in y reacción del pool remoto."""
	frase_fluvial = TRANSITO_FLUVIAL_Y_CAMINOS[0]
	categoria = resolve_segment_category(frase_fluvial)
	assert categoria == "alerta_criolla", (
		f"El tránsito fluvial debe clasificarse como 'alerta_criolla', se obtuvo: '{categoria}'"
	)

	plan = build_radio_dialogue_plan(
		intro="Arranca La Rockola.",
		hora_seg="Las tres",
		minuto_seg="de la tarde",
		fortuna=frase_fluvial,
		outro="¡Que suene la música!",
		host_voice="es-AR-TomasNeural",
		cohost_voice="es-AR-ElenaNeural",
	)

	lead_in_text = next(t[0] for t in plan if t[2] == "lead_in")
	reaccion_text = next(t[0] for t in plan if t[2] == "reaccion")

	# Debe pertenecer al pool remoto de alertas, nunca al de avisos comerciales
	assert any(l in lead_in_text for l in LEAD_INS_ALERTAS), (
		f"Lead-in no pertenece a LEAD_INS_ALERTAS: '{lead_in_text}'"
	)
	assert not any(l in lead_in_text for l in LEAD_INS_AVISOS), (
		f"Lead-in pertenece indebidamente a LEAD_INS_AVISOS: '{lead_in_text}'"
	)

	assert any(r in reaccion_text for r in REACCIONES_ALERTAS), (
		f"Reacción no pertenece a REACCIONES_ALERTAS: '{reaccion_text}'"
	)
	assert not any(r in reaccion_text for r in REACCIONES_AVISOS), (
		f"Reacción pertenece indebidamente a REACCIONES_AVISOS: '{reaccion_text}'"
	)
