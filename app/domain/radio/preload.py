"""
Módulo de precarga en segundo plano para la caché de edge-tts.
Recolecta únicamente los segmentos de locución realmente utilizados por RadioService
con allow_cache=True, evitando generar frases muertas o combinaciones descartadas.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from app.domain.radio.classification import CARPINCHO_PHRASES
from app.domain.radio.dialogue import (
	get_all_fortune_reaction_segments,
	get_all_intro_segments,
	get_all_outro_segments,
	get_all_reaction_segments,
	get_all_time_segments,
	get_all_weather_handoff_segments,
	get_all_weather_reaction_segments,
)
from app.domain.radio.linguistics import (
	apply_rioplatense_tts_phonetics,
	format_fortune_for_speech,
)
from app.domain.radio.segments import RADIO_LEAD_INS
from app.domain.radio.templates import expand_phrase_variants
from app.domain.radio.voices import DEFAULT_TTS_TIMEOUT, VOICE_NAMES, VOICES
from app.infrastructure.binaries.manager import is_internet_available
from app.infrastructure.media.tts_cache import (
	HAS_EDGE_TTS,
	get_cache_key,
	init_tts_cache_db,
	prune_tts_cache_db,
	synthesize_segment,
)

logger = logging.getLogger("RockolaCarpincho")


def collect_preload_phrases() -> list[tuple[str, str]]:
	"""
	Recolecta todas las frases activas a precargar estructuradas en tuplas (categoría, texto).
	Incluye solo segmentos que se sintetizan con allow_cache=True en RadioService:
	- Intros radiales y separadores (con saludo y nombres expandidos)
	- Lead-ins de contenido (RADIO_LEAD_INS)
	- Frases carpinchas y fortunas catalogadas (CARPINCHO_PHRASES)
	- Salidas radiales (continuas, pausas, recreos, DJ y por categoría)
	- Locuciones horarias completas (SPECIAL_HOURS + HOUR_NAMES x MINUTE_SEGMENTS)
	- Pases a clima dirigidos al cohost (PASES_A_CLIMA)
	- Reacciones de cabina, de clima y de fortuna
	"""
	items: list[tuple[str, str]] = []

	for intro in get_all_intro_segments():
		items.append(("intro", intro))

	for lead in RADIO_LEAD_INS:
		for variant in expand_phrase_variants(lead):
			items.append(("lead_in", variant))

	for phrase in CARPINCHO_PHRASES:
		speech_phrase = format_fortune_for_speech(phrase.text)
		for variant in expand_phrase_variants(speech_phrase):
			items.append((phrase.category, variant))

	for outro in get_all_outro_segments():
		items.append(("salida", outro))

	for time_str in get_all_time_segments():
		items.append(("hora", time_str))

	for handoff_weather in get_all_weather_handoff_segments():
		items.append(("pase", handoff_weather))

	for reaction in get_all_reaction_segments():
		items.append(("reaccion", reaction))

	for reaction_weather in get_all_weather_reaction_segments():
		items.append(("reaccion", reaction_weather))

	for reaction_fortune in get_all_fortune_reaction_segments():
		items.append(("reaccion", reaction_fortune))

	seen: set[tuple[str, str]] = set()
	unique_items: list[tuple[str, str]] = []
	for cat, txt in items:
		phonetic_txt = apply_rioplatense_tts_phonetics(txt)
		key = (cat, phonetic_txt)
		if key not in seen:
			seen.add(key)
			unique_items.append((cat, phonetic_txt))

	return unique_items


def _load_existing_cache_keys(db_path: Path) -> set[str]:
	"""Obtiene todas las cache_key ya presentes en tts_cache en una única consulta."""
	if not db_path.exists():
		return set()
	with contextlib.closing(sqlite3.connect(db_path, timeout=5.0)) as conn:
		rows = conn.execute("SELECT cache_key FROM tts_cache").fetchall()
		return {row[0] for row in rows if row and row[0]}


async def _synthesize_one(
	semaphore: asyncio.Semaphore,
	category: str,
	text: str,
	voice: str,
	db_path: Path,
	delay: float,
	max_retries: int,
	stats: dict[str, int],
	quiet: bool,
) -> None:
	"""Sintetiza un segmento individual con límite de concurrencia y reintentos."""
	voice_display = VOICE_NAMES.get(voice, voice)
	async with semaphore:
		success = False
		for attempt in range(1, max_retries + 1):
			try:
				await synthesize_segment(
					text=text,
					voice=voice,
					category=category,
					allow_cache=True,
					timeout=DEFAULT_TTS_TIMEOUT,
					db_path=db_path,
				)
				stats["synthesized"] += 1
				if not quiet:
					short_text = text if len(text) <= 50 else f"{text[:47]}..."
					logger.info(
						f"✨ [{stats['synthesized'] + stats['skipped']}] Guardado [{category}] ({voice_display}): {short_text}"
					)
				success = True
				break
			except asyncio.CancelledError:
				raise
			except Exception as e:
				if attempt < max_retries:
					wait_time = (2**attempt) + random.uniform(0.5, 1.5)
					if not quiet:
						logger.warning(
							f"⚠️ Reintentando [{attempt}/{max_retries}] para ({voice_display}) '{text[:30]}...' en {wait_time:.1f}s ({e})"
						)
					await asyncio.sleep(wait_time)
				else:
					logger.warning(f"❌ Falló preload ({voice_display}) '{text[:30]}...': {e}")
					stats["failed"] += 1

		if success and delay > 0:
			await asyncio.sleep(delay)


async def run_tts_preload(
	voices: Sequence[str] | None = None,
	concurrency: int = 2,
	delay: float = 0.25,
	max_retries: int = 3,
	db_path: Path | str | None = None,
	max_entries: int = 9000,
	quiet: bool = False,
) -> dict[str, int]:
	"""
	Orquesta la precarga de todos los segmentos activos en segundo plano.
	Salta en una única consulta los elementos ya cacheados para minimizar E/S.
	"""
	stats: dict[str, int] = {"skipped": 0, "synthesized": 0, "failed": 0, "offline": 0}

	if not HAS_EDGE_TTS:
		if not quiet:
			logger.warning("⚠️ 'edge-tts' no está instalado; omitiendo precarga de caché TTS.")
		return stats

	has_net = await asyncio.to_thread(is_internet_available)
	if not has_net:
		stats["offline"] = 1
		if not quiet:
			logger.info("📡 Sin conexión a internet; omitiendo precarga TTS en segundo plano.")
		return stats

	target_voices = list(voices) if voices else list(VOICES)
	target_db = init_tts_cache_db(db_path)
	phrases = collect_preload_phrases()
	existing_keys = await asyncio.to_thread(_load_existing_cache_keys, target_db)

	pending: list[tuple[str, str, str]] = []
	for voice in target_voices:
		for category, text in phrases:
			key = get_cache_key(category, voice, text)
			if key in existing_keys:
				stats["skipped"] += 1
			else:
				pending.append((category, text, voice))

	if not pending:
		if not quiet:
			logger.info(f"🎙️ Caché TTS al día ({stats['skipped']} segmentos ya precargados).")
		return stats

	logger.info(
		f"🎙️ Precarga TTS en segundo plano: {len(pending)} segmentos nuevos por sintetizar ({stats['skipped']} ya en caché)."
	)

	semaphore = asyncio.Semaphore(max(1, concurrency))
	tasks = [
		asyncio.create_task(
			_synthesize_one(
				semaphore=semaphore,
				category=category,
				text=text,
				voice=voice,
				db_path=target_db,
				delay=delay,
				max_retries=max_retries,
				stats=stats,
				quiet=quiet,
			)
		)
		for category, text, voice in pending
	]

	try:
		await asyncio.gather(*tasks)
	except asyncio.CancelledError:
		for t in tasks:
			t.cancel()
		await asyncio.gather(*tasks, return_exceptions=True)
		raise

	if stats["synthesized"] > 0:
		await asyncio.to_thread(prune_tts_cache_db, max_entries=max_entries, db_path=target_db)

	logger.info(
		f"🎙️ Precarga TTS finalizada -> nuevos: {stats['synthesized']}, en caché: {stats['skipped']}, fallidos: {stats['failed']}."
	)
	return stats
