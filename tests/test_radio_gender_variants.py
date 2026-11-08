"""
Pruebas de la arquitectura de variantes por género (any, m, f) y eliminación de placeholders obsoletos.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.domain.radio.context import build_radio_context
from app.domain.radio.dialogue import (
	build_radio_dialogue_plan,
)
from app.domain.radio.nlp import get_phrase_last_played, record_phrase_played
from app.domain.radio.segments import (
	BASE_RADIO_INTROS,
	get_intros_for_first_block,
	get_pases_for_weather_condition,
)
from app.domain.radio.templates import (
	expand_phrase_variants,
	render_phrase,
	resolve_bank_for_gender,
	resolve_phrase_for_gender,
)
from app.domain.radio.validation import ALLOWED_RADIO_PLACEHOLDERS, validate_radio_banks
from app.domain.radio.voices import (
	VOICE_ELENA,
	VOICE_MARIA,
	VOICE_TOMAS,
	VOICE_VALENTINA,
	GenderVariant,
	resolve_voice_gender,
)
from app.infrastructure.db.connection import init_db


def test_gender_variant_model() -> None:
	"""Verifica la resolución directa de GenderVariant según el género solicitado."""
	gv = GenderVariant(
		m="Acá {host} el jefe de la mañana.",
		f="Acá {host} la jefa de la mañana.",
	)
	assert gv.for_gender("m") == "Acá {host} el jefe de la mañana."
	assert gv.for_gender("f") == "Acá {host} la jefa de la mañana."
	assert gv.all_variants() == (
		"Acá {host} el jefe de la mañana.",
		"Acá {host} la jefa de la mañana.",
	)


def test_resolve_phrase_and_bank_for_gender() -> None:
	"""Verifica la resolución de bancos mixtos (strings universales + GenderVariants)."""
	bank: list[str | GenderVariant] = [
		"Frase universal para cualquiera.",
		GenderVariant(
			m="Acá {host}, siempre listo.",
			f="Acá {host}, siempre lista.",
		),
	]
	resolved_m = resolve_bank_for_gender(bank, "m")
	assert resolved_m == ["Frase universal para cualquiera.", "Acá {host}, siempre listo."]

	resolved_f = resolve_bank_for_gender(bank, "f")
	assert resolved_f == ["Frase universal para cualquiera.", "Acá {host}, siempre lista."]

	assert resolve_phrase_for_gender("Solo texto", "m") == "Solo texto"
	assert resolve_phrase_for_gender("Solo texto", "f") == "Solo texto"


def test_voice_gender_resolution() -> None:
	"""Verifica que las voces del sistema resuelvan su género gramatical correctamente."""
	assert resolve_voice_gender(VOICE_TOMAS) == "m"
	assert resolve_voice_gender(VOICE_ELENA) == "f"
	assert resolve_voice_gender(VOICE_MARIA) == "f"
	assert resolve_voice_gender(VOICE_VALENTINA) == "f"
	assert resolve_voice_gender(None) == "m"


def test_expand_phrase_variants_supports_gender_variant() -> None:
	"""Verifica que expand_phrase_variants expanda ambas ramas de un GenderVariant para precarga TTS."""
	gv = GenderVariant(
		m="Acá {host}, el jefe.",
		f="Acá {host}, la jefa.",
	)
	variants = expand_phrase_variants(gv)
	assert len(variants) >= 4
	assert any("el jefe" in v for v in variants)
	assert any("la jefa" in v for v in variants)
	assert all("{" not in v and "}" not in v for v in variants)


def test_legacy_gender_placeholders_removed() -> None:
	"""Verifica que los viejos placeholders rígidos ({vocativo}, {companero}, {filosofo}) hayan sido removidos."""
	assert "vocativo" not in ALLOWED_RADIO_PLACEHOLDERS
	assert "companero" not in ALLOWED_RADIO_PLACEHOLDERS
	assert "filosofo" not in ALLOWED_RADIO_PLACEHOLDERS
	assert ALLOWED_RADIO_PLACEHOLDERS == {"momento", "saludo", "cohost", "host"}


def test_radio_intros_contain_gender_variants() -> None:
	"""Verifica que BASE_RADIO_INTROS contenga variantes de género para presentaciones del locutor."""
	has_gv = any(isinstance(intro, GenderVariant) for intro in BASE_RADIO_INTROS)
	assert has_gv, "BASE_RADIO_INTROS debe contener elementos GenderVariant"

	# Verificamos que get_intros_for_first_block filtre por género si se solicita
	m_intros = get_intros_for_first_block("hora", gender="m")
	f_intros = get_intros_for_first_block("hora", gender="f")
	assert all(isinstance(i, str) for i in m_intros)
	assert all(isinstance(i, str) for i in f_intros)
	assert any("listo" in i for i in m_intros)
	assert any("lista" in i for i in f_intros)


def test_pases_and_reactions_use_gender_variants() -> None:
	"""Verifica que pases y reacciones usen GenderVariant para compadre/comadre y filósofo/filósofa."""
	pases_m = get_pases_for_weather_condition("frio", gender="m")
	pases_f = get_pases_for_weather_condition("frio", gender="f")
	assert any("compadre" in p for p in pases_m)
	assert any("comadre" in p for p in pases_f)
	assert not any("comadre" in p for p in pases_m)
	assert not any("compadre" in p for p in pases_f)


def test_dialogue_plan_uses_correct_gender_for_host_and_cohost(tmp_path: Path) -> None:
	"""Verifica que en el diálogo el host reciba frases acordes a su género y el cohost a su género."""
	db_file = tmp_path / "test_dialogue_gender.db"
	init_db(db_file)
	ctx = build_radio_context(datetime(2026, 11, 8, 10, 0))

	# Tomás (m) de host, Elena (f) de cohost
	plan_tomas_elena = build_radio_dialogue_plan(
		host_voice=VOICE_TOMAS,
		cohost_voice=VOICE_ELENA,
		weather_text="Cielo despejado",
		ctx=ctx,
		db_path=db_file,
	)
	# La intro de Tomás (host m) nunca debe contener palabras femeninas de locutor como "la jefa" o "siempre lista"
	intro_text = plan_tomas_elena[0][0]
	assert "la jefa" not in intro_text
	assert "siempre lista" not in intro_text

	# El pase de Tomás a Elena (cohost f) debe usar términos femeninos si es gendered ("comadre")
	pase_turn = next(turn for turn in plan_tomas_elena if turn[2] == "pase")
	pase_text = pase_turn[0]
	assert "compadre" not in pase_text  # Elena es mujer

	# Elena (f) de host, Tomás (m) de cohost
	plan_elena_tomas = build_radio_dialogue_plan(
		host_voice=VOICE_ELENA,
		cohost_voice=VOICE_TOMAS,
		weather_text="Cielo despejado",
		ctx=ctx,
		db_path=db_file,
	)

	intro_elena = plan_elena_tomas[0][0]
	assert "el jefe" not in intro_elena
	assert "siempre listo" not in intro_elena

	pase_elena_turn = next(turn for turn in plan_elena_tomas if turn[2] == "pase")
	pase_elena_text = pase_elena_turn[0]
	assert "comadre" not in pase_elena_text  # Tomás es varón


def test_recency_anti_repetition_couples_gender_variants(tmp_path: Path) -> None:
	"""Verifica que registrar la reproducción de una variante femenina impida que la masculina se repita de inmediato."""
	db_file = tmp_path / "test_recency_coupling.db"
	init_db(db_file)

	# Buscamos una intro GenderVariant real de BASE_RADIO_INTROS
	gv = next(i for i in BASE_RADIO_INTROS if isinstance(i, GenderVariant) and "jefe" in i.m)

	# Elena dice la versión femenina
	spoken_f = render_phrase(gv.f, host_name="Elena", host_voice=VOICE_ELENA)
	record_phrase_played(spoken_f, category="intro", timestamp=50000.0, db_path=db_file)

	# La consulta sobre la versión masculina ("Acá Tomás, el jefe...") debe reflejar que ya fue reproducida
	last_m = get_phrase_last_played(gv.m, category="intro", db_path=db_file)
	assert last_m == 50000.0


def test_build_content_block_has_no_unreachable_code() -> None:
	"""Verifica por AST que _build_content_block no tenga sentencias inalcanzables tras el return."""
	import ast

	dialogue_path = Path("app/domain/radio/dialogue.py")
	tree = ast.parse(dialogue_path.read_text(encoding="utf-8"))

	content_block_fn = None
	for node in ast.walk(tree):
		if isinstance(node, ast.FunctionDef) and node.name == "_build_content_block":
			content_block_fn = node
			break

	assert content_block_fn is not None, "No se encontró la función _build_content_block"
	returns = [stmt for stmt in content_block_fn.body if isinstance(stmt, ast.Return)]
	assert len(returns) == 1, f"Se esperaba exactamente 1 return en _build_content_block, pero hay {len(returns)}"
	assert isinstance(content_block_fn.body[-1], ast.Return), "La última sentencia debe ser el return"


def test_carpincho_gender_styling_phrases_in_banks() -> None:
	"""Verifica que los bancos contengan frases que retraten la feminidad y masculinidad carpincha (ropa, facha, looks)."""
	from app.domain.radio.segments import PASES_A_CLIMA, RADIO_OUTROS

	# 1. Intros con bermudas / mini / looks
	intros_gv = [i for i in BASE_RADIO_INTROS if isinstance(i, GenderVariant)]
	assert any("mini re cortita" in i.f and "bermudas" in i.m for i in intros_gv)
	assert any("congelan las patas" in i.f for i in intros_gv)

	# 2. Outros con pollera / bermudas o calzado festivo
	outros_gv = [o for o in RADIO_OUTROS if isinstance(o, GenderVariant)]
	assert any("pollera" in o.f and "bermudas" in o.m for o in outros_gv)

	# 3. Pases al clima con looks de frío / calor
	pases_gv = [p for p in PASES_A_CLIMA if isinstance(p, GenderVariant)]
	assert any("mini re cortita" in p.f or "solero" in p.f for p in pases_gv)


def test_sensual_and_suggestive_carpincho_phrases_in_banks() -> None:
	"""Verifica frases sugestivas y sensuales carpinchas en fin de cola (break), outros e intros."""
	from app.domain.radio.segments import RADIO_OUTROS_BREAK, get_outros_for_category

	# 1. Fin de cola (break outros) con 'after con mi gata / gato' y 'perreando'
	break_gv = [b for b in RADIO_OUTROS_BREAK if isinstance(b, GenderVariant)]
	assert any("after con mi gata" in b.m and "after con mi gato" in b.f for b in break_gv)
	assert any("perreando" in b.m and "perreando" in b.f for b in break_gv)

	# 2. Resolución de género en break
	break_m = get_outros_for_category("", outro_mode="break", gender="m")
	break_f = get_outros_for_category("", outro_mode="break", gender="f")
	assert any("after con mi gata" in o for o in break_m)
	assert any("after con mi gato" in o for o in break_f)
	assert not any("after con mi gato" in o for o in break_m)
	assert not any("after con mi gata" in o for o in break_f)


def test_static_validation_passes_with_gender_variants() -> None:
	"""Verifica que validate_radio_banks valide la integridad sin placeholders obsoletos."""
	validate_radio_banks(strict=True)
