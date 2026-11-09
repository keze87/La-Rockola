"""
Plantillas dinámicas, renderizado contextual y expansión de variantes radiales y meteorológicas.
"""

from __future__ import annotations

import functools
import random
import re

from app.domain.radio.classification import resolve_weather_desc_category
from app.domain.radio.context import (
	FRANJAS_NOCTURNAS,
	MOMENTO_POR_FRANJA,
	SALUDOS_UNICOS,
	RadioContext,
	filter_by_context,
)
from app.domain.radio.phrase_banks.weather import WEATHER_DESC_PHRASES
from app.domain.radio.voices import (
	DEFAULT_COHOST_NAME,
	FALLBACK_HOST_NAME,
	VOICE_NAMES,
	GenderVariant,
)


def get_weather_desc_phrase(
	desc: str | None = None,
	code: int | str | None = None,
	lang_es: str | None = None,
	variant_idx: int | None = None,
	ctx: RadioContext | None = None,
) -> str:
	"""
	Retorna una frase descriptiva con impronta criolla para el estado actual del cielo
	según el weatherDesc, weatherCode o lang_es de wttr.in.
	Si no se proporcionan descripciones ni códigos válidos, retorna cadena vacía "".
	Si variant_idx se especifica, retorna esa variante determinista (variant_idx=0 es la clásica).
	Si variant_idx es None, elige una variante aleatoria.
	"""
	if not desc and code is None and not lang_es:
		return ""

	category = resolve_weather_desc_category(desc=desc, code=code, lang_es=lang_es)
	if ctx is not None and category == "sunny" and ctx.franja in FRANJAS_NOCTURNAS:
		category = "clear_night"
	options = WEATHER_DESC_PHRASES.get(category, WEATHER_DESC_PHRASES["default"])
	if ctx is not None:
		# Filtramos con category="clima" para activar las reglas de sol, tarde y meteorología
		filtered_opts = filter_by_context(options, ctx, category="clima")
		if not filtered_opts:
			# Fallback seguro: filtramos también el banco por defecto con category="clima"
			fallback_filtered = filter_by_context(WEATHER_DESC_PHRASES["default"], ctx, category="clima")
			filtered_opts = fallback_filtered if fallback_filtered else list(WEATHER_DESC_PHRASES["default"])
		options = filtered_opts
	if variant_idx is not None:
		return options[variant_idx % len(options)]
	return random.choice(options)


def get_all_weather_desc_phrases() -> list[str]:
	"""Devuelve la lista consolidada de las descripciones climáticas canónicas."""
	res: list[str] = []
	for category, p_list in WEATHER_DESC_PHRASES.items():
		if category == "default":
			continue
		for p in p_list:
			if p not in res:
				res.append(p)
	return res


# ---------------------------------------------------------------------------
# Charla de cabina: Pases y Reacciones
# ---------------------------------------------------------------------------


_PLACEHOLDER_RE = re.compile(r"\{(momento|saludo|cohost|host)\}")


def resolve_phrase_for_gender(phrase: str | GenderVariant, gender: str) -> str:
	"""Resuelve una frase o GenderVariant al texto correspondiente para el género solicitado ('m' o 'f')."""
	if isinstance(phrase, GenderVariant):
		return phrase.for_gender(gender)
	return str(phrase)


def resolve_bank_for_gender(
	bank: list[str | GenderVariant] | tuple[str | GenderVariant, ...],
	gender: str,
) -> list[str]:
	"""Resuelve una colección de frases o GenderVariants a una lista de cadenas acordes al género ('m' o 'f')."""
	return [resolve_phrase_for_gender(p, gender) for p in bank]


def _placeholder_values(
	momento: str,
	saludo: str,
	cohost_name: str | None,
	host_name: str | None = None,
) -> dict[str, str]:
	return {
		"momento": momento,
		"saludo": saludo,
		"cohost": cohost_name or DEFAULT_COHOST_NAME,
		"host": host_name or FALLBACK_HOST_NAME,
	}


def render_phrase(
	template: str,
	ctx: RadioContext | None = None,
	cohost_name: str | None = None,
	host_name: str | None = None,
	host_voice: str | None = None,
) -> str:
	"""
	Resuelve los placeholders de una plantilla radial: {momento}, {saludo} (según la franja horaria), {cohost} y {host}.
	Sin ctx usa fórmulas neutras ("la jornada", "Muy buenas"). Las llaves desconocidas se dejan intactas.
	"""
	if "{" not in template:
		return template
	momento = ctx.momento if ctx else "la jornada"
	saludo = ctx.saludo if ctx else "Muy buenas"
	effective_host = host_name or (
		VOICE_NAMES.get(host_voice, FALLBACK_HOST_NAME) if host_voice else FALLBACK_HOST_NAME
	)
	values = _placeholder_values(momento, saludo, cohost_name, effective_host)
	return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


@functools.lru_cache(maxsize=512)
def _expand_phrase_variants_cached(template: str) -> tuple[str, ...]:
	needs = set(_PLACEHOLDER_RE.findall(template))
	if not needs:
		return (template,)
	voice_names: list[str | None] = [name for name in VOICE_NAMES.values()]
	hosts: list[str | None] = voice_names if "host" in needs else [None]
	cohosts: list[str | None] = voice_names if "cohost" in needs else [None]
	momentos: list[str] = list(dict.fromkeys(MOMENTO_POR_FRANJA.values())) if "momento" in needs else [""]
	saludos: list[str] = list(SALUDOS_UNICOS) if "saludo" in needs else [""]
	out: list[str] = []
	for h_name in hosts:
		for c_name in cohosts:
			if h_name is not None and c_name is not None and h_name == c_name:
				continue
			for momento in momentos:
				for saludo in saludos:
					values = _placeholder_values(momento, saludo, cohost_name=c_name, host_name=h_name)
					text = _PLACEHOLDER_RE.sub(lambda m, v=values: v[m.group(1)], template)
					if text not in out:
						out.append(text)
	return tuple(out)


def expand_phrase_variants(template: str | GenderVariant) -> list[str]:
	"""Todas las versiones habladas posibles de una plantilla o GenderVariant (útil para precargar la caché de TTS)."""
	if isinstance(template, GenderVariant):
		res: list[str] = []
		for variant_text in template.all_variants():
			for expanded in _expand_phrase_variants_cached(variant_text):
				if expanded not in res:
					res.append(expanded)
		return res
	return list(_expand_phrase_variants_cached(template))
