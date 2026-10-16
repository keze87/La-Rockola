"""Pruebas unitarias para el contexto dinámico y la concordancia de frases radiales."""

from datetime import datetime

from scripts import preload_tts_cache, radio_announcer
from scripts.radio_banks import (
	RadioContext,
	RadioPhrase,
	build_radio_context,
	context_allows,
	expand_phrase_variants,
	filter_by_context,
	get_estacion,
	get_franja_horaria,
	get_saludo_horario,
	get_weather_desc_phrase,
	phrase_fits_context,
	render_phrase,
)


def test_get_franja_horaria_all_slots():
	# Madrugada: 0 a 5
	for h in range(6):
		assert get_franja_horaria(h) == "madrugada"
	# Mañana: 6 a 11
	for h in range(6, 12):
		assert get_franja_horaria(h) == "mañana"
	# Mediodía: 12 y 13
	for h in (12, 13):
		assert get_franja_horaria(h) == "mediodia"
	# Tarde: 14 a 19
	for h in range(14, 20):
		assert get_franja_horaria(h) == "tarde"
	# Noche: 20 a 23
	for h in range(20, 24):
		assert get_franja_horaria(h) == "noche"
	# Manejo de horas módulo 24
	assert get_franja_horaria(25) == "madrugada"


def test_get_saludo_horario():
	# Buenas noches antes de las 5 am
	assert get_saludo_horario(3) == "Buenas noches"
	assert get_saludo_horario(4) == "Buenas noches"
	# Buen día desde las 5 hasta antes de las 12
	assert get_saludo_horario(5) == "Buen día"
	assert get_saludo_horario(11) == "Buen día"
	# Buenas tardes de 12 a 19
	assert get_saludo_horario(12) == "Buenas tardes"
	assert get_saludo_horario(19) == "Buenas tardes"
	# Buenas noches de 20 a 23
	assert get_saludo_horario(20) == "Buenas noches"
	assert get_saludo_horario(23) == "Buenas noches"


def test_get_estacion():
	assert get_estacion(12) == "verano"
	assert get_estacion(1) == "verano"
	assert get_estacion(2) == "verano"
	assert get_estacion(3) == "otoño"
	assert get_estacion(5) == "otoño"
	assert get_estacion(6) == "invierno"
	assert get_estacion(8) == "invierno"
	assert get_estacion(9) == "primavera"
	assert get_estacion(11) == "primavera"


def test_build_radio_context_deterministic():
	# Domingo 12 de Julio a las 15:30 (Invierno, domingo, tarde, frío 10°C)
	dt = datetime(2026, 7, 12, 15, 30)
	ctx = build_radio_context(dt, temp_c=10.2)
	assert ctx.franja == "tarde"
	assert ctx.momento == "la tarde"
	assert ctx.saludo == "Buenas tardes"
	assert ctx.dia_semana == 6
	assert ctx.dia_nombre == "domingo"
	assert ctx.es_finde is True
	assert ctx.estacion == "invierno"
	assert ctx.mes == 7
	assert ctx.temp_c == 10


def test_context_allows_temperature_and_month_fallback():
	# Con temperatura explícita
	ctx_hot = RadioContext(temp_c=28, mes=7)  # Julio pero caluroso (28°C)
	assert context_allows("calor", ctx_hot) is True
	assert context_allows("frio", ctx_hot) is False
	assert context_allows("bichos", ctx_hot) is True

	ctx_cold = RadioContext(temp_c=12, mes=1)  # Enero pero frío atípico (12°C)
	assert context_allows("calor", ctx_cold) is False
	assert context_allows("frio", ctx_cold) is True
	assert context_allows("bichos", ctx_cold) is False

	# Sin temperatura (usa el mes del año)
	ctx_summer = RadioContext(temp_c=None, mes=1)
	assert context_allows("calor", ctx_summer) is True
	assert context_allows("frio", ctx_summer) is False
	assert context_allows("bichos", ctx_summer) is True

	ctx_winter = RadioContext(temp_c=None, mes=7)
	assert context_allows("calor", ctx_winter) is False
	assert context_allows("frio", ctx_winter) is True
	assert context_allows("bichos", ctx_winter) is False

	# Condición no catalogada
	assert context_allows("desconocida", ctx_winter) is True


def test_phrase_fits_context_rules():
	ctx_madrugada = RadioContext(franja="madrugada", dia_semana=2, mes=7, temp_c=8)
	ctx_tarde = RadioContext(franja="tarde", dia_semana=5, mes=1, temp_c=30)

	# Regla de franja
	assert phrase_fits_context("Linda tardecita para matear", ctx_tarde) is True
	assert phrase_fits_context("Linda tardecita para matear", ctx_madrugada) is False
	assert phrase_fits_context("Arriba, arriba que arranca el día", ctx_madrugada) is True
	assert phrase_fits_context("Arriba, arriba que arranca el día", ctx_tarde) is False

	# Regla de día de semana
	ctx_domingo = RadioContext(franja="tarde", dia_semana=6)
	ctx_viernes = RadioContext(franja="tarde", dia_semana=4)
	# "este sábado" tiene sentido en la previa o el mismo sábado, no el domingo
	assert phrase_fits_context("Bingo familiar este sábado", ctx_viernes) is True
	assert phrase_fits_context("Bingo familiar este sábado", ctx_domingo) is False

	# Regla climática de mosquitos / calor
	assert phrase_fits_context("¡Qué calor insoportable!", ctx_tarde, category="alerta_criolla") is True
	assert phrase_fits_context("¡Qué calor insoportable!", ctx_madrugada, category="alerta_criolla") is False


def test_filter_by_context_candidates_and_fallback():
	ctx = RadioContext(franja="madrugada", dia_semana=1, mes=7, temp_c=5)
	candidates = [
		"Hermosa tarde ribereña.",
		"De madrugada junto al fogón.",
	]
	filtered = filter_by_context(candidates, ctx)
	assert filtered == ["De madrugada junto al fogón."]

	# Si todas son filtradas, devuelve la lista original como red de seguridad
	all_invalid = ["Hermosa tarde soleada.", "Cae la tarde en el bañado."]
	assert filter_by_context(all_invalid, ctx) == all_invalid

	# Soporte para tuplas y RadioPhrase
	tuple_candidates = [
		("Hermosa tarde ribereña.", "aviso"),
		("De madrugada junto al fogón.", "aviso"),
	]
	res_tuples = filter_by_context(tuple_candidates, ctx)
	assert res_tuples == [("De madrugada junto al fogón.", "aviso")]

	phrase_candidates = [
		RadioPhrase("Hermosa tarde ribereña.", "aviso"),
		RadioPhrase("De madrugada junto al fogón.", "aviso"),
	]
	res_phrases = filter_by_context(phrase_candidates, ctx)
	assert res_phrases == [RadioPhrase("De madrugada junto al fogón.", "aviso")]


def test_render_phrase_gender_and_context():
	ctx = RadioContext(momento="esta noche", saludo="Buenas noches")

	# Hacia interlocutor masculino (Tomás)
	tpl = "¡Tal cual, {vocativo}! {saludo}, qué {filosofo} de bañado."
	rendered_m = render_phrase(tpl, ctx, addressee_voice=radio_announcer.VOICE_TOMAS)
	assert rendered_m == "¡Tal cual, compadre! Buenas noches, qué filósofo de bañado."

	# Hacia interlocutor femenino (Elena)
	rendered_f = render_phrase(tpl, ctx, addressee_voice=radio_announcer.VOICE_ELENA)
	assert rendered_f == "¡Tal cual, comadre! Buenas noches, qué filósofa de bañado."

	# Con nombre de cohost
	tpl_cohost = "Che {cohost}, asomate al bañado."
	assert render_phrase(tpl_cohost, ctx, cohost_name="Elena") == "Che Elena, asomate al bañado."

	# Sin contexto utiliza fallbacks neutros
	tpl_simple = "{saludo}, bienvenidos a {momento}."
	assert render_phrase(tpl_simple, None) == "Muy buenas, bienvenidos a la jornada."


def test_expand_phrase_variants():
	tpl = "Qué hacés, {vocativo}."
	variants = expand_phrase_variants(tpl)
	assert "Qué hacés, compadre." in variants
	assert "Qué hacés, comadre." in variants
	assert len(variants) == 2

	# Frase sin placeholders devuelve la frase original intacta
	plain = "Música sin vueltas."
	assert expand_phrase_variants(plain) == [plain]


def test_extract_current_temp_c_and_recent_temp_c(tmp_path):
	db_path = tmp_path / "test_radio.db"

	# Extracción desde payload JSON
	valid_data = {"current_condition": [{"temp_C": "21.6"}]}
	assert radio_announcer.extract_current_temp_c(valid_data) == 22
	assert radio_announcer.extract_current_temp_c({}) is None

	# Caché de temperatura reciente
	now = 100000.0
	radio_announcer.set_radio_state("last_temp_c", 24, db_path=db_path)
	radio_announcer.set_radio_state("last_temp_ts", now - 1800, db_path=db_path)  # 30 minutos atrás
	assert radio_announcer._recent_temp_c(now, db_path=db_path) == 24

	# Expirada (> 3 horas)
	radio_announcer.set_radio_state("last_temp_ts", now - (4 * 3600), db_path=db_path)
	assert radio_announcer._recent_temp_c(now, db_path=db_path) is None


def test_weather_desc_night_vs_day_selection():
	ctx_noche = RadioContext(franja="noche")
	ctx_dia = RadioContext(franja="tarde")

	# Cielo soleado/despejado de noche se mapea a clear_night ("estrellas")
	desc_noche = get_weather_desc_phrase(desc="Sunny", ctx=ctx_noche, variant_idx=0)
	assert "estrellas" in desc_noche.lower()

	# De día mantiene la descripción diurna
	desc_dia = get_weather_desc_phrase(desc="Sunny", ctx=ctx_dia, variant_idx=0)
	assert "sol" in desc_dia.lower() or "brillante" in desc_dia.lower() or "radiante" in desc_dia.lower()


def test_preload_collect_phrases_has_no_unresolved_placeholders():
	"""Garantiza que la precarga de TTS no deje llaves de plantillas sin resolver."""
	items = preload_tts_cache.collect_phrases()
	unresolved = [(cat, text) for cat, text in items if "{" in text]
	assert unresolved == [], f"Se encontraron plantillas sin expandir en preload: {unresolved}"
