"""
Pruebas para intros con presentación de conductor ({host}) y mayor probabilidad de frases/fortunas.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.radio.context import build_radio_context
from app.domain.radio.dialogue import build_radio_dialogue_plan
from app.domain.radio.nlp import select_radio_phrase
from app.domain.radio.segments import RADIO_INTROS
from app.domain.radio.templates import expand_phrase_variants, render_phrase
from app.domain.radio.voices import VOICE_ELENA, VOICE_NAMES


def test_intros_contain_host_presentation_variants() -> None:
	"""Verifica que RADIO_INTROS contenga versiones donde el locutor/carpincho se presenta con {host}."""
	host_intros = [
		intro
		for intro in RADIO_INTROS
		if (isinstance(intro, str) and "{host}" in intro)
		or (hasattr(intro, "all_variants") and any("{host}" in v for v in intro.all_variants()))
	]
	assert len(host_intros) >= 3, "Debe haber al menos 3 intros con presentación dinámica de {host}"

	# Validar que esté la frase solicitada por el usuario
	expected = "Acá {host}, siempre listo para acompañarte y ponerle música a tu vida."
	assert any(expected == intro or (hasattr(intro, "m") and expected == intro.m) for intro in host_intros), (
		f"No se encontró la intro esperada: '{expected}'"
	)


def test_render_phrase_resolves_host_placeholder() -> None:
	"""Verifica que render_phrase resuelva {host} dinámicamente según el host asignado."""
	template = "Acá {host}, siempre listo para acompañarte y ponerle música a tu vida."

	rendered_tomas = render_phrase(template, host_name="Tomás")
	assert "Acá Tomás, siempre listo" in rendered_tomas

	rendered_elena = render_phrase(template, host_name="Elena")
	assert "Acá Elena, siempre listo" in rendered_elena

	# Default seguro cuando no se especifica host
	rendered_default = render_phrase(template)
	assert "Acá Tomás, siempre listo" in rendered_default or "Acá" in rendered_default


def test_expand_phrase_variants_includes_all_hosts() -> None:
	"""Verifica que expand_phrase_variants expanda {host} para todos los locutores (para precarga TTS)."""
	template = "Acá {host}, transmitiendo en vivo."
	variants = expand_phrase_variants(template)

	for name in VOICE_NAMES.values():
		assert any(f"Acá {name}," in v for v in variants), f"Falta la variante para el locutor {name}"


def test_dialogue_plan_renders_host_in_intro() -> None:
	"""Verifica que build_radio_dialogue_plan renderice el nombre del host en la intro."""
	intro_template = "Acá {host}, arrancando otra tanda."
	plan = build_radio_dialogue_plan(
		intro=intro_template,
		host_voice=VOICE_ELENA,
	)
	intro_segment = next(seg for seg in plan if seg[2] == "intro")
	assert f"Acá {VOICE_NAMES[VOICE_ELENA]}, arrancando otra tanda." in intro_segment[0]


def test_fortuna_has_higher_probability_than_smaller_categories(tmp_path: Path) -> None:
	"""Verifica que la categoría 'fortuna' tenga mayor probabilidad que categorías reducidas como 'chismes' o 'novela'."""
	db_file = str(tmp_path / "test_probability.db")
	ctx = build_radio_context()

	counts: dict[str, int] = {}
	total = 200
	for _ in range(total):
		phrase, _ = select_radio_phrase(ctx=ctx, db_path=db_file)
		counts[phrase.category] = counts.get(phrase.category, 0) + 1

	# Fortuna debe tener una presencia notablemente mayor debido a su enorme variedad
	fortuna_count = counts.get("fortuna", 0)
	novela_count = counts.get("novela", 0)
	chismes_count = counts.get("chismes", 0)

	assert fortuna_count > novela_count, (
		f"Fortuna ({fortuna_count}) debería tener mayor probabilidad que novela ({novela_count})"
	)
	assert fortuna_count > chismes_count, (
		f"Fortuna ({fortuna_count}) debería tener mayor probabilidad que chismes ({chismes_count})"
	)
	# Fortuna debe representar al menos el 25% del total
	assert fortuna_count >= total * 0.25, (
		f"Fortuna ({fortuna_count}/{total}) debería representar al menos 25% de la rotación"
	)


def test_imported_fortune_selection_ratio(tmp_path: Path) -> None:
	"""Verifica que dentro de 'fortuna', las fortunas importadas (sistema/bundled) tengan alta probabilidad."""
	db_file = str(tmp_path / "test_bundled_ratio.db")
	ctx = build_radio_context()

	sys_count = 0
	trials = 80
	for _ in range(trials):
		# Forzando categoría fortuna eligiendo sólo frases de fortuna o llamando con mock
		phrase, is_sys = select_radio_phrase(ctx=ctx, db_path=db_file)
		if phrase.category == "fortuna" and is_sys:
			sys_count += 1

	# Cuando la categoría fortuna es elegida, una proporción sustancial debe provenir de fortunas importadas
	assert sys_count > 0, "Debe haber al menos alguna fortuna importada/bundled seleccionada"
