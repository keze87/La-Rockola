"""Pruebas de cohesión editorial, naturalidad radial y contexto temporal."""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

import app.domain.radio.voices as voices_mod
from app.domain.radio import get_modular_time_segments
from app.domain.radio.classification import (
	CARPINCHO_PHRASES,
	RadioPhrase,
	resolve_segment_subcategory,
)
from app.domain.radio.context import build_radio_context, filter_by_context
from app.domain.radio.dialogue import (
	build_radio_dialogue_plan,
	select_radio_hosts,
)
from app.domain.radio.nlp import (
	record_phrase_played,
	select_radio_phrase,
	weighted_choice_by_recency,
)
from app.domain.radio.phrase_banks import (
	ALERTAS_INCOMODIDAD_CRIOLLA,
	AVISOS_PARROQUIALES_Y_EXTRAVIOS,
	CARPINCHO_ADS,
	DEDICATORIAS_OYENTES,
	NOVELA_VECINAL,
	TRANSITO_FLUVIAL_Y_CAMINOS,
)
from app.domain.radio.phrase_banks.weather import WEATHER_DESC_PHRASES
from app.domain.radio.segments import (
	HOUR_NAMES,
	REACCIONES_AVISOS_COMERCIALES,
	REACCIONES_AVISOS_COMUNITARIOS,
	REACCIONES_CLIMA,
	REACCIONES_CLIMA_ALERTAS,
	REACCIONES_TRANSITO,
	SPECIAL_HOURS,
	WEATHER_TEMPLATES,
)


class TestEditorialCohesionAndRadioQuality:
	"""Suite de validación rigurosa para los 10 criterios de aceptación editorial."""

	def test_01_concordancia_gramatical_de_la_hora(self):
		"""1. Verifica 'Las una' en lugar de 'La una' y ausencia de infantilismos ('mimir')."""
		assert HOUR_NAMES[1] == "Las una"
		assert SPECIAL_HOURS[1].startswith("Las una")
		assert "mimir" not in SPECIAL_HOURS[1].lower()
		assert SPECIAL_HOURS[13].startswith("Las una")

		for hour in (1, 13):
			for minute in (0, 5, 15, 30, 45, 50):
				h_str, m_str, full_str = get_modular_time_segments(datetime(2026, 5, 10, hour, minute))
				assert "la una" not in h_str.lower(), f"Concordancia inválida en {hour}:{minute:02d}: {h_str}"
				assert "la una" not in full_str.lower(), f"Concordancia inválida en {hour}:{minute:02d}: {full_str}"
				if m_str:
					assert "la una" not in m_str.lower()

		for hour in range(2, 13):
			h_str, _m_str, _full = get_modular_time_segments(datetime(2026, 5, 10, hour, 0))
			assert h_str.lower().startswith("las "), f"Hora plural esperada en {hour}:00: {h_str}"

	def test_02_coherencia_temperatura_condicion_y_prudencia_climatica(self):
		"""2. Verifica que no se confunda temperatura ambiente con térmica, prudencia ante tormentas y descripciones objetivas."""
		for tpl in WEATHER_TEMPLATES:
			assert "térmica" not in tpl.lower(), f"Plantilla confunde temperatura ambiente con térmica: {tpl}"

		# En weather.py, las descripciones de lluvia intensa no deben afirmar visibilidad reducida o calles anegadas como hechos fácticos
		for phrase in WEATHER_DESC_PHRASES.get("heavy_rain", ()):
			low = phrase.lower()
			assert "visibilidad reducida" not in low, f"Afirmación fáctica no provista en lluvia: {phrase}"
			assert "calles anegadas" not in low, f"Afirmación fáctica no provista en lluvia: {phrase}"
			assert "mucha agua acumulada en los caminos" not in low, (
				f"Afirmación fáctica no provista en lluvia: {phrase}"
			)

		severe_weather = (
			"En Tigre tenemos 14 grados, cielo cubierto y alerta por tormentas fuertes y sudestada en el Delta."
		)
		ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 16, 0),
			temp_c=14,
		)
		for _ in range(30):
			plan = build_radio_dialogue_plan(
				fortuna=RadioPhrase("Qué lindo es escuchar la radio mirando el río.", "fortuna"),
				weather_text=severe_weather,
				weather_condition="lluvia",
				outro_mode="continue",
				host_voice="es-AR-TomasNeural",
				cohost_voice="es-AR-ElenaNeural",
				dialogue_mode=True,
				ctx=ctx,
			)
			full_text = " ".join(text for text, _v, _c, _a in plan).lower()
			assert "chapotear" not in full_text, f"Reacción imprudente ante tormenta severa: {full_text}"
			assert "clima perfecto" not in full_text, f"Reacción imprudente ante tormenta severa: {full_text}"
			assert "día ideal para el carpincho" not in full_text, f"Reacción imprudente ante tormenta: {full_text}"

	def test_03_adecuacion_temporal_pronosticos_y_reacciones_nocturnas(self):
		"""3. Valida exhaustivamente todos los elementos reales de calor y alertas contra contextos nocturnos."""
		night_ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 22, 30),
			temp_c=29,
		)
		midday_ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 12, 30),
			temp_c=29,
		)

		diurnal_forbidden_markers = (
			"solazo",
			"solcito",
			"protector solar",
			"secarse al sol",
			"a la sombra",
			"sombrita",
			"chapuzón en la laguna",
			"en el agua todo el día",
			"tereré",
			"para la tarde",
		)

		# 1. Validación exhaustiva del banco REACCIONES_CLIMA['calor']
		filtered_night_reactions = filter_by_context(REACCIONES_CLIMA["calor"], night_ctx, category="reaccion_clima")
		assert len(filtered_night_reactions) >= 2, "Debe haber variantes nocturnas de calor disponibles"
		for r in filtered_night_reactions:
			low = r.lower()
			for marker in diurnal_forbidden_markers:
				assert marker not in low, f"Reacción diurna de calor filtrada erróneamente en la noche: {r}"

		# 2. Las reacciones nocturnas deben ser rechazadas al mediodía
		filtered_midday = filter_by_context(filtered_night_reactions, midday_ctx, category="reaccion_clima")
		for r in filtered_midday:
			assert "noche" not in r.lower(), f"Reacción nocturna admitida al mediodía: {r}"

		# 3. Validación en generación completa de diálogo
		for _ in range(30):
			plan = build_radio_dialogue_plan(
				hora_seg="Las diez",
				minuto_seg="y media.",
				fortuna=RadioPhrase("La noche en la isla tiene su propio ritmo.", "fortuna"),
				weather_text="En Tigre la noche sigue templada con 28 grados y cielo despejado.",
				weather_condition="calor",
				outro_mode="continue",
				host_voice="es-AR-TomasNeural",
				cohost_voice="es-AR-ElenaNeural",
				dialogue_mode=True,
				ctx=night_ctx,
			)
			full_text = " ".join(text for text, _v, _c, _a in plan).lower()
			for marker in diurnal_forbidden_markers:
				assert marker not in full_text, (
					f"Marcador diurno detectado en diálogo nocturno ('{marker}'): {full_text}"
				)

	def test_04_compatibilidad_presentacion_y_subcategoria_sin_doble_introduccion(self):
		"""4. Verifica que avisos comunitarios vs publicidades no se mezclen y los bancos no contengan prefijos redundantes."""
		ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 12, 0),
			temp_c=22,
		)

		# Un aviso parroquial / extravío no debe presentarse como auspiciante comercial
		for notice in AVISOS_PARROQUIALES_Y_EXTRAVIOS[:5]:
			for _ in range(10):
				plan = build_radio_dialogue_plan(
					fortuna=RadioPhrase(notice, "aviso"),
					outro_mode="continue",
					host_voice="es-AR-TomasNeural",
					cohost_voice="es-AR-ElenaNeural",
					dialogue_mode=True,
					ctx=ctx,
				)
				lead_ins = [text.lower() for text, _v, cat, _a in plan if cat == "lead_in"]
				for li in lead_ins:
					assert "auspiciante" not in li, f"Aviso comunitario presentado como auspiciante: {li}"
					assert "publicitario" not in li, f"Aviso comunitario presentado como publicidad: {li}"
					assert "patrocina" not in li, f"Aviso comunitario presentado como patrocinador: {li}"

		# Una publicidad comercial no debe presentarse como objeto perdido o aviso parroquial
		for ad in CARPINCHO_ADS[:5]:
			for _ in range(10):
				plan = build_radio_dialogue_plan(
					fortuna=RadioPhrase(ad, "aviso"),
					outro_mode="continue",
					host_voice="es-AR-TomasNeural",
					cohost_voice="es-AR-ElenaNeural",
					dialogue_mode=True,
					ctx=ctx,
				)
				lead_ins = [text.lower() for text, _v, cat, _a in plan if cat == "lead_in"]
				for li in lead_ins:
					assert "parroquial" not in li, f"Publicidad presentada como aviso parroquial: {li}"
					assert "objetos perdidos" not in li, f"Publicidad presentada como objetos perdidos: {li}"

		# Ningún segmento de contenido debe conservar prefijos redundantes en los bancos
		redundant_prefixes = (
			"telenovela comunal:",
			"espacio publicitario:",
			"aviso parroquial:",
			"objetos perdidos:",
			"servicio a la comunidad:",
			"clasificados del juncal:",
			"mensaje al whatsapp de la radio:",
			"audio que nos mandan desde",
			"reporte fluvial:",
			"estado de los caminos:",
			"alerta meteorológica criolla:",
			"pronóstico del humor isleño:",
			"radiopasillo del juncal:",
			"chisme de último momento:",
			"comentan en la fila de la lancha:",
			"rumor de muelle:",
			"dicen las malas lenguas en el arroyo:",
			"se comenta en el almacén de ramos generales:",
		)
		for phrase in CARPINCHO_PHRASES:
			low = phrase.text.lower().strip()
			for prefix in redundant_prefixes:
				assert not low.startswith(prefix), (
					f"Prefijo redundante que causa doble introducción en '{phrase.category}': {phrase.text}"
				)

	def test_05_correspondencia_semantica_de_las_reacciones(self):
		"""5. Verifica que las reacciones correspondan estrictamente a la subcategoría semántica del contenido."""
		ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 12, 0),
			temp_c=22,
		)

		# Subcategoría aviso_comercial -> reacción de REACCIONES_AVISOS_COMERCIALES
		plan_comercial = build_radio_dialogue_plan(
			fortuna=RadioPhrase(CARPINCHO_ADS[0], "aviso"),
			outro_mode="continue",
			dialogue_mode=True,
			ctx=ctx,
		)
		reaccion_ad = next(t[0] for t in plan_comercial if t[2] == "reaccion")
		assert reaccion_ad in REACCIONES_AVISOS_COMERCIALES, f"Reacción comercial inválida: {reaccion_ad}"

		# Subcategoría aviso_comunitario -> reacción de REACCIONES_AVISOS_COMUNITARIOS
		plan_comunitario = build_radio_dialogue_plan(
			fortuna=RadioPhrase(AVISOS_PARROQUIALES_Y_EXTRAVIOS[0], "aviso"),
			outro_mode="continue",
			dialogue_mode=True,
			ctx=ctx,
		)
		reaccion_com = next(t[0] for t in plan_comunitario if t[2] == "reaccion")
		assert reaccion_com in REACCIONES_AVISOS_COMUNITARIOS, f"Reacción comunitaria inválida: {reaccion_com}"

		# Subcategoría alerta_transito -> reacción de REACCIONES_TRANSITO
		plan_transito = build_radio_dialogue_plan(
			fortuna=RadioPhrase(TRANSITO_FLUVIAL_Y_CAMINOS[0], "alerta_criolla"),
			outro_mode="continue",
			dialogue_mode=True,
			ctx=ctx,
		)
		reaccion_tra = next(t[0] for t in plan_transito if t[2] == "reaccion")
		assert reaccion_tra in REACCIONES_TRANSITO, f"Reacción vial/fluvial inválida: {reaccion_tra}"

		# Subcategoría alerta_clima -> reacción de REACCIONES_CLIMA_ALERTAS
		plan_clima = build_radio_dialogue_plan(
			fortuna=RadioPhrase(ALERTAS_INCOMODIDAD_CRIOLLA[0], "alerta_criolla"),
			outro_mode="continue",
			dialogue_mode=True,
			ctx=ctx,
		)
		reaccion_cli = next(t[0] for t in plan_clima if t[2] == "reaccion")
		assert reaccion_cli in REACCIONES_CLIMA_ALERTAS, f"Reacción climática inválida: {reaccion_cli}"

		# Clasificación de pedidos de oyentes que usan 'queremos'
		subcat_pedido = resolve_segment_subcategory(
			"Nos escriben desde el quincho: 'Queremos cumbia santafesina clásica'", "oyentes"
		)
		assert subcat_pedido == "oyentes_pedido"

		# Dedicatorias de oyentes no deben tener reacciones incrustadas al final de la cita
		for msg in DEDICATORIAS_OYENTES:
			if '"' in msg:
				after_last_quote = msg.rsplit('"', 1)[-1].strip()
				assert len(after_last_quote) <= 2, (
					f"Mensaje de oyente contiene reacción incrustada después de la cita: {msg}"
				)

	def test_06_integracion_de_pausa_y_cierre_en_flujo_de_simulacion(self):
		"""6. Prueba de integración que reproduce el flujo real de run_mock_radio_simulation en modos de corte."""
		forbidden_when_stopping = (
			"el temazo que viene",
			"el próximo tema",
			"mandale play",
			"seguimos con más música",
			"no te vayas que ya suena",
			"continúa la música",
			"sigue sonando",
			"subí el volumen que",
			"que suene el próximo",
			"dejate llevar por el ritmo que sigue",
		)
		outro_modes = ["pause", "break"]

		for i in range(40):
			dt = datetime(2026, 4, 15, 14, (i * 7) % 60)
			temp = 22
			o_mode = random.choice(outro_modes)

			# Flujo real: o_mode se determina ANTES de crear el contexto y seleccionar la frase
			ctx = build_radio_context(dt, temp_c=temp, outro_mode=o_mode)
			phrase, _is_sys = select_radio_phrase(force_system_fortune=False, ctx=ctx)

			plan = build_radio_dialogue_plan(
				fortuna=phrase,
				outro_mode=o_mode,
				host_voice="es-AR-TomasNeural",
				cohost_voice="es-AR-ElenaNeural",
				dialogue_mode=True,
				ctx=ctx,
				dt=dt,
			)
			full_text = " ".join(text for text, _v, _c, _a in plan).lower()
			for forbidden in forbidden_when_stopping:
				assert forbidden not in full_text, (
					f"En simulación con modo '{o_mode}' se prometió música ('{forbidden}'): {full_text}"
				)

	def test_07_ausencia_de_referencias_a_colocutor_en_modo_individual(self):
		"""7. Verifica que en modo solitario (dialogue_mode=False) no se hable a un co-locutor."""
		ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 10, 0),
			temp_c=22,
		)
		duo_markers = (
			"compadre",
			"comadre",
			"¿cómo la ves",
			"¿no es así",
			"contame qué dicen",
			"te doy el pase",
			"mi compañero",
			"mi compañera",
		)
		for _ in range(30):
			plan = build_radio_dialogue_plan(
				hora_seg="Las diez",
				minuto_seg="en punto.",
				fortuna=RadioPhrase("Un buen mate acompaña cualquier mañana.", "fortuna"),
				weather_text="En Tigre tenemos 22 grados y cielo despejado.",
				weather_condition="agradable",
				outro_mode="continue",
				host_voice="es-AR-TomasNeural",
				cohost_voice="es-AR-ElenaNeural",
				dialogue_mode=False,
				ctx=ctx,
			)
			voices = {voice for _t, voice, _c, _a in plan}
			assert voices == {"es-AR-TomasNeural"}
			full_text = " ".join(text for text, _v, _c, _a in plan).lower()
			for marker in duo_markers:
				assert marker not in full_text, f"Referencia a co-locutor en modo individual: {full_text}"

	def test_08_propagacion_de_db_y_prioridad_de_recencia_en_sqlite(self, tmp_path: Path):
		"""8. Verifica que weighted_choice_by_recency propague db_path y priorice la frase no reproducida en SQLite."""
		db_file = str(tmp_path / "test_recency_sqlite.db")
		ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 12, 0),
			temp_c=22,
		)

		candidates = list(NOVELA_VECINAL[:5])
		target_unplayed = candidates[-1]

		# Registramos en SQLite todas las frases menos la última
		for item in candidates[:-1]:
			record_phrase_played(item, "novela", db_path=db_file)

		# Probamos directamente weighted_choice_by_recency propagando db_file
		picked_count = 0
		for _ in range(40):
			picked = weighted_choice_by_recency(candidates, category="novela", db_path=db_file)
			if picked == target_unplayed:
				picked_count += 1

		assert picked_count >= 20, (
			f"La frase no reproducida no tuvo prioridad de recencia en SQLite ({picked_count}/40)"
		)

		# Verifica además que el texto planificado no contamine la vista con fonética forzada TTS
		plan = build_radio_dialogue_plan(
			fortuna=RadioPhrase("Tirate en el pasto, cebate unos verdes y relajate con DJ Bara.", "fortuna"),
			outro_mode="dj",
			host_voice="es-AR-TomasNeural",
			cohost_voice="es-AR-ElenaNeural",
			dialogue_mode=True,
			ctx=ctx,
		)
		full_text = " ".join(text for text, _v, _c, _a in plan)
		assert "tiráte" not in full_text.lower()
		assert "cebáte" not in full_text.lower()
		assert "diyei" not in full_text.lower()

	def test_09_integracion_de_perfiles_prosodia_y_afinidad_de_voces(self):
		"""9. Verifica que los perfiles editoriales influyan en la selección de voces y prosodia diferenciada."""
		host_profiles = getattr(voices_mod, "HOST_PROFILES", {})
		assert len(host_profiles) >= 4

		for voice_id in (
			"es-AR-TomasNeural",
			"es-AR-ElenaNeural",
			"es-UY-ValentinaNeural",
			"es-CR-MariaNeural",
		):
			profile = host_profiles[voice_id]
			assert "name" in profile
			assert "role" in profile
			assert "style" in profile
			assert "preferred_categories" in profile
			assert "pacing" in profile

		# Asignación afín a la temática según el perfil
		host_chismes, cohost_chismes = select_radio_hosts(category="chismes")
		assert "es-UY-ValentinaNeural" in (host_chismes, cohost_chismes), "Valentina debe participar en chismes/novela"

		host_aviso, cohost_aviso = select_radio_hosts(category="aviso")
		assert "es-AR-ElenaNeural" in (host_aviso, cohost_aviso), "Elena debe participar en avisos comunitarios"

		# Prosodia diferenciada por personaje
		prosody = getattr(voices_mod, "VOICE_PROSODY", {})
		assert prosody["es-AR-TomasNeural"]["rate"] != prosody["es-UY-ValentinaNeural"]["rate"]
		assert prosody["es-AR-TomasNeural"]["pitch"] != prosody["es-CR-MariaNeural"]["pitch"]

	def test_10_distribucion_balanceada_y_equitativa_de_categorias(self, tmp_path: Path):
		"""10. Verifica sobre 180 muestras que las 6 categorías se distribuyan equitativamente sin monopolio."""
		db_file = str(tmp_path / "test_balance.db")
		ctx = build_radio_context(
			dt=datetime(2026, 5, 10, 12, 0),
			temp_c=22,
		)
		counts: dict[str, int] = {}
		total_samples = 180

		for _ in range(total_samples):
			phrase, _ = select_radio_phrase(ctx=ctx, db_path=db_file)
			record_phrase_played(phrase.text, phrase.category, db_path=db_file)
			counts[phrase.category] = counts.get(phrase.category, 0) + 1

		expected = {"fortuna", "aviso", "oyentes", "alerta_criolla", "chismes", "novela"}
		assert expected.issubset(counts.keys()), f"Categorías faltantes: {expected - counts.keys()}"

		# Con 180 muestras entre 6 categorías, la media teórica es 30.
		# Ninguna categoría debe quedar sub-representada (< 15) ni monopolizar la transmisión (> 55).
		for cat, count in counts.items():
			assert count >= 15, f"Categoría '{cat}' sub-representada ({count}/{total_samples})"
			assert count <= 55, f"Categoría '{cat}' monopoliza el dial ({count}/{total_samples})"
