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
from datetime import datetime, timezone
from pathlib import Path

# Añadir directorio raíz al sys.path para importar scripts y server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
	from scripts.radio_announcer import (
		CARPINCHO_FORTUNES,
		HAS_EDGE_TTS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		format_radio_time,
		get_cached_audio,
		init_tts_cache_db,
		synthesize_segment,
	)
except ImportError:
	from radio_announcer import (
		CARPINCHO_FORTUNES,
		HAS_EDGE_TTS,
		RADIO_INTROS,
		RADIO_LEAD_INS,
		RADIO_OUTROS,
		VOICE_ELENA,
		VOICE_MARIA,
		VOICE_NAMES,
		VOICE_TOMAS,
		VOICE_VALENTINA,
		VOICES,
		format_radio_time,
		get_cached_audio,
		init_tts_cache_db,
		synthesize_segment,
	)

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s - %(levelname)s - %(message)s",
	datefmt="%H:%M:%S",
)
logger = logging.getLogger("rockola.preload")


def format_hour_for_cache(dt: datetime) -> str:
	"""Formatea la hora de manera idéntica a como la construye el locutor radial."""
	raw = format_radio_time(dt)
	hora = raw[0].upper() + raw[1:]
	if not hora.endswith("."):
		hora += "."
	return hora


def collect_phrases(all_minutes: bool = False) -> list[tuple[str, str]]:
	"""
	Recolecta todas las frases a precargar estructuradas en tuplas (categoría, texto).
	"""
	items: list[tuple[str, str]] = []

	# 1. Intros
	for intro in RADIO_INTROS:
		items.append(("intro", intro))

	# 2. Conectores / Lead-ins
	for lead in RADIO_LEAD_INS:
		items.append(("lead_in", lead))

	# 3. Fortunas y propagandas carpinchas (con el formato de comillas que usa el locutor)
	for fort in CARPINCHO_FORTUNES:
		items.append(("fortuna", f"«{fort}»."))

	# 4. Salidas / Despedidas
	for outro in RADIO_OUTROS:
		items.append(("salida", outro))

	# 5. Horas
	added_hours: set[str] = set()
	if all_minutes:
		logger.info("⏰ Modo completo: generando las 1.440 combinaciones horarias posibles...")
		for h in range(24):
			for m in range(60):
				dt = datetime(2026, 1, 1, h, m, tzinfo=timezone.utc)
				formatted = format_hour_for_cache(dt)
				if formatted not in added_hours:
					added_hours.add(formatted)
					items.append(("hora", formatted))
	else:
		logger.info("⏰ Modo estándar: generando horarios en punto, y cuarto, y media, menos cuarto...")
		for h in range(24):
			for m in (0, 15, 30, 45):
				dt = datetime(2026, 1, 1, h, m, tzinfo=timezone.utc)
				formatted = format_hour_for_cache(dt)
				if formatted not in added_hours:
					added_hours.add(formatted)
					items.append(("hora", formatted))
		# Incluir la hora actual exacta
		now_dt = datetime.now(timezone.utc).astimezone()
		now_str = format_hour_for_cache(now_dt)
		if now_str not in added_hours:
			added_hours.add(now_str)
			items.append(("hora", now_str))

	return items


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
					timeout=8.0,
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
	all_minutes: bool = False,
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

	phrase_items = collect_phrases(all_minutes=all_minutes)
	total_combinations = len(phrase_items) * len(voices)
	logger.info(
		f"📋 Total de frases: {len(phrase_items)} | Voces: {len(voices)} ({', '.join(VOICE_NAMES.get(v, v) for v in voices)})"
	)
	logger.info(f"🎯 Total de clips a evaluar: {total_combinations}")

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
		"--all-minutes",
		action="store_true",
		help="Precargar las 1.440 combinaciones de minutos (por defecto precarga cuartos de hora: :00, :15, :30, :45).",
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
			all_minutes=args.all_minutes,
			concurrency=args.concurrency,
			delay=args.delay,
			max_retries=args.retries,
			db_path=target_db_path,
		)
	)


if __name__ == "__main__":
	main()
