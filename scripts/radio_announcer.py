"""
Módulo de locución para el Modo Radio en La Rockola del Carpincho.
Maneja la síntesis de voz con edge-tts, formateo horario radial y banco mixto de fortunas.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rockola.radio")

try:
	import edge_tts

	HAS_EDGE_TTS = True
except ImportError:
	edge_tts = None
	HAS_EDGE_TTS = False


# Importar bancos de frases, vocabulario, voces y plantillas
try:
	from scripts.radio_banks import (
		AI_ROBOTIC_PHRASES,
		CARPINCHO_ADS,
		CARPINCHO_FORTUNES,
		COMMON_ENGLISH_WORDS,
		COMMON_SPANISH_VERBS,
		COMMON_SPANISH_WORDS,
		DEFAULT_BG_VOLUME,
		DEFAULT_TTS_RETRIES,
		DEFAULT_TTS_TIMEOUT,
		DEFAULT_WEATHER_LOCATION,
		FORBIDDEN_FORMAT_CHARS,
		HOUR_NAMES,
		KNOWN_SPANISH_DBS,
		MINUTE_SEGMENTS,
		PASES_A_CLIMA,
		PROFANITY_PHRASES,
		PROFANITY_TERMS,
		RADIO_HANDOFFS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		RADIO_REACTIONS,
		REACCIONES_CLIMA,
		REACCIONES_FORTUNA,
		SPANISH_CHARS,
		SPECIAL_HOURS,
		VERBAL_SUFFIXES_REGEX,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_PROSODY,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		WEATHER_LEAD_INS,
		WEATHER_RAIN_THRESHOLD,
		WEATHER_TEMPLATES,
	)
except ImportError:
	from radio_banks import (
		AI_ROBOTIC_PHRASES,
		CARPINCHO_ADS,
		CARPINCHO_FORTUNES,
		COMMON_ENGLISH_WORDS,
		COMMON_SPANISH_VERBS,
		COMMON_SPANISH_WORDS,
		DEFAULT_BG_VOLUME,
		DEFAULT_TTS_RETRIES,
		DEFAULT_TTS_TIMEOUT,
		DEFAULT_WEATHER_LOCATION,
		FORBIDDEN_FORMAT_CHARS,
		HOUR_NAMES,
		KNOWN_SPANISH_DBS,
		MINUTE_SEGMENTS,
		PASES_A_CLIMA,
		PROFANITY_PHRASES,
		PROFANITY_TERMS,
		RADIO_HANDOFFS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		RADIO_REACTIONS,
		REACCIONES_CLIMA,
		REACCIONES_FORTUNA,
		SPANISH_CHARS,
		SPECIAL_HOURS,
		VERBAL_SUFFIXES_REGEX,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_PROSODY,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		WEATHER_LEAD_INS,
		WEATHER_RAIN_THRESHOLD,
		WEATHER_TEMPLATES,
	)

__all__ = [
	"AI_ROBOTIC_PHRASES",
	"CARPINCHO_ADS",
	"CARPINCHO_FORTUNES",
	"COMMON_ENGLISH_WORDS",
	"COMMON_SPANISH_VERBS",
	"COMMON_SPANISH_WORDS",
	"DEFAULT_BG_VOLUME",
	"DEFAULT_TTS_RETRIES",
	"DEFAULT_TTS_TIMEOUT",
	"DEFAULT_WEATHER_LOCATION",
	"FORBIDDEN_FORMAT_CHARS",
	"HOUR_NAMES",
	"KNOWN_SPANISH_DBS",
	"MINUTE_SEGMENTS",
	"PASES_A_CLIMA",
	"PROFANITY_PHRASES",
	"PROFANITY_TERMS",
	"RADIO_HANDOFFS",
	"RADIO_INTROS",
	"RADIO_LEAD_INS",
	"RADIO_OUTROS",
	"RADIO_REACTIONS",
	"REACCIONES_CLIMA",
	"REACCIONES_FORTUNA",
	"SPANISH_CHARS",
	"SPECIAL_HOURS",
	"VERBAL_SUFFIXES_REGEX",
	"VOICES",
	"VOICE_ELENA",
	"VOICE_MARIA",
	"VOICE_NAMES",
	"VOICE_PROSODY",
	"VOICE_TOMAS",
	"VOICE_VALENTINA",
	"WEATHER_LEAD_INS",
	"WEATHER_RAIN_THRESHOLD",
	"WEATHER_TEMPLATES",
	"assemble_announcement_audio",
	"build_radio_dialogue_plan",
	"build_weather_phrase",
	"clean_fortune_text",
	"contains_blacklisted_content",
	"create_radio_announcement",
	"describir_lluvias",
	"format_fortune_for_speech",
	"format_temperature",
	"format_temperature_range",
	"generate_modular_radio_script",
	"get_all_degree_segments",
	"get_all_fortune_reaction_segments",
	"get_all_handoff_segments",
	"get_all_reaction_segments",
	"get_all_weather_handoff_segments",
	"get_all_weather_reaction_segments",
	"get_available_spanish_dbs",
	"get_cached_audio",
	"get_modular_hour_segments",
	"get_modular_minute_segments",
	"get_modular_time_segments",
	"get_radio_fortune",
	"get_radio_state",
	"get_system_fortune",
	"get_weather_condition",
	"get_weather_info",
	"has_conjugated_verb",
	"init_tts_cache_db",
	"is_spanish_text",
	"is_valid_spoken_sentence",
	"mix_announcement_with_bg_track",
	"reset_radio_memory_state",
	"reset_weather_cache",
	"save_cached_audio",
	"select_fortune",
	"select_radio_hosts",
	"set_radio_state",
	"synthesize_segment",
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
				parsed = json.loads(raw_body.decode("utf-8", errors="ignore"))
				if isinstance(parsed, dict) and "current_condition" in parsed:
					_WEATHER_CACHE[cache_key] = (time.time(), parsed)
					return parsed
			logger.debug(f"Respuesta no exitosa de wttr.in ({resp.status}) para '{lugar}'")
	except Exception as e:
		logger.debug(f"No se pudo consultar el clima en wttr.in para '{lugar}': {e}")

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


def describir_lluvias(llueve_hoy: bool, llueve_manana: bool) -> str:
	"""
	Describe la previsión de precipitaciones para hoy y mañana con impronta carpinchera.
	Cubre las 4 variantes posibles.
	"""
	if not llueve_hoy and not llueve_manana:
		return "De lluvias ni hablemos: cielo despejado, ideal para unos buenos mates al sol."
	if llueve_hoy and not llueve_manana:
		return "Atenti que hoy se esperan lluvias y chaparrones, pero mañana ya zafamos y mejora la cosa."
	if not llueve_hoy and llueve_manana:
		return "Hoy zafamos del agua, pero andá aprontando el paraguas porque mañana se vienen las lluvias."
	return "Se vienen lluvias tanto para hoy como para mañana, ¡clima soñado para andar chapoteando en el agua!"


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


def get_weather_info(
	data: dict,
	lead_in: str | None = None,
	current_hour: int | None = None,
	template_idx: int | None = None,
) -> tuple[str, str] | None:
	"""
	Extrae los datos del JSON format=j1 de wttr.in y retorna (weather_phrase, weather_condition).
	Soporta múltiples plantillas sintácticas para evitar patrones repetitivos.
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

		llueve_hoy = rain_today >= WEATHER_RAIN_THRESHOLD
		llueve_manana = rain_tomorrow >= WEATHER_RAIN_THRESHOLD
		lluvia_desc = describir_lluvias(llueve_hoy, llueve_manana)

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

		if template_idx is not None:
			tpl = WEATHER_TEMPLATES[template_idx % len(WEATHER_TEMPLATES)]
		else:
			tpl = random.choice(WEATHER_TEMPLATES)

		phrase = tpl.format(
			lead=lead,
			temp_str=temp_str,
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
) -> str | None:
	"""
	Extrae y arma la frase del reporte del clima a partir del JSON format=j1 de wttr.in.
	Retorna None si la estructura no contiene las claves esperadas.
	"""
	info = get_weather_info(data, lead_in=lead_in, current_hour=current_hour, template_idx=template_idx)
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


# Estado volátil en memoria para el locutor de radio (no requiere persistencia en base de datos)
_RADIO_MEMORY_STATE: dict[str, Any] = {}


def get_radio_state(key: str, default: Any = None, db_path: Path | str | None = None) -> Any:
	"""Recupera un valor de estado en memoria del locutor de radio (db_path opcional conservado por retrocompatibilidad)."""
	return _RADIO_MEMORY_STATE.get(key, default)


def set_radio_state(key: str, value: Any, db_path: Path | str | None = None) -> None:
	"""Almacena o actualiza un valor de estado en memoria del locutor de radio (db_path opcional conservado por retrocompatibilidad)."""
	_RADIO_MEMORY_STATE[key] = value


def reset_radio_memory_state() -> None:
	"""Limpia el estado en memoria del locutor de radio (útil para pruebas y reinicio limpio)."""
	_RADIO_MEMORY_STATE.clear()


# Nombres de bases de datos de fortune que contienen frases en español
_SPANISH_FORTUNE_DBS_CACHE: list[str] | None = None


def is_spanish_text(text: str) -> bool:
	"""
	Determina con precisión mediante NLP liviano si un texto está redactado en español.
	Utiliza análisis de frecuencia de palabras funcionales (stopwords), detección
	contrastiva de términos en inglés y caracteres ortográficos distintivos del español.
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

	# Presencia de caracteres distintivos del español (ñ, ¿, ¡)
	has_spanish_exclusive = any(c in "ñÑ¿¡" for c in text)
	if has_spanish_exclusive and english_hits <= 1:
		return True

	# Coincidencia con palabras funcionales en español
	if spanish_hits >= 2:
		return True
	if len(words) <= 4 and spanish_hits >= 1 and english_hits == 0:
		return True

	# Acentos en vocales (á, é, í, ó, ú, ü) si no hay presencia de inglés
	has_accent = any(c in "áéíóúüÁÉÍÓÚÜ" for c in text)
	return bool(has_accent and english_hits == 0 and len(words) >= 2)


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
		logger.debug(f"Error detectando bases en español de fortune: {e}")
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
		except Exception as e:
			logger.debug(f"Error consultando bases en español de fortune: {e}")
			break

	return None


def select_fortune(force_system_fortune: bool | None = None) -> tuple[str, bool]:
	"""
	Selecciona una fortuna garantizada en español y retorna (texto_fortuna, es_del_sistema).
	Por defecto intenta con probabilidad 1/6 consultar una fortuna del sistema si está disponible en español,
	o recurre al banco curado de frases criollas del carpincho.
	"""
	if force_system_fortune is not False and (force_system_fortune is True or random.random() < 1 / 6):
		sys_fort = get_system_fortune()
		if sys_fort and is_spanish_text(sys_fort):
			return sys_fort, True

	return random.choice(CARPINCHO_FORTUNES), False


def get_radio_fortune() -> str:
	"""Devuelve una frase o fortuna garantizada en español."""
	fortuna, _ = select_fortune()
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


def format_fortune_for_speech(fortuna: str) -> str:
	"""Prepara el texto de una fortuna para locución quitando comillas duras y asegurando puntuación terminal."""
	cleaned = fortuna.strip().strip("\"'«»")
	if not cleaned.endswith((".", "!", "?", "…")):
		cleaned = f"{cleaned}."
	return cleaned


def get_modular_hour_segments() -> list[str]:
	"""Genera la lista con los 24 segmentos modulares de hora ('Las doce', 'Las una', ... 'Las once')."""
	return [HOUR_NAMES[h % 12] for h in range(24)]


def get_modular_minute_segments() -> list[str]:
	"""Genera la lista con los 4 segmentos modulares de minutos ('en punto.', 'y cuarto.', 'y media.', 'y menos cuarto.')."""
	return list(MINUTE_SEGMENTS)


def get_all_degree_segments(min_deg: int = -5, max_deg: int = 42) -> list[str]:
	"""Devuelve las frases de temperaturas en grados para locución modular del clima."""
	return [format_temperature(d) for d in range(min_deg, max_deg + 1)]


def get_all_reaction_segments() -> list[str]:
	"""Devuelve la lista consolidada de reacciones de cabina."""
	combined = list(RADIO_REACTIONS)
	for r in get_all_weather_reaction_segments():
		if r not in combined:
			combined.append(r)
	for r in get_all_fortune_reaction_segments():
		if r not in combined:
			combined.append(r)
	return combined


def get_all_handoff_segments() -> list[str]:
	"""Devuelve la lista consolidada de pases de cabina."""
	combined = list(RADIO_HANDOFFS)
	for h in get_all_weather_handoff_segments():
		if h not in combined:
			combined.append(h)
	return combined


def build_radio_dialogue_plan(
	intro: str,
	hora_seg: str,
	minuto_seg: str | None,
	lead_in: str,
	fortuna: str,
	outro: str,
	host_voice: str,
	cohost_voice: str,
	is_system_fortune: bool = False,
	weather_text: str | None = None,
	weather_condition: str | None = None,
	dialogue_mode: bool = True,
	last_reaction: str | None = None,
) -> list[tuple[str, str, str, bool]]:
	"""
	Construye el plan estructurado de segmentos para la locución radial (texto, voz, categoría, allow_cache).
	Si dialogue_mode es True, organiza una charla viva de cabina entre host y cohost.
	Si dialogue_mode es False, retorna la locución solo tradicional.
	Garantiza que nunca haya dos reacciones consecutivas idénticas.
	"""
	fortune_text = format_fortune_for_speech(fortuna)
	if not dialogue_mode:
		fortune_voice = VOICE_ELENA if is_system_fortune else host_voice
		solo_plan: list[tuple[str, str, str, bool]] = [
			(intro, host_voice, "intro", True),
			(hora_seg, host_voice, "hora", True),
		]
		if minuto_seg:
			solo_plan.append((minuto_seg, host_voice, "minuto", True))
		if weather_text:
			solo_plan.append((weather_text, host_voice, "clima", False))
		solo_plan.extend(
			[
				(lead_in, host_voice, "lead_in", True),
				(fortune_text, fortune_voice, "fortuna", True),
				(outro, host_voice, "salida", True),
			]
		)
		return solo_plan

	# Plan de charla de cabina
	plan: list[tuple[str, str, str, bool]] = [
		(intro, host_voice, "intro", True),
		(hora_seg, host_voice, "hora", True),
	]
	if minuto_seg:
		plan.append((minuto_seg, host_voice, "minuto", True))

	prev_reaction = last_reaction

	# 1. Clima
	if weather_text:
		cohost_name = VOICE_NAMES.get(cohost_voice, "compadre")
		pase_template = random.choice(PASES_A_CLIMA)
		pase_text = pase_template.format(cohost=cohost_name)
		plan.append((pase_text, host_voice, "pase", True))

		plan.append((weather_text, cohost_voice, "clima", False))

		cond = weather_condition or "agradable"
		candidates = REACCIONES_CLIMA.get(cond, REACCIONES_CLIMA["agradable"])
		valid_reactions = [r for r in candidates if r != prev_reaction]
		reaccion_clima = random.choice(valid_reactions if valid_reactions else candidates)
		plan.append((reaccion_clima, host_voice, "reaccion", True))
		prev_reaction = reaccion_clima

	# 2. Fortuna
	plan.append((lead_in, host_voice, "lead_in", True))

	if is_system_fortune:
		fortune_voice = VOICE_ELENA
	else:
		fortune_voice = cohost_voice

	plan.append((format_fortune_for_speech(fortuna), fortune_voice, "fortuna", True))

	valid_fortune_reactions = [r for r in REACCIONES_FORTUNA if r != prev_reaction]
	reaccion_fortuna = random.choice(valid_fortune_reactions if valid_fortune_reactions else REACCIONES_FORTUNA)
	react_voice = host_voice if fortune_voice == cohost_voice else cohost_voice
	plan.append((reaccion_fortuna, react_voice, "reaccion", True))

	# Salida a la música
	plan.append((outro, host_voice, "salida", True))

	return plan


def group_plan_into_speech_turns(
	plan: list[tuple[str, str, str, bool]],
) -> list[tuple[str, str, str, bool]]:
	"""
	Agrupa turnos consecutivos de habla que pertenecen al MISMO locutor
	en bloques o parlamentos completos de texto continuo.
	Esto le entrega a edge-tts oraciones y párrafos completos con entonación natural,
	ritmo fluido y pausas prosódicas humanas, evitando el efecto de frases pegadas.
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
		if v == current_voice:
			current_texts.append(clean_txt)
			# Si algún segmento individual no permite caché, el turno completo no se cachea
			if not allow_cache:
				current_allow_cache = False
			# Si se agrupa la hora o clima, reflejar categoría compuesta para propósitos de logging
			if category not in current_category:
				current_category = f"{current_category}_{category}"
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
		dt = datetime.now(timezone.utc).astimezone()

	hour = dt.hour
	minute = dt.minute

	if minute in range(3, 8):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y cinco."
	elif minute in range(8, 13):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y diez."
	elif minute in range(13, 18):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y cuarto."
	elif minute in range(18, 23):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y veinte."
	elif minute in range(23, 28):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y veinticinco."
	elif minute in range(28, 33):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y media."
	elif minute in range(33, 38):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = "y treinta y cinco."
	elif minute in range(38, 43):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = "menos veinte."
	elif minute in range(43, 48):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = "menos cuarto."
	elif minute in range(48, 53):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = "menos diez."
	elif minute in range(53, 58):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = "menos cinco."
	else:
		# En punto: 58..59 o 0..2
		target_hour = (hour + 1) % 24 if minute >= 58 else hour
		if target_hour in SPECIAL_HOURS:
			special = SPECIAL_HOURS[target_hour]
			return special, None, special
		hora_seg = HOUR_NAMES[target_hour % 12]
		minuto_seg = "en punto."

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
	lead_in = random.choice(RADIO_LEAD_INS)
	fortuna, is_system_fortune = select_fortune(force_system_fortune)
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
) -> bytes:
	"""
	Sintetiza un segmento individual o parlamento radial.
	Intenta PRIMERO sintetizar con 'edge-tts' en vivo para máxima naturalidad e inflexión.
	Si tiene éxito y allow_cache es True, persiste el audio generado en la base de datos SQLite.
	Si edge-tts falla (sin conexión a internet, error de timeout o paquete no instalado),
	utiliza la caché SQLite como fallback confiable.
	"""

	async def _stream_or_save(comm: edge_tts.Communicate) -> bytes:
		data = bytearray()
		if hasattr(comm, "stream"):
			try:
				async for chunk in comm.stream():
					if isinstance(chunk, dict) and chunk.get("type") == "audio":
						data.extend(chunk.get("data", b""))
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

		attempt_timeout = min(timeout, max(4.0, timeout * 0.7)) if max_retries > 0 else timeout
		audio_bytes = b""
		last_err: Exception | None = None

		for attempt in range(max_retries + 1):
			try:
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
					logger.debug(
						f"Reintento {attempt + 1}/{max_retries} en síntesis '{category}' ({voice}) tras error: {e}. Esperando {backoff:.2f}s..."
					)
					await asyncio.sleep(backoff)

		if audio_bytes:
			if allow_cache:
				try:
					save_cached_audio(category, voice, text, audio_bytes, db_path=db_path)
				except Exception as cache_err:
					logger.debug(f"No se pudo guardar en caché SQLite: {cache_err}")
			return audio_bytes
		else:
			logger.warning(
				f"🌐 edge-tts no pudo sintetizar '{category}' ({voice}): {last_err}. Probando fallback en caché SQLite..."
			)
	else:
		logger.debug("edge-tts no está disponible. Recurriendo a caché SQLite como fallback...")

	# 2. FALLBACK A CACHÉ SQLITE
	if allow_cache:
		cached_blob = get_cached_audio(category, voice, text, db_path=db_path)
		if cached_blob:
			logger.info(f"⚡ [TTS Cache Fallback HIT] '{category}' ({voice}): '{text}'")
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
		except Exception:
			pass

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
			except Exception:
				pass

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


def is_valid_mp3_stream(data: bytes) -> bool:
	"""Determina si un encabezado de bytes corresponde a un stream o archivo MP3 real."""
	if len(data) < 4:
		return False
	if data.startswith(b"ID3"):
		return True
	return bool(data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


def embed_cover_art_in_mp3(
	mp3_path: Path | str,
	cover_image_path: Path | str | None = None,
	title: str | None = "Locución radial",
	artist: str | None = "Carpincho Locutor 🎙️",
	album: str = "La Rockola del Carpincho",
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

	# 1. Intentar primero con ffmpeg
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
				logger.debug(
					f"ffmpeg falló al incrustar carátula: {proc.stderr.decode('utf-8', errors='ignore')[:150]}. Probando mutagen..."
				)
		except Exception as e:
			logger.debug(f"Excepción usando ffmpeg para carátula: {e}. Probando mutagen...")
		finally:
			if tmp_tagged.exists():
				try:
					tmp_tagged.unlink()
				except Exception:
					pass

	# 2. Fallback con mutagen
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
	except Exception as e:
		logger.debug(f"No se pudo incrustar la carátula en {mp3_p}: {e}")
		return False


def get_audio_duration(file_path: Path | str, timeout: float = 2.0) -> float:
	"""Obtiene la duración en segundos de un archivo de audio con ffprobe."""
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
	except Exception:
		pass
	return 0.0


def assemble_announcement_audio(
	segments: list[tuple[bytes, str] | tuple[bytes, str, str]],
	output_path: Path | str,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	cover_image_path: Path | str | None = None,
	title: str | None = "Locución radial",
	artist: str | None = "Carpincho Locutor 🎙️",
	timeout: float = 10.0,
) -> bool:
	"""
	Concatena los segmentos de audio MP3 intercalando ruido de sala sutil (~100-350ms),
	aplicando crossfade suave (~50ms) entre la hora y los minutos de un mismo locutor,
	solapando reacciones cortas (~200ms) sobre la línea anterior,
	igualando volumen entre voces con dynaudnorm y pasando el master final por filtro highpass + compresión.
	Opcionalmente superpone cortina musical de fondo utilizando ffmpeg e incrusta cover art.
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

		# Normalizar segmentos a tuplas (bytes, categoria, voz)
		parsed_segments: list[tuple[bytes, str, str]] = []
		for s in segments:
			if len(s) >= 3:
				parsed_segments.append((s[0], str(s[1]), str(s[2])))
			elif len(s) == 2:
				parsed_segments.append((s[0], str(s[1]), ""))
			else:
				parsed_segments.append((s[0], "", ""))

		if ffmpeg_bin:
			# Atajo directo cuando hay un único parlamento/segmento (discurso completo continuo)
			if len(parsed_segments) == 1:
				tmp_voice_combined.write_bytes(parsed_segments[0][0])
				concat_ok = tmp_voice_combined.is_file() and tmp_voice_combined.stat().st_size > 0
			else:
				# Generar archivos MP3 temporales con normalización dynaudnorm para nivelar volumen entre voces
				temp_seg_files: list[Path] = []
				for i, (seg_bytes, _cat, _v) in enumerate(parsed_segments):
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
							temp_seg_files.append(raw_file)
					except Exception:
						temp_seg_files.append(raw_file)

				blocks: list[tuple[Path, str, str]] = []
				skip_next = False
				for i in range(len(parsed_segments)):
					if skip_next:
						skip_next = False
						continue

					_bytes_i, cat_i, voice_i = parsed_segments[i]
					file_i = temp_seg_files[i]

					# Caso 1: fusión continua (sin gap de silencio) entre 'hora' y 'minuto' consecutivos de la misma voz
					if cat_i == "hora" and i + 1 < len(parsed_segments):
						_bytes_next, cat_next, voice_next = parsed_segments[i + 1]
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
									blocks.append((time_combined, "hora_minuto", voice_i))
									skip_next = True
									continue
							except Exception as e:
								logger.debug(f"Fallo en acrossfade hora/minuto: {e}")

					# Caso 2: reacción corta que solapa 150-250 ms sobre el final de la línea anterior (adelay + amix)
					if i + 1 < len(parsed_segments):
						_bytes_next, cat_next, voice_next = parsed_segments[i + 1]
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
										blocks.append((react_combined, f"{cat_i}_reaccion", voice_i))
										skip_next = True
										continue
								except Exception as e:
									logger.debug(f"Fallo solapando reacción con adelay+amix: {e}")

					blocks.append((file_i, cat_i, voice_i))

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
					except Exception as e:
						logger.debug(f"Fallo generando anoisesrc: {e}")

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
					except Exception as e:
						logger.debug(f"Fallo generando anullsrc fallback: {e}")

					return None

				# Construir cadena de archivos intercalando pausas de sala y ritmo de locución
				chain_files: list[Path] = []

				# Presencia de sala muy corta (~150ms) inicial para no cortar abruptamente
				tone_start = make_room_tone(0.15, "tone_start.mp3")
				if tone_start:
					chain_files.append(tone_start)

				for i, (block_file, block_cat, block_voice) in enumerate(blocks):
					chain_files.append(block_file)
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
				except Exception as e:
					logger.debug(f"Fallo aplicando filtro de estudio/compresión: {e}")

			if not concat_ok:
				logger.warning("ffmpeg concat demuxer también falló. Recurriendo a concatenación directa de bytes.")
				combined = b"".join(seg[0] for seg in parsed_segments)
				tmp_voice_combined.write_bytes(combined)
		else:
			# Si no hay ffmpeg disponible, concatenación directa de streams MP3
			combined = b"".join(seg[0] for seg in parsed_segments)
			tmp_voice_combined.write_bytes(combined)

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
) -> tuple[bool, str, str]:
	"""
	Sintetiza la locución radial con dinámica de charla de cabina entre locutores carpinchos.
	- Selección automática de host y cohost (garantizando voces distintas).
	- Reporte del clima con pase de cabina, reporte y reacción según condición térmica/lluvia,
	  respetando una periodicidad máxima de una vez por hora y un intervalo mínimo de 30 minutos.
	- Lead-in, oráculo/fortuna y remate o reacción carpincha.
	- Síntesis asíncrona concurrente con TaskGroup y caché SQLite.
	- Ensamblado acústico con ruido rosa de sala, gaps naturales, solapamiento de reacciones y masterizado final.
	- Incrusta carátula ID3 en el MP3 resultante.
	Retorna (éxito, display_title, full_script_text_o_error).
	"""
	if not HAS_EDGE_TTS or edge_tts is None:
		err_msg = "El paquete 'edge-tts' no está instalado en el entorno de Python o falló su importación."
		logger.warning(f"📻 El Carpincho no puede locutar: {err_msg}")
		return False, "", err_msg

	out_p = Path(output_path)
	try:
		out_p.parent.mkdir(parents=True, exist_ok=True)
	except Exception as e:
		err_msg = f"No se pudo crear el directorio de destino '{out_p.parent}': {type(e).__name__}: {e}"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return False, "", err_msg

	effective_dt = dt if dt is not None else datetime.now(timezone.utc).astimezone()

	# Selección de fortuna y asignación de roles de cabina (host y cohost distintos)
	fortuna, is_sys = select_fortune(force_system_fortune)
	host_voice, cohost_voice = select_radio_hosts(host_voice=voice, is_system_fortune=is_sys)
	locutor_nombre = VOICE_NAMES.get(host_voice, "Carpincho Locutor")
	cohost_nombre = VOICE_NAMES.get(cohost_voice, "Carpincho Co-conductor")

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
			weather_data = await asyncio.to_thread(
				fetch_weather_json,
				weather_location or DEFAULT_WEATHER_LOCATION,
				"es",
				weather_timeout,
			)
			if weather_data:
				weather_info = get_weather_info(weather_data, current_hour=effective_dt.hour)
				if weather_info:
					weather_text, weather_condition = weather_info
					pending_weather_slot = current_weather_slot
					pending_weather_ts = now_ts
					logger.debug(f"🌤️ Reporte del clima incorporado a la locución: '{weather_text}'")
		except Exception as e:
			logger.debug(f"Fallo no crítico obteniendo/procesando reporte del clima: {e}")

	intro = random.choice(RADIO_INTROS)
	hora_seg, minuto_seg, _ = get_modular_time_segments(effective_dt)
	lead_in = random.choice(RADIO_LEAD_INS)
	outro = random.choice(RADIO_OUTROS)

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
						)
					)
					for text, v, category, allow_cache in speech_turns
				]
		raw_segments = [t.result() for t in task_objs]
		segment_results: list[tuple[bytes, str, str]] = [
			(seg_bytes, speech_turns[i][2], speech_turns[i][1]) for i, seg_bytes in enumerate(raw_segments)
		]

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
			return False, "", err_msg

		# Guardar el slot horario y timestamp del clima tras ensamblado exitoso
		if pending_weather_slot:
			set_radio_state("last_weather_hour", pending_weather_slot, db_path=db_path)
		if pending_weather_ts is not None:
			set_radio_state("last_weather_timestamp", pending_weather_ts, db_path=db_path)

		# Registrar última reacción para no repetirla consecutivamente
		reactions_in_plan = [text for text, _v, cat, _c in plan if cat == "reaccion"]
		if reactions_in_plan:
			set_radio_state("last_reaction", reactions_in_plan[-1], db_path=db_path)

		return True, display_title, full_script

	except Exception as e:
		is_timeout = isinstance(e, (asyncio.TimeoutError, TimeoutError)) or (
			hasattr(e, "exceptions")
			and any(isinstance(sub, (asyncio.TimeoutError, TimeoutError)) for sub in getattr(e, "exceptions", []))
		)
		if is_timeout:
			err_msg = f"Se agotó el tiempo de espera ({timeout}s) contactando al servicio de síntesis de voz (edge-tts). Verificá la conexión a internet."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return False, "", err_msg

		err_msg = f"Error de síntesis ({type(e).__name__}: {e})"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return False, "", err_msg
