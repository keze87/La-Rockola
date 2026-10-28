"""
Cliente meteorológico y formateador criollo de pronósticos (wttr.in) con caché en memoria.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.domain.radio.classification import resolve_weather_desc_category
from app.domain.radio.context import RadioContext
from app.domain.radio.phrase_banks.weather import (
	DEFAULT_WEATHER_LOCATION,
	PRECIPITATING_CATEGORIES,
	RAIN_DESCRIPTIONS,
	WEATHER_RAIN_THRESHOLD,
)
from app.domain.radio.segments import (
	WEATHER_LEAD_INS,
	WEATHER_TEMPLATES,
)
from app.domain.radio.templates import get_weather_desc_phrase

logger = logging.getLogger("rockola.radio")

_WEATHER_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
WEATHER_CACHE_TTL: float = 30 * 60


def reset_weather_cache() -> None:
	"""Limpia la caché en memoria de pronósticos meteorológicos."""
	_WEATHER_CACHE.clear()


def construir_url_json(lugar: str, idioma: str = "es") -> str:
	"""Construye la URL de consulta JSON para wttr.in."""
	lugar_limpio = lugar.strip() if lugar else ""
	lugar_escapado = urllib.parse.quote(lugar_limpio, safe=",~-")
	return f"https://wttr.in/{lugar_escapado}?format=j1&lang={idioma}"


def fetch_weather_json(
	lugar: str = DEFAULT_WEATHER_LOCATION,
	idioma: str = "es",
	timeout: float = 5.0,
) -> dict[str, Any] | None:
	"""Obtiene los datos meteorológicos de wttr.in con fallback a caché de 30 minutos."""
	cache_key = (lugar.strip().lower() if lugar else "", idioma.strip().lower() if idioma else "es")
	url = construir_url_json(lugar, idioma)
	try:
		req = urllib.request.Request(url, headers={"User-Agent": "LaRockolaDelCarpincho/1.0"})
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			if resp.status == 200:
				raw_body = resp.read()
				try:
					parsed = json.loads(raw_body.decode("utf-8", errors="ignore"))
				except (json.JSONDecodeError, ValueError) as jde:
					logger.warning(f"Respuesta JSON malformada de wttr.in para '{lugar}': {jde}")
					parsed = None

				if isinstance(parsed, dict) and "current_condition" in parsed:
					_WEATHER_CACHE[cache_key] = (time.time(), parsed)
					return parsed
				elif parsed is not None:
					logger.warning(f"Estructura JSON inesperada o incompleta de wttr.in para '{lugar}'")
			else:
				logger.warning(f"Respuesta HTTP no exitosa de wttr.in ({resp.status}) para '{lugar}'")
	except urllib.error.HTTPError as he:
		if he.code == 429:
			logger.warning(f"Límite de peticiones alcanzado (HTTP 429 Rate Limit) en wttr.in para '{lugar}'")
		elif he.code == 503:
			logger.warning(f"Servicio no disponible (HTTP 503 Service Unavailable) en wttr.in para '{lugar}'")
		else:
			logger.warning(f"Error HTTP {he.code} ({he.reason}) al consultar wttr.in para '{lugar}'")
	except urllib.error.URLError as ue:
		logger.warning(f"Fallo de red o conexión al consultar wttr.in para '{lugar}': {ue.reason}")
	except TimeoutError as te:
		logger.warning(f"Tiempo de espera agotado (timeout) consultando wttr.in para '{lugar}': {te}")
	except Exception as e:
		logger.warning(f"No se pudo consultar el clima en wttr.in para '{lugar}': {e}")

	if cache_key in _WEATHER_CACHE:
		cached_time, cached_data = _WEATHER_CACHE[cache_key]
		if (time.time() - cached_time) <= WEATHER_CACHE_TTL:
			return cached_data

	return None


def describir_lluvias(llueve_hoy: bool, llueve_manana: bool, variant_idx: int | None = None) -> str:
	"""Describe la previsión de lluvias para hoy y mañana con impronta criolla."""
	options = RAIN_DESCRIPTIONS.get((llueve_hoy, llueve_manana))
	if not options:
		return "De lluvias ni hablemos: cielo despejado, ideal para unos buenos mates al sol."
	if variant_idx is not None:
		return options[variant_idx % len(options)]
	return random.choice(options)


def get_all_rain_descriptions() -> list[str]:
	"""Devuelve todas las descripciones de lluvia posibles para precarga."""
	res: list[str] = []
	for descs in RAIN_DESCRIPTIONS.values():
		for d in descs:
			if d not in res:
				res.append(d)
	return res


def _is_slot_relevant_for_hour(h: dict[str, Any], current_hour: int) -> bool:
	"""Determina si una franja horaria de wttr.in cubre desde la hora actual en adelante."""
	time_val = h.get("time")
	if time_val is None:
		return True
	try:
		slot_hour = int(time_val) // 100
		return (slot_hour + 2) >= current_hour
	except (ValueError, TypeError):
		return True


def format_temperature(temp: int) -> str:
	"""Formatea un valor de temperatura cuidando el singular y bajo cero."""
	abs_val = abs(temp)
	noun = "grado" if abs_val == 1 else "grados"
	if temp < 0:
		return f"{abs_val} {noun} bajo cero"
	return f"{temp} {noun}"


def format_temperature_range(min_temp: int, max_temp: int) -> str:
	"""Formatea un rango de temperaturas con concordancia gramatical."""
	if min_temp < 0 and max_temp < 0:
		noun = "grado" if abs(max_temp) == 1 else "grados"
		return f"entre {abs(min_temp)} y {abs(max_temp)} {noun} bajo cero"
	if min_temp < 0 and max_temp >= 0:
		min_noun = "grado" if abs(min_temp) == 1 else "grados"
		max_noun = "grado" if max_temp == 1 else "grados"
		return f"entre {abs(min_temp)} {min_noun} bajo cero y {max_temp} {max_noun}"
	noun = "grado" if max_temp == 1 else "grados"
	return f"entre {min_temp} y {max_temp} {noun}"


def get_weather_condition(
	current_temp: int,
	llueve_hoy: bool = False,
	llueve_manana: bool = False,
) -> str:
	"""Clasifica la condición climática en 'lluvia', 'calor', 'frio' o 'agradable'."""
	if llueve_hoy or llueve_manana:
		return "lluvia"
	if current_temp >= 30:
		return "calor"
	if current_temp <= 10:
		return "frio"
	return "agradable"


def normalize_location_pronunciation(name: str) -> str:
	"""Añade tildes a localidades como Metán y Tucumán para que el TTS las pronuncie bien."""
	if not name:
		return name
	name = re.sub(r"\bMetan\b", "Metán", name, flags=re.IGNORECASE)
	name = re.sub(r"\bTucuman\b", "Tucumán", name, flags=re.IGNORECASE)
	return name


def extract_location_from_weather_data(data: dict[str, Any]) -> str | None:
	"""Extrae el nombre de la localidad resuelta por wttr.in."""
	try:
		areas = data.get("nearest_area")
		if isinstance(areas, list) and areas:
			first_area = areas[0]
			if isinstance(first_area, dict):
				for key in ("areaName", "region", "country"):
					items = first_area.get(key)
					if isinstance(items, list) and items:
						val = items[0].get("value")
						if val and isinstance(val, str) and val.strip():
							raw_loc = val.replace("+", " ").replace("_", " ").strip()
							return normalize_location_pronunciation(raw_loc)
	except Exception as e:
		logger.warning(f"No se pudo extraer la ubicación desde los datos del clima: {e}")
	return None


def extract_current_temp_c(data: dict[str, Any]) -> int | None:
	"""Extrae la temperatura actual redondeada en °C del JSON de wttr.in."""
	try:
		return round(float(data["current_condition"][0]["temp_C"]))
	except (KeyError, IndexError, ValueError, TypeError):
		return None


def get_weather_info(
	data: dict[str, Any],
	lead_in: str | None = None,
	current_hour: int | None = None,
	template_idx: int | None = None,
	location: str | None = None,
	ctx: RadioContext | None = None,
) -> tuple[str, str] | None:
	"""Extrae los datos del JSON de wttr.in y retorna (weather_phrase, weather_condition)."""
	try:
		current_temp = round(float(data["current_condition"][0]["temp_C"]))
		weather_days = data["weather"]
		today = weather_days[0]
		min_today = round(float(today["mintempC"]))
		max_today = round(float(today["maxtempC"]))
		tomorrow = weather_days[1] if len(weather_days) > 1 else today
		min_tomorrow = round(float(tomorrow["mintempC"]))
		max_tomorrow = round(float(tomorrow["maxtempC"]))

		curr = data["current_condition"][0] if data.get("current_condition") else {}
		desc_raw = curr["weatherDesc"][0].get("value") if curr.get("weatherDesc") else None
		lang_es_raw = curr["lang_es"][0].get("value") if curr.get("lang_es") else None
		code_raw = curr.get("weatherCode")

		current_cat = resolve_weather_desc_category(desc=desc_raw, code=code_raw, lang_es=lang_es_raw)

		today_hourly = today.get("hourly", [])
		if current_hour is not None:
			today_hourly = [h for h in today_hourly if _is_slot_relevant_for_hour(h, current_hour)]

		rain_today = max((int(h.get("chanceofrain", 0)) for h in today_hourly), default=0)
		rain_tomorrow = max((int(h.get("chanceofrain", 0)) for h in tomorrow.get("hourly", [])), default=0)

		llueve_hoy = (rain_today >= WEATHER_RAIN_THRESHOLD) or (current_cat in PRECIPITATING_CATEGORIES)
		llueve_manana = rain_tomorrow >= WEATHER_RAIN_THRESHOLD
		lluvia_desc = describir_lluvias(llueve_hoy, llueve_manana, variant_idx=template_idx)

		condition = get_weather_condition(current_temp, llueve_hoy=llueve_hoy, llueve_manana=llueve_manana)
		lead = lead_in if lead_in is not None else random.choice(WEATHER_LEAD_INS)
		temp_str = format_temperature(current_temp)

		if min_today < 0:
			min_noun = "grado" if abs(min_today) == 1 else "grados"
			min_today_str = f"{abs(min_today)} {min_noun} bajo cero"
		elif min_today == 1:
			min_today_str = "1 grado"
		else:
			min_today_str = f"{min_today}"

		if max_today < 0:
			max_noun = "grado" if abs(max_today) == 1 else "grados"
			max_today_str = f"{abs(max_today)} {max_noun} bajo cero"
		elif max_today == 1:
			max_today_str = "1 grado"
		else:
			max_today_str = f"{max_today} grados"

		range_tomorrow_str = format_temperature_range(min_tomorrow, max_tomorrow)

		loc_from_json = extract_location_from_weather_data(data)
		if loc_from_json:
			loc_clean = loc_from_json
		elif location and location.strip():
			clean_candidate = location.replace("+", " ").replace("_", " ").strip()
			if re.match(r"^[-+]?\d+(\.\d+)?\s*,\s*[-+]?\d+(\.\d+)?$", clean_candidate):
				loc_clean = DEFAULT_WEATHER_LOCATION
			else:
				loc_clean = normalize_location_pronunciation(clean_candidate)
		else:
			loc_clean = DEFAULT_WEATHER_LOCATION

		weather_desc_phrase = get_weather_desc_phrase(
			desc=desc_raw,
			code=code_raw,
			lang_es=lang_es_raw,
			variant_idx=template_idx,
			ctx=ctx,
		)
		desc_phrase_str = f" {weather_desc_phrase}" if weather_desc_phrase else ""

		tpl = (
			WEATHER_TEMPLATES[template_idx % len(WEATHER_TEMPLATES)]
			if template_idx is not None
			else random.choice(WEATHER_TEMPLATES)
		)

		phrase = tpl.format(
			lead=lead,
			location=loc_clean,
			temp_str=temp_str,
			desc_phrase=desc_phrase_str,
			min_today_str=min_today_str,
			max_today_str=max_today_str,
			range_tomorrow_str=range_tomorrow_str,
			lluvia_desc=lluvia_desc,
		)
		return phrase, condition
	except (KeyError, IndexError, ValueError, TypeError) as e:
		logger.debug(f"Estructura de datos de clima incompleta o inválida: {e}")
		return None


def build_weather_phrase(
	data: dict[str, Any],
	lead_in: str | None = None,
	current_hour: int | None = None,
	template_idx: int | None = None,
	location: str | None = None,
	ctx: RadioContext | None = None,
) -> str | None:
	"""Arma la frase completa del reporte del clima a partir del JSON de wttr.in."""
	info = get_weather_info(
		data,
		lead_in=lead_in,
		current_hour=current_hour,
		template_idx=template_idx,
		location=location,
		ctx=ctx,
	)
	return info[0] if info else None
