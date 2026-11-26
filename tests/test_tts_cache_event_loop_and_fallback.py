"""Tests TDD para lock por event loop, rotación de fallback SQLite y separación de categoría DJ en TTS."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain.radio.preload import collect_preload_phrases
from app.domain.radio.voices import VOICE_VALENTINA
from app.infrastructure.media import tts_cache
from app.infrastructure.media.tts_cache import (
	get_cache_key,
	init_tts_cache_db,
	save_cached_audio,
	synthesize_segment,
)


def test_synthesize_segment_works_across_multiple_event_loops(tmp_path: Path) -> None:
	"""Reproduce el reinicio de Uvicorn en Chaquopy: dos event loops consecutivos no deben romper _tts_lock."""
	db_path = tmp_path / "tts_cache.db"

	class FakeCommunicate:
		def __init__(self, text: str, voice: str, **_kwargs: object) -> None:
			self.text = text

		async def stream(self):
			await asyncio.sleep(0)
			yield {"type": "audio", "data": b"ID3FAKEAUDIO" + self.text.encode("utf-8")}

	fake_edge = MagicMock()
	fake_edge.Communicate = FakeCommunicate

	async def _run_concurrent_first_loop() -> None:
		# Forzamos que el lock se ate al primer event loop mediante contención real
		await asyncio.gather(
			synthesize_segment(
				text="Las doce y cinco.",
				voice=VOICE_VALENTINA,
				category="hora",
				allow_cache=False,
				db_path=db_path,
			),
			synthesize_segment(
				text="Las doce y diez.",
				voice=VOICE_VALENTINA,
				category="hora",
				allow_cache=False,
				db_path=db_path,
			),
		)

	async def _run_second_loop() -> bytes:
		return await synthesize_segment(
			text="Las doce y veinte.",
			voice=VOICE_VALENTINA,
			category="hora",
			allow_cache=False,
			db_path=db_path,
		)

	with (
		patch.object(tts_cache, "HAS_EDGE_TTS", True),
		patch.object(tts_cache, "get_edge_tts", return_value=fake_edge),
	):
		asyncio.run(_run_concurrent_first_loop())
		res2 = asyncio.run(_run_second_loop())

	assert b"Las doce y veinte." in res2


@pytest.mark.asyncio
async def test_tts_fallback_rotates_phrases_and_logs_actual_cached_text(
	tmp_path: Path,
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""El fallback por categoría debe rotar frases (no repetir siempre la más usada) y loguear el texto real."""
	db_path = tmp_path / "tts_cache.db"
	init_tts_cache_db(db_path)

	save_cached_audio("lead_in", VOICE_VALENTINA, "Frase uno.", b"AUDIO_1", duration=1.0, db_path=db_path)
	save_cached_audio("lead_in", VOICE_VALENTINA, "Frase dos.", b"AUDIO_2", duration=1.0, db_path=db_path)

	# Simulamos que "Frase uno." quedó con mayor use_count y last_used más reciente
	key1 = get_cache_key("lead_in", VOICE_VALENTINA, "Frase uno.")
	key2 = get_cache_key("lead_in", VOICE_VALENTINA, "Frase dos.")
	with sqlite3.connect(db_path) as conn:
		conn.execute("UPDATE tts_cache SET use_count = 10, last_used = 2000.0 WHERE cache_key = ?", (key1,))
		conn.execute("UPDATE tts_cache SET use_count = 1, last_used = 1000.0 WHERE cache_key = ?", (key2,))
		conn.commit()

	caplog.set_level(logging.INFO, logger="rockola.radio")

	with (
		patch.object(tts_cache, "HAS_EDGE_TTS", False),
		patch.object(tts_cache, "get_edge_tts", return_value=None),
	):
		first_audio = await synthesize_segment(
			text="Texto nuevo que falla A.",
			voice=VOICE_VALENTINA,
			category="lead_in",
			allow_cache=True,
			db_path=db_path,
		)
		second_audio = await synthesize_segment(
			text="Texto nuevo que falla B.",
			voice=VOICE_VALENTINA,
			category="lead_in",
			allow_cache=True,
			db_path=db_path,
		)

	assert {first_audio, second_audio} == {b"AUDIO_1", b"AUDIO_2"}
	fallback_logs = [r.message for r in caplog.records if "TTS Cache Fallback HIT" in r.message]
	assert any("Frase dos." in msg or "Frase uno." in msg for msg in fallback_logs)
	assert all("Texto nuevo que falla" not in msg for msg in fallback_logs)


@pytest.mark.asyncio
async def test_salida_fallback_never_returns_dj_bara_outro_when_dj_disabled(tmp_path: Path) -> None:
	"""Si solo hay salidas de DJ Bara en caché, otro modo de salida no debe usarlas en fallback."""
	from app.domain.radio.service import get_outro_cache_category

	assert get_outro_cache_category("dj") == "salida_dj"
	assert get_outro_cache_category("continue") == "salida"

	db_path = tmp_path / "tts_cache.db"
	init_tts_cache_db(db_path)
	save_cached_audio(
		"salida_dj",
		VOICE_VALENTINA,
		"El DJ Bara toma el control de las bandejas.",
		b"AUDIO_DJ_BARA",
		duration=2.0,
		db_path=db_path,
	)

	with (
		patch.object(tts_cache, "HAS_EDGE_TTS", False),
		patch.object(tts_cache, "get_edge_tts", return_value=None),
		pytest.raises(RuntimeError),
	):
		await synthesize_segment(
			text="Sigue la música en la rockola.",
			voice=VOICE_VALENTINA,
			category="salida",
			allow_cache=True,
			db_path=db_path,
		)


def test_collect_preload_phrases_separates_dj_outros_from_general_salida() -> None:
	"""Los outros del modo DJ deben precargarse bajo 'salida_dj' y no mezclarse con 'salida'."""
	items = collect_preload_phrases()
	salida_texts = [txt for cat, txt in items if cat == "salida"]
	dj_texts = [txt for cat, txt in items if cat == "salida_dj"]

	assert dj_texts, "Debe haber frases precargadas en 'salida_dj'"
	assert any("DJ Bara" in txt or "Bara" in txt for txt in dj_texts)
	assert all("DJ Bara" not in txt for txt in salida_texts)


def test_init_tts_cache_db_migrates_legacy_dj_bara_entries_out_of_salida(tmp_path: Path) -> None:
	"""Las filas viejas de DJ Bara guardadas bajo 'salida' deben migrarse a 'salida_dj'."""
	db_path = tmp_path / "tts_cache.db"
	init_tts_cache_db(db_path)
	save_cached_audio(
		"salida",
		VOICE_VALENTINA,
		"El DJ Bara toma el control de las bandejas.",
		b"LEGACY_DJ",
		duration=2.0,
		db_path=db_path,
	)

	init_tts_cache_db(db_path)

	with sqlite3.connect(db_path) as conn:
		row = conn.execute("SELECT category FROM tts_cache WHERE text LIKE '%DJ Bara%'").fetchone()
	assert row is not None
	assert row[0] == "salida_dj"
