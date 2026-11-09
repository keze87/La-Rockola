"""
Pruebas para las 4 mejoras de código rescatadas y perfeccionadas del commit c9762d9.
Valida:
1. Balanceo probabilístico por categoría y propagación de db_path en recencia (nlp.py).
2. Perfiles editoriales de locutores y afinidad temática en cabina (voices.py, dialogue.py).
3. Subcategorización semántica fina y coherencia de lead-ins / reacciones (classification.py, segments.py).
4. Soporte robusto de outro_mode, fallbacks contextuales seguros y limpieza de horas (dialogue.py, context.py, segments.py).
"""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

import app.domain.radio.voices as voices_mod
from app.domain.radio.classification import (
	CARPINCHO_PHRASES,
	RadioPhrase,
	resolve_segment_subcategory,
)
from app.domain.radio.context import build_radio_context, phrase_fits_context
from app.domain.radio.dialogue import (
	NO_MERGE_CATEGORIES,
	build_radio_dialogue_plan,
	generate_modular_radio_script,
	select_radio_hosts,
)
from app.domain.radio.nlp import (
	get_phrase_last_played,
	record_phrase_played,
	reset_radio_memory_state,
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
	LEAD_INS_FORTUNA_MUSICAL,
	LEAD_INS_FORTUNA_REFLEXIVA,
	LEAD_INS_TRANSITO,
	RADIO_OUTROS_PAUSE,
	REACCIONES_AVISOS_COMERCIALES,
	REACCIONES_AVISOS_COMUNITARIOS,
	REACCIONES_CLIMA_ALERTAS,
	REACCIONES_FORTUNA_MUSICAL,
	REACCIONES_FORTUNA_REFLEXIVA,
	REACCIONES_TRANSITO,
	get_lead_ins_for_category,
	get_reactions_for_category,
)
from app.domain.radio.voices import (
	VOICE_ELENA,
	VOICE_MARIA,
	VOICE_TOMAS,
	VOICE_VALENTINA,
	VOICES,
)


def test_01_balanceo_probabilistico_y_recencia_con_db_path(tmp_path: Path, monkeypatch) -> None:
	"""1. Verifica propagación de db_path en recencia tras reinicio y distribución de categorías con RNG aislado."""
	isolated_rng = random.Random(20261108)
	monkeypatch.setattr(random, "random", isolated_rng.random)
	monkeypatch.setattr(random, "choice", isolated_rng.choice)
	monkeypatch.setattr(random, "choices", isolated_rng.choices)
	monkeypatch.setattr(random, "sample", isolated_rng.sample)
	monkeypatch.setattr(random, "uniform", isolated_rng.uniform)

	db_file = str(tmp_path / "test_recency_isolation.db")
	ctx = build_radio_context(dt=datetime(2026, 5, 10, 12, 0), temp_c=22)

	# A. Propagación de db_path en weighted_choice_by_recency, incluso tras reiniciar la memoria en RAM
	candidates = list(NOVELA_VECINAL[:5])
	target_unplayed = candidates[-1]
	for item in candidates[:-1]:
		record_phrase_played(item, "novela", db_path=db_file)

	# Simulamos reinicio del proceso borrando la memoria RAM sin borrar SQLite
	reset_radio_memory_state(clear_db=False)

	picked_count = sum(
		1
		for _ in range(30)
		if weighted_choice_by_recency(candidates, category="novela", db_path=db_file) == target_unplayed
	)
	assert picked_count >= 20, (
		f"La frase no jugada no tuvo prioridad con db_path propagado tras reinicio ({picked_count}/30)"
	)

	# B. Distribución con semilla fija: verifica pesos y cobertura de todas las categorías
	counts: dict[str, int] = {}
	total_samples = 240
	for _ in range(total_samples):
		phrase, _ = select_radio_phrase(ctx=ctx, db_path=db_file)
		record_phrase_played(phrase.text, phrase.category, db_path=db_file)
		counts[phrase.category] = counts.get(phrase.category, 0) + 1

	expected_cats = {"fortuna", "aviso", "oyentes", "alerta_criolla", "chismes", "novela"}
	assert expected_cats.issubset(counts.keys()), f"Faltan categorías en la selección: {expected_cats - counts.keys()}"
	for cat, count in counts.items():
		assert count >= 6, f"Categoría '{cat}' sub-representada ({count}/{total_samples})"
		assert count <= 160, f"Categoría '{cat}' monopoliza la rotación ({count}/{total_samples})"


def test_02_perfiles_editoriales_y_afinidad_tematica(monkeypatch) -> None:
	"""2. Verifica perfiles de locutores en voices.py, afinidad temática (incluida María) y que host != cohost."""
	isolated_rng = random.Random(1337)
	monkeypatch.setattr(random, "random", isolated_rng.random)
	monkeypatch.setattr(random, "choice", isolated_rng.choice)
	monkeypatch.setattr(random, "choices", isolated_rng.choices)

	host_profiles = getattr(voices_mod, "HOST_PROFILES", {})
	assert len(host_profiles) >= 4, "HOST_PROFILES debe definir los 4 perfiles de cabina"

	valid_segment_categories = {"fortuna", "aviso", "alerta_criolla", "oyentes", "chismes", "novela"}
	for v in VOICES:
		profile = host_profiles.get(v)
		assert profile is not None, f"Falta perfil para la voz {v}"
		assert "name" in profile
		assert "role" in profile
		assert "style" in profile
		assert "preferred_categories" in profile
		assert "pacing" in profile
		prefs = set(profile["preferred_categories"])
		assert prefs.issubset(valid_segment_categories), (
			f"Perfil de {v} contiene categorías inexistentes: {prefs - valid_segment_categories}"
		)

	# María debe ser elegible automáticamente como host principal en sus categorías preferidas (oyentes y fortuna)
	maria_as_host_oyentes = sum(1 for _ in range(30) if select_radio_hosts(category="oyentes")[0] == VOICE_MARIA)
	assert maria_as_host_oyentes >= 8, f"María debe actuar como host automático en oyentes ({maria_as_host_oyentes}/30)"
	maria_as_host_fortuna = sum(1 for _ in range(30) if select_radio_hosts(category="fortuna")[0] == VOICE_MARIA)
	assert maria_as_host_fortuna >= 8, f"María debe actuar como host automático en fortuna ({maria_as_host_fortuna}/30)"

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

	# Tres situaciones obligatorias: (a) ninguna voz, (b) solo host, (c) solo cohost
	for cat in ("fortuna", "aviso", "alerta_criolla", "oyentes", "chismes", "novela"):
		for _ in range(10):
			# a) Ninguna voz proporcionada
			h1, c1 = select_radio_hosts(category=cat)
			assert h1 != c1

			# b) Solo host proporcionado
			for v in VOICES:
				h2, c2 = select_radio_hosts(host_voice=v, category=cat)
				assert h2 == v and h2 != c2

			# c) Solo cohost proporcionado (incluyendo cohost=VOICE_TOMAS en alerta_criolla)
			for v in VOICES:
				h3, c3 = select_radio_hosts(cohost_voice=v, category=cat)
				assert c3 == v and h3 != c3
				plan = build_radio_dialogue_plan(
					cohost_voice=v,
					fortuna=RadioPhrase("Reporte de prueba.", cat),
				)
				host_used = plan[0][1]
				fortune_used = next(t[1] for t in plan if t[2] == cat)
				assert host_used != v
				assert fortune_used == v


def test_03_subcategorizacion_semantica_fina(tmp_path: Path) -> None:
	"""3. Verifica clasificación fina de subcategorías (incluyendo fortunas) y alineación del historial de recencia."""
	db_file = tmp_path / "test_subcat_recency.db"

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

	# D. Fortunas: musical vs reflexiva con sus bancos específicos
	assert resolve_segment_subcategory("La música te salva una y otra vez.", category="fortuna") == "fortuna_musical"
	assert resolve_segment_subcategory("Al que madruga Dios lo ayuda.", category="fortuna") == "fortuna_reflexiva"
	assert get_lead_ins_for_category("fortuna", subcategory="fortuna_musical") == LEAD_INS_FORTUNA_MUSICAL
	assert get_lead_ins_for_category("fortuna", subcategory="fortuna_reflexiva") == LEAD_INS_FORTUNA_REFLEXIVA
	assert get_reactions_for_category("fortuna", subcategory="fortuna_musical") == REACCIONES_FORTUNA_MUSICAL
	assert get_reactions_for_category("fortuna", subcategory="fortuna_reflexiva") == REACCIONES_FORTUNA_REFLEXIVA

	# E. Coherencia en lead-ins y reacciones de avisos y alertas
	assert get_lead_ins_for_category("aviso", subcategory="aviso_comercial") == LEAD_INS_AVISOS_COMERCIALES
	assert get_lead_ins_for_category("aviso", subcategory="aviso_comunitario") == LEAD_INS_AVISOS_COMUNITARIOS
	assert get_lead_ins_for_category("alerta_criolla", subcategory="alerta_transito") == LEAD_INS_TRANSITO

	assert get_reactions_for_category("aviso", subcategory="aviso_comercial") == REACCIONES_AVISOS_COMERCIALES
	assert get_reactions_for_category("aviso", subcategory="aviso_comunitario") == REACCIONES_AVISOS_COMUNITARIOS
	assert get_reactions_for_category("alerta_criolla", subcategory="alerta_transito") == REACCIONES_TRANSITO
	assert get_reactions_for_category("alerta_criolla", subcategory="alerta_clima") == REACCIONES_CLIMA_ALERTAS

	# F. Alineación de historial de recencia entre categoría general ("reaccion" / "lead_in") y subcategorías
	ad_react = REACCIONES_AVISOS_COMERCIALES[0]
	record_phrase_played(ad_react, category="reaccion", timestamp=70000.0, db_path=db_file)
	assert get_phrase_last_played(ad_react, category="reaccion_aviso_comercial", db_path=db_file) == 70000.0

	ad_lead = LEAD_INS_AVISOS_COMERCIALES[0]
	record_phrase_played(ad_lead, category="lead_in", timestamp=71000.0, db_path=db_file)
	assert get_phrase_last_played(ad_lead, category="lead_in_aviso_comercial", db_path=db_file) == 71000.0

	# G. Contenido no reconocido clasifica como 'unknown' y no se convierte silenciosamente en 'fortuna_reflexiva'
	assert resolve_segment_subcategory("Una frase externa misteriosa 12345XYZ.") == "unknown"
	assert resolve_segment_subcategory("Una frase externa misteriosa 12345XYZ.", category="unknown") == "unknown"

	# H. Subcategoría explícita poblada en CARPINCHO_PHRASES y sin falsos positivos por subcadenas sin \b
	assert all(bool(p.subcategory) for p in CARPINCHO_PHRASES), (
		"Todas las RadioPhrase en CARPINCHO_PHRASES deben tener subcategory explícita"
	)
	assert (
		resolve_segment_subcategory("El sistema eléctrico tiene un problema grave.", category="fortuna")
		== "fortuna_reflexiva"
	)
	assert (
		resolve_segment_subcategory("Se puso la camisa limpia para salir a vender.", category="aviso")
		== "aviso_comercial"
	)
	assert (
		resolve_segment_subcategory("Calor pesado pero ideal para disfrutar a la sombra.", category="alerta_criolla")
		== "alerta_clima"
	)
	assert (
		resolve_segment_subcategory("Ese viento canalla nos voló el sombrero.", category="alerta_criolla")
		== "alerta_clima"
	)
	assert (
		resolve_segment_subcategory("Nada impide que mandemos un abrazo grande a la barra.", category="oyentes")
		== "oyentes_saludo"
	)
	assert (
		resolve_segment_subcategory("El tema del agua potable en la isla preocupa a los vecinos.", category="fortuna")
		== "fortuna_reflexiva"
	)
	assert (
		resolve_segment_subcategory("Tomate un mate y disfrutá el temazo que viene.", category="fortuna")
		== "fortuna_musical"
	)


def test_04_outro_mode_fallbacks_y_limpieza_de_horas(monkeypatch) -> None:
	"""4. Verifica integración real de outro_mode en contexto/generadores y que los fallbacks respeten el contexto."""
	import app.domain.radio.dialogue as dialogue_mod

	# A. No merge de categorías estructurales
	assert {"lead_in", "reaccion", "pase"}.issubset(NO_MERGE_CATEGORIES), (
		f"NO_MERGE_CATEGORIES debe incluir lead_in, reaccion y pase: {NO_MERGE_CATEGORIES}"
	)

	# B. outro_mode se propaga automáticamente cuando build_radio_dialogue_plan y generate_modular_radio_script crean el contexto
	dt_afternoon = datetime(2026, 5, 10, 14, 0)
	plan_pause = build_radio_dialogue_plan(
		fortuna=RadioPhrase("El mate se toma amargo y tranquilo.", "fortuna"),
		outro_mode="pause",
		dt=dt_afternoon,
	)
	text_plan = " ".join(t[0] for t in plan_pause).lower()
	assert "dejate llevar por el ritmo" not in text_plan, "En pausa no se debe prometer música en continuado"
	assert "cambiame la música" not in text_plan

	_, _, _, _, _, _, script_outro, _, full_script = generate_modular_radio_script(
		dt=dt_afternoon,
		outro_mode="pause",
	)
	assert script_outro in RADIO_OUTROS_PAUSE
	assert "cambiame la música" not in full_script.lower()

	# C. El fallback nunca debe reintroducir frases incompatibles con el contexto si filter_by_context descarta todas las candidatas
	ctx_morning = build_radio_context(dt=datetime(2026, 5, 10, 9, 0))
	monkeypatch.setattr(
		dialogue_mod,
		"get_intros_for_first_block",
		lambda first_block=None, gender=None: ("Tardecita dorada en la ribera.",),
	)
	plan_fallback = build_radio_dialogue_plan(
		fortuna=RadioPhrase("Una reflexión.", "fortuna"),
		ctx=ctx_morning,
	)
	chosen_intro = plan_fallback[0][0]
	assert "tardecita" not in chosen_intro.lower(), (
		f"El fallback reintrodujo una frase descartada por el filtro: {chosen_intro}"
	)
	assert phrase_fits_context(chosen_intro, ctx_morning, "intro")

	# D. El fallback final de salida debe depender de outro_mode y nunca prometer música en pause o break
	ctx_pause = build_radio_context(dt=datetime(2026, 5, 10, 15, 0), outro_mode="pause")
	pause_fallback = dialogue_mod._filter_with_safe_fallback([], ctx_pause, "salida", fallback_pool=[])
	assert len(pause_fallback) >= 1
	assert phrase_fits_context(pause_fallback[0], ctx_pause, "salida")
	assert "seguimos con más música" not in pause_fallback[0].lower()
	assert "paus" in pause_fallback[0].lower() or "respiro" in pause_fallback[0].lower()

	ctx_break = build_radio_context(dt=datetime(2026, 5, 10, 15, 0), outro_mode="break")
	break_fallback = dialogue_mod._filter_with_safe_fallback([], ctx_break, "salida", fallback_pool=[])
	assert len(break_fallback) >= 1
	assert phrase_fits_context(break_fallback[0], ctx_break, "salida")
	assert "seguimos con más música" not in break_fallback[0].lower()
	assert (
		"recreo" in break_fallback[0].lower()
		or "descanso" in break_fallback[0].lower()
		or "cola" in break_fallback[0].lower()
		or "lista" in break_fallback[0].lower()
		or "sumen" in break_fallback[0].lower()
	)


def test_05_cierres_nocturnos_y_matutinos_en_todas_las_categorias() -> None:
	"""5. Verifica que los cierres temporales (noche/previa) se integren en todas las categorías y se excluyan a la mañana."""
	from app.domain.radio.segments import get_outros_for_category

	ctx_night = build_radio_context(dt=datetime(2026, 5, 10, 22, 0))
	ctx_morning = build_radio_context(dt=datetime(2026, 5, 10, 8, 0))

	categories_to_test = ("fortuna", "chismes", "novela", "aviso", "oyentes", "alerta_criolla")

	for cat in categories_to_test:
		# De noche, todas las categorías deben tener acceso a cierres nocturnos y de previa
		night_outros = get_outros_for_category(cat, "continue", gender="m", ctx=ctx_night)
		has_night = any("levante" in o.lower() or "perreo" in o.lower() or "previa" in o.lower() for o in night_outros)
		assert has_night, f"Categoría '{cat}' no incluye cierres nocturnos/de previa en horario nocturno"

		# De mañana, ninguna categoría debe recibir cierres de noche, previa o levante
		morning_outros = get_outros_for_category(cat, "continue", gender="m", ctx=ctx_morning)
		has_inappropriate = any(
			"esta noche" in o.lower() or "perreo" in o.lower() or "levante" in o.lower() or "previa" in o.lower()
			for o in morning_outros
		)
		assert not has_inappropriate, f"Categoría '{cat}' incluyó frases de previa/noche en horario matutino (08:00)"


def test_06_simulacion_coherencia_contexto_y_modo() -> None:
	"""6. Verifica que en el simulador el contexto se construya con el modo de salida elegido y coincidan."""
	from scripts.simulate_radio_locutions import run_mock_radio_simulation

	result = run_mock_radio_simulation(iterations=300, seed=42)
	assert result["total_locutions"] == 300
	for loc in result["locutions"]:
		# En el contexto descriptivo se guarda 'modo:xyz'
		ctx_str = loc["context"]
		assert "modo:" in ctx_str
		mode = ctx_str.split("modo:")[-1].strip()
		assert mode in ("continue", "dj", "pause", "break")
		# Verificamos que ninguna locución en modo pause o break contenga frases que contradigan la pausa
		full_text = loc["full_text"].lower()
		if mode in ("pause", "break"):
			assert "¡seguimos con más música!" not in full_text
			assert "dejate llevar por el ritmo" not in full_text
			assert "cambiame la música" not in full_text


def test_07_reglas_franja_en_alertas_y_previa() -> None:
	"""7. Verifica que las alertas criollas con referencias horarias ('tarde', 'siesta', 'noche') respeten la franja."""
	ctx_morning = build_radio_context(dt=datetime(2026, 5, 11, 8, 0), temp_c=31)
	ctx_afternoon = build_radio_context(dt=datetime(2026, 5, 11, 15, 0), temp_c=31)
	ctx_night = build_radio_context(dt=datetime(2026, 5, 11, 23, 0), temp_c=31)

	alerta_tarde = "Reporte del clima pesadito: Tarde de siesta bravísima en el humedal."
	assert not phrase_fits_context(alerta_tarde, ctx_morning, "alerta_criolla")
	assert phrase_fits_context(alerta_tarde, ctx_afternoon, "alerta_criolla")
	assert not phrase_fits_context(alerta_tarde, ctx_night, "alerta_criolla")

	alerta_noche = "Noche húmeda y pesada en la ribera, no corre ni una gota de aire."
	assert not phrase_fits_context(alerta_noche, ctx_morning, "alerta_criolla")
	assert not phrase_fits_context(alerta_noche, ctx_afternoon, "alerta_criolla")
	assert phrase_fits_context(alerta_noche, ctx_night, "alerta_criolla")


def test_08_constantes_locutor_e_invalidacion_cache_indice() -> None:
	"""8. Verifica nombres claros de constantes de locutor e invalidación del lru_cache del índice de recencia."""
	from app.domain.radio.nlp import _get_phrase_recency_index, reset_radio_memory_state
	from app.domain.radio.voices import DEFAULT_HOST_NAME, FALLBACK_HOST_NAME

	assert FALLBACK_HOST_NAME == "Tomás"
	assert DEFAULT_HOST_NAME == "Transmisión de Cabina"

	# El índice se cachea al invocarse
	_get_phrase_recency_index()
	assert _get_phrase_recency_index.cache_info().currsize >= 1

	# reset_radio_memory_state debe limpiar el lru_cache
	reset_radio_memory_state(clear_db=False)
	assert _get_phrase_recency_index.cache_info().currsize == 0
