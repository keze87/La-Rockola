"""Tests para la auditoría de frases y precarga en segundo plano de edge-tts."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.radio.segments import WEATHER_LEAD_INS
from app.infrastructure.media.tts_cache import get_cache_key, init_tts_cache_db


def test_collect_preload_phrases_excludes_unused_segments() -> None:
	"""Verifica que collect_preload_phrases no genere frases muertas (clima, minuto, horas sueltas ni weather lead-ins)."""
	from app.domain.radio.preload import collect_preload_phrases

	items = collect_preload_phrases()
	assert len(items) > 1000

	categories = {cat for cat, _ in items}
	assert "clima" not in categories
	assert "minuto" not in categories

	texts_by_cat: dict[str, set[str]] = {}
	for cat, txt in items:
		assert "{" not in txt and "}" not in txt, f"Placeholder sin resolver en [{cat}]: {txt}"
		texts_by_cat.setdefault(cat, set()).add(txt)

	# No debe incluir horas modulares sueltas sin minutos ni WEATHER_LEAD_INS
	assert "Las tres" not in texts_by_cat.get("hora", set())
	for wl in WEATHER_LEAD_INS:
		assert wl not in texts_by_cat.get("lead_in", set())

	# Sí debe incluir combinaciones reales de hora y categorías activas
	assert "Las tres y cinco." in texts_by_cat.get("hora", set())
	for expected_cat in ("intro", "lead_in", "salida", "hora", "pase", "reaccion", "fortuna", "chismes", "novela"):
		assert expected_cat in categories


@pytest.mark.asyncio
async def test_run_tts_preload_skips_cached_and_synthesizes_missing(tmp_path: Path) -> None:
	"""Verifica que run_tts_preload saltee claves ya cacheadas y solo sintetice las faltantes."""
	from app.domain.radio.preload import run_tts_preload

	db_path = tmp_path / "tts_cache.db"
	init_tts_cache_db(db_path)

	voice = "es-AR-TomasNeural"
	cached_item = ("intro", "Hola gente.")
	missing_item = ("intro", "Chau gente.")

	cached_key = get_cache_key(cached_item[0], voice, cached_item[1])
	with sqlite3.connect(db_path) as conn:
		conn.execute(
			"""
			INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
			VALUES (?, ?, ?, ?, ?, ?, 1000.0, 1000.0, 1)
			""",
			(cached_key, cached_item[0], voice, cached_item[1], b"MP3DATA", 1.0),
		)
		conn.commit()

	synth_mock = AsyncMock(return_value=b"NEW_MP3")

	with (
		patch("app.domain.radio.preload.HAS_EDGE_TTS", True),
		patch("app.domain.radio.preload.is_internet_available", return_value=True),
		patch("app.domain.radio.preload.collect_preload_phrases", return_value=[cached_item, missing_item]),
		patch("app.domain.radio.preload.synthesize_segment", synth_mock),
	):
		stats = await run_tts_preload(
			voices=[voice],
			concurrency=1,
			delay=0.0,
			max_retries=1,
			db_path=db_path,
		)

	assert stats["skipped"] == 1
	assert stats["synthesized"] == 1
	assert stats["failed"] == 0
	synth_mock.assert_awaited_once()
	assert synth_mock.await_args.kwargs["text"] == "Chau gente."


@pytest.mark.asyncio
async def test_run_tts_preload_skips_when_offline(tmp_path: Path) -> None:
	"""Verifica que run_tts_preload aborte sin errores ni llamadas si no hay internet."""
	from app.domain.radio.preload import run_tts_preload

	db_path = tmp_path / "tts_cache.db"
	synth_mock = AsyncMock()

	with (
		patch("app.domain.radio.preload.HAS_EDGE_TTS", True),
		patch("app.domain.radio.preload.is_internet_available", return_value=False),
		patch("app.domain.radio.preload.synthesize_segment", synth_mock),
	):
		stats = await run_tts_preload(
			voices=["es-AR-TomasNeural"],
			delay=0.0,
			db_path=db_path,
		)

	assert stats["synthesized"] == 0
	assert stats["offline"] == 1
	synth_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_tts_preload_handles_cancellation(tmp_path: Path) -> None:
	"""Verifica que la tarea de precarga propague CancelledError limpiamente al apagarse el servidor."""
	from app.domain.radio.preload import run_tts_preload

	db_path = tmp_path / "tts_cache.db"

	async def slow_synth(**_kwargs: object) -> bytes:
		await asyncio.sleep(5.0)
		return b"MP3"

	with (
		patch("app.domain.radio.preload.HAS_EDGE_TTS", True),
		patch("app.domain.radio.preload.is_internet_available", return_value=True),
		patch("app.domain.radio.preload.collect_preload_phrases", return_value=[("intro", "Lento.")]),
		patch("app.domain.radio.preload.synthesize_segment", side_effect=slow_synth),
	):
		task = asyncio.create_task(run_tts_preload(voices=["es-AR-TomasNeural"], delay=0.0, db_path=db_path))
		await asyncio.sleep(0.05)
		task.cancel()
		with pytest.raises(asyncio.CancelledError):
			await task


@pytest.mark.asyncio
async def test_run_tts_preload_skips_when_metered_or_non_wifi(tmp_path: Path) -> None:
	"""En modo Wi-Fi no medido obligatorio, omite precarga si la red es móvil o medida."""
	from app.domain.radio.preload import run_tts_preload

	db_path = tmp_path / "tts_cache.db"
	synth_mock = AsyncMock()

	with (
		patch("app.domain.radio.preload.HAS_EDGE_TTS", True),
		patch("app.domain.radio.preload.is_unmetered_wifi_available", return_value=False),
		patch("app.domain.radio.preload.synthesize_segment", synth_mock),
	):
		stats = await run_tts_preload(
			voices=["es-AR-TomasNeural"],
			delay=0.0,
			db_path=db_path,
			require_unmetered_wifi=True,
		)

	assert stats["synthesized"] == 0
	assert stats["metered"] == 1
	synth_mock.assert_not_awaited()


def test_prune_tts_cache_db_enforces_max_mb_cap(tmp_path: Path) -> None:
	"""prune_tts_cache_db poda los audios más viejos cuando los blobs superan max_mb."""
	import time

	from app.infrastructure.media.tts_cache import prune_tts_cache_db

	db_path = tmp_path / "tts_cache.db"
	init_tts_cache_db(db_path)

	now = time.time()
	blob_600 = b"A" * 600
	with sqlite3.connect(db_path) as conn:
		for idx, ts in enumerate((now - 300.0, now - 200.0, now - 100.0)):
			key = get_cache_key("intro", "v1", f"frase {idx}")
			conn.execute(
				"""
				INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
				VALUES (?, 'intro', 'v1', ?, ?, 1.0, ?, ?, 1)
				""",
				(key, f"frase {idx}", blob_600, ts, ts),
			)
		conn.commit()

	# 3 * 600 = 1800 bytes; con tope ~0.001 MB (~1048 bytes) debe borrar los 2 más viejos o al menos 2 para quedar <= 1048
	deleted = prune_tts_cache_db(max_entries=9000, max_mb=0.001, db_path=db_path)
	assert deleted >= 2

	with sqlite3.connect(db_path) as conn:
		rows = conn.execute("SELECT text, LENGTH(audio_blob) FROM tts_cache ORDER BY last_used ASC").fetchall()
		total_bytes = sum(r[1] for r in rows)
		assert total_bytes <= int(0.001 * 1024 * 1024)
		assert rows[-1][0] == "frase 2"


@pytest.mark.asyncio
async def test_run_tts_preload_stops_batches_when_max_mb_reached(tmp_path: Path) -> None:
	"""La precarga debe revisar max_mb por tandas y frenar antes de sintetizar toda la cola."""
	from app.domain.radio.preload import run_tts_preload

	db_path = tmp_path / "tts_cache.db"
	init_tts_cache_db(db_path)

	phrases = [("intro", f"Frase larga número {i}") for i in range(12)]

	async def _fake_synth_and_store(*, text: str, voice: str, category: str, **_kwargs: object) -> bytes:
		key = get_cache_key(category, voice, text)
		with sqlite3.connect(db_path) as conn:
			conn.execute(
				"""
				INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
				VALUES (?, ?, ?, ?, ?, 1.0, 1000.0, 1000.0, 1)
				""",
				(key, category, voice, text, b"X" * 600),
			)
			conn.commit()
		return b"X" * 600

	synth_mock = AsyncMock(side_effect=_fake_synth_and_store)

	with (
		patch("app.domain.radio.preload.HAS_EDGE_TTS", True),
		patch("app.domain.radio.preload.is_internet_available", return_value=True),
		patch("app.domain.radio.preload.collect_preload_phrases", return_value=phrases),
		patch("app.domain.radio.preload.synthesize_segment", synth_mock),
	):
		stats = await run_tts_preload(
			voices=["es-AR-TomasNeural"],
			concurrency=1,
			delay=0.0,
			max_retries=1,
			db_path=db_path,
			max_mb=0.001,  # ~1048 bytes -> con 1 tanda de <=4 ya supera el tope y frena antes de las 12
		)

	assert stats["synthesized"] < len(phrases)
	assert synth_mock.await_count < len(phrases)


def test_preload_script_passes_max_mb_flag(monkeypatch: pytest.MonkeyPatch) -> None:
	"""scripts/preload_tts_cache.py debe aceptar --max-mb y reenviarlo a run_preload."""
	import sys

	from scripts import preload_tts_cache

	captured: dict[str, object] = {}

	async def _fake_run_preload(**kwargs: object) -> None:
		captured.update(kwargs)

	monkeypatch.setattr(preload_tts_cache, "run_preload", _fake_run_preload)
	monkeypatch.setattr(sys, "argv", ["preload_tts_cache.py", "--voices", "tomas", "--max-mb", "512"])

	preload_tts_cache.main()
	assert captured.get("max_mb") == 512.0


def test_should_auto_preload_tts_is_opt_in_on_android(monkeypatch: pytest.MonkeyPatch) -> None:
	"""En Android la precarga automática al arranque debe ser opt-in (desactivada por defecto)."""
	from app.main import should_auto_preload_tts

	monkeypatch.delenv("ROCKOLA_TTS_PRELOAD_ANDROID", raising=False)
	assert should_auto_preload_tts(android_mode=False) is True
	assert should_auto_preload_tts(android_mode=True) is False

	monkeypatch.setenv("ROCKOLA_TTS_PRELOAD_ANDROID", "1")
	assert should_auto_preload_tts(android_mode=True) is True
