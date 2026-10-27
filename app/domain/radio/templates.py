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
	COMPANEROS,
	DEFAULT_COHOST_NAME,
	DEFAULT_GENDER,
	FILOSOFOS,
	VOCATIVOS,
	VOICE_GENDERS,
	VOICE_NAMES,
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
		# Evita "tarde templada" de madrugada o "sol radiante" de noche
		filtered_opts = filter_by_context(options, ctx)
		options = filtered_opts if filtered_opts else WEATHER_DESC_PHRASES["default"]
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


_PLACEHOLDER_RE = re.compile(r"\{(vocativo|companero|filosofo|momento|saludo|cohost)\}")


def _placeholder_values(
	gender: str,
	momento: str,
	saludo: str,
	cohost_name: str | None,
) -> dict[str, str]:
	return {
		"vocativo": VOCATIVOS.get(gender, VOCATIVOS[DEFAULT_GENDER]),
		"companero": COMPANEROS.get(gender, COMPANEROS[DEFAULT_GENDER]),
		"filosofo": FILOSOFOS.get(gender, FILOSOFOS[DEFAULT_GENDER]),
		"momento": momento,
		"saludo": saludo,
		"cohost": cohost_name or DEFAULT_COHOST_NAME,
	}


def render_phrase(
	template: str,
	ctx: RadioContext | None = None,
	addressee_voice: str | None = None,
	cohost_name: str | None = None,
) -> str:
	"""
	Resuelve los placeholders de una frase: {vocativo}, {companero}, {filosofo} (concuerdan con el género de
	quien recibe el mensaje, addressee_voice), {momento}, {saludo} (según la franja horaria) y {cohost}.
	Sin ctx usa fórmulas neutras ("la jornada", "Muy buenas"). Las llaves desconocidas se dejan intactas.
	"""
	if "{" not in template:
		return template
	gender = VOICE_GENDERS.get(addressee_voice or "", DEFAULT_GENDER)
	momento = ctx.momento if ctx else "la jornada"
	saludo = ctx.saludo if ctx else "Muy buenas"
	values = _placeholder_values(gender, momento, saludo, cohost_name)
	return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


@functools.lru_cache(maxsize=512)
def _expand_phrase_variants_cached(template: str) -> tuple[str, ...]:
	needs = set(_PLACEHOLDER_RE.findall(template))
	if not needs:
		return (template,)
	if "cohost" in needs:
		subjects: list[tuple[str | None, str]] = [
			(name, VOICE_GENDERS.get(v, DEFAULT_GENDER)) for v, name in VOICE_NAMES.items()
		]
	elif needs & {"vocativo", "companero", "filosofo"}:
		subjects = [(None, "m"), (None, "f")]
	else:
		subjects = [(None, DEFAULT_GENDER)]
	momentos: list[str] = list(dict.fromkeys(MOMENTO_POR_FRANJA.values())) if "momento" in needs else [""]
	saludos: list[str] = list(SALUDOS_UNICOS) if "saludo" in needs else [""]
	out: list[str] = []
	for name, gender in subjects:
		for momento in momentos:
			for saludo in saludos:
				values = _placeholder_values(gender, momento, saludo, name)
				text = _PLACEHOLDER_RE.sub(lambda m, v=values: v[m.group(1)], template)
				if text not in out:
					out.append(text)
	return tuple(out)


def expand_phrase_variants(template: str) -> list[str]:
	"""Todas las versiones habladas posibles de una plantilla (útil para precargar la caché de TTS)."""
	return list(_expand_phrase_variants_cached(template))
