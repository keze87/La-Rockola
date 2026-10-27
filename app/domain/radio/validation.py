"""
Validación estática y automática de bancos de frases, plantillas, placeholders y metadatos del dominio de radio.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain.radio.classification import CARPINCHO_PHRASES, RadioPhrase
from app.domain.radio.phrase_banks.advertisements import (
	AVISOS_PARROQUIALES_Y_EXTRAVIOS,
)
from app.domain.radio.phrase_banks.fortunes import (
	CARPINCHO_SABIDURIA,
)
from app.domain.radio.phrase_banks.gossip import (
	CHISMES_CARPINCHOS,
)
from app.domain.radio.phrase_banks.listeners import (
	ALERTAS_INCOMODIDAD_CRIOLLA,
	DEDICATORIAS_OYENTES,
	SEPARADORES_Y_SLOGANS,
	TRANSITO_FLUVIAL_Y_CAMINOS,
)
from app.domain.radio.phrase_banks.soap_opera import (
	NOVELA_VECINAL,
)
from app.domain.radio.segments import (
	LEAD_INS_BY_CATEGORY,
	OUTROS_BY_CATEGORY,
	PASES_A_CLIMA,
	RADIO_INTROS,
	RADIO_LEAD_INS,
	RADIO_OUTROS,
	RADIO_REACTIONS,
	WEATHER_TEMPLATES,
)
from app.domain.radio.templates import expand_phrase_variants

ALLOWED_RADIO_PLACEHOLDERS: frozenset[str] = frozenset(
	{"vocativo", "companero", "filosofo", "momento", "saludo", "cohost"}
)
ALLOWED_WEATHER_PLACEHOLDERS: frozenset[str] = frozenset(
	{
		"lead",
		"location",
		"temp_str",
		"min_today_str",
		"max_today_str",
		"range_tomorrow_str",
		"lluvia_desc",
		"desc_phrase",
	}
)
VALID_CATEGORIES: frozenset[str] = frozenset({"fortuna", "aviso", "alerta_criolla", "oyentes", "chismes", "novela"})
MAX_ALLOWED_VARIANTS_PER_TEMPLATE: int = 120
PLACEHOLDER_REGEX = re.compile(r"\{([^{}]+)\}")


def validate_radio_banks(strict: bool = False) -> list[str]:
	"""
	Valida automáticamente la integridad de todos los bancos de frases y plantillas de radio:
	1. Placeholders desconocidos en plantillas radiales o de clima.
	2. Frases vacías o con espacios en blanco únicamente.
	3. Metadatos de categoría faltantes o inválidos en RadioPhrase.
	4. Entradas duplicadas en bancos donde se espera unicidad léxica.
	5. Conteo de variantes excesivo o explosión combinatoria incontrolada.
	"""
	issues: list[str] = []

	# Bancos con verificación de unicidad léxica y no vacíos
	banks_to_check: dict[str, Sequence[str]] = {
		"CARPINCHO_SABIDURIA": CARPINCHO_SABIDURIA,
		"AVISOS_PARROQUIALES_Y_EXTRAVIOS": AVISOS_PARROQUIALES_Y_EXTRAVIOS,
		"TRANSITO_FLUVIAL_Y_CAMINOS": TRANSITO_FLUVIAL_Y_CAMINOS,
		"ALERTAS_INCOMODIDAD_CRIOLLA": ALERTAS_INCOMODIDAD_CRIOLLA,
		"SEPARADORES_Y_SLOGANS": SEPARADORES_Y_SLOGANS,
		"DEDICATORIAS_OYENTES": DEDICATORIAS_OYENTES,
		"CHISMES_CARPINCHOS": CHISMES_CARPINCHOS,
		"NOVELA_VECINAL": NOVELA_VECINAL,
		"PASES_A_CLIMA": PASES_A_CLIMA,
		"RADIO_REACTIONS": RADIO_REACTIONS,
	}

	for bank_name, phrases in banks_to_check.items():
		seen: set[str] = set()
		for p in phrases:
			if not p or not p.strip():
				issues.append(f"{bank_name}: contiene frase vacía o sólo espacios.")
			elif p in seen:
				issues.append(f"{bank_name}: frase duplicada detectada: '{p[:40]}...'")
			seen.add(p)

	# 1 & 5. Placeholders desconocidos y explosión de variantes
	templates_to_check: dict[str, Sequence[str]] = {
		"RADIO_INTROS": RADIO_INTROS,
		"RADIO_LEAD_INS": RADIO_LEAD_INS,
		"RADIO_OUTROS": RADIO_OUTROS,
		"PASES_A_CLIMA": PASES_A_CLIMA,
		"RADIO_REACTIONS": RADIO_REACTIONS,
	}
	for cat, lead_in_list in LEAD_INS_BY_CATEGORY.items():
		templates_to_check[f"LEAD_INS_{cat}"] = lead_in_list
	for cat, outro_list in OUTROS_BY_CATEGORY.items():
		templates_to_check[f"OUTROS_{cat}"] = outro_list

	for name, collection in templates_to_check.items():
		for tpl in collection:
			found = set(PLACEHOLDER_REGEX.findall(tpl))
			unknown = found - ALLOWED_RADIO_PLACEHOLDERS
			if unknown:
				issues.append(f"{name}: placeholders desconocidos {unknown} en '{tpl}'")
			if "{" in tpl:
				vars_count = len(expand_phrase_variants(tpl))
				if vars_count > MAX_ALLOWED_VARIANTS_PER_TEMPLATE:
					issues.append(
						f"{name}: explosión de variantes ({vars_count} > {MAX_ALLOWED_VARIANTS_PER_TEMPLATE}) en '{tpl}'"
					)

	# Plantillas de clima
	for tpl in WEATHER_TEMPLATES:
		found = set(PLACEHOLDER_REGEX.findall(tpl))
		unknown = found - ALLOWED_WEATHER_PLACEHOLDERS
		if unknown:
			issues.append(f"WEATHER_TEMPLATES: placeholders desconocidos {unknown} en '{tpl}'")

	# 3. Metadatos de categoría en RadioPhrase
	for rp in CARPINCHO_PHRASES:
		if not isinstance(rp, RadioPhrase):
			issues.append(f"CARPINCHO_PHRASES: elemento no es RadioPhrase: {rp}")
			continue
		if not rp.text or not rp.text.strip():
			issues.append(f"CARPINCHO_PHRASES: RadioPhrase con texto vacío (categoría '{rp.category}')")
		if rp.category not in VALID_CATEGORIES:
			issues.append(f"CARPINCHO_PHRASES: categoría inválida o faltante '{rp.category}' en '{rp.text[:30]}...'")

	if strict and issues:
		raise ValueError(f"Fallo en validación de bancos de frases: {issues}")

	return issues
