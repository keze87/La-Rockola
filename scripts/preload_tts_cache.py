#!/usr/bin/env python3
"""
Script de precarga manual para la base de datos de caché de TTS en La Rockola del Carpincho.
Delega en app.domain.radio.preload para compartir la misma lógica auditada que el servidor.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Añadir directorio raíz al sys.path para importar el paquete app
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.radio.preload import collect_preload_phrases, run_tts_preload
from app.domain.radio.voices import (
	VOICE_ELENA,
	VOICE_MARIA,
	VOICE_TOMAS,
	VOICE_VALENTINA,
	VOICES,
)
from app.infrastructure.media.tts_cache import init_tts_cache_db

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s - %(levelname)s - %(message)s",
	datefmt="%H:%M:%S",
)
logger = logging.getLogger("rockola.preload")


def collect_phrases() -> list[tuple[str, str]]:
	"""Recolecta todas las frases activas a precargar (alias compatible para CLI y tests)."""
	return collect_preload_phrases()


async def run_preload(
	voices: list[str],
	concurrency: int = 2,
	delay: float = 0.25,
	max_retries: int = 3,
	db_path: Path | None = None,
	max_entries: int = 9000,
) -> None:
	"""Orquesta la precarga CLI delegando en run_tts_preload y mostrando resumen en consola."""
	target_db = init_tts_cache_db(db_path)
	logger.info(f"🧉 Iniciando precarga de caché TTS en: {target_db}")
	start_time = time.time()

	stats = await run_tts_preload(
		voices=voices,
		concurrency=concurrency,
		delay=delay,
		max_retries=max_retries,
		db_path=target_db,
		max_entries=max_entries,
		quiet=False,
	)

	if stats.get("offline"):
		logger.error("❌ No hay conexión a internet disponible. Abortando precarga de frases.")
		return

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


def main() -> None:
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
	parser.add_argument(
		"--max-entries",
		type=int,
		default=9000,
		help="Capacidad máxima de la base de datos tts_cache.db (default: 9000).",
	)

	args = parser.parse_args()

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
			max_entries=args.max_entries,
		)
	)


if __name__ == "__main__":
	main()
