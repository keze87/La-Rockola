"""
Manejo de contexto temporal, meteorológico y filtrado contextual de frases radiales.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import NamedTuple

FRANJAS: tuple[str, ...] = ("madrugada", "mañana", "mediodia", "tarde", "noche")
FRANJAS_DIURNAS: frozenset[str] = frozenset({"mañana", "mediodia", "tarde"})
FRANJAS_NOCTURNAS: frozenset[str] = frozenset({"noche", "madrugada"})

# Siempre femeninos para que concuerde el adjetivo ("{momento} está tan pesada")
MOMENTO_POR_FRANJA: dict[str, str] = {
	"madrugada": "la madrugada",
	"mañana": "la mañana",
	"mediodia": "la jornada",
	"tarde": "la tarde",
	"noche": "la noche",
}
SALUDOS_UNICOS: tuple[str, ...] = ("Buen día", "Buenas tardes", "Buenas noches")
DIAS_SEMANA: tuple[str, ...] = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

VOCATIVOS: dict[str, str] = {"m": "compadre", "f": "comadre"}
COMPANEROS: dict[str, str] = {"m": "compañero", "f": "compañera"}
FILOSOFOS: dict[str, str] = {"m": "filósofo", "f": "filósofa"}


class RadioContext(NamedTuple):
	"""Situación en vivo de la transmisión (hora, día, estación y temperatura conocida)."""

	franja: str = "tarde"
	momento: str = "la tarde"
	saludo: str = "Buenas tardes"
	dia_semana: int = 0  # 0 = lunes ... 6 = domingo
	dia_nombre: str = "lunes"
	es_finde: bool = False
	estacion: str = "primavera"
	mes: int = 10
	temp_c: int | None = None


def get_franja_horaria(hour: int) -> str:
	"""madrugada 0-5, mañana 6-11, mediodía 12-13, tarde 14-19, noche 20-23."""
	h = int(hour) % 24
	if h < 6:
		return "madrugada"
	if h < 12:
		return "mañana"
	if h < 14:
		return "mediodia"
	if h < 20:
		return "tarde"
	return "noche"


def get_saludo_horario(hour: int) -> str:
	"""Saludo radial acorde a la hora ("Buen día" desde las 5 hasta el mediodía)."""
	h = int(hour) % 24
	if h < 5:
		return "Buenas noches"
	if h < 12:
		return "Buen día"
	if h < 20:
		return "Buenas tardes"
	return "Buenas noches"


def get_estacion(month: int) -> str:
	"""Estación meteorológica del hemisferio sur."""
	if month in (12, 1, 2):
		return "verano"
	if month in (3, 4, 5):
		return "otoño"
	if month in (6, 7, 8):
		return "invierno"
	return "primavera"


def build_radio_context(dt: datetime | None = None, temp_c: float | None = None) -> RadioContext:
	"""Arma el contexto de la transmisión a partir de la fecha/hora local y (opcional) la temperatura actual."""
	if dt is None:
		dt = datetime.now().astimezone()
	wd = dt.weekday()
	franja = get_franja_horaria(dt.hour)
	return RadioContext(
		franja=franja,
		momento=MOMENTO_POR_FRANJA[franja],
		saludo=get_saludo_horario(dt.hour),
		dia_semana=wd,
		dia_nombre=DIAS_SEMANA[wd],
		es_finde=wd >= 5,
		estacion=get_estacion(dt.month),
		mes=dt.month,
		temp_c=None if temp_c is None else round(float(temp_c)),
	)


def context_allows(cond: str, ctx: RadioContext) -> bool:
	"""
	Filtro de verosimilitud climática y estacional para la atmósfera satírica de la radio.
	No es un sensor meteorológico fáctico: usa la temperatura real si se conoce y, si no, el mes calendario.
	"""
	t = ctx.temp_c
	if cond == "calor":
		return t >= 26 if t is not None else ctx.mes in (11, 12, 1, 2, 3)
	if cond == "frio":
		return t <= 14 if t is not None else ctx.mes in (5, 6, 7, 8)
	if cond == "bichos":
		return t >= 16 if t is not None else ctx.mes in (10, 11, 12, 1, 2, 3, 4)
	return True


class _ContextRule(NamedTuple):
	pattern: re.Pattern[str]
	franjas: frozenset[str] | None = None
	dias: frozenset[int] | None = None
	cond: str | None = None
	only_categories: frozenset[str] | None = None


def _rule(
	pattern: str,
	franjas: tuple[str, ...] | None = None,
	dias: tuple[int, ...] | None = None,
	cond: str | None = None,
	only_categories: tuple[str, ...] | None = None,
) -> _ContextRule:
	return _ContextRule(
		re.compile(pattern, re.IGNORECASE),
		frozenset(franjas) if franjas else None,
		frozenset(dias) if dias else None,
		cond,
		frozenset(only_categories) if only_categories else None,
	)


_CAT_CLIMA_CRIOLLA = ("alerta_criolla", "aviso", "oyentes")
_CAT_LOCUCION_EN_VIVO = ("intro", "clima", "salida", "pase")

# Una frase que cumple una regla solo se puede decir cuando el contexto la satisface (todas las que apliquen).
CONTEXT_RULES: list[_ContextRule] = [
	# --- Franja horaria para locución y clima en vivo ---
	# Saludos y reportes temporales inmediatos (intros, clima, salidas, pases)
	_rule(r"\btard(?:e|ecit\w*)\b", franjas=("tarde",), only_categories=_CAT_LOCUCION_EN_VIVO),
	_rule(r"\bmadrugada\b", franjas=("madrugada", "mañana"), only_categories=_CAT_LOCUCION_EN_VIVO),
	_rule(
		r"\bde la mañana\b",
		franjas=("madrugada", "mañana", "mediodia"),
		only_categories=("intro", "clima", "salida", "hora"),
	),
	_rule(r"\b(?:noche larga|turno noche|cuadrilla de la noche|trasnoch\w*)\b", franjas=("noche", "madrugada")),
	_rule(r"\bse nos viene la noche\b", franjas=("mediodia", "tarde")),
	# El sol en sentido meteorológico literal (no metafórico como 'trapitos al sol' ni marcas comerciales)
	_rule(
		r"(?<!trapitos al )(?<!panadería el )\bsol(?:azo|cito)?\b",
		franjas=("mañana", "mediodia", "tarde"),
		only_categories=("clima", "alerta_criolla", "pase"),
	),
	_rule(r"\bsol cae\b|\bcae el sol\b", franjas=("tarde",), only_categories=_CAT_LOCUCION_EN_VIVO),
	_rule(r"\bgolondrinas?\b", franjas=("mañana", "mediodia", "tarde"), only_categories=("clima", "pase")),
	_rule(r"\barriba, arriba\b", franjas=("madrugada", "mañana"), only_categories=("intro", "salida")),
	_rule(r"\byendo a laburar\b", franjas=("mañana", "mediodia", "tarde", "noche")),
	# --- Día de la semana (convocatorias futuras vs menciones cotidianas/históricas) ---
	_rule(
		r"\b(?:este|el próximo)\s+domingo\b|\bel domingo\s+después de misa\b",
		dias=(0, 1, 2, 3, 4, 5),
		only_categories=("aviso",),
	),
	_rule(r"\beste sábado\b", dias=(0, 1, 2, 3, 4, 5), only_categories=("aviso",)),
	# --- Estación / temperatura real (filtros de verosimilitud atmosférica) ---
	_rule(
		r"\bcalor\w*|\bcuarenta grados\b|\bventilador\b|\basfalto\b|\bsudando\b|\bverano\b|\bheladera\b",
		cond="calor",
		only_categories=_CAT_CLIMA_CRIOLLA,
	),
	_rule(
		r"\bmosquitos?\b|\bjejenes\b|\btábanos\b|\bmoscas\b",
		cond="bichos",
		only_categories=("alerta_criolla", "aviso"),
	),
]


def _split_item(item: object, category: str | None = None) -> tuple[str, str | None]:
	"""Extrae (texto, categoría) de un str, una tupla o un RadioPhrase."""
	if isinstance(item, tuple):
		text = item[0] if item else ""
		cat = item[1] if len(item) > 1 and item[1] else category
		return str(text), cat
	return str(item), category


def phrase_fits_context(text: str, ctx: RadioContext | None, category: str | None = None) -> bool:
	"""True si la frase es coherente con la franja horaria, el día y el clima actuales (ctx None => siempre)."""
	if ctx is None or not text:
		return True
	for rule in CONTEXT_RULES:
		if rule.only_categories and category not in rule.only_categories:
			continue
		if not rule.pattern.search(text):
			continue
		if rule.franjas and ctx.franja not in rule.franjas:
			return False
		if rule.dias and ctx.dia_semana not in rule.dias:
			return False
		if rule.cond and not context_allows(rule.cond, ctx):
			return False
	return True


def filter_by_context(candidates: list, ctx: RadioContext | None, category: str | None = None) -> list:
	"""
	Descarta las frases incoherentes con el contexto (franja horaria, día o clima).
	Retorna únicamente las frases compatibles, o una lista vacía si ninguna cumple las reglas.
	Deja en manos de quien llama la decisión explícita de política de fallback.
	"""
	if ctx is None:
		return list(candidates)
	kept = []
	for c in candidates:
		text, cat = _split_item(c, category)
		if phrase_fits_context(text, ctx, cat):
			kept.append(c)
	return kept
