"""
Tests de Etapa 7: Verificación de probabilidad 50/50 de fortunas,
estrategia Cache-First para síntesis TTS y robustez en pregeneración radial.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.radio.nlp import select_radio_phrase
from app.domain.radio.service import RadioService
from app.infrastructure.db.connection import init_db
from app.infrastructure.media import tts_cache


def test_select_radio_phrase_half_and_half_probability(tmp_path: Path) -> None:
	"""Verifica que la probabilidad de usar fortunas sea de 50/50 (mitad y mitad, umbral 0.5)."""
	db_p = tmp_path / "test_fortune.db"
	init_db(db_p)

	# Con valor menor a 0.5 (ej. 0.45) debe elegir fortuna
	with (
		patch("random.random", return_value=0.45),
		patch("app.domain.radio.nlp.get_system_fortune", return_value="La suerte favorece a los audaces."),
	):
		_phrase, is_sys = select_radio_phrase(db_path=db_p)
		assert is_sys is True

	# Con valor mayor o igual a 0.5 (ej. 0.55) debe elegir frase de carpincho común
	with patch("random.random", return_value=0.55):
		_phrase, is_sys = select_radio_phrase(db_path=db_p)
		assert is_sys is False


@pytest.mark.asyncio
async def test_tts_cache_first_avoids_remote_call(tmp_path: Path) -> None:
	"""Verifica que si el audio ya está en la caché SQLite, se retorne de inmediato sin tocar la red."""
	db_p = tmp_path / "tts_cache_test.db"
	tts_cache.init_tts_cache_db(db_p)

	cached_bytes = b"ID3\x04\x00\x00\x00\x00\x00\x00CACHED_AUDIO_DATA"
	text = "Buenas tardes amigos de la laguna"
	voice = "es-AR-TomasNeural"
	category = "intro"

	tts_cache.save_cached_audio(category, voice, text, cached_bytes, duration=2.5, db_path=db_p)

	mock_communicate = MagicMock()

	with patch.object(tts_cache, "edge_tts", create=True) as mock_edge:
		mock_edge.Communicate = mock_communicate
		result = await tts_cache.synthesize_segment(
			text=text,
			voice=voice,
			category=category,
			allow_cache=True,
			db_path=db_p,
			return_cues=True,
		)
		# No debe haberse llamado a Communicate porque existía en caché
		mock_communicate.assert_not_called()
		assert isinstance(result, tuple)
		audio_res, cues = result
		assert audio_res == cached_bytes
		assert len(cues) > 0


@pytest.mark.asyncio
async def test_tts_synthesize_handles_rate_limit_with_cache_fallback(tmp_path: Path) -> None:
	"""Verifica que ante errores 429 de Edge-TTS, se use el fallback de caché SQLite sin colgar la app."""
	db_p = tmp_path / "tts_429_test.db"
	tts_cache.init_tts_cache_db(db_p)

	fallback_bytes = b"ID3\x04\x00\x00\x00\x00\x00\x00FALLBACK_AUDIO"
	text = "Reporte meteorológico dinámico"
	voice = "es-AR-ElenaNeural"
	category = "clima"

	tts_cache.save_cached_audio(category, voice, text, fallback_bytes, duration=3.0, db_path=db_p)

	# Mock de stream que simula un error 429
	class Dummy429Comm:
		async def stream(self):
			raise RuntimeError("429 Too Many Requests")
			yield {}  # unreachable generator

	with patch.object(tts_cache, "edge_tts", create=True) as mock_edge:
		mock_edge.Communicate.return_value = Dummy429Comm()
		result = await tts_cache.synthesize_segment(
			text=text,
			voice=voice,
			category=category,
			allow_cache=True,
			db_path=db_p,
			timeout=0.1,
			max_retries=1,
		)
		assert result == fallback_bytes


@pytest.mark.asyncio
async def test_radio_pregeneration_pipeline_end_to_end(tmp_path: Path) -> None:
	"""Verifica que start_pregeneration popule pregenerated_announcement correctamente."""
	db_p = tmp_path / "pregen_pipeline.db"
	init_db(db_p)

	svc = RadioService(db_path=db_p)
	fake_ann_path = tmp_path / "radio_pregenerated.mp3"
	svc.pregenerated_path = fake_ann_path

	fake_result = MagicMock()
	fake_result.ok = True
	fake_result.display_title = "Carpincho en Vivo"
	fake_result.script = "Buenas tardes. Sigue la música."
	fake_result.outro_mode = "continue"
	fake_result.host_voice = "es-AR-TomasNeural"
	fake_result.stem_segments = []

	with (
		patch("app.domain.radio.service.HAS_EDGE_TTS", True),
		patch("app.domain.radio.service.create_radio_announcement", AsyncMock(return_value=fake_result)),
	):
		svc.start_pregeneration(track_duration=120.0)
		assert svc.pregeneration_task is not None
		await svc.pregeneration_task
		assert svc.pregenerated_announcement is not None
		assert svc.pregenerated_announcement["display_title"] == "Carpincho en Vivo"


def test_prune_tts_cache_db_large_capacity(tmp_path: Path) -> None:
	"""Verifica que la capacidad por defecto de la caché sea de al menos 9000 entradas (evitando podas prematuras)."""
	import inspect

	sig = inspect.signature(tts_cache.prune_tts_cache_db)
	max_entries_default = sig.parameters["max_entries"].default
	assert max_entries_default >= 9000, f"max_entries default ({max_entries_default}) debe ser >= 9000"


def test_collect_phrases_expands_placeholders_and_numbers() -> None:
	"""Verifica que collect_phrases expanda todos los placeholders y prevea números y clima para uso offline."""
	from scripts.preload_tts_cache import collect_phrases

	items = collect_phrases()
	assert len(items) > 1000, f"Debe recolectar un banco amplio (>1000), obtuvo {len(items)}"

	# Ninguna frase debe tener placeholders crudos sin resolver
	for cat, text in items:
		assert "{" not in text and "}" not in text, f"Frase con placeholder sin resolver en [{cat}]: '{text}'"

	# Debe incluir minutos modulares (al menos 1 a 59)
	minutos = [txt for cat, txt in items if cat == "minuto"]
	assert len(minutos) >= 59
	assert any("un minuto." in m or "1 minuto." in m for m in minutos)
	assert any("59 minutos." in m for m in minutos)

	# Debe incluir números de temperatura y clima
	clima_items = [txt for cat, txt in items if cat == "clima"]
	assert len(clima_items) >= 40
	assert any("bajo cero" in c for c in clima_items)
	assert any("grados" in c for c in clima_items)
