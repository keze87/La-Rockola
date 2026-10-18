"""
Procesamiento de lenguaje natural (NLP) criollo, validación de oraciones habladas,
filtros de listas negras y limpieza de fortunas en español para el Modo Radio.
"""

from __future__ import annotations

import logging
import math
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.domain.radio.banks import (
	AI_ROBOTIC_PHRASES,
	CARPINCHO_PHRASES,
	COMMON_ENGLISH_WORDS,
	COMMON_SPANISH_VERBS,
	COMMON_SPANISH_WORDS,
	FORBIDDEN_FORMAT_CHARS,
	KNOWN_SPANISH_DBS,
	LEAD_INS_BY_CATEGORY,
	PASES_A_CLIMA,
	PROFANITY_PHRASES,
	PROFANITY_TERMS,
	REACCIONES_BY_CATEGORY,
	REACCIONES_CLIMA,
	VERBAL_SUFFIXES_REGEX,
	RadioContext,
	RadioPhrase,
	expand_phrase_variants,
	filter_by_context,
	phrase_fits_context,
	render_phrase,
)

logger = logging.getLogger("RockolaCarpincho")

# Estado volátil en memoria para el locutor de radio
_RADIO_MEMORY_STATE: dict[str, Any] = {}
_PHRASE_HISTORY_MEMORY: dict[str, float] = {}
_RENDERED_TO_TEMPLATE_KEY: dict[str, str] = {}
_SPANISH_FORTUNE_DBS_CACHE: list[str] | None = None
_BUNDLED_FORTUNES_CACHE: list[str] | None = None


def get_radio_state(key: str, default: Any = None, db_path: Path | str | None = None) -> Any:
	"""Recupera un valor de estado en memoria del locutor de radio."""
	return _RADIO_MEMORY_STATE.get(key, default)


def set_radio_state(key: str, value: Any, db_path: Path | str | None = None) -> None:
	"""Almacena o actualiza un valor de estado en memoria del locutor de radio."""
	_RADIO_MEMORY_STATE[key] = value


def reset_radio_memory_state() -> None:
	"""Limpia el estado en memoria del locutor de radio."""
	_RADIO_MEMORY_STATE.clear()
	_PHRASE_HISTORY_MEMORY.clear()
	_RENDERED_TO_TEMPLATE_KEY.clear()


def _clean_phrase_text(text: str) -> str:
	return text.strip().strip("\"'«»").rstrip(".!?:;…").lower()


def _normalize_phrase_key(phrase: str | tuple[str, str] | RadioPhrase, category: str = "") -> str:
	if isinstance(phrase, (tuple, list)):
		phrase_text = phrase[0] if len(phrase) > 0 else ""
		if not category and len(phrase) > 1:
			category = str(phrase[1])
	else:
		phrase_text = str(phrase)
	cleaned = _clean_phrase_text(phrase_text)
	cleaned = _RENDERED_TO_TEMPLATE_KEY.get(cleaned, cleaned)
	return f"{category}:{cleaned}" if category else cleaned


def render_tracked_phrase(
	template: str,
	ctx: RadioContext | None = None,
	addressee_voice: str | None = None,
	cohost_name: str | None = None,
) -> str:
	"""Resuelve placeholders y recuerda de qué plantilla salió el texto para ponderar recencia."""
	rendered = render_phrase(template, ctx, addressee_voice=addressee_voice, cohost_name=cohost_name)
	if rendered != template:
		_RENDERED_TO_TEMPLATE_KEY[_clean_phrase_text(rendered)] = _clean_phrase_text(template)
	return rendered


def _same_phrase(spoken: str, template: str) -> bool:
	target = _clean_phrase_text(spoken)
	if target == _clean_phrase_text(template):
		return True
	if "{" in template:
		return any(_clean_phrase_text(v) == target for v in expand_phrase_variants(template))
	return False


def _find_pase_template(spoken: str) -> str | None:
	for tpl in PASES_A_CLIMA:
		if _same_phrase(spoken, tpl):
			return tpl
	return None


def get_phrase_last_played(
	phrase: str | tuple[str, str] | RadioPhrase,
	category: str = "",
	db_path: Path | str | None = None,
) -> float | None:
	"""Recupera la marca de tiempo en que una frase fue reproducida por última vez."""
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

	if category.startswith("lead_in_"):
		val = _PHRASE_HISTORY_MEMORY.get(_normalize_phrase_key(phrase_text, "lead_in"))
		if val is not None:
			return val
	elif category.startswith("reaccion_"):
		val = _PHRASE_HISTORY_MEMORY.get(_normalize_phrase_key(phrase_text, "reaccion"))
		if val is not None:
			return val
	elif category == "pase":
		tpl = _find_pase_template(phrase_text)
		if tpl is not None:
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

	if category == "lead_in" or category.startswith("lead_in_"):
		_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, "lead_in")] = ts
		for cat_name, cat_list in LEAD_INS_BY_CATEGORY.items():
			match = next((item for item in cat_list if _same_phrase(phrase_text, item)), None)
			if match is not None:
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(match, f"lead_in_{cat_name}")] = ts
				break
	elif category == "reaccion" or category.startswith("reaccion_"):
		_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(phrase_text, "reaccion")] = ts
		for cat_name, cat_list in REACCIONES_BY_CATEGORY.items():
			match = next((item for item in cat_list if _same_phrase(phrase_text, item)), None)
			if match is not None:
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(match, "reaccion")] = ts
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(match, f"reaccion_{cat_name}")] = ts
				break
		for clim_list in REACCIONES_CLIMA.values():
			match = next((item for item in clim_list if _same_phrase(phrase_text, item)), None)
			if match is not None:
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(match, "reaccion")] = ts
				_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(match, "reaccion_clima")] = ts
				break
	elif category == "pase":
		tpl = _find_pase_template(phrase_text)
		if tpl is not None:
			_PHRASE_HISTORY_MEMORY[_normalize_phrase_key(tpl, "pase")] = ts


def weighted_choice_by_recency(
	candidates: list[Any],
	category: str = "",
	db_path: Path | str | None = None,
	current_time: float | None = None,
	tau: float = 1800.0,
	min_weight: float = 0.02,
) -> Any:
	"""Selecciona una frase de la lista candidata ponderando por antigüedad de última reproducción."""
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


def is_spanish_text(text: str) -> bool:
	"""Determina con precisión y bajo costo computacional si un texto está en español."""
	if not text or not isinstance(text, str):
		return False

	words = [w.lower() for w in re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b", text)]
	if not words:
		return False

	spanish_hits = sum(1 for w in words if w in COMMON_SPANISH_WORDS)
	english_hits = sum(1 for w in words if w in COMMON_ENGLISH_WORDS)

	if english_hits > spanish_hits and english_hits >= 2:
		return False
	if english_hits >= 2 and spanish_hits == 0:
		return False
	if english_hits > 0 and len(words) <= 5 and spanish_hits == 0:
		return False

	if any(c in "ñÑ¿¡" for c in text) and english_hits <= 1:
		return True

	if spanish_hits >= 2 or (len(words) <= 4 and spanish_hits >= 1 and english_hits == 0):
		return True

	if english_hits == 0:
		if any(c in "áéíóúüÁÉÍÓÚÜ" for c in text) and len(words) >= 2:
			return True
		low = text.lower()
		if any(ng in low for ng in ("ción", "sión", "mente", "illo", "illa", "ante")):
			return True

	return False


def contains_blacklisted_content(text: str) -> bool:
	"""Verifica si el texto contiene términos prohibidos (vulgaridades o jerga robótica/IA)."""
	norm = text.lower()
	for phrase in AI_ROBOTIC_PHRASES:
		if phrase in norm:
			return True
	for phrase in PROFANITY_PHRASES:
		if phrase in norm:
			return True
	words = set(re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b", norm))
	return any(w in PROFANITY_TERMS for w in words)


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
	"""Determina si el texto es apto para ser locutado por radio como una oración completa."""
	if not text or not isinstance(text, str):
		return False

	clean = text.strip()
	if clean.startswith(("...", "…", ",", ";", ":", "-", "—", "–")):
		return False
	if clean.endswith((":", ";", ",", "-", "—", "–")):
		return False

	first_alpha = re.search(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", clean)
	if not first_alpha or first_alpha.group(0).islower():
		return False

	if any(c in clean for c in FORBIDDEN_FORMAT_CHARS):
		return False

	if re.match(r"^\s*(?:\d+[\.\)\-]|[a-zA-Z][\.\)]|[-*•])\s+", clean):
		return False

	if re.search(r"\b\d+[\.\)]\s+[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", clean):
		return False

	words = re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+\b", clean)
	if not (5 <= len(words) <= 88):
		return False

	clauses = [re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+\b", c) for c in re.split(r"[,;:\—–\n]+", clean) if c.strip()]
	if len(clauses) >= 3:
		short_clauses = sum(1 for c in clauses if 1 <= len(c) < 3)
		if short_clauses >= 3 or (len(clauses) >= 4 and short_clauses >= 2 and (short_clauses / len(clauses)) >= 0.5):
			return False

	if not has_conjugated_verb(words):
		return False

	return not contains_blacklisted_content(clean)


def is_tts_friendly_fortune(text: str) -> bool:
	"""Determina si una frase de la colección bundled de fortunas es apta para TTS."""
	if not text or not isinstance(text, str):
		return False

	clean = text.strip()
	words = re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]+\b", clean)
	if not (3 <= len(words) <= 120):
		return False

	if re.search(r"[/\\|_#=~*]{3,}|<{3,}|>{3,}|:{3,}", clean):
		return False

	letters = len(re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", clean))
	symbols = len(re.findall(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:¡!¿?\"'()—–-]", clean))
	if (letters + symbols) > 0 and (symbols / (letters + symbols)) > 0.15:
		return False

	has_spanish_exclusive = bool(re.search(r"[áéíóúüñÁÉÍÓÚÜÑ¿¡]", clean))
	if not has_spanish_exclusive:
		pure_en = {w for w in COMMON_ENGLISH_WORDS if w not in COMMON_SPANISH_WORDS and w not in {"no", "a", "me"}}
		lower_words = [w.lower() for w in words]
		en_matches = [w for w in lower_words if w in pure_en]
		if len(words) > 0 and (len(en_matches) / len(words) >= 0.35 or len(set(en_matches)) >= 3):
			return False

	return True


def clean_fortune_text(raw_text: str) -> str:
	"""
	Limpia el texto de una fortuna o cita de Unix:
	- Remueve líneas de firma de autor al final (-- Autor, — Autor, ~ Autor).
	- Elimina comillas dobles, simples y tipográficas (« » “ ” ‘ ’ " ' `).
	- Limpia saltos de línea y normaliza espacios en blanco.
	- Quita enlaces web (URLs), tags HTML, corchetes [...] y paréntesis bibliográficos.
	"""
	if not raw_text:
		return ""

	text = raw_text

	# 1. Quitar línea final de atribución de autor (ej. "\n  -- José Hernández")
	text = re.sub(r"(?:\r?\n)+\s*(?:--|—|~)\s*[^\r\n]+\s*$", "", text)

	# 2. Quitar URLs y enlaces web
	text = re.sub(r"https?://\S+|www\.\S+", "", text)

	# 3. Quitar etiquetas tipo HTML (<...>)
	text = re.sub(r"<[^>]+>", "", text)

	# 4. Quitar corchetes editoriales o bibliográficos: [...]
	text = re.sub(r"\[[^\]]*\]", "", text)

	# 5. Quitar paréntesis bibliográficos (años, fechas, tomos, páginas, referencias)
	text = re.sub(
		r"\([^)]*(?:\b\d{1,4}\b|siglo|pág|pag|ibid|op\.?\s*cit|ed\.?|vol\.?|cap\.?|trad\.?)[^)]*\)",
		"",
		text,
		flags=re.IGNORECASE,
	)

	# 6. Normalizar guiones dobles internos a raya
	text = re.sub(r"\s*(?:--|—|~)\s*", " — ", text)

	# 7. Eliminar comillas dobles, simples y tipográficas
	text = re.sub(r"[«»“”‘’\"'`]", "", text)

	# 8. Espacios antes de signos de puntuación
	text = re.sub(r"\s+([,.:;!?])", r"\1", text)

	# 9. Normalizar saltos de línea y espacios
	text = re.sub(r"\s+", " ", text).strip()

	# 10. Limpiar puntuación huérfana al inicio
	text = re.sub(r"^[.,;:—–\s]+", "", text).strip()

	# 11. Asegurar puntuación terminal
	if text and (text[-1].isalnum() or text[-1] in (")", "]")):
		text = f"{text}."

	return text


def get_available_spanish_dbs(timeout: float = 2.0) -> list[str]:
	"""Detecta y cachea las bases de datos en español disponibles para el comando fortune."""
	global _SPANISH_FORTUNE_DBS_CACHE
	if _SPANISH_FORTUNE_DBS_CACHE is not None:
		return _SPANISH_FORTUNE_DBS_CACHE

	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		_SPANISH_FORTUNE_DBS_CACHE = []
		return _SPANISH_FORTUNE_DBS_CACHE

	from app.infrastructure.binaries.manager import get_clean_env

	try:
		res = subprocess.run(
			[fortune_bin, "-f"],
			capture_output=True,
			text=True,
			timeout=timeout,
			check=False,
			env=get_clean_env(),
		)
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


def get_system_fortune(timeout: float = 2.0, max_attempts: int = 3) -> str | None:
	"""Intenta obtener una fortuna corta en español mediante el comando Unix `fortune -s`."""
	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		return None

	spanish_dbs = get_available_spanish_dbs(timeout=timeout)
	if not spanish_dbs:
		return None

	from app.infrastructure.binaries.manager import get_clean_env

	cmd = [fortune_bin, "-s"] + spanish_dbs
	for _ in range(max_attempts):
		try:
			res = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				timeout=timeout,
				check=False,
				env=get_clean_env(),
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


def get_bundled_fortunes_path(custom_path: Path | str | None = None) -> Path:
	"""Resuelve la ruta absoluta a la carpeta o archivo de fortunas en formato Unix %."""
	if custom_path:
		return Path(custom_path)
	if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
		for rel in (Path("app") / "domain" / "radio" / "fortune-es", Path("scripts") / "fortune-es"):
			candidate_dir = Path(sys._MEIPASS) / rel
			if candidate_dir.is_dir():
				return candidate_dir
	root_dir = Path(__file__).resolve().parents[3]
	for candidate in (
		Path(__file__).parent / "fortune-es",
		root_dir / "scripts" / "fortune-es",
		root_dir / "scripts" / "data" / "fortunes_es.txt",
	):
		if candidate.exists():
			return candidate
	return Path(__file__).parent / "fortune-es"


def load_bundled_fortunes(target: Path | str | None = None) -> list[str]:
	"""Carga y valida fortunas en formato Unix (delimitador %)."""
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
	"""Retorna una fortuna o cita célebre en español del banco propio bundled."""
	global _BUNDLED_FORTUNES_CACHE
	if _BUNDLED_FORTUNES_CACHE is None:
		_BUNDLED_FORTUNES_CACHE = load_bundled_fortunes()
	if not _BUNDLED_FORTUNES_CACHE:
		return None
	return weighted_choice_by_recency(_BUNDLED_FORTUNES_CACHE, category="fortuna_bundled", db_path=db_path)


def select_radio_phrase(
	force_system_fortune: bool | None = None,
	db_path: Path | str | None = None,
	ctx: RadioContext | None = None,
) -> tuple[RadioPhrase, bool]:
	"""Selecciona una frase o fortuna radial explícita (RadioPhrase, es_del_sistema)."""
	if force_system_fortune is not False and (force_system_fortune is True or random.random() < 1 / 6):
		sys_fort = get_system_fortune()
		if sys_fort and is_spanish_text(sys_fort) and phrase_fits_context(sys_fort, ctx):
			return RadioPhrase(sys_fort, "fortuna"), True
		bundled = get_bundled_fortune(db_path=db_path)
		if bundled and is_spanish_text(bundled) and phrase_fits_context(bundled, ctx):
			return RadioPhrase(bundled, "fortuna"), True

	pool = filter_by_context(CARPINCHO_PHRASES, ctx)
	chosen = weighted_choice_by_recency(pool, category="fortuna", db_path=db_path)
	return chosen, False


def select_fortune(
	force_system_fortune: bool | None = None,
	db_path: Path | str | None = None,
	ctx: RadioContext | None = None,
) -> tuple[str, bool]:
	"""Selecciona una fortuna garantizada en español y retorna (texto_fortuna, es_del_sistema)."""
	phrase, is_sys = select_radio_phrase(force_system_fortune=force_system_fortune, db_path=db_path, ctx=ctx)
	return phrase.text, is_sys


def get_radio_fortune(db_path: Path | str | None = None, ctx: RadioContext | None = None) -> str:
	"""Devuelve una frase o fortuna garantizada en español."""
	fortuna, _ = select_fortune(db_path=db_path, ctx=ctx)
	return fortuna
