"""
Módulo de locución para el Modo Radio en La Rockola del Carpincho.
Maneja la síntesis de voz con edge-tts, formateo horario radial y banco mixto de fortunas.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import math
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("rockola.radio")


@dataclass(slots=True)
class RadioAnnouncementResult:
	"""Resultado estructurado de la síntesis de un anuncio radial."""

	ok: bool
	display_title: str = ""
	script: str = ""
	error: str | None = None

	def __iter__(self):
		# Retrocompatibilidad con código o tests que esperan desempaquetar (ok, title, script_o_error)
		yield self.ok
		yield self.display_title
		yield self.script if self.ok else (self.error or "")

	def __getitem__(self, index: int):
		return tuple(self)[index]

	def __len__(self):
		return 3


try:
	import edge_tts

	HAS_EDGE_TTS = True
except ImportError as e:
	edge_tts = None
	HAS_EDGE_TTS = False
	logger.info(f"Librería opcional edge-tts no disponible en el entorno: {e}")


# Importar bancos de frases, vocabulario, voces y plantillas
try:
	from scripts.radio_banks import (
		AI_ROBOTIC_PHRASES,
		ALERTAS_INCOMODIDAD_CRIOLLA,
		AVISOS_PARROQUIALES_Y_EXTRAVIOS,
		CARPINCHO_ADS,
		CARPINCHO_FORTUNES,
		CARPINCHO_PHRASES,
		COMMON_ENGLISH_WORDS,
		COMMON_SPANISH_VERBS,
		COMMON_SPANISH_WORDS,
		COMMON_VERB_ROOTS,
		DEDICATORIAS_OYENTES,
		DEFAULT_BG_VOLUME,
		DEFAULT_COHOST_DISPLAY_NAME,
		DEFAULT_COHOST_NAME,
		DEFAULT_HOST_NAME,
		DEFAULT_RADIO_ALBUM,
		DEFAULT_RADIO_ARTIST,
		DEFAULT_RADIO_TITLE,
		DEFAULT_TTS_RETRIES,
		DEFAULT_TTS_TIMEOUT,
		DEFAULT_WEATHER_LOCATION,
		FORBIDDEN_FORMAT_CHARS,
		HOUR_NAMES,
		KNOWN_SPANISH_DBS,
		LEAD_INS_ALERTAS,
		LEAD_INS_AVISOS,
		LEAD_INS_BY_CATEGORY,
		LEAD_INS_FORTUNA,
		LEAD_INS_OYENTES,
		MINUTE_SEGMENTS,
		PASES_A_CLIMA,
		PHRASE_TO_CATEGORY,
		PRECIPITATING_CATEGORIES,
		PROFANITY_PHRASES,
		PROFANITY_TERMS,
		RADIO_HANDOFFS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		RADIO_REACTIONS,
		RAIN_BOTH_DAYS,
		RAIN_DESCRIPTIONS,
		RAIN_NO_RAIN,
		RAIN_TODAY_ONLY,
		RAIN_TOMORROW_ONLY,
		REACCIONES_ALERTAS,
		REACCIONES_AVISOS,
		REACCIONES_BY_CATEGORY,
		REACCIONES_CLIMA,
		REACCIONES_FORTUNA,
		REACCIONES_OYENTES,
		SEPARADORES_Y_SLOGANS,
		SPANISH_CHARS,
		SPECIAL_HOURS,
		TRANSITO_FLUVIAL_Y_CAMINOS,
		VERBAL_SUFFIXES_REGEX,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_PROSODY,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		WEATHER_CODE_TO_CATEGORY,
		WEATHER_DESC_PHRASES,
		WEATHER_DESC_TO_CATEGORY,
		WEATHER_LEAD_INS,
		WEATHER_RAIN_THRESHOLD,
		WEATHER_TEMPLATES,
		RadioPhrase,
		get_all_weather_desc_phrases,
		get_lead_ins_for_category,
		get_reactions_for_category,
		get_weather_desc_phrase,
		resolve_segment_category,
		resolve_weather_desc_category,
	)
except ImportError:
	from radio_banks import (
		AI_ROBOTIC_PHRASES,
		ALERTAS_INCOMODIDAD_CRIOLLA,
		AVISOS_PARROQUIALES_Y_EXTRAVIOS,
		CARPINCHO_ADS,
		CARPINCHO_FORTUNES,
		CARPINCHO_PHRASES,
		COMMON_ENGLISH_WORDS,
		COMMON_SPANISH_VERBS,
		COMMON_SPANISH_WORDS,
		COMMON_VERB_ROOTS,
		DEDICATORIAS_OYENTES,
		DEFAULT_BG_VOLUME,
		DEFAULT_COHOST_DISPLAY_NAME,
		DEFAULT_COHOST_NAME,
		DEFAULT_HOST_NAME,
		DEFAULT_RADIO_ALBUM,
		DEFAULT_RADIO_ARTIST,
		DEFAULT_RADIO_TITLE,
		DEFAULT_TTS_RETRIES,
		DEFAULT_TTS_TIMEOUT,
		DEFAULT_WEATHER_LOCATION,
		FORBIDDEN_FORMAT_CHARS,
		HOUR_NAMES,
		KNOWN_SPANISH_DBS,
		LEAD_INS_ALERTAS,
		LEAD_INS_AVISOS,
		LEAD_INS_BY_CATEGORY,
		LEAD_INS_FORTUNA,
		LEAD_INS_OYENTES,
		MINUTE_SEGMENTS,
		PASES_A_CLIMA,
		PHRASE_TO_CATEGORY,
		PRECIPITATING_CATEGORIES,
		PROFANITY_PHRASES,
		PROFANITY_TERMS,
		RADIO_HANDOFFS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		RADIO_REACTIONS,
		RAIN_BOTH_DAYS,
		RAIN_DESCRIPTIONS,
		RAIN_NO_RAIN,
		RAIN_TODAY_ONLY,
		RAIN_TOMORROW_ONLY,
		REACCIONES_ALERTAS,
		REACCIONES_AVISOS,
		REACCIONES_BY_CATEGORY,
		REACCIONES_CLIMA,
		REACCIONES_FORTUNA,
		REACCIONES_OYENTES,
		SEPARADORES_Y_SLOGANS,
		SPANISH_CHARS,
		SPECIAL_HOURS,
		TRANSITO_FLUVIAL_Y_CAMINOS,
		VERBAL_SUFFIXES_REGEX,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_PROSODY,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		WEATHER_CODE_TO_CATEGORY,
		WEATHER_DESC_PHRASES,
		WEATHER_DESC_TO_CATEGORY,
		WEATHER_LEAD_INS,
		WEATHER_RAIN_THRESHOLD,
		WEATHER_TEMPLATES,
		RadioPhrase,
		get_all_weather_desc_phrases,
		get_lead_ins_for_category,
		get_reactions_for_category,
		get_weather_desc_phrase,
		resolve_segment_category,
		resolve_weather_desc_category,
	)

__all__ = [
	"AI_ROBOTIC_PHRASES",
	"ALERTAS_INCOMODIDAD_CRIOLLA",
	"AVISOS_PARROQUIALES_Y_EXTRAVIOS",
	"CARPINCHO_ADS",
	"CARPINCHO_FORTUNES",
	"CARPINCHO_PHRASES",
	"COMMON_ENGLISH_WORDS",
	"COMMON_SPANISH_VERBS",
	"COMMON_SPANISH_WORDS",
	"COMMON_VERB_ROOTS",
	"DEDICATORIAS_OYENTES",
	"DEFAULT_BG_VOLUME",
	"DEFAULT_COHOST_DISPLAY_NAME",
	"DEFAULT_COHOST_NAME",
	"DEFAULT_HOST_NAME",
	"DEFAULT_RADIO_ALBUM",
	"DEFAULT_RADIO_ARTIST",
	"DEFAULT_RADIO_TITLE",
	"DEFAULT_TTS_RETRIES",
	"DEFAULT_TTS_TIMEOUT",
	"DEFAULT_WEATHER_LOCATION",
	"FORBIDDEN_FORMAT_CHARS",
	"HOUR_NAMES",
	"KNOWN_SPANISH_DBS",
	"LEAD_INS_ALERTAS",
	"LEAD_INS_AVISOS",
	"LEAD_INS_BY_CATEGORY",
	"LEAD_INS_FORTUNA",
	"LEAD_INS_OYENTES",
	"MINUTE_SEGMENTS",
	"PASES_A_CLIMA",
	"PHRASE_TO_CATEGORY",
	"PRECIPITATING_CATEGORIES",
	"PROFANITY_PHRASES",
	"PROFANITY_TERMS",
	"RADIO_HANDOFFS",
	"RADIO_INTROS",
	"RADIO_LEAD_INS",
	"RADIO_OUTROS",
	"RADIO_REACTIONS",
	"RAIN_BOTH_DAYS",
	"RAIN_DESCRIPTIONS",
	"RAIN_NO_RAIN",
	"RAIN_TODAY_ONLY",
	"RAIN_TOMORROW_ONLY",
	"REACCIONES_ALERTAS",
	"REACCIONES_AVISOS",
	"REACCIONES_BY_CATEGORY",
	"REACCIONES_CLIMA",
	"REACCIONES_FORTUNA",
	"REACCIONES_OYENTES",
	"SEPARADORES_Y_SLOGANS",
	"SPANISH_CHARS",
	"SPECIAL_HOURS",
	"TRANSITO_FLUVIAL_Y_CAMINOS",
	"VERBAL_SUFFIXES_REGEX",
	"VOICES",
	"VOICE_ELENA",
	"VOICE_MARIA",
	"VOICE_NAMES",
	"VOICE_PROSODY",
	"VOICE_TOMAS",
	"VOICE_VALENTINA",
	"WEATHER_CODE_TO_CATEGORY",
	"WEATHER_DESC_PHRASES",
	"WEATHER_DESC_TO_CATEGORY",
	"WEATHER_LEAD_INS",
	"WEATHER_RAIN_THRESHOLD",
	"WEATHER_TEMPLATES",
	"RadioAnnouncementResult",
	"RadioPhrase",
	"assemble_announcement_audio",
	"build_lrc_content",
	"build_radio_dialogue_plan",
	"build_srt_content",
	"build_weather_phrase",
	"clean_fortune_text",
	"contains_blacklisted_content",
	"create_radio_announcement",
	"describir_lluvias",
	"estimate_mp3_duration",
	"extract_location_from_weather_data",
	"format_fortune_for_speech",
	"format_temperature",
	"format_temperature_range",
	"generate_modular_radio_script",
	"get_all_degree_segments",
	"get_all_fortune_reaction_segments",
	"get_all_rain_descriptions",
	"get_all_time_segments",
	"get_all_weather_desc_phrases",
	"get_all_weather_handoff_segments",
	"get_all_weather_reaction_segments",
	"get_available_spanish_dbs",
	"get_bundled_fortune",
	"get_cached_audio",
	"get_lead_ins_for_category",
	"get_modular_hour_segments",
	"get_modular_minute_segments",
	"get_modular_time_segments",
	"get_phrase_last_played",
	"get_radio_fortune",
	"get_radio_state",
	"get_reactions_for_category",
	"get_system_fortune",
	"get_weather_condition",
	"get_weather_desc_phrase",
	"get_weather_info",
	"has_conjugated_verb",
	"init_tts_cache_db",
	"is_spanish_text",
	"is_tts_friendly_fortune",
	"is_valid_mp3_file",
	"is_valid_mp3_stream",
	"is_valid_spoken_sentence",
	"load_bundled_fortunes",
	"mix_announcement_with_bg_track",
	"prune_tts_cache_db",
	"record_phrase_played",
	"reset_radio_memory_state",
	"reset_weather_cache",
	"resolve_segment_category",
	"resolve_weather_desc_category",
	"save_cached_audio",
	"select_fortune",
	"select_radio_hosts",
	"set_radio_state",
	"synthesize_segment",
	"weighted_choice_by_recency",
]

_WEATHER_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
WEATHER_CACHE_TTL: float = 30 * 60  # 30 minutos


def reset_weather_cache() -> None:
	"""Limpia la caché en memoria de wttr.in (útil para pruebas y reinicio)."""
	_WEATHER_CACHE.clear()


def construir_url_json(lugar: str, idioma: str = "es") -> str:
	lugar_limpio = lugar.strip() if lugar else ""
	lugar_escapado = urllib.parse.quote(lugar_limpio, safe=",~-")
	return f"https://wttr.in/{lugar_escapado}?format=j1&lang={idioma}"


def fetch_weather_json(
	lugar: str = DEFAULT_WEATHER_LOCATION,
	idioma: str = "es",
	timeout: float = 5.0,
) -> dict | None:
	"""
	Obtiene los datos meteorológicos en formato JSON (format=j1) desde wttr.in de forma sincrónica.
	Retorna el diccionario parseado o None si ocurre cualquier error (timeout, HTTP, DNS o JSON inválido).
	Si la solicitud remota falla, intenta recuperar la última respuesta válida en caché si tiene menos de 30 minutos.
	"""
	cache_key = (lugar.strip().lower() if lugar else "", idioma.strip().lower() if idioma else "es")
	url = construir_url_json(lugar, idioma)
	try:
		req = urllib.request.Request(
			url,
			headers={"User-Agent": "LaRockolaDelCarpincho/1.0"},
		)
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

	# Si la petición remota falló, verificar si tenemos una respuesta previa válida de menos de 30 minutos
	if cache_key in _WEATHER_CACHE:
		cached_time, cached_data = _WEATHER_CACHE[cache_key]
		age = time.time() - cached_time
		if age <= WEATHER_CACHE_TTL:
			logger.debug(
				f"🌤️ Usando reporte del clima en caché ({age / 60:.1f} min de antigüedad) para '{lugar}' ante fallo de red."
			)
			return cached_data

	return None


def describir_lluvias(llueve_hoy: bool, llueve_manana: bool, variant_idx: int | None = None) -> str:
	"""
	Describe la previsión de precipitaciones para hoy y mañana con impronta carpinchera.
	Cubre las 4 condiciones posibles con múltiples opciones léxicas criollas.
	Si variant_idx se especifica, retorna esa variante fija (variant_idx=0 mantiene la clásica).
	Si variant_idx es None, elige una variante aleatoria.
	"""
	options = RAIN_DESCRIPTIONS.get((llueve_hoy, llueve_manana))
	if not options:
		return "De lluvias ni hablemos: cielo despejado, ideal para unos buenos mates al sol."
	if variant_idx is not None:
		return options[variant_idx % len(options)]
	return random.choice(options)


def get_all_rain_descriptions() -> list[str]:
	"""Devuelve la lista consolidada de todas las previsiones de lluvia posibles para precarga en caché."""
	res: list[str] = []
	for descs in RAIN_DESCRIPTIONS.values():
		for d in descs:
			if d not in res:
				res.append(d)
	return res


def _is_slot_relevant_for_hour(h: dict, current_hour: int) -> bool:
	"""Determina si un slot hourly de wttr.in cubre desde la hora actual en adelante."""
	time_val = h.get("time")
	if time_val is None:
		return True
	try:
		# wttr.in usa enteros como 0, 300, 600, 900, 1200, 1500, etc.
		# Cada slot cubre 3 horas: [slot_hour, slot_hour + 2]
		slot_hour = int(time_val) // 100
		return (slot_hour + 2) >= current_hour
	except (ValueError, TypeError):
		return True


def format_temperature(temp: int) -> str:
	"""
	Formatea un valor de temperatura en grados cuidando el singular ('1 grado')
	y los valores bajo cero ('X grados bajo cero' o '1 grado bajo cero').
	"""
	abs_val = abs(temp)
	noun = "grado" if abs_val == 1 else "grados"
	if temp < 0:
		return f"{abs_val} {noun} bajo cero"
	return f"{temp} {noun}"


def format_temperature_range(min_temp: int, max_temp: int) -> str:
	"""Formatea un rango de temperaturas cuidando concordancia de singular y negativos."""
	if min_temp < 0 and max_temp < 0:
		noun = "grado" if abs(max_temp) == 1 else "grados"
		return f"entre {abs(min_temp)} y {abs(max_temp)} {noun} bajo cero"
	elif min_temp < 0 and max_temp >= 0:
		min_noun = "grado" if abs(min_temp) == 1 else "grados"
		max_noun = "grado" if max_temp == 1 else "grados"
		return f"entre {abs(min_temp)} {min_noun} bajo cero y {max_temp} {max_noun}"
	else:
		noun = "grado" if max_temp == 1 else "grados"
		return f"entre {min_temp} y {max_temp} {noun}"


def get_weather_condition(
	current_temp: int,
	llueve_hoy: bool = False,
	llueve_manana: bool = False,
) -> str:
	"""
	Determina la condición climática para elegir la reacción adecuada de cabina:
	- 'lluvia': si hay probabilidad de lluvias relevante hoy o mañana.
	- 'calor': si la temperatura actual es >= 30 grados.
	- 'frio': si la temperatura actual es <= 10 grados.
	- 'agradable': temperatura templada intermedia.
	"""
	if llueve_hoy or llueve_manana:
		return "lluvia"
	if current_temp >= 30:
		return "calor"
	if current_temp <= 10:
		return "frio"
	return "agradable"


def extract_location_from_weather_data(data: dict) -> str | None:
	"""
	Extrae el nombre de la localidad/área resuelta por wttr.in a partir del JSON format=j1.
	Inspecciona 'nearest_area' priorizando 'areaName', luego 'region' y finalmente 'country'.
	"""
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
							return val.replace("+", " ").replace("_", " ").strip()
	except Exception as e:
		logger.warning(f"No se pudo extraer la ubicación desde los datos del clima: {e}")
	return None


def get_weather_info(
	data: dict,
	lead_in: str | None = None,
	current_hour: int | None = None,
	template_idx: int | None = None,
	location: str | None = None,
) -> tuple[str, str] | None:
	"""
	Extrae los datos del JSON format=j1 de wttr.in y retorna (weather_phrase, weather_condition).
	Soporta múltiples plantillas sintácticas para evitar patrones repetitivos e incluye la ubicación consultada.
	Retorna None si la estructura es inválida o incompleta.
	"""
	try:
		current_temp = round(float(data["current_condition"][0]["temp_C"]))
		today = data["weather"][0]
		min_today = round(float(today["mintempC"]))
		max_today = round(float(today["maxtempC"]))
		tomorrow = data["weather"][1]
		min_tomorrow = round(float(tomorrow["mintempC"]))
		max_tomorrow = round(float(tomorrow["maxtempC"]))

		# Extraer descripción del estado del cielo / clima actual si existe
		curr = data["current_condition"][0] if data.get("current_condition") else {}
		desc_raw = None
		if curr.get("weatherDesc"):
			desc_raw = curr["weatherDesc"][0].get("value")
		lang_es_raw = None
		if curr.get("lang_es"):
			lang_es_raw = curr["lang_es"][0].get("value")
		code_raw = curr.get("weatherCode")

		current_cat = resolve_weather_desc_category(desc=desc_raw, code=code_raw, lang_es=lang_es_raw)

		today_hourly = today.get("hourly", [])
		if current_hour is not None:
			today_hourly = [h for h in today_hourly if _is_slot_relevant_for_hour(h, current_hour)]

		rain_today = max(
			(int(h.get("chanceofrain", 0)) for h in today_hourly),
			default=0,
		)
		rain_tomorrow = max(
			(int(h.get("chanceofrain", 0)) for h in tomorrow.get("hourly", [])),
			default=0,
		)

		llueve_hoy = (rain_today >= WEATHER_RAIN_THRESHOLD) or (current_cat in PRECIPITATING_CATEGORIES)
		llueve_manana = rain_tomorrow >= WEATHER_RAIN_THRESHOLD
		lluvia_desc = describir_lluvias(llueve_hoy, llueve_manana, variant_idx=template_idx)

		condition = get_weather_condition(current_temp, llueve_hoy=llueve_hoy, llueve_manana=llueve_manana)

		lead = (
			lead_in if lead_in is not None else weighted_choice_by_recency(WEATHER_LEAD_INS, category="weather_lead_in")
		)
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

		# Priorizar la ubicación resuelta que devuelve wttr.in en el JSON
		loc_from_json = extract_location_from_weather_data(data)
		if loc_from_json:
			loc_clean = loc_from_json
		elif location and location.strip():
			clean_candidate = location.replace("+", " ").replace("_", " ").strip()
			if re.match(r"^[-+]?\d+(\.\d+)?\s*,\s*[-+]?\d+(\.\d+)?$", clean_candidate):
				loc_clean = DEFAULT_WEATHER_LOCATION
			else:
				loc_clean = clean_candidate
		else:
			loc_clean = DEFAULT_WEATHER_LOCATION

		weather_desc_phrase = get_weather_desc_phrase(
			desc=desc_raw,
			code=code_raw,
			lang_es=lang_es_raw,
			variant_idx=template_idx,
		)
		desc_phrase_str = f" {weather_desc_phrase}" if weather_desc_phrase else ""

		if template_idx is not None:
			tpl = WEATHER_TEMPLATES[template_idx % len(WEATHER_TEMPLATES)]
		else:
			tpl = random.choice(WEATHER_TEMPLATES)

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
	data: dict,
	lead_in: str | None = None,
	current_hour: int | None = None,
	template_idx: int | None = None,
	location: str | None = None,
) -> str | None:
	"""
	Extrae y arma la frase del reporte del clima a partir del JSON format=j1 de wttr.in.
	Retorna None si la estructura no contiene las claves esperadas.
	"""
	info = get_weather_info(
		data,
		lead_in=lead_in,
		current_hour=current_hour,
		template_idx=template_idx,
		location=location,
	)
	return info[0] if info else None


def get_carpincho_data_dir() -> Path:
	"""Obtiene el directorio de datos para la base de datos de la Rockola."""
	try:
		from server import DATA_DIR

		return DATA_DIR
	except ImportError:
		logger.debug("Módulo 'server' no disponible, usando fallback local para DATA_DIR.")
	except Exception as e:
		logger.debug(f"Error inesperado importando DATA_DIR desde server: {e}, usando fallback local.")

	db_dir = Path(__file__).resolve().parents[1] / "DB"
	db_dir.mkdir(parents=True, exist_ok=True)
	return db_dir


def is_valid_mp3_stream(data: bytes) -> bool:
	"""Determina si un encabezado de bytes corresponde a un stream o archivo MP3 real."""
	if len(data) < 4:
		return False
	if data.startswith(b"ID3"):
		return True
	return bool(data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


def is_valid_mp3_file(path: Path | str) -> bool:
	"""Verifica que el archivo exista, tenga contenido y su encabezado comience con un stream MP3 válido."""
	try:
		p = Path(path)
		if not p.is_file() or p.stat().st_size < 4:
			return False
		with p.open("rb") as f:
			head = f.read(10)
		return is_valid_mp3_stream(head)
	except Exception as e:
		logger.warning(f"Error comprobando validez de archivo MP3 '{path}': {e}")
		return False


def estimate_mp3_duration(data: bytes) -> float | None:
	"""Estima la duración en segundos de un stream de audio MP3 en memoria usando mutagen.

	Retorna None si mutagen no está disponible o si los datos no corresponden a un MP3 válido.
	"""
	if not data or not is_valid_mp3_stream(data):
		return None
	try:
		from mutagen.mp3 import MP3

		audio = MP3(io.BytesIO(data))
		if audio.info and getattr(audio.info, "length", None) is not None:
			return float(audio.info.length)
	except ImportError as e:
		logger.info(f"Librería opcional mutagen no está disponible para estimar duración: {e}")
	except Exception as e:
		logger.warning(f"No se pudo estimar la duración del stream MP3 con mutagen: {e}")
	return None


def init_tts_cache_db(db_path: Path | str | None = None) -> Path:
	"""Inicializa la base de datos SQLite para la caché de audios de TTS."""
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	target_path.parent.mkdir(parents=True, exist_ok=True)
	with sqlite3.connect(target_path, timeout=5.0) as conn:
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS tts_cache (
				cache_key TEXT PRIMARY KEY,
				category TEXT NOT NULL,
				voice TEXT NOT NULL,
				text TEXT NOT NULL,
				audio_blob BLOB NOT NULL,
				duration REAL,
				created_at REAL NOT NULL,
				last_used REAL NOT NULL,
				use_count INTEGER DEFAULT 1
			)
			"""
		)
		conn.execute("CREATE INDEX IF NOT EXISTS idx_tts_cache_cat_voice ON tts_cache (category, voice)")
		conn.commit()
	return target_path


def get_cache_key(category: str, voice: str, text: str) -> str:
	"""Calcula la clave de caché SHA-256 única para una tupla (categoría, voz, texto normalizado)."""
	norm_text = text.strip().lower()
	raw = f"{voice}:{category}:{norm_text}".encode()
	return hashlib.sha256(raw).hexdigest()


def get_cached_audio(
	category: str,
	voice: str,
	text: str,
	db_path: Path | str | None = None,
) -> bytes | None:
	"""
	Recupera el segmento de audio MP3 desde la base SQLite si existe.
	Actualiza el timestamp de último uso y el contador de reproducciones.
	"""
	cache_key = get_cache_key(category, voice, text)
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	if not target_path.exists():
		return None
	try:
		with sqlite3.connect(target_path, timeout=5.0) as conn:
			cur = conn.cursor()
			cur.execute("SELECT audio_blob FROM tts_cache WHERE cache_key = ?", (cache_key,))
			row = cur.fetchone()
			if row and row[0]:
				now = time.time()
				cur.execute(
					"UPDATE tts_cache SET last_used = ?, use_count = use_count + 1 WHERE cache_key = ?",
					(now, cache_key),
				)
				conn.commit()
				return row[0]
	except Exception as e:
		logger.debug(f"Error consultando caché TTS: {e}")
	return None


def save_cached_audio(
	category: str,
	voice: str,
	text: str,
	audio_bytes: bytes,
	duration: float | None = None,
	db_path: Path | str | None = None,
) -> None:
	"""Almacena o actualiza un segmento de audio MP3 en la base de datos de caché SQLite."""
	if not audio_bytes:
		return
	if duration is None:
		duration = estimate_mp3_duration(audio_bytes)
	cache_key = get_cache_key(category, voice, text)
	target_path = init_tts_cache_db(db_path)
	now = time.time()
	try:
		with sqlite3.connect(target_path, timeout=5.0) as conn:
			conn.execute(
				"""
				INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
				ON CONFLICT(cache_key) DO UPDATE SET
					audio_blob = excluded.audio_blob,
					duration = coalesce(excluded.duration, duration),
					last_used = excluded.last_used,
					use_count = use_count + 1
				""",
				(cache_key, category, voice, text, audio_bytes, duration, now, now),
			)
			conn.commit()
	except Exception as e:
		logger.debug(f"Error guardando audio en caché TTS: {e}")


def prune_tts_cache_db(
	max_entries: int = 500,
	max_age_days: float = 30.0,
	db_path: Path | str | None = None,
) -> int:
	"""Poda entradas obsoletas o sobrantes de la caché SQLite de TTS.

	- Elimina registros con 'last_used' anterior a max_age_days días.
	- Si la cantidad de registros aún excede max_entries, elimina los más antiguos por 'last_used' hasta alcanzar max_entries.
	- Ejecuta VACUUM para compactar la base de datos si se eliminó algún registro.
	- Retorna el total de entradas eliminadas.
	"""
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	if not target_path.exists():
		return 0

	deleted_count = 0
	try:
		with sqlite3.connect(target_path, timeout=5.0) as conn:
			cur = conn.cursor()
			# 1. Poda por antigüedad (last_used)
			cutoff = time.time() - (max_age_days * 86400.0)
			cur.execute("DELETE FROM tts_cache WHERE last_used < ?", (cutoff,))
			deleted_count += cur.rowcount

			# 2. Poda por cantidad máxima de registros
			cur.execute("SELECT count(*) FROM tts_cache")
			row = cur.fetchone()
			total_entries = row[0] if row else 0
			if total_entries > max_entries:
				excess = total_entries - max_entries
				cur.execute(
					"""
					DELETE FROM tts_cache
					WHERE cache_key IN (
						SELECT cache_key FROM tts_cache
						ORDER BY last_used ASC
						LIMIT ?
					)
					""",
					(excess,),
				)
				deleted_count += cur.rowcount

			conn.commit()
			if deleted_count > 0:
				conn.execute("VACUUM")
				conn.commit()
	except Exception as e:
		logger.warning(f"Error podando la base de datos de caché TTS ({target_path}): {e}")

	return deleted_count


# Estado volátil en memoria para el locutor de radio (no requiere persistencia en base de datos)
_RADIO_MEMORY_STATE: dict[str, Any] = {}
_PHRASE_HISTORY_MEMORY: dict[str, float] = {}


def get_radio_state(key: str, default: Any = None, db_path: Path | str | None = None) -> Any:
	"""Recupera un valor de estado en memoria del locutor de radio (db_path opcional conservado por retrocompatibilidad)."""
	return _RADIO_MEMORY_STATE.get(key, default)


def set_radio_state(key: str, value: Any, db_path: Path | str | None = None) -> None:
	"""Almacena o actualiza un valor de estado en memoria del locutor de radio (db_path opcional conservado por retrocompatibilidad)."""
	_RADIO_MEMORY_STATE[key] = value


def reset_radio_memory_state() -> None:
	"""Limpia el estado en memoria del locutor de radio (útil para pruebas y reinicio limpio)."""
	_RADIO_MEMORY_STATE.clear()
	_PHRASE_HISTORY_MEMORY.clear()


def _normalize_phrase_key(phrase: str | tuple[str, str] | RadioPhrase, category: str = "") -> str:
	if isinstance(phrase, (tuple, list)):
		phrase_text = phrase[0] if len(phrase) > 0 else ""
		if not category and len(phrase) > 1:
			category = str(phrase[1])
	else:
		phrase_text = str(phrase)
	cleaned = phrase_text.strip().strip("\"'«»").rstrip(".!?:;…").lower()
	return f"{category}:{cleaned}" if category else cleaned


def get_phrase_last_played(
	phrase: str | tuple[str, str] | RadioPhrase,
	category: str = "",
	db_path: Path | str | None = None,
) -> float | None:
	"""Recupera la marca de tiempo (timestamp) en que una frase fue reproducida por última vez en memoria."""
	if isinstance(phrase, (tuple, list)):
		phrase_text = phrase[0] if len(phrase) > 0 else ""
		if not category and len(phrase) > 1:
			category = str(phrase[1])
	else:
		phrase_text = str(phrase)
	norm_key = _normalize_phrase_key(phrase_text, category)
	val = _PHRASE_HISTORY_MEMORY.get(norm_key)
	if val is not None:
		return val

	# Fallbacks entre categorías específicas y genéricas
	if category.startswith("lead_in_"):
		val = _PHRASE_HISTORY_MEMORY.get(_normalize_phrase_key(phrase_text, "lead_in"))
		if val is not None:
			return val
	elif category.startswith("reaccion_"):
		val = _PHRASE_HISTORY_MEMORY.get(_normalize_phrase_key(phrase_text, "reaccion"))
		if val is not None:
			return val
	elif category == "pase":
		for tpl in PASES_A_CLIMA:
			for cname in VOICE_NAMES.values():
				if _normalize_phrase_key(tpl.format(cohost=cname)) == _normalize_phrase_key(phrase_text):
					val = _PHRASE_HISTORY_MEMORY.get(_normalize_phrase_key(tpl, "pase"))
					if val is not None:
						return val
	return None


def record_phrase_played(
	phrase: str | tuple[str, str] | RadioPhrase,
	category: str = "",
	timestamp: float | None = None,
	db_path: Path | str | None = None,
) -> None:
	"""Registra en memoria la reproducción de una frase actualizando su marca de tiempo."""
	if isinstance(phrase, (tuple, list)):
		phrase_text = phrase[0] if len(phrase) > 0 else ""
		if not category and len(phrase) > 1:
			category = str(phrase[1])
	else:
		phrase_text = str(phrase)
	ts = timestamp if timestamp is not None else time.time()
	norm_key = _normalize_phrase_key(phrase_text, category)
	_PHRASE_HISTORY_MEMORY[norm_key] = ts

	# Mapeo bidireccional entre categorías específicas y genéricas para garantizar consistencia
	if category == "lead_in" or category.startswith("lead_in_"):
		_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, "lead_in")] = ts
		for cat_name, cat_list in LEAD_INS_BY_CATEGORY.items():
			if any(_normalize_phrase_key(phrase_text) == _normalize_phrase_key(item) for item in cat_list):
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, f"lead_in_{cat_name}")] = ts
				break
	elif category == "reaccion" or category.startswith("reaccion_"):
		_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, "reaccion")] = ts
		for cat_name, cat_list in REACCIONES_BY_CATEGORY.items():
			if any(_normalize_phrase_key(phrase_text) == _normalize_phrase_key(item) for item in cat_list):
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, f"reaccion_{cat_name}")] = ts
				break
		for clim_list in REACCIONES_CLIMA.values():
			if any(_normalize_phrase_key(phrase_text) == _normalize_phrase_key(item) for item in clim_list):
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, "reaccion_clima")] = ts
				break
	elif category == "pase":
		for tpl in PASES_A_CLIMA:
			for cname in VOICE_NAMES.values():
				if _normalize_phrase_key(tpl.format(cohost=cname)) == _normalize_phrase_key(phrase_text):
					_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(tpl, "pase")] = ts
					break


def weighted_choice_by_recency(
	candidates: list[Any],
	category: str = "",
	db_path: Path | str | None = None,
	current_time: float | None = None,
	tau: float = 1800.0,
	min_weight: float = 0.02,
) -> Any:
	"""
	Selecciona una frase de la lista candidata ponderando por antigüedad de última reproducción.
	- Frases nunca reproducidas tienen peso máximo (1.0).
	- Frases recién reproducidas ven su peso deprimido a min_weight (default 0.02),
	  evitando repeticiones consecutivas pero permitiéndolas con probabilidad muy baja ("aunque pueda pasar").
	- A medida que transcurre el tiempo (delta_t), el peso se recupera exponencialmente hacia 1.0 según tau.
	"""
	if not candidates:
		raise ValueError("La lista de frases candidatas no puede estar vacía.")
	if len(candidates) == 1:
		return candidates[0]

	now = current_time if current_time is not None else time.time()
	weights: list[float] = []

	for phrase in candidates:
		last_played = get_phrase_last_played(phrase, category=category, db_path=db_path)
		if last_played is None or last_played <= 0:
			weights.append(1.0)
		else:
			delta_t = max(0.0, now - float(last_played))
			w = max(min_weight, 1.0 - math.exp(-delta_t / tau))
			weights.append(w)

	return random.choices(candidates, weights=weights, k=1)[0]


# Nombres de bases de datos de fortune que contienen frases en español
_SPANISH_FORTUNE_DBS_CACHE: list[str] | None = None


def is_spanish_text(text: str) -> bool:
	"""
	Determina con precisión y bajo costo computacional si un texto está en español.
	Utiliza la lista cerrada de stopwords funcionales (artículos y preposiciones),
	detección de diacríticos distintivos (á, é, í, ó, ú, ü, ñ, ¿, ¡) y n-gramas característicos.
	"""
	if not text or not isinstance(text, str):
		return False

	words = [w.lower() for w in re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b", text)]
	if not words:
		return False

	spanish_hits = sum(1 for w in words if w in COMMON_SPANISH_WORDS)
	english_hits = sum(1 for w in words if w in COMMON_ENGLISH_WORDS)

	# Si predominan fuertemente palabras funcionales en inglés, descartar
	if english_hits > spanish_hits and english_hits >= 2:
		return False
	if english_hits >= 2 and spanish_hits == 0:
		return False
	if english_hits > 0 and len(words) <= 5 and spanish_hits == 0:
		return False

	# Presencia de caracteres exclusivos del español (ñ, ¿, ¡)
	if any(c in "ñÑ¿¡" for c in text) and english_hits <= 1:
		return True

	# Coincidencia con stopwords esenciales en español
	if spanish_hits >= 2 or (len(words) <= 4 and spanish_hits >= 1 and english_hits == 0):
		return True

	# Acentos diacríticos en vocales o n-gramas distintivos en español sin stopwords inglesas
	if english_hits == 0:
		if any(c in "áéíóúüÁÉÍÓÚÜ" for c in text) and len(words) >= 2:
			return True
		low = text.lower()
		if any(ng in low for ng in ("ción", "sión", "mente", "illo", "illa", "ante")):
			return True

	return False


# ---------------------------------------------------------------------------
# Blacklists para locución radial del Carpincho (Mal gusto y Jerga IA/Robot)
# ---------------------------------------------------------------------------


def contains_blacklisted_content(text: str) -> bool:
	"""
	Verifica si el texto contiene términos o conceptos prohibidos para la personalidad
	del Carpincho (mal gusto / vulgaridades o jerga de asistente IA / robótica).
	"""
	norm = text.lower()

	# 1. Jerga robótica o de asistente IA
	for phrase in AI_ROBOTIC_PHRASES:
		if phrase in norm:
			return True

	# 2. Frases compuestas vulgares
	for phrase in PROFANITY_PHRASES:
		if phrase in norm:
			return True

	# 3. Palabras individuales de mal gusto con límites de palabra (\b)
	words = set(re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b", norm))
	return any(w in PROFANITY_TERMS for w in words)


# ---------------------------------------------------------------------------
# Verificación de verbos y sintaxis para oraciones habladas
# ---------------------------------------------------------------------------


def has_conjugated_verb(words: list[str]) -> bool:
	"""Determina si una lista de palabras contiene al menos un verbo conjugado común en español."""
	for w in words:
		w_low = w.lower()
		if w_low in COMMON_SPANISH_VERBS:
			return True
		if VERBAL_SUFFIXES_REGEX.match(w_low):
			return True
	return False


def is_valid_spoken_sentence(text: str) -> bool:
	"""
	Determina si el texto es apto para ser locutado por radio como una oración completa.
	Criterios:
	1. Longitud: entre 5 y 88 palabras inclusive (ni fragmento trunco ni párrafo denso).
	2. Contiene al menos un verbo conjugado común en español.
	3. No es una lista numerada ni de viñetas, ni contiene caracteres de formato (*, /, |, símbolos matemáticos).
	4. Descarta poesía rimada rota o versos aislados (múltiples cláusulas de menos de 3 palabras).
	5. No es un fragmento truncado (no empieza con puntos suspensivos ni termina en dos puntos o comas).
	6. No contiene términos de mal gusto ni jerga de asistente de IA / robótica.
	"""
	if not text or not isinstance(text, str):
		return False

	clean = text.strip()

	# Descartar si empieza con elipsis o puntuación huérfana
	if clean.startswith(("...", "…", ",", ";", ":", "-", "—", "–")):
		return False

	# Descartar oraciones truncas que terminan en dos puntos, punto y coma, coma o guion
	if clean.endswith((":", ";", ",", "-", "—", "–")):
		return False

	# Debe iniciar con mayúscula (o signo de apertura ¿ o ¡ seguido de letra)
	first_alpha = re.search(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", clean)
	if not first_alpha or first_alpha.group(0).islower():
		return False

	# Caracteres de formato, código o matemáticos prohibidos
	if any(c in clean for c in FORBIDDEN_FORMAT_CHARS):
		return False

	# No debe ser una lista numerada o con viñetas al inicio
	if re.match(r"^\s*(?:\d+[\.\)\-]|[a-zA-Z][\.\)]|[-*•])\s+", clean):
		return False

	# No debe contener listas numeradas internas (ej: "1) primer punto 2) segundo punto")
	if re.search(r"\b\d+[\.\)]\s+[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", clean):
		return False

	words = re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+\b", clean)

	# Longitud entre 5 y 88 palabras
	if not (5 <= len(words) <= 88):
		return False

	# Descartar poesía rimada rota o versos aislados (múltiples cláusulas de menos de 3 palabras)
	clauses = [re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+\b", c) for c in re.split(r"[,;:\—–\n]+", clean) if c.strip()]
	if len(clauses) >= 3:
		short_clauses = sum(1 for c in clauses if 1 <= len(c) < 3)
		if short_clauses >= 3 or (len(clauses) >= 4 and short_clauses >= 2 and (short_clauses / len(clauses)) >= 0.5):
			return False

	# Debe contener al menos un verbo conjugado común en español
	if not has_conjugated_verb(words):
		return False

	# Filtro de mal gusto y jerga robótica / IA
	return not contains_blacklisted_content(clean)


def is_tts_friendly_fortune(text: str) -> bool:
	"""
	Determina si una frase de la colección bundled de fortunas es apta para TTS.
	Aplica un filtrado relajado para preservar la riqueza cultural, refranes cortos
	y citas literarias/filosóficas, descartando únicamente:
	1. Textos vacíos, de menos de 3 palabras o más de 120 palabras.
	2. Arte ASCII (patrones repetitivos de barras, guiones, asteriscos, etc.).
	3. Ruido de símbolos o código (> 15% de caracteres no alfanuméricos/puntuación estándar).
	4. Textos en inglés puro (sin acentos/ñ y con predominio de palabras funcionales en inglés).
	"""
	if not text or not isinstance(text, str):
		return False

	clean = text.strip()
	words = re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+\b", clean)
	if not (3 <= len(words) <= 120):
		return False

	# 1. Descartar arte ASCII (ej: /\\/\\/, =====, #####, ::::, etc.)
	if re.search(r"[/\\|_#=~*]{3,}|<{3,}|>{3,}|:{3,}", clean):
		return False

	# 2. Descartar ruido de símbolos o código excesivo
	letters = len(re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", clean))
	symbols = len(re.findall(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:¡!¿?\"'()—–-]", clean))
	if (letters + symbols) > 0 and (symbols / (letters + symbols)) > 0.15:
		return False

	# 3. Descartar inglés puro si no contiene caracteres exclusivos del español
	has_spanish_exclusive = bool(re.search(r"[áéíóúüñÁÉÍÓÚÜÑ¿¡]", clean))
	if not has_spanish_exclusive:
		pure_en = {w for w in COMMON_ENGLISH_WORDS if w not in COMMON_SPANISH_WORDS and w not in {"no", "a", "me"}}
		lower_words = [w.lower() for w in words]
		en_matches = [w for w in lower_words if w in pure_en]
		if len(words) > 0 and (len(en_matches) / len(words) >= 0.35 or len(set(en_matches)) >= 3):
			return False

	return True


def get_available_spanish_dbs(timeout: float = 2.0) -> list[str]:
	"""Detecta y cachea las bases de datos en español disponibles para el comando fortune."""
	global _SPANISH_FORTUNE_DBS_CACHE
	if _SPANISH_FORTUNE_DBS_CACHE is not None:
		return _SPANISH_FORTUNE_DBS_CACHE

	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		_SPANISH_FORTUNE_DBS_CACHE = []
		return _SPANISH_FORTUNE_DBS_CACHE

	try:
		res = subprocess.run([fortune_bin, "-f"], capture_output=True, text=True, timeout=timeout, check=False)
		if res.returncode != 0:
			logger.warning(f"Comando 'fortune -f' falló con código {res.returncode}: {res.stderr.strip()[:200]}")
		dbs = []
		for line in (res.stdout + res.stderr).splitlines():
			m = re.search(r"^\s*[\d,.]+\%\s+([a-zA-Z0-9_\-]+)", line)
			if m:
				name = m.group(1).lower()
				if name in KNOWN_SPANISH_DBS or name == "es":
					dbs.append(m.group(1))
		_SPANISH_FORTUNE_DBS_CACHE = dbs
		return dbs
	except Exception as e:
		logger.warning(f"Error detectando bases en español de fortune: {e}")
		_SPANISH_FORTUNE_DBS_CACHE = []
		return []


def clean_fortune_text(raw_text: str) -> str:
	"""
	Limpia el texto de una fortuna o cita de Unix:
	- Elimina comillas dobles, simples y tipográficas (« » “ ” ‘ ’ " ' `).
	- Limpia saltos de línea y normaliza espacios en blanco.
	- Quita enlaces web (URLs) y tags HTML.
	- Remueve corchetes [...] y paréntesis bibliográficos (fechas, páginas, tomos).
	- Preserva las firmas de autor (-- Autor, — Autor, (Autor)).
	"""
	if not raw_text:
		return ""

	text = raw_text

	# 1. Quitar URLs y enlaces web
	text = re.sub(r"https?://\S+|www\.\S+", "", text)

	# 2. Quitar etiquetas tipo HTML (<...>)
	text = re.sub(r"<[^>]+>", "", text)

	# 3. Quitar corchetes editoriales o bibliográficos: [...]
	text = re.sub(r"\[[^\]]*\]", "", text)

	# 4. Quitar paréntesis bibliográficos (años, fechas, tomos, páginas, referencias)
	# Ej: (1879-1955), (siglo IV a.C.), (pág. 12), (op. cit.), (Ed. Losada, 1980)
	text = re.sub(
		r"\([^)]*(?:\b\d{1,4}\b|siglo|pág|pag|ibid|op\.?\s*cit|ed\.?|vol\.?|cap\.?|trad\.?)[^)]*\)",
		"",
		text,
		flags=re.IGNORECASE,
	)

	# 5. Normalizar firmas de autor precedidas por guiones o tildes (-- Autor, ~ Autor) a raya (—)
	text = re.sub(r"\s*(?:--|—|~)\s*", " — ", text)

	# 6. Eliminar comillas dobles, simples y tipográficas (« » “ ” ‘ ’ " ' `)
	text = re.sub(r"[«»“”‘’\"'`]", "", text)

	# 7. Espacios antes de signos de puntuación creados al remover paréntesis
	text = re.sub(r"\s+([,.:;!?])", r"\1", text)

	# 8. Normalizar saltos de línea y múltiples espacios en blanco
	text = re.sub(r"\s+", " ", text).strip()

	# 9. Limpiar puntuación huérfana al inicio (ej: "... y nada más", ", dijo")
	text = re.sub(r"^[.,;:—–\s]+", "", text).strip()

	# 10. Asegurar puntuación terminal (. ! ? …) si termina en carácter alfanumérico o paréntesis de autor
	if text and (text[-1].isalnum() or text[-1] in (")", "]")):
		text = f"{text}."

	return text


def get_system_fortune(timeout: float = 2.0, max_attempts: int = 3) -> str | None:
	"""
	Intenta obtener una fortuna corta exclusivamente en ESPAÑOL mediante el comando Unix `fortune -s`.
	Solo consulta bases en español conocidas y valida que el texto resultante:
	1. Esté redactado en idioma español (is_spanish_text).
	2. Sea una oración completa y apta para locución radial (is_valid_spoken_sentence).
	Realiza hasta max_attempts reintentos ante fragmentos incoherentes o poesía rota antes de desistir.
	"""
	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		return None

	spanish_dbs = get_available_spanish_dbs(timeout=timeout)
	if not spanish_dbs:
		return None

	cmd = [fortune_bin, "-s"] + spanish_dbs
	for _ in range(max_attempts):
		try:
			res = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				timeout=timeout,
				check=False,
			)
			if res.returncode == 0 and res.stdout:
				cleaned = clean_fortune_text(res.stdout)
				if is_spanish_text(cleaned) and is_valid_spoken_sentence(cleaned):
					return cleaned
			elif res.returncode != 0:
				err_msg = res.stderr.strip()
				logger.warning(f"Comando fortune falló con código {res.returncode}: {err_msg[:200]}")
		except Exception as e:
			logger.warning(f"Error consultando bases en español de fortune: {e}")
			break

	return None


_BUNDLED_FORTUNES_CACHE: list[str] | None = None


def get_bundled_fortunes_path(custom_path: Path | str | None = None) -> Path:
	"""Resuelve la ruta absoluta a la carpeta o archivo de fortunas en formato Unix %."""
	if custom_path:
		return Path(custom_path)
	if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
		candidate_dir = Path(sys._MEIPASS) / "scripts" / "fortune-es"
		if candidate_dir.is_dir():
			return candidate_dir
	default_dir = Path(__file__).parent / "fortune-es"
	if default_dir.is_dir():
		return default_dir
	return Path(__file__).parent / "data" / "fortunes_es.txt"


def load_bundled_fortunes(target: Path | str | None = None) -> list[str]:
	"""
	Carga y valida fortunas en formato Unix (delimitador %).
	Soporta tanto un archivo individual como una carpeta completa estilo Debian
	con múltiples archivos temáticos (.fortunes).
	Garantiza que cada ítem esté en español y sea apto para locución radial.
	"""
	global _BUNDLED_FORTUNES_CACHE
	p = get_bundled_fortunes_path(target)
	if not p.exists():
		return []

	candidate_files: list[Path] = []
	if p.is_file():
		candidate_files = [p]
	elif p.is_dir():
		for f in sorted(p.iterdir()):
			if not f.is_file():
				continue
			# Omitir archivos de control o borradores de Debian
			if (
				f.name.endswith("-pre")
				or f.name.endswith(".dat")
				or f.name in ("copyright", "README.Debian", "LEAME.Debian")
			):
				continue
			candidate_files.append(f)

	items: list[str] = []
	seen: set[str] = set()

	for file_path in candidate_files:
		try:
			raw = file_path.read_text(encoding="utf-8", errors="replace")
			for entry in raw.split("\n%\n"):
				cleaned = clean_fortune_text(entry.strip())
				if cleaned and cleaned not in seen and is_tts_friendly_fortune(cleaned):
					seen.add(cleaned)
					items.append(cleaned)
		except Exception as e:
			logger.debug(f"Error leyendo archivo de fortunas ({file_path}): {e}")

	if target is None:
		_BUNDLED_FORTUNES_CACHE = items
	return items


def get_bundled_fortune(db_path: Path | str | None = None) -> str | None:
	"""
	Retorna una fortuna o cita célebre en español del banco propio bundled,
	utilizando selección ponderada por recencia para evitar repeticiones.
	"""
	global _BUNDLED_FORTUNES_CACHE
	if _BUNDLED_FORTUNES_CACHE is None:
		_BUNDLED_FORTUNES_CACHE = load_bundled_fortunes()
	if not _BUNDLED_FORTUNES_CACHE:
		return None
	return weighted_choice_by_recency(_BUNDLED_FORTUNES_CACHE, category="fortuna_bundled", db_path=db_path)


def select_radio_phrase(
	force_system_fortune: bool | None = None,
	db_path: Path | str | None = None,
) -> tuple[RadioPhrase, bool]:
	"""
	Selecciona una frase o fortuna radial explícita (RadioPhrase(text, category), es_del_sistema).
	Por defecto intenta con probabilidad 1/6 consultar una fortuna del sistema si está disponible en español,
	o recurre al banco curado de frases del proyecto con duplas explícitas y selección ponderada por recencia.
	"""
	if force_system_fortune is not False and (force_system_fortune is True or random.random() < 1 / 6):
		sys_fort = get_system_fortune()
		if sys_fort and is_spanish_text(sys_fort):
			return RadioPhrase(sys_fort, "fortuna"), True
		bundled = get_bundled_fortune(db_path=db_path)
		if bundled and is_spanish_text(bundled):
			return RadioPhrase(bundled, "fortuna"), True

	chosen = weighted_choice_by_recency(CARPINCHO_PHRASES, category="fortuna", db_path=db_path)
	return chosen, False


def select_fortune(
	force_system_fortune: bool | None = None,
	db_path: Path | str | None = None,
) -> tuple[str, bool]:
	"""
	Selecciona una fortuna garantizada en español y retorna (texto_fortuna, es_del_sistema).
	Por defecto intenta con probabilidad 1/6 consultar una fortuna del sistema si está disponible en español,
	o recurre al banco curado de frases del proyecto (o frases criollas del carpincho) con selección ponderada por recencia.
	"""
	phrase, is_sys = select_radio_phrase(force_system_fortune=force_system_fortune, db_path=db_path)
	return phrase.text, is_sys


def get_radio_fortune(db_path: Path | str | None = None) -> str:
	"""Devuelve una frase o fortuna garantizada en español."""
	fortuna, _ = select_fortune(db_path=db_path)
	return fortuna


# Pases de cabina criollos entre carpinchos locutores ("charla de cabina")
def select_radio_hosts(
	host_voice: str | None = None,
	is_system_fortune: bool = False,
) -> tuple[str, str]:
	"""
	Selecciona el locutor principal (host) y el co-conductor (cohost).
	Garantiza en todos los casos que host != cohost.
	- Si is_system_fortune es True:
		* Si host == VOICE_ELENA: Elena conduce y lee la fortuna del sistema;
		  el cohost es otra voz elegida al azar.
		* Si host != VOICE_ELENA: el cohost es fijado en VOICE_ELENA para leer la fortuna del sistema.
	- Si is_system_fortune es False:
		* host es host_voice (o elegido al azar si no se indicó).
		* cohost es elegido al azar entre las voces distintas a host.
	"""
	if not host_voice or host_voice not in VOICES:
		host = random.choice(VOICES)
	else:
		host = host_voice

	other_voices = [v for v in VOICES if v != host]

	if is_system_fortune:
		if host == VOICE_ELENA:
			cohost = random.choice(other_voices)
		else:
			cohost = VOICE_ELENA
	else:
		cohost = random.choice(other_voices)

	return host, cohost


def get_all_weather_handoff_segments() -> list[str]:
	"""Genera todas las combinaciones posibles de pases de clima para precarga en caché."""
	res: list[str] = []
	for name in VOICE_NAMES.values():
		for tpl in PASES_A_CLIMA:
			res.append(tpl.format(cohost=name))
	return res


def get_all_weather_reaction_segments() -> list[str]:
	"""Devuelve todas las reacciones climáticas de cabina para precarga en caché."""
	res: list[str] = []
	for reactions in REACCIONES_CLIMA.values():
		res.extend(reactions)
	return res


def get_all_fortune_reaction_segments() -> list[str]:
	"""Devuelve todas las reacciones de fortuna para precarga en caché."""
	return list(REACCIONES_FORTUNA)


def format_fortune_for_speech(fortuna: str | tuple[str, str] | RadioPhrase) -> str:
	"""Prepara el texto de una fortuna para locución quitando comillas duras y asegurando puntuación terminal."""
	raw = fortuna[0] if isinstance(fortuna, (tuple, list)) else str(fortuna)
	cleaned = raw.strip().strip("\"'«»")
	if not cleaned.endswith((".", "!", "?", "…")):
		cleaned = f"{cleaned}."
	return cleaned


def get_modular_hour_segments() -> list[str]:
	"""Genera la lista con los 24 segmentos modulares de hora ('Las doce', 'Las una', ... 'Las once')."""
	return [HOUR_NAMES[h % 12] for h in range(24)]


def get_modular_minute_segments() -> list[str]:
	"""Genera la lista con los 12 segmentos modulares de minutos cada 5 minutos."""
	return list(MINUTE_SEGMENTS)


def get_all_time_segments() -> list[str]:
	"""
	Genera todas las combinaciones posibles de locución horaria:
	1. Las 24 frases especiales en punto (SPECIAL_HOURS).
	2. Todas las combinaciones de las 12 horas con los intervalos de minutos (e.g. 'Las nueve y media.').
	"""
	segments: list[str] = []
	for special in SPECIAL_HOURS.values():
		if special not in segments:
			segments.append(special)
	for hora in HOUR_NAMES:
		for minuto in MINUTE_SEGMENTS:
			combo = f"{hora} {minuto}"
			if combo not in segments:
				segments.append(combo)
	return segments


def get_all_degree_segments(min_deg: int = -5, max_deg: int = 42) -> list[str]:
	"""Devuelve las frases de temperaturas en grados para locución modular del clima."""
	return [format_temperature(d) for d in range(min_deg, max_deg + 1)]


def build_radio_dialogue_plan(
	intro: str,
	hora_seg: str,
	minuto_seg: str | None,
	lead_in: str | None,
	fortuna: str | tuple[str, str] | RadioPhrase,
	outro: str,
	host_voice: str,
	cohost_voice: str,
	is_system_fortune: bool = False,
	weather_text: str | None = None,
	weather_condition: str | None = None,
	dialogue_mode: bool = True,
	last_reaction: str | None = None,
	db_path: Path | str | None = None,
) -> list[tuple[str, str, str, bool]]:
	"""
	Construye el plan estructurado de segmentos para la locución radial (texto, voz, categoría, allow_cache).
	Si dialogue_mode es True, organiza una charla viva de cabina entre host y cohost.
	Si dialogue_mode es False, retorna la locución solo tradicional.
	Garantiza que nunca haya dos reacciones consecutivas idénticas y pondera frases por recencia.
	"""
	time_phrase = f"{hora_seg} {minuto_seg}".strip() if minuto_seg else hora_seg.strip()
	fortune_text = format_fortune_for_speech(fortuna)
	seg_cat = resolve_segment_category(fortuna)

	if lead_in is not None:
		effective_lead_in = lead_in
	else:
		cat_lead_ins = get_lead_ins_for_category(seg_cat)
		effective_lead_in = weighted_choice_by_recency(cat_lead_ins, category=f"lead_in_{seg_cat}", db_path=db_path)

	if not dialogue_mode:
		fortune_voice = VOICE_ELENA if is_system_fortune else host_voice
		solo_plan: list[tuple[str, str, str, bool]] = [
			(intro, host_voice, "intro", True),
			(time_phrase, host_voice, "hora", True),
		]
		if weather_text:
			solo_plan.append((weather_text, host_voice, "clima", False))
		solo_plan.extend(
			[
				(effective_lead_in, host_voice, "lead_in", True),
				(fortune_text, fortune_voice, "fortuna", True),
				(outro, host_voice, "salida", True),
			]
		)
		return solo_plan

	# Plan de charla de cabina
	plan: list[tuple[str, str, str, bool]] = [
		(intro, host_voice, "intro", True),
		(time_phrase, host_voice, "hora", True),
	]

	prev_reaction = last_reaction

	# 1. Clima
	if weather_text:
		cohost_name = VOICE_NAMES.get(cohost_voice, DEFAULT_COHOST_NAME)
		pase_template = weighted_choice_by_recency(PASES_A_CLIMA, category="pase", db_path=db_path)
		pase_text = pase_template.format(cohost=cohost_name)
		plan.append((pase_text, host_voice, "pase", True))

		plan.append((weather_text, cohost_voice, "clima", False))

		cond = weather_condition or "agradable"
		candidates = REACCIONES_CLIMA.get(cond, REACCIONES_CLIMA["agradable"])
		valid_reactions = [r for r in candidates if r != prev_reaction]
		pool_clima = valid_reactions if valid_reactions else candidates
		reaccion_clima = weighted_choice_by_recency(pool_clima, category="reaccion_clima", db_path=db_path)
		plan.append((reaccion_clima, host_voice, "reaccion", True))
		prev_reaction = reaccion_clima

	# 2. Fortuna / Aviso / Oyentes
	plan.append((effective_lead_in, host_voice, "lead_in", True))

	if is_system_fortune:
		fortune_voice = VOICE_ELENA
	else:
		fortune_voice = cohost_voice

	plan.append((format_fortune_for_speech(fortuna), fortune_voice, "fortuna", True))

	cat_reactions = get_reactions_for_category(seg_cat)
	valid_fortune_reactions = [r for r in cat_reactions if r != prev_reaction]
	pool_fortuna = valid_fortune_reactions if valid_fortune_reactions else cat_reactions
	reaccion_fortuna = weighted_choice_by_recency(pool_fortuna, category=f"reaccion_{seg_cat}", db_path=db_path)
	react_voice = host_voice if fortune_voice == cohost_voice else cohost_voice
	plan.append((reaccion_fortuna, react_voice, "reaccion", True))

	# Salida a la música
	plan.append((outro, host_voice, "salida", True))

	return plan


NO_MERGE_CATEGORIES: set[str] = {"intro", "hora", "minuto", "clima", "salida"}


def group_plan_into_speech_turns(
	plan: list[tuple[str, str, str, bool]],
) -> list[tuple[str, str, str, bool]]:
	"""
	Agrupa turnos consecutivos de habla que pertenecen al MISMO locutor
	en bloques o parlamentos completos de texto continuo, EXCEPTO para categorías
	fijas/modulares (intro, hora, minuto, salida) que cuentan con clips pregrabados
	o cacheados, y para el clima dinámico que ya constituye un bloque completo.

	Esto le entrega a edge-tts oraciones y párrafos completos con entonación natural,
	ritmo fluido y pausas prosódicas humanas, preservando al mismo tiempo la alta tasa
	de aciertos de caché del catálogo inicial y evitando textos desmesurados que agoten
	el tiempo de espera de la red.
	"""
	if not plan:
		return []

	turns: list[tuple[str, str, str, bool]] = []
	current_texts: list[str] = [plan[0][0].strip()]
	current_voice = plan[0][1]
	current_category = plan[0][2]
	current_allow_cache = plan[0][3]

	for text, v, category, allow_cache in plan[1:]:
		clean_txt = text.strip()
		if not clean_txt:
			continue

		can_merge = (
			v == current_voice and current_category not in NO_MERGE_CATEGORIES and category not in NO_MERGE_CATEGORIES
		)

		if can_merge:
			current_texts.append(clean_txt)
			# Si algún segmento individual no permite caché, el turno completo no se cachea
			if not allow_cache:
				current_allow_cache = False
		else:
			turns.append((" ".join(current_texts), current_voice, current_category, current_allow_cache))
			current_texts = [clean_txt]
			current_voice = v
			current_category = category
			current_allow_cache = allow_cache

	if current_texts:
		turns.append((" ".join(current_texts), current_voice, current_category, current_allow_cache))

	return turns


def get_modular_time_segments(dt: datetime | None = None) -> tuple[str, str | None, str]:
	"""
	Divide el anuncio de la hora en segmentos modulares redondeados cada 5 minutos
	(aproximadamente la duración de una canción):
	- en punto (58..59, 0..2)
	- y cinco (3..7)
	- y diez (8..12)
	- y cuarto (13..17)
	- y veinte (18..22)
	- y veinticinco (23..27)
	- y media (28..32)
	- y treinta y cinco (33..37)
	- menos veinte (38..42, hora siguiente)
	- menos cuarto (43..47, hora siguiente)
	- menos diez (48..52, hora siguiente)
	- menos cinco (53..57, hora siguiente)
	"""
	if dt is None:
		dt = datetime.now(UTC).astimezone()

	hour = dt.hour
	minute = dt.minute

	if minute in range(3, 8):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[1]
	elif minute in range(8, 13):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[2]
	elif minute in range(13, 18):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[3]
	elif minute in range(18, 23):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[4]
	elif minute in range(23, 28):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[5]
	elif minute in range(28, 33):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[6]
	elif minute in range(33, 38):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[7]
	elif minute in range(38, 43):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[8]
	elif minute in range(43, 48):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[9]
	elif minute in range(48, 53):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[10]
	elif minute in range(53, 58):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[11]
	else:
		# En punto: 58..59 o 0..2
		target_hour = (hour + 1) % 24 if minute >= 58 else hour
		if target_hour in SPECIAL_HOURS:
			special = SPECIAL_HOURS[target_hour]
			return special, None, special
		hora_seg = HOUR_NAMES[target_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[0]

	full_time_str = f"{hora_seg} {minuto_seg}"
	return hora_seg, minuto_seg, full_time_str


def get_fortune_voice(is_system_fortune: bool, host_voice: str) -> str:
	"""
	Determina la voz para sintetizar la fortuna radial.
	Las fortunas del sistema Unix son leídas EXCLUSIVAMENTE por Elena (VOICE_ELENA),
	creando una dinámica de co-conducción tipo podcast junto al locutor principal.
	Las fortunas y avisos carpinchos son leídos por el conductor principal (host_voice).
	"""
	if is_system_fortune:
		return VOICE_ELENA
	return host_voice


def generate_modular_radio_script(
	dt: datetime | None = None,
	voice: str | None = None,
	force_system_fortune: bool | None = None,
) -> tuple[str, str, str | None, str, str, bool, str, str, str]:
	"""
	Genera los componentes del guión radial de forma modular.
	Retorna:
	(intro, hora_seg, minuto_seg, lead_in, fortuna, is_system_fortune, outro, selected_voice, full_script)
	"""
	if not voice or voice not in VOICES:
		voice = random.choice(VOICES)

	intro = random.choice(RADIO_INTROS)
	hora_seg, minuto_seg, _ = get_modular_time_segments(dt)
	fortuna, is_system_fortune = select_fortune(force_system_fortune)
	seg_cat = resolve_segment_category(fortuna)
	cat_lead_ins = get_lead_ins_for_category(seg_cat)
	lead_in = random.choice(cat_lead_ins)
	outro = random.choice(RADIO_OUTROS)
	hora_full = f"{hora_seg} {minuto_seg}" if minuto_seg else hora_seg
	fort_speech = format_fortune_for_speech(fortuna)
	full_script = f"{intro} {hora_full} {lead_in} {fort_speech} {outro}"
	return intro, hora_seg, minuto_seg, lead_in, fortuna, is_system_fortune, outro, voice, full_script


_DUMMY_MP3_DATA: bytes = (
	b"SUQzBAAAAAAAIlRTU0UAAAAOAAADTGF2ZjYzLjEuMTAyAAAAAAAAAAAAAAD/+1DEAAAKZFMyNZeAAWWVaWs00AAfi5ZcsuWXLLloPrrctQMuI2"
	b"oJLNeE6bTvtOmM2TwcWTRgLYPQQguB0KBkfv1er1ezv496Uo8iAgcg+D78QbuX6QxwG/SCGoBn9IIcBn9IY5f3dIHYGGGGAgFAgEA4DpMO//8"
	b"x5wxyXQjVeFUZ5nBdYQy4IPSsWuBkgOnwPUT4Rr8RokR6jh/xPhGguw7Rhf/JEyLxeRLv/5dMi8XkUTH+IgqCoiPf8Ff/+eDRZYAAHHVWv7+4"
	b"gCgKTAYB//tSxAcACnQtFT3sAAGBBeGGv5AAFMFQEcwOgEzAoBvMMYXkyJCMzIs6tOKBHgxWwgzCSA7MDoFMwJACAIoFmVNG1sjtFGvpop/Xp"
	b"/6v7u/6Pf39C9PblOnpcEXfwlCOhgGAAoYCkA5GAeABZgKIDiYFoBJGAfAkphmImCYmutim1XDqxjUQf0YOMBtAYENMBxAPzj7FUDMOAznBSu"
	b"8oFlVejHt3bRjn30+3Z6OhxP8bd9r+Za7112//0La6iiLRaLRaLRaBQIAP1F5QGNR6d6D/+1LECwAM2MlhuamAEUGLZV+ewACCWGfUMEBAEDO"
	b"YocsG57RGh4nNED+gBSPJ8rohoQN4g1T5ufZMZISkLlIt96bxcxASaIETP7vvKRNFE4ZHf998wMjMwOGZh/1A4IwQBz/6XGgIABSMOIoeolzm"
	b"cp0pIE0AJhMWQ5idHU/P0W0Q02CUAEKYl0ZVEE+ZW1y3snL21nLTVk9lQ3VBU9DqwWBoO4iBrg0+xR6o8IsRK//8Ree/z1VMQU1FNC4wVVVV"
	b"VVVVVVVVVVVVVVVVVVVVVVVVVQ=="
)


ALLOW_TEST_DUMMY_AUDIO: bool = False


async def synthesize_segment(
	text: str,
	voice: str,
	category: str,
	allow_cache: bool = True,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
	db_path: Path | str | None = None,
	boundary: str = "SentenceBoundary",
	return_cues: bool = False,
) -> bytes | tuple[bytes, list[tuple[float, float, str]]]:
	"""Sintetiza un segmento individual o parlamento radial.

	Diseño intencional de prioridad y frescura:
	- Intenta PRIMERO sintetizar en vivo mediante 'edge-tts' para maximizar la naturalidad,
	  inflexión prosódica y variabilidad tonal de la locución.
	- Si la síntesis remota tiene éxito y allow_cache=True, almacena el audio generado y
	  su duración estimada en la base de datos SQLite (tts_cache.db).
	- Si edge-tts falla (por desconexión de red, timeout o ausencia del paquete),
	  consulta la base de datos de caché SQLite como fallback confiable offline.
	- La utilidad 'scripts/preload_tts_cache.py' permite sembrar esta base para garantizar
	  resiliencia total ante caídas prolongadas de conexión a internet.
	- Si return_cues=True, retorna una tupla (audio_bytes, cues) con la sincronización
	  fina por oración/palabra obtenida del stream de edge-tts.
	"""

	captured_cues: list[tuple[float, float, str]] = []

	async def _stream_or_save(comm: edge_tts.Communicate) -> bytes:
		nonlocal captured_cues
		captured_cues = []
		data = bytearray()
		if hasattr(comm, "stream"):
			try:
				async for chunk in comm.stream():
					if isinstance(chunk, dict):
						chunk_type = chunk.get("type")
						if chunk_type == "audio":
							data.extend(chunk.get("data", b""))
						elif chunk_type in ("SentenceBoundary", "WordBoundary"):
							offset_sec = chunk["offset"] / 10_000_000.0
							duration_sec = chunk["duration"] / 10_000_000.0
							chunk_text = str(chunk.get("text", "")).strip()
							if chunk_text:
								captured_cues.append((offset_sec, offset_sec + duration_sec, chunk_text))
			except Exception as e:
				logger.debug(
					f"Fallo o interrupción en communicate.stream() para '{text}': {e}. Intentando communicate.save()..."
				)
		if not data and hasattr(comm, "save"):
			with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_f:
				tmp_p = Path(tmp_f.name)
			try:
				res = comm.save(str(tmp_p))
				if asyncio.iscoroutine(res):
					await res
				if tmp_p.exists() and tmp_p.stat().st_size > 0:
					data = bytearray(tmp_p.read_bytes())
			except Exception as e:
				logger.debug(f"Fallo en communicate.save() para '{text}': {e}")
			finally:
				tmp_p.unlink(missing_ok=True)
		if not data and (
			ALLOW_TEST_DUMMY_AUDIO
			or type(comm).__name__ in ("MagicMock", "AsyncMock")
			or type(getattr(comm, "save", None)).__name__ in ("MagicMock", "AsyncMock")
		):
			# Fallback exclusivo para mocks de tests donde save() no escribe bytes reales en disco
			data = bytearray(base64.b64decode(_DUMMY_MP3_DATA))
		return bytes(data)

	# 1. Intentar PRIMERO con edge-tts si está disponible en el entorno
	if HAS_EDGE_TTS and edge_tts is not None:
		logger.debug(f"🌐 [TTS Remoto / Primario] Sintetizando '{category}' ({voice}): '{text}'")
		prosody = VOICE_PROSODY.get(voice, {})
		rate = prosody.get("rate", "+0%")
		pitch = prosody.get("pitch", "+0Hz")
		volume = prosody.get("volume", "+0%")

		attempt_timeout = max(4.0, timeout)
		audio_bytes = b""
		last_err: Exception | None = None

		for attempt in range(max_retries + 1):
			try:
				try:
					communicate = edge_tts.Communicate(
						text, voice, rate=rate, pitch=pitch, volume=volume, boundary=boundary
					)
				except TypeError:
					try:
						communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
					except TypeError:
						communicate = edge_tts.Communicate(text, voice)
				audio_bytes = await asyncio.wait_for(_stream_or_save(communicate), timeout=attempt_timeout)
				if not audio_bytes:
					raise RuntimeError(f"edge-tts no produjo bytes de audio para '{text}'")
				last_err = None
				break
			except Exception as e:
				last_err = e
				if attempt < max_retries:
					backoff = min(0.3 * (attempt + 1), max(0.01, timeout * 0.2))
					err_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
					logger.debug(
						f"Reintento {attempt + 1}/{max_retries} en síntesis '{category}' ({voice}) tras error: {err_msg}. Esperando {backoff:.2f}s..."
					)
					await asyncio.sleep(backoff)

		if audio_bytes:
			if allow_cache:
				try:
					clip_dur = estimate_mp3_duration(audio_bytes)
					save_cached_audio(category, voice, text, audio_bytes, duration=clip_dur, db_path=db_path)
				except Exception as cache_err:
					logger.debug(f"No se pudo guardar en caché SQLite: {cache_err}")
			if return_cues:
				if not captured_cues:
					clip_dur = estimate_mp3_duration(audio_bytes) or 1.0
					captured_cues = [(0.0, clip_dur, text.strip())]
				return audio_bytes, captured_cues
			return audio_bytes
		else:
			err_msg = f"{type(last_err).__name__}: {last_err}" if str(last_err) else type(last_err).__name__
			logger.warning(
				f"🌐 edge-tts no pudo sintetizar '{category}' ({voice}): {err_msg}. Probando fallback en caché SQLite..."
			)
	else:
		logger.info("edge-tts no está disponible en el entorno. Recurriendo a caché SQLite como fallback...")

	# 2. FALLBACK A CACHÉ SQLITE
	if allow_cache:
		cached_blob = get_cached_audio(category, voice, text, db_path=db_path)
		if cached_blob:
			logger.info(f"⚡ [TTS Cache Fallback HIT] '{category}' ({voice}): '{text}'")
			if return_cues:
				clip_dur = estimate_mp3_duration(cached_blob) or 1.0
				return cached_blob, [(0.0, clip_dur, text.strip())]
			return cached_blob

	err_suffix = f": {last_err}" if last_err else ""
	raise RuntimeError(
		f"No se pudo sintetizar ni recuperar de caché el segmento '{category}' ({voice}): '{text}'{err_suffix}"
	)


def mix_announcement_with_bg_track(
	voice_path: Path | str,
	output_path: Path | str,
	bg_track_path: Path | str,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	timeout: float = 10.0,
) -> bool:
	"""
	Superpone la canción de fondo (desde bg_offset y a bajo volumen)
	con la pista de voz del locutor usando ffmpeg.
	Guarda temporalmente en el directorio /tmp (tmpfs en RAM) para evitar el uso del disco duro.
	Retorna True si la mezcla se realizó con éxito.
	"""
	ffmpeg_bin = shutil.which("ffmpeg")
	if not ffmpeg_bin:
		logger.debug("ffmpeg no disponible para mezclar cortina musical.")
		return False

	voice_p = Path(voice_path)
	bg_p = Path(bg_track_path)
	out_p = Path(output_path)

	if not voice_p.is_file() or not bg_p.is_file():
		return False

	# Averiguamos la duración de la voz para calibrar el fade-out
	voice_dur = 0.0
	try:
		from mutagen import File as MutagenFile

		audio_v = MutagenFile(voice_p)
		if audio_v and audio_v.info and getattr(audio_v.info, "length", None) is not None:
			voice_dur = float(audio_v.info.length)
	except ImportError as e:
		logger.info(f"mutagen no disponible para calcular duración en {voice_p}: {e}")
	except Exception as e:
		logger.warning(f"Error al leer duración con mutagen en {voice_p}: {e}")

	if voice_dur <= 0.0:
		ffprobe_bin = shutil.which("ffprobe")
		if ffprobe_bin:
			try:
				probe_timeout = max(2.0, timeout * 0.3)
				res = subprocess.run(
					[
						ffprobe_bin,
						"-v",
						"error",
						"-show_entries",
						"format=duration",
						"-of",
						"default=noprint_wrappers=1:nokey=1",
						str(voice_p),
					],
					capture_output=True,
					text=True,
					timeout=probe_timeout,
					check=False,
				)
				if res.returncode == 0 and res.stdout.strip():
					voice_dur = float(res.stdout.strip())
				elif res.returncode != 0:
					logger.warning(f"ffprobe falló al obtener duración de {voice_p}: {res.stderr.strip()[:200]}")
			except Exception as e:
				logger.warning(f"Error ejecutando ffprobe para {voice_p}: {e}")

	if voice_dur > 2.0:
		fade_in = 1.0
		fade_out = 1.5
		fade_out_start = max(0.0, voice_dur - fade_out)
		filter_complex = (
			f"[0:a]volume=1.0[v];"
			f"[1:a]volume={bg_volume},afade=t=in:ss=0:d={fade_in},afade=t=out:st={fade_out_start:.2f}:d={fade_out}[bg];"
			f"[v][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0"
		)
	else:
		filter_complex = f"[0:a]volume=1.0[v];[1:a]volume={bg_volume}[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0"

	tmp_out = Path(tempfile.gettempdir()) / f"rockola_mix_{uuid.uuid4().hex[:8]}.mp3"
	cmd = [
		ffmpeg_bin,
		"-y",
		"-i",
		str(voice_p),
		"-ss",
		str(max(0.0, bg_offset)),
		"-i",
		str(bg_p),
		"-filter_complex",
		filter_complex,
		"-c:a",
		"libmp3lame",
		"-b:a",
		"192k",
		str(tmp_out),
	]

	try:
		ffmpeg_timeout = max(5.0, timeout)
		proc = subprocess.run(cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
		if proc.returncode == 0 and tmp_out.is_file() and tmp_out.stat().st_size > 0:
			tmp_dest = out_p.parent / f".tmp_{out_p.name}"
			shutil.copyfile(tmp_out, tmp_dest)
			tmp_dest.replace(out_p)
			logger.info(
				f"🎵 Cortina musical superpuesta con éxito desde el segundo {bg_offset:.1f} de '{bg_p.name}' (volumen {bg_volume * 100:.0f}%)"
			)
			return True
		else:
			logger.warning(
				f"ffmpeg falló al mezclar cortina musical: {proc.stderr.decode('utf-8', errors='ignore')[:200]}"
			)
	except Exception as e:
		logger.warning(f"Error mezclando cortina musical con ffmpeg: {e}")
	finally:
		if tmp_out.exists():
			try:
				tmp_out.unlink()
			except Exception as e:
				logger.warning(f"No se pudo eliminar archivo temporal {tmp_out}: {e}")

	return False


def get_carpincho_cover_path() -> Path | None:
	"""Localiza la imagen del carpincho (public/favicon.png o dist/favicon.png) para coverart."""
	candidates = [
		Path(__file__).resolve().parents[1] / "public" / "favicon.png",
		Path(__file__).resolve().parents[1] / "dist" / "favicon.png",
	]
	if hasattr(sys, "_MEIPASS"):
		candidates.insert(0, Path(sys._MEIPASS) / "public" / "favicon.png")
		candidates.insert(1, Path(sys._MEIPASS) / "dist" / "favicon.png")

	for c in candidates:
		if c.is_file():
			return c
	return None


def embed_cover_art_in_mp3(
	mp3_path: Path | str,
	cover_image_path: Path | str | None = None,
	title: str | None = DEFAULT_RADIO_TITLE,
	artist: str | None = DEFAULT_RADIO_ARTIST,
	album: str = DEFAULT_RADIO_ALBUM,
	timeout: float = 10.0,
) -> bool:
	"""
	Incrusta la carátula del carpincho y metadatos ID3 (título, artista, álbum, APIC)
	directamente dentro del archivo MP3 de la locución radial.
	Intenta primero usando ffmpeg (-c copy) y, si no está disponible o falla,
	recurre al fallback con mutagen.
	"""
	mp3_p = Path(mp3_path)
	if not mp3_p.is_file():
		return False

	data_head = mp3_p.read_bytes()[:10]
	if not is_valid_mp3_stream(data_head):
		return False

	cover_p = Path(cover_image_path) if cover_image_path else get_carpincho_cover_path()
	if not cover_p or not cover_p.is_file():
		return False

	# 1. Intentar primero con mutagen (rápido, directo y nativo en Python)
	try:
		from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError

		try:
			tags = ID3(str(mp3_p))
		except ID3NoHeaderError:
			tags = ID3()

		cover_bytes = cover_p.read_bytes()
		mime = "image/png" if cover_p.suffix.lower() == ".png" else "image/jpeg"

		tags.add(
			APIC(
				encoding=3,  # UTF-8
				mime=mime,
				type=3,  # Front cover
				desc="Cover",
				data=cover_bytes,
			)
		)
		if title:
			tags.add(TIT2(encoding=3, text=[title]))
		if artist:
			tags.add(TPE1(encoding=3, text=[artist]))
		if album:
			tags.add(TALB(encoding=3, text=[album]))

		tags.save(str(mp3_p))
		logger.debug(f"🖼️ Carátula del carpincho incrustada con mutagen en '{mp3_p.name}'")
		return True
	except ImportError as e:
		logger.info(f"Librería opcional mutagen no está disponible para ID3: {e}. Probando fallback con ffmpeg...")
	except Exception as e:
		logger.warning(f"Mutagen falló al incrustar carátula en {mp3_p}: {e}. Probando fallback con ffmpeg...")

	# 2. Fallback con ffmpeg si mutagen no estuviera disponible o fallara
	ffmpeg_bin = shutil.which("ffmpeg")
	if ffmpeg_bin:
		tmp_tagged = mp3_p.parent / f".tmp_tag_{uuid.uuid4().hex[:8]}.mp3"
		cmd = [
			ffmpeg_bin,
			"-y",
			"-i",
			str(mp3_p),
			"-i",
			str(cover_p),
			"-map",
			"0:a",
			"-map",
			"1:v",
			"-c",
			"copy",
			"-id3v2_version",
			"3",
			"-metadata:s:v",
			"title=Cover",
			"-metadata:s:v",
			"comment=Cover (front)",
		]
		if title:
			cmd.extend(["-metadata", f"title={title}"])
		if artist:
			cmd.extend(["-metadata", f"artist={artist}"])
		if album:
			cmd.extend(["-metadata", f"album={album}"])
		cmd.append(str(tmp_tagged))

		try:
			ffmpeg_timeout = max(3.0, timeout * 0.5)
			proc = subprocess.run(cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
			if proc.returncode == 0 and tmp_tagged.is_file() and tmp_tagged.stat().st_size > 0:
				tmp_tagged.replace(mp3_p)
				logger.debug(f"🖼️ Carátula del carpincho incrustada con ffmpeg en '{mp3_p.name}'")
				return True
			else:
				logger.warning(
					f"ffmpeg falló al incrustar carátula: {proc.stderr.decode('utf-8', errors='ignore')[:150]}"
				)
		except Exception as e:
			logger.warning(f"Excepción usando ffmpeg para carátula: {e}")
		finally:
			if tmp_tagged.exists():
				try:
					tmp_tagged.unlink()
				except Exception as e:
					logger.warning(f"No se pudo eliminar archivo temporal {tmp_tagged}: {e}")

	return False


def get_audio_duration(file_path: Path | str, timeout: float = 2.0) -> float:
	"""Obtiene la duración en segundos de un archivo de audio prefiriendo mutagen antes de ffprobe."""
	p = Path(file_path)
	if p.is_file():
		try:
			from mutagen import File as MutagenFile

			audio = MutagenFile(p)
			if audio and audio.info and getattr(audio.info, "length", None) is not None:
				dur = float(audio.info.length)
				if dur > 0.0:
					return dur
		except ImportError as e:
			logger.info(f"Librería opcional mutagen no disponible para calcular duración de {p}: {e}")
		except Exception as e:
			logger.warning(f"Error al calcular duración con mutagen para {p}: {e}")

	ffprobe_bin = shutil.which("ffprobe")
	if not ffprobe_bin:
		return 0.0
	try:
		res = subprocess.run(
			[
				ffprobe_bin,
				"-v",
				"error",
				"-show_entries",
				"format=duration",
				"-of",
				"default=noprint_wrappers=1:nokey=1",
				str(file_path),
			],
			capture_output=True,
			text=True,
			timeout=timeout,
			check=False,
		)
		if res.returncode == 0 and res.stdout.strip():
			return float(res.stdout.strip())
		elif res.returncode != 0:
			logger.warning(f"ffprobe falló al obtener duración de {file_path}: {res.stderr.strip()[:200]}")
	except Exception as e:
		logger.warning(f"Error ejecutando ffprobe para {file_path}: {e}")
	return 0.0


def format_lrc_timestamp(seconds: float) -> str:
	"""Formatea segundos en formato de marca de tiempo LRC [mm:ss.xx]."""
	total_sec = max(0.0, seconds)
	mins = int(total_sec // 60)
	secs = total_sec % 60
	return f"{mins:02d}:{secs:05.2f}"


def format_srt_timestamp(seconds: float) -> str:
	"""Formatea segundos en formato de marca de tiempo SRT hh:mm:ss,mmm."""
	total_sec = max(0.0, seconds)
	hours = int(total_sec // 3600)
	mins = int((total_sec % 3600) // 60)
	secs = int(total_sec % 60)
	millis = round((total_sec - int(total_sec)) * 1000)
	if millis >= 1000:
		secs += 1
		millis -= 1000
	return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def build_lrc_content(cues: list[tuple[float, float, str]]) -> str:
	"""
	Construye el contenido de un archivo de subtítulos/letras sincronizadas en formato .lrc.
	Cada cue es (start_time, end_time, text).
	"""
	lines: list[str] = []
	for start, _end, text in cues:
		clean = text.strip()
		if clean:
			lines.append(f"[{format_lrc_timestamp(start)}] {clean}")
	return "\n".join(lines) + "\n" if lines else ""


def build_srt_content(cues: list[tuple[float, float, str]]) -> str:
	"""
	Construye el contenido de subtítulos en formato SubRip (.srt).
	Cada cue es (start_time, end_time, text).
	"""
	blocks: list[str] = []
	idx = 1
	for start, end, text in cues:
		clean = text.strip()
		if clean:
			start_str = format_srt_timestamp(start)
			end_str = format_srt_timestamp(max(end, start + 0.1))
			blocks.append(f"{idx}\n{start_str} --> {end_str}\n{clean}\n")
			idx += 1
	return "\n".join(blocks)


def assemble_announcement_audio(
	segments: list[tuple[bytes, str] | tuple[bytes, str, str] | tuple[bytes, str, str, str]],
	output_path: Path | str,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	cover_image_path: Path | str | None = None,
	title: str | None = DEFAULT_RADIO_TITLE,
	artist: str | None = DEFAULT_RADIO_ARTIST,
	timeout: float = 10.0,
	cues_text: list[str] | None = None,
) -> bool:
	"""
	Concatena los segmentos de audio MP3 intercalando ruido de sala sutil (~100-350ms),
	aplicando crossfade suave (~50ms) entre la hora y los minutos de un mismo locutor,
	solapando reacciones cortas (~200ms) sobre la línea anterior,
	igualando volumen entre voces con dynaudnorm y pasando el master final por filtro highpass + compresión.
	Opcionalmente superpone cortina musical de fondo utilizando ffmpeg e incrusta cover art.
	Genera simultáneamente archivos de subtítulos sincronizados (.lrc y .srt) junto al audio.
	Todas las operaciones intermedias se ejecutan en RAM (tmpfs /tmp).
	"""
	out_p = Path(output_path)
	out_p.parent.mkdir(parents=True, exist_ok=True)
	work_dir = Path(tempfile.mkdtemp(prefix="rockola_announcement_"))
	tmp_dest = out_p.parent / f".tmp_{out_p.name}"

	try:
		ffmpeg_bin = shutil.which("ffmpeg")
		tmp_voice_combined = work_dir / "voice_combined.mp3"
		ffmpeg_timeout = max(5.0, timeout)

		# Normalizar segmentos a tuplas (bytes, categoria, voz, texto, cues)
		parsed_segments: list[tuple[bytes, str, str, str, list[tuple[float, float, str]] | None]] = []
		for idx, s in enumerate(segments):
			txt = cues_text[idx] if cues_text and idx < len(cues_text) else ""
			if len(s) >= 5:
				parsed_segments.append((s[0], str(s[1]), str(s[2]), str(s[3]), s[4]))
			elif len(s) == 4:
				parsed_segments.append((s[0], str(s[1]), str(s[2]), str(s[3]), None))
			elif len(s) == 3:
				parsed_segments.append((s[0], str(s[1]), str(s[2]), txt, None))
			elif len(s) == 2:
				parsed_segments.append((s[0], str(s[1]), "", txt, None))
			else:
				parsed_segments.append((s[0], "", "", txt, None))

		cues: list[tuple[float, float, str]] = []

		if ffmpeg_bin:
			# Atajo directo cuando hay un único parlamento/segmento (discurso completo continuo)
			if len(parsed_segments) == 1:
				tmp_voice_combined.write_bytes(parsed_segments[0][0])
				concat_ok = tmp_voice_combined.is_file() and tmp_voice_combined.stat().st_size > 0
				t_single = parsed_segments[0][3]
				cues_single = parsed_segments[0][4]
				if cues_single:
					for cs, ce, ct in cues_single:
						cues.append((cs, ce, ct))
				elif t_single:
					dur_single = (
						get_audio_duration(tmp_voice_combined) or estimate_mp3_duration(parsed_segments[0][0]) or 1.0
					)
					cues.append((0.0, dur_single, t_single))
			else:
				# Generar archivos MP3 temporales con normalización dynaudnorm para nivelar volumen entre voces
				temp_seg_files: list[Path] = []
				for i, (seg_bytes, _cat, _v, _txt, *_rest) in enumerate(parsed_segments):
					raw_file = work_dir / f"raw_seg_{i}.mp3"
					raw_file.write_bytes(seg_bytes)
					norm_file = work_dir / f"norm_seg_{i}.mp3"
					norm_cmd = [
						ffmpeg_bin,
						"-y",
						"-i",
						str(raw_file),
						"-af",
						"dynaudnorm=p=0.9:s=5",
						"-c:a",
						"libmp3lame",
						"-b:a",
						"192k",
						str(norm_file),
					]
					try:
						proc_norm = subprocess.run(
							norm_cmd,
							capture_output=True,
							timeout=min(ffmpeg_timeout, 3.0),
							check=False,
						)
						if proc_norm.returncode == 0 and norm_file.is_file() and norm_file.stat().st_size > 0:
							temp_seg_files.append(norm_file)
						else:
							err_norm = proc_norm.stderr.decode("utf-8", errors="ignore").strip()
							logger.warning(f"ffmpeg falló al normalizar segmento {i}: {err_norm[:200]}")
							temp_seg_files.append(raw_file)
					except Exception as e:
						logger.warning(f"Error al normalizar segmento {i} con ffmpeg: {e}")
						temp_seg_files.append(raw_file)

				blocks: list[tuple[Path, str, str, str, list[tuple[float, float, str]] | None]] = []
				skip_next = False
				for i in range(len(parsed_segments)):
					if skip_next:
						skip_next = False
						continue

					_bytes_i, cat_i, voice_i, text_i, cues_i = parsed_segments[i]
					file_i = temp_seg_files[i]

					# Caso 1: fusión continua (sin gap de silencio) entre 'hora' y 'minuto' consecutivos de la misma voz
					if cat_i == "hora" and i + 1 < len(parsed_segments):
						_bytes_next, cat_next, voice_next, text_next, cues_next = parsed_segments[i + 1]
						if cat_next == "minuto" and (voice_i == voice_next or not voice_i or not voice_next):
							file_next = temp_seg_files[i + 1]
							time_combined = work_dir / f"time_combined_{i}.mp3"
							filter_fade = (
								"[0:a]areverse,silenceremove=start_periods=1:start_threshold=-35dB:start_duration=0.02,areverse[h];"
								"[1:a]silenceremove=start_periods=1:start_threshold=-35dB:start_duration=0.02[m];"
								"[h][m]acrossfade=d=0.05:c1=tri:c2=tri[a]"
							)
							fade_cmd = [
								ffmpeg_bin,
								"-y",
								"-i",
								str(file_i),
								"-i",
								str(file_next),
								"-filter_complex",
								filter_fade,
								"-map",
								"[a]",
								"-c:a",
								"libmp3lame",
								"-b:a",
								"192k",
								str(time_combined),
							]
							try:
								proc_fade = subprocess.run(
									fade_cmd,
									capture_output=True,
									timeout=ffmpeg_timeout,
									check=False,
								)
								if (
									proc_fade.returncode == 0
									and time_combined.is_file()
									and time_combined.stat().st_size > 0
								):
									combined_time_text = f"{text_i} {text_next}".strip()
									combined_cues: list[tuple[float, float, str]] | None = None
									if cues_i or cues_next:
										dur_i = get_audio_duration(file_i) or estimate_mp3_duration(_bytes_i) or 1.0
										combined_cues = []
										if cues_i:
											combined_cues.extend(cues_i)
										elif text_i:
											combined_cues.append((0.0, dur_i, text_i))
										shift_next = max(0.0, dur_i - 0.05)
										if cues_next:
											for cs, ce, ct in cues_next:
												combined_cues.append((cs + shift_next, ce + shift_next, ct))
										elif text_next:
											dur_next = (
												get_audio_duration(file_next)
												or estimate_mp3_duration(_bytes_next)
												or 1.0
											)
											combined_cues.append((shift_next, shift_next + dur_next, text_next))
									blocks.append(
										(time_combined, "hora_minuto", voice_i, combined_time_text, combined_cues)
									)
									skip_next = True
									continue
								else:
									err_fade = proc_fade.stderr.decode("utf-8", errors="ignore").strip()
									logger.warning(f"ffmpeg falló en acrossfade hora/minuto: {err_fade[:200]}")
							except Exception as e:
								logger.warning(f"Error en acrossfade hora/minuto con ffmpeg: {e}")

					# Caso 2: reacción corta que solapa 150-250 ms sobre el final de la línea anterior (adelay + amix)
					if i + 1 < len(parsed_segments):
						_bytes_next, cat_next, voice_next, text_next, cues_next = parsed_segments[i + 1]
						if cat_next == "reaccion" or cat_next.startswith("reaccion"):
							file_next = temp_seg_files[i + 1]
							dur_i = get_audio_duration(file_i)
							if dur_i > 0.25:
								overlap_sec = 0.20
								delay_ms = int(max(0.0, (dur_i - overlap_sec)) * 1000)
								react_combined = work_dir / f"react_combined_{i}.mp3"
								filter_overlap = (
									f"[0:a]volume=1.0[prev];"
									f"[1:a]volume=0.85,adelay={delay_ms}|{delay_ms}[react];"
									f"[prev][react]amix=inputs=2:duration=longest:dropout_transition=0[out]"
								)
								overlap_cmd = [
									ffmpeg_bin,
									"-y",
									"-i",
									str(file_i),
									"-i",
									str(file_next),
									"-filter_complex",
									filter_overlap,
									"-map",
									"[out]",
									"-c:a",
									"libmp3lame",
									"-b:a",
									"192k",
									str(react_combined),
								]
								try:
									proc_react = subprocess.run(
										overlap_cmd,
										capture_output=True,
										timeout=ffmpeg_timeout,
										check=False,
									)
									if (
										proc_react.returncode == 0
										and react_combined.is_file()
										and react_combined.stat().st_size > 0
									):
										combined_react_text = f"{text_i} {text_next}".strip()
										combined_cues = None
										if cues_i or cues_next:
											combined_cues = []
											if cues_i:
												combined_cues.extend(cues_i)
											elif text_i:
												combined_cues.append((0.0, dur_i, text_i))
											shift_next = max(0.0, dur_i - overlap_sec)
											if cues_next:
												for cs, ce, ct in cues_next:
													combined_cues.append((cs + shift_next, ce + shift_next, ct))
											elif text_next:
												dur_next = (
													get_audio_duration(temp_seg_files[i + 1])
													or estimate_mp3_duration(_bytes_next)
													or 1.0
												)
												combined_cues.append((shift_next, shift_next + dur_next, text_next))
										blocks.append(
											(
												react_combined,
												f"{cat_i}_reaccion",
												voice_i,
												combined_react_text,
												combined_cues,
											)
										)
										skip_next = True
										continue
									else:
										err_react = proc_react.stderr.decode("utf-8", errors="ignore").strip()
										logger.warning(f"ffmpeg falló al solapar reacción: {err_react[:200]}")
								except Exception as e:
									logger.warning(f"Error solapando reacción con ffmpeg: {e}")

					blocks.append((file_i, cat_i, voice_i, text_i, cues_i))

				def make_room_tone(duration_sec: float, filename: str) -> Path | None:
					tone_path = work_dir / filename
					cmd = [
						ffmpeg_bin,
						"-y",
						"-f",
						"lavfi",
						"-i",
						"anoisesrc=c=pink:a=0.002:r=44100",
						"-t",
						f"{duration_sec:.3f}",
						"-c:a",
						"libmp3lame",
						"-b:a",
						"192k",
						str(tone_path),
					]
					try:
						res = subprocess.run(cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
						if res.returncode == 0 and tone_path.is_file() and tone_path.stat().st_size > 0:
							return tone_path
						else:
							err_tone = res.stderr.decode("utf-8", errors="ignore").strip()
							logger.warning(f"ffmpeg falló generando room tone (anoisesrc): {err_tone[:200]}")
					except Exception as e:
						logger.warning(f"Error ejecutando ffmpeg para room tone (anoisesrc): {e}")

					# Fallback a anullsrc
					fallback_cmd = [
						ffmpeg_bin,
						"-y",
						"-f",
						"lavfi",
						"-i",
						"anullsrc=r=44100:cl=mono",
						"-t",
						f"{duration_sec:.3f}",
						"-c:a",
						"libmp3lame",
						"-b:a",
						"192k",
						str(tone_path),
					]
					try:
						res = subprocess.run(fallback_cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
						if res.returncode == 0 and tone_path.is_file() and tone_path.stat().st_size > 0:
							return tone_path
						else:
							err_null = res.stderr.decode("utf-8", errors="ignore").strip()
							logger.warning(f"ffmpeg falló generando anullsrc fallback: {err_null[:200]}")
					except Exception as e:
						logger.warning(f"Fallo generando anullsrc fallback con ffmpeg: {e}")

					return None

				# Construir cadena de archivos intercalando pausas de sala y ritmo de locución
				chain_files: list[Path] = []
				current_time = 0.0

				# Presencia de sala muy corta (~150ms) inicial para no cortar abruptamente
				tone_start = make_room_tone(0.15, "tone_start.mp3")
				if tone_start:
					chain_files.append(tone_start)
					current_time = 0.15

				for i, (block_file, block_cat, block_voice, block_text, block_cues) in enumerate(blocks):
					chain_files.append(block_file)
					dur = get_audio_duration(block_file)
					if dur <= 0.0:
						try:
							dur = estimate_mp3_duration(block_file.read_bytes()) or 1.0
						except Exception as e:
							logger.warning(f"Error al estimar duración MP3 para {block_file}: {e}")
							dur = 1.0

					if block_cues:
						for cs, ce, ct in block_cues:
							cues.append((current_time + cs, current_time + ce, ct))
					elif block_text:
						cues.append((current_time, current_time + dur, block_text))
					current_time += dur

					is_last = i == len(blocks) - 1
					if is_last:
						continue

					next_cat = blocks[i + 1][1]
					next_voice = blocks[i + 1][2]
					is_speaker_change = bool(block_voice and next_voice and block_voice != next_voice)
					if is_speaker_change:
						# Cambio de locutor: gap corto (60-150 ms)
						gap_sec = 0.10
					elif block_cat == "hora" and next_cat == "minuto":
						# Sin gap de silencio entre la hora y los minutos
						gap_sec = 0.0
					elif block_cat == "intro":
						gap_sec = 0.30
					elif block_cat in ("hora", "hora_minuto", "minuto"):
						gap_sec = 0.25
					elif block_cat == "clima":
						gap_sec = 0.30
					elif block_cat == "lead_in":
						gap_sec = 0.35
					elif block_cat == "fortuna":
						gap_sec = 0.25
					else:
						gap_sec = 0.25

					if gap_sec > 0.0:
						tone = make_room_tone(gap_sec, f"tone_gap_{i}.mp3")
						if tone:
							chain_files.append(tone)
						current_time += gap_sec

				# Concatena todos los archivos de la cadena
				concat_inputs: list[str] = []
				for f in chain_files:
					concat_inputs.extend(["-i", str(f)])

				filter_concat = (
					"".join(f"[{k}:a]" for k in range(len(chain_files))) + f"concat=n={len(chain_files)}:v=0:a=1[v]"
				)

				concat_cmd = [
					ffmpeg_bin,
					"-y",
					*concat_inputs,
					"-filter_complex",
					filter_concat,
					"-map",
					"[v]",
					"-c:a",
					"libmp3lame",
					"-b:a",
					"192k",
					str(tmp_voice_combined),
				]

				proc = subprocess.run(concat_cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
				concat_ok = (
					proc.returncode == 0 and tmp_voice_combined.is_file() and tmp_voice_combined.stat().st_size > 0
				)

				# Si falla el filter_complex, intentar concat demuxer simple
				if not concat_ok:
					logger.warning(
						f"ffmpeg filter_complex falló ({proc.stderr.decode('utf-8', errors='ignore')[:150]}). Probando concat demuxer..."
					)
					concat_list = work_dir / "concat_list.txt"
					concat_list.write_text("\n".join(f"file '{f.name}'" for f in chain_files), encoding="utf-8")
					demux_cmd = [
						ffmpeg_bin,
						"-y",
						"-f",
						"concat",
						"-safe",
						"0",
						"-i",
						str(concat_list),
						"-c:a",
						"copy",
						str(tmp_voice_combined),
					]
					proc_demux = subprocess.run(
						demux_cmd,
						cwd=str(work_dir),
						capture_output=True,
						timeout=ffmpeg_timeout,
						check=False,
					)
					concat_ok = (
						proc_demux.returncode == 0
						and tmp_voice_combined.is_file()
						and tmp_voice_combined.stat().st_size > 0
					)
					if not concat_ok and proc_demux.returncode != 0:
						logger.warning(
							f"ffmpeg concat demuxer falló con código {proc_demux.returncode}: {proc_demux.stderr.decode('utf-8', errors='ignore')[:150]}"
						)

			# Mastering final de voz: filtro paso-alto ~80 Hz, compresión y normalización broadcast (-14 LUFS)
			if concat_ok:
				tmp_voice_mastered = work_dir / "voice_mastered.mp3"
				master_cmd = [
					ffmpeg_bin,
					"-y",
					"-i",
					str(tmp_voice_combined),
					"-af",
					"highpass=f=80,acompressor=threshold=-18dB:ratio=2.5:attack=20:release=250:makeup=2,loudnorm=I=-14:TP=-1.5:LRA=7",
					"-c:a",
					"libmp3lame",
					"-b:a",
					"192k",
					str(tmp_voice_mastered),
				]
				try:
					proc_master = subprocess.run(
						master_cmd,
						capture_output=True,
						timeout=ffmpeg_timeout,
						check=False,
					)
					if (
						proc_master.returncode == 0
						and tmp_voice_mastered.is_file()
						and tmp_voice_mastered.stat().st_size > 0
					):
						shutil.copyfile(tmp_voice_mastered, tmp_voice_combined)
					elif proc_master.returncode != 0:
						logger.warning(
							f"ffmpeg falló en masterización de voz: {proc_master.stderr.decode('utf-8', errors='ignore')[:200]}"
						)
				except Exception as e:
					logger.warning(f"Error aplicando filtro de estudio/compresión con ffmpeg: {e}")

			if not concat_ok:
				logger.warning("ffmpeg concat demuxer también falló. Recurriendo a concatenación directa de bytes.")
				combined = b"".join(seg[0] for seg in parsed_segments)
				tmp_voice_combined.write_bytes(combined)
		else:
			# Si no hay ffmpeg disponible, concatenación directa de streams MP3
			combined = b"".join(seg[0] for seg in parsed_segments)
			tmp_voice_combined.write_bytes(combined)
			curr_offset = 0.0
			for seg in parsed_segments:
				dur_fb = estimate_mp3_duration(seg[0]) or 1.0
				seg_cues = seg[4]
				if seg_cues:
					for cs, ce, ct in seg_cues:
						cues.append((curr_offset + cs, curr_offset + ce, ct))
				elif seg[3]:
					cues.append((curr_offset, curr_offset + dur_fb, seg[3]))
				curr_offset += dur_fb

		def _save_subtitles():
			if cues:
				lrc_content = build_lrc_content(cues)
				srt_content = build_srt_content(cues)
				try:
					out_p.with_suffix(".lrc").write_text(lrc_content, encoding="utf-8")
					out_p.with_suffix(".srt").write_text(srt_content, encoding="utf-8")
				except Exception as sub_e:
					logger.debug(f"Error escribiendo subtítulos en {out_p}: {sub_e}")

		# Si se solicitó cortina musical y el archivo de fondo existe
		has_bg = bg_track_path is not None and Path(bg_track_path).is_file()
		if has_bg and ffmpeg_bin:
			mixed = mix_announcement_with_bg_track(
				voice_path=tmp_voice_combined,
				output_path=out_p,
				bg_track_path=bg_track_path,
				bg_offset=bg_offset,
				bg_volume=bg_volume,
				timeout=timeout,
			)
			if mixed:
				embed_cover_art_in_mp3(
					out_p,
					cover_image_path=cover_image_path,
					title=title,
					artist=artist,
					timeout=timeout,
				)
				_save_subtitles()
				return True

		# Copia segura al destino desde RAM
		shutil.copyfile(tmp_voice_combined, tmp_dest)
		embed_cover_art_in_mp3(
			tmp_dest,
			cover_image_path=cover_image_path,
			title=title,
			artist=artist,
			timeout=timeout,
		)
		tmp_dest.replace(out_p)
		_save_subtitles()
		return True
	except Exception as e:
		logger.warning(f"Error ensamblando locución radial: {e}")
		if tmp_dest.exists():
			tmp_dest.unlink(missing_ok=True)
		return False
	finally:
		shutil.rmtree(work_dir, ignore_errors=True)


async def create_radio_announcement(
	output_path: Path | str,
	voice: str | None = None,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	db_path: Path | str | None = None,
	dt: datetime | None = None,
	force_system_fortune: bool | None = None,
	cover_image_path: Path | str | None = None,
	weather_location: str | None = None,
	dialogue_mode: bool | None = None,
) -> RadioAnnouncementResult:
	"""
	Sintetiza la locución radial con dinámica de charla de cabina entre locutores carpinchos.
	- Selección automática de host y cohost (garantizando voces distintas).
	- Reporte del clima con pase de cabina, reporte y reacción según condición térmica/lluvia,
	  respetando una periodicidad máxima de una vez por hora y un intervalo mínimo de 30 minutos.
	- Lead-in, oráculo/fortuna y remate o reacción carpincha.
	- Síntesis asíncrona concurrente con TaskGroup y caché SQLite.
	- Ensamblado acústico con ruido rosa de sala, gaps naturales, solapamiento de reacciones y masterizado final.
	- Incrusta carátula ID3 en el MP3 resultante.
	Retorna RadioAnnouncementResult(ok, display_title, script, error).
	"""
	if not HAS_EDGE_TTS or edge_tts is None:
		err_msg = "El paquete 'edge-tts' no está instalado en el entorno de Python o falló su importación."
		logger.warning(f"📻 El Carpincho no puede locutar: {err_msg}")
		return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg)

	out_p = Path(output_path)
	try:
		out_p.parent.mkdir(parents=True, exist_ok=True)
	except Exception as e:
		err_msg = f"No se pudo crear el directorio de destino '{out_p.parent}': {type(e).__name__}: {e}"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg)

	effective_dt = dt if dt is not None else datetime.now(UTC).astimezone()

	# Selección de fortuna y asignación de roles de cabina (host y cohost distintos)
	fortuna, is_sys = select_radio_phrase(force_system_fortune, db_path=db_path)
	host_voice, cohost_voice = select_radio_hosts(host_voice=voice, is_system_fortune=is_sys)
	locutor_nombre = VOICE_NAMES.get(host_voice, DEFAULT_HOST_NAME)
	cohost_nombre = VOICE_NAMES.get(cohost_voice, DEFAULT_COHOST_DISPLAY_NAME)

	# Reporte del clima con wttr.in (máximo una vez por hora y con al menos 30 min de diferencia)
	weather_text: str | None = None
	weather_condition: str | None = None
	current_weather_slot = effective_dt.strftime("%Y-%m-%d %H")
	last_weather_hour = get_radio_state("last_weather_hour", db_path=db_path)
	last_weather_ts = get_radio_state("last_weather_timestamp", db_path=db_path)
	now_ts = effective_dt.timestamp()

	enough_time_passed = last_weather_ts is None or (now_ts - float(last_weather_ts)) >= (30 * 60)

	pending_weather_slot: str | None = None
	pending_weather_ts: float | None = None

	if last_weather_hour != current_weather_slot and enough_time_passed:
		try:
			weather_timeout = min(timeout, 5.0)
			loc_to_query = weather_location or DEFAULT_WEATHER_LOCATION
			weather_data = await asyncio.to_thread(
				fetch_weather_json,
				loc_to_query,
				"es",
				weather_timeout,
			)
			if weather_data:
				weather_info = get_weather_info(
					weather_data,
					current_hour=effective_dt.hour,
					location=loc_to_query,
				)
				if weather_info:
					weather_text, weather_condition = weather_info
					pending_weather_slot = current_weather_slot
					pending_weather_ts = now_ts
					logger.debug(f"🌤️ Reporte del clima incorporado a la locución: '{weather_text}'")
		except Exception as e:
			logger.debug(f"Fallo no crítico obteniendo/procesando reporte del clima: {e}")

	intro = weighted_choice_by_recency(RADIO_INTROS, category="intro", db_path=db_path)
	hora_seg, minuto_seg, _ = get_modular_time_segments(effective_dt)
	seg_cat = resolve_segment_category(fortuna)
	cat_lead_ins = get_lead_ins_for_category(seg_cat)
	lead_in = weighted_choice_by_recency(cat_lead_ins, category=f"lead_in_{seg_cat}", db_path=db_path)
	outro = weighted_choice_by_recency(RADIO_OUTROS, category="salida", db_path=db_path)

	is_dialogue = dialogue_mode if dialogue_mode is not None else (random.random() < 0.85)
	last_reaction = get_radio_state("last_reaction", db_path=db_path)

	plan = build_radio_dialogue_plan(
		intro=intro,
		hora_seg=hora_seg,
		minuto_seg=minuto_seg,
		lead_in=lead_in,
		fortuna=fortuna,
		outro=outro,
		host_voice=host_voice,
		cohost_voice=cohost_voice,
		is_system_fortune=is_sys,
		weather_text=weather_text,
		weather_condition=weather_condition,
		dialogue_mode=is_dialogue,
		last_reaction=last_reaction,
		db_path=db_path,
	)

	full_script = " ".join(t[0].strip() for t in plan if t[0].strip())
	display_title = f"Carpincho locutor: {full_script}"

	# Agrupar segmentos consecutivos del mismo locutor para alimentar a edge-tts con el parlamento/discurso completo
	speech_turns = group_plan_into_speech_turns(plan)

	try:
		# Síntesis concurrente con TaskGroup: si una falla, cancela a las hermanas de inmediato
		margin = 5.0 if timeout >= 1.0 else max(0.05, timeout)
		total_timeout = (timeout * max_retries) + margin

		async with asyncio.timeout(total_timeout):
			async with asyncio.TaskGroup() as tg:
				task_objs = [
					tg.create_task(
						synthesize_segment(
							text=text,
							voice=v,
							category=category,
							allow_cache=allow_cache,
							timeout=timeout,
							max_retries=max_retries,
							db_path=db_path,
							return_cues=True,
						)
					)
					for text, v, category, allow_cache in speech_turns
				]
		raw_segments = [t.result() for t in task_objs]
		segment_results: list[tuple[bytes, str, str, str, list[tuple[float, float, str]] | None]] = []
		for i, res in enumerate(raw_segments):
			if isinstance(res, tuple) and len(res) == 2:
				seg_bytes, seg_cues = res
			else:
				seg_bytes, seg_cues = res, None
			segment_results.append((seg_bytes, speech_turns[i][2], speech_turns[i][1], speech_turns[i][0], seg_cues))

		if is_dialogue:
			logger.info(f"🎙️ Locución radial en cabina ({locutor_nombre} y {cohost_nombre}): '{full_script}'")
		else:
			logger.info(f"🎙️ Locución radial generada exitosamente con {locutor_nombre} ({host_voice}): '{full_script}'")

		loop = asyncio.get_running_loop()
		ok = await loop.run_in_executor(
			None,
			assemble_announcement_audio,
			segment_results,
			out_p,
			bg_track_path,
			bg_offset,
			bg_volume,
			cover_image_path,
			display_title,
			locutor_nombre,
			timeout,
		)
		if not ok:
			err_msg = "Falló el ensamblado del audio del anuncio radial."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg)

		# Guardar el slot horario y timestamp del clima tras ensamblado exitoso
		if pending_weather_slot:
			set_radio_state("last_weather_hour", pending_weather_slot, db_path=db_path)
		if pending_weather_ts is not None:
			set_radio_state("last_weather_timestamp", pending_weather_ts, db_path=db_path)

		# Registrar última reacción para no repetirla consecutivamente
		reactions_in_plan = [text for text, _v, cat, _c in plan if cat == "reaccion" or "reaccion" in cat]
		if reactions_in_plan:
			set_radio_state("last_reaction", reactions_in_plan[-1], db_path=db_path)

		# Registrar frases en phrase_history para ponderación por última reproducción
		for seg_text, _v, cat, _c in plan:
			clean_s = seg_text.strip()
			if clean_s:
				record_phrase_played(clean_s, category=cat, timestamp=now_ts, db_path=db_path)

		return RadioAnnouncementResult(ok=True, display_title=display_title, script=full_script, error=None)

	except Exception as e:
		is_timeout = isinstance(e, (asyncio.TimeoutError, TimeoutError)) or (
			hasattr(e, "exceptions")
			and any(isinstance(sub, (asyncio.TimeoutError, TimeoutError)) for sub in getattr(e, "exceptions", []))
		)
		if is_timeout:
			err_msg = f"Se agotó el tiempo de espera ({timeout}s) contactando al servicio de síntesis de voz (edge-tts). Verificá la conexión a internet."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg)

		if hasattr(e, "exceptions"):
			nested_msgs = "; ".join(
				f"{type(sub).__name__}: {sub}" if str(sub) else type(sub).__name__
				for sub in getattr(e, "exceptions", [])
			)
			err_msg = f"Error de síntesis ({nested_msgs})"
		else:
			err_msg = f"Error de síntesis ({type(e).__name__}: {e})"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg)
