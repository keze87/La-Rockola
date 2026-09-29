#!/usr/bin/env python3
"""
Script de precarga para la base de datos de caché de TTS en La Rockola del Carpincho.
Sintetiza y almacena en SQLite (tts_cache.db) los segmentos de audio modulares
(intros, horas, lead-ins, fortunas curadas y propagandas carpinchas, y salidas).

Características:
- Respeta los audios ya cacheados: si una frase ya existe para esa voz, se salta (cero red).
- Control de concurrencia y rate limit para no saturar los servidores de edge-tts.
- Reintentos automáticos con backoff exponencial ante fallos de conexión o timeout.
- Soporta las 4 voces disponibles (Tomás, Elena, María, Valentina).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import time
from pathlib import Path

# Añadir directorio raíz al sys.path para importar scripts y server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
	from scripts.binary_utils import is_internet_available
except ImportError:
	try:
		from binary_utils import is_internet_available
	except ImportError:

		def is_internet_available(timeout: float = 0.8) -> bool:
			return True


try:
	from scripts.radio_announcer import (
		CARPINCHO_FORTUNES,
		DEFAULT_TTS_TIMEOUT,
		HAS_EDGE_TTS,
		RADIO_HANDOFFS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		RADIO_REACTIONS,
		SPECIAL_HOURS,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		format_fortune_for_speech,
		get_all_degree_segments,
		get_all_fortune_reaction_segments,
		get_all_weather_handoff_segments,
		get_all_weather_reaction_segments,
		get_cached_audio,
		get_modular_hour_segments,
		get_modular_minute_segments,
		init_tts_cache_db,
		synthesize_segment,
	)
except ImportError:
	from radio_announcer import (
		CARPINCHO_FORTUNES,
		DEFAULT_TTS_TIMEOUT,
		HAS_EDGE_TTS,
		RADIO_HANDOFFS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		RADIO_REACTIONS,
		SPECIAL_HOURS,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		format_fortune_for_speech,
		get_all_degree_segments,
		get_all_fortune_reaction_segments,
		get_all_weather_handoff_segments,
		get_all_weather_reaction_segments,
		get_cached_audio,
		get_modular_hour_segments,
		get_modular_minute_segments,
		init_tts_cache_db,
		synthesize_segment,
	)

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s - %(levelname)s - %(message)s",
	datefmt="%H:%M:%S",
)
logger = logging.getLogger("rockola.preload")


def collect_phrases() -> list[tuple[str, str]]:
	"""
	Recolecta todas las frases a precargar estructuradas en tuplas (categoría, texto).
	Incluye:
	- Intros radiales
	- Conectores / Lead-ins
	- Fortunas y propagandas carpinchas (en texto plano sin comillas duras)
	- Salidas radiales
	- 24 Horas especiales (minuto 0 en punto con impronta carpincha)
	- 24 Segmentos de hora ("Las doce", "Las una", ... "Las once")
	- 4 Segmentos de cuartos de hora ("en punto.", "y cuarto.", "y media.", "y menos cuarto.")
	- Pases de cabina criollos y pases a clima personalizados con nombre de cohost
	- Reacciones de cabina criollas, reacciones climáticas por condición y de fortuna
	- Segmentos de temperatura en grados
	"""
	items: list[tuple[str, str]] = []

	# 1. Intros
	for intro in RADIO_INTROS:
		items.append(("intro", intro))

	# 2. Conectores / Lead-ins
	for lead in RADIO_LEAD_INS:
		items.append(("lead_in", lead))

	# 3. Fortunas y propagandas carpinchas (en texto plano sin comillas duras)
	for fort in CARPINCHO_FORTUNES:
		items.append(("fortuna", format_fortune_for_speech(fort)))

	# 4. Salidas / Despedidas
	for outro in RADIO_OUTROS:
		items.append(("salida", outro))

	# 5. Horas especiales (las 24 horas cuando el minuto es 0 en punto)
	for special in SPECIAL_HOURS.values():
		items.append(("hora", special))

	# 6. Segmentos modulares de horas (0 a 23) importados desde radio_announcer
	for hora_str in get_modular_hour_segments():
		items.append(("hora", hora_str))

	# 7. Segmentos modulares de minutos (1 a 59) importados desde radio_announcer
	for minuto_str in get_modular_minute_segments():
		items.append(("minuto", minuto_str))

	# 8. Pases de cabina criollos
	for handoff in RADIO_HANDOFFS:
		items.append(("pase", handoff))

	# 9. Pases a clima dirigidos al cohost
	for handoff_weather in get_all_weather_handoff_segments():
		items.append(("pase", handoff_weather))

	# 10. Reacciones de cabina criollas
	for reaction in RADIO_REACTIONS:
		items.append(("reaccion", reaction))

	# 11. Reacciones de cabina por condición de clima
	for reaction_weather in get_all_weather_reaction_segments():
		items.append(("reaccion", reaction_weather))

	# 12. Reacciones de cabina a la fortuna
	for reaction_fortune in get_all_fortune_reaction_segments():
		items.append(("reaccion", reaction_fortune))

	# 13. Segmentos de temperatura en grados
	for deg in get_all_degree_segments():
		items.append(("clima", deg))

	# Deduplicar manteniendo orden
	seen: set[tuple[str, str]] = set()
	unique_items: list[tuple[str, str]] = []
	for cat, txt in items:
		key = (cat, txt)
		if key not in seen:
			seen.add(key)
			unique_items.append((cat, txt))

	return unique_items


async def process_item(
	semaphore: asyncio.Semaphore,
	category: str,
	text: str,
	voice: str,
	db_path: Path,
	delay: float,
	max_retries: int,
	stats: dict[str, int],
) -> None:
	"""Procesa un segmento individual con verificación previa de caché, rate limit y reintentos."""
	voice_display = VOICE_NAMES.get(voice, voice)

	# 1. Chequeo de caché existente (sin llamar a la red)
	cached = get_cached_audio(category, voice, text, db_path=db_path)
	if cached is not None:
		stats["skipped"] += 1
		return

	async with semaphore:
		# Verificamos de nuevo dentro del semáforo por si otro hilo lo cargó
		cached = get_cached_audio(category, voice, text, db_path=db_path)
		if cached is not None:
			stats["skipped"] += 1
			return

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
				short_text = text if len(text) <= 50 else f"{text[:47]}..."
				logger.info(
					f"✨ [{stats['synthesized'] + stats['skipped']}] Guardado [{category}] ({voice_display}): {short_text}"
				)
				success = True
				break
			except Exception as e:
				if attempt < max_retries:
					wait_time = (2**attempt) + random.uniform(0.5, 1.5)
					logger.warning(
						f"⚠️ Reintentando [{attempt}/{max_retries}] para ({voice_display}) '{text[:30]}...' en {wait_time:.1f}s ({e})"
					)
					await asyncio.sleep(wait_time)
				else:
					logger.error(f"❌ Falló tras {max_retries} intentos ({voice_display}) '{text[:30]}...': {e}")
					stats["failed"] += 1

		# Pausa de cortesía para respetar los rate limits de Microsoft
		if success and delay > 0:
			await asyncio.sleep(delay)


async def run_preload(
	voices: list[str],
	concurrency: int = 2,
	delay: float = 0.25,
	max_retries: int = 3,
	db_path: Path | None = None,
) -> None:
	"""Orquesta la precarga de todos los elementos para las voces solicitadas."""
	if not HAS_EDGE_TTS:
		logger.error("❌ 'edge-tts' no está instalado en el entorno de Python.")
		return

	target_db = init_tts_cache_db(db_path)
	logger.info(f"🧉 Iniciando precarga de caché TTS en: {target_db}")

	phrase_items = collect_phrases()
	total_combinations = len(phrase_items) * len(voices)
	logger.info(
		f"📋 Total de frases: {len(phrase_items)} | Voces: {len(voices)} ({', '.join(VOICE_NAMES.get(v, v) for v in voices)})"
	)
	logger.info(f"🎯 Total de clips a evaluar: {total_combinations}")

	if not is_internet_available(timeout=0.8):
		logger.error("❌ No hay conexión a internet disponible. Abortando precarga de frases.")
		return

	semaphore = asyncio.Semaphore(max(1, concurrency))
	stats = {"skipped": 0, "synthesized": 0, "failed": 0}

	start_time = time.time()
	tasks = []
	for cat, text in phrase_items:
		for v in voices:
			task = asyncio.create_task(
				process_item(
					semaphore=semaphore,
					category=cat,
					text=text,
					voice=v,
					db_path=target_db,
					delay=delay,
					max_retries=max_retries,
					stats=stats,
				)
			)
			tasks.append(task)

	await asyncio.gather(*tasks)

	elapsed = time.time() - start_time
	db_size_mb = target_db.stat().st_size / (1024 * 1024) if target_db.exists() else 0.0

	logger.info("=" * 60)
	logger.info("🧉 ¡Precarga carpincha completada con éxito!")
	logger.info(f"⏱️ Tiempo total: {elapsed:.1f} segundos")
	logger.info(f"⏭️ Ya estaban en caché (salteados): {stats['skipped']}")
	logger.info(f"🎙️ Nuevos clips sintetizados y guardados: {stats['synthesized']}")
	logger.info(f"❌ Fallidos: {stats['failed']}")
	logger.info(f"💾 Tamaño de la base de datos de caché: {db_size_mb:.2f} MB ({target_db.name})")
	logger.info("=" * 60)


def main():
	parser = argparse.ArgumentParser(
		description="Precarga la base de datos de caché de TTS para el Carpincho Locutor.",
	)
	parser.add_argument(
		"--voices",
		type=str,
		default="all",
		help="Voces a precargar separadas por coma ('tomas', 'elena', 'maria', 'valentina' o 'all'). Default: all",
	)
	parser.add_argument(
		"--concurrency",
		type=int,
		default=2,
		help="Cantidad máxima de peticiones simultáneas a edge-tts (default: 2).",
	)
	parser.add_argument(
		"--delay",
		type=float,
		default=0.25,
		help="Pausa en segundos entre peticiones exitosas (default: 0.25).",
	)
	parser.add_argument(
		"--retries",
		type=int,
		default=3,
		help="Reintentos con backoff ante fallos de conexión (default: 3).",
	)
	parser.add_argument(
		"--db-path",
		type=str,
		default=None,
		help="Ruta personalizada a la base de datos tts_cache.db (opcional).",
	)

	args = parser.parse_args()

	# Resolver voces
	voice_map = {
		"tomas": VOICE_TOMAS,
		"elena": VOICE_ELENA,
		"maria": VOICE_MARIA,
		"valentina": VOICE_VALENTINA,
	}

	if args.voices.lower() == "all":
		selected_voices = list(VOICES)
	else:
		selected_voices = []
		for v in args.voices.split(","):
			key = v.strip().lower()
			if key in voice_map:
				selected_voices.append(voice_map[key])
			elif v.strip() in VOICES:
				selected_voices.append(v.strip())
			else:
				logger.warning(f"Voz '{v}' no reconocida. Opciones: {list(voice_map.keys())} o 'all'")

		if not selected_voices:
			selected_voices = list(VOICES)

	target_db_path = Path(args.db_path) if args.db_path else None

	asyncio.run(
		run_preload(
			voices=selected_voices,
			concurrency=args.concurrency,
			delay=args.delay,
			max_retries=args.retries,
			db_path=target_db_path,
		)
	)


if __name__ == "__main__":
	main()
