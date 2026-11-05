"""
Pruebas para la permutación aleatoria y modular de bloques de locución radial.
Garantiza que el orden de los bloques (hora, clima, contenido) varíe de forma natural
manteniendo siempre la intro al inicio, el outro al final y la coherencia del diálogo.
"""

import logging
from datetime import datetime

from app.domain.radio.classification import RadioPhrase
from app.domain.radio.dialogue import (
	build_radio_dialogue_plan,
	group_plan_into_speech_turns,
)
from app.domain.radio.segments import get_reactions_for_category


def _extract_block_order(plan: list[tuple[str, str, str, bool]]) -> list[str]:
	"""Identifica el orden de los bloques temáticos ('hora', 'clima', 'contenido') en el plan."""
	order: list[str] = []
	for _text, _voice, category, _allow_cache in plan:
		if category in ("hora", "minuto") and "hora" not in order:
			order.append("hora")
		elif category in ("pase", "clima", "reaccion_clima") and "clima" not in order:
			order.append("clima")
		elif category in ("lead_in", "fortuna", "oyentes", "aviso", "chismes", "novela") and "contenido" not in order:
			order.append("contenido")
	return order


def test_plan_preserves_intro_and_outro_boundaries():
	"""El plan debe comenzar siempre con intro y terminar siempre con salida (outro)."""
	dt = datetime(2026, 11, 5, 17, 30)
	phrase = RadioPhrase("El mate bien cebado no se niega.", "fortuna")

	for _ in range(20):
		plan = build_radio_dialogue_plan(
			dt=dt,
			fortuna=phrase,
			weather_text="En Tigre hacen 22 grados con cielo despejado.",
			weather_condition="agradable",
			dialogue_mode=True,
		)
		assert plan[0][2] == "intro"
		assert plan[-1][2] == "salida"

		turns = group_plan_into_speech_turns(plan)
		assert turns[-1][2] == "salida"


def test_plan_permutes_blocks_randomly():
	"""Múltiples llamadas deben generar diferentes órdenes de bloques entre intro y outro."""
	dt = datetime(2026, 11, 5, 17, 30)
	phrase = RadioPhrase("Mensaje de oyente en el dial", "oyentes")

	observed_orders: set[tuple[str, ...]] = set()

	for _ in range(50):
		plan = build_radio_dialogue_plan(
			dt=dt,
			fortuna=phrase,
			weather_text="25 grados con sol",
			weather_condition="agradable",
			dialogue_mode=True,
		)
		order = tuple(_extract_block_order(plan))
		observed_orders.add(order)

	# Con 3 bloques (hora, clima, contenido), hay 6 posibles permutaciones;
	# en 50 intentos esperamos ver al menos 3 órdenes distintos (no siempre el mismo orden fijo).
	assert len(observed_orders) >= 3, f"Solo se observaron los siguientes órdenes: {observed_orders}"


def test_explicit_block_order():
	"""Se puede forzar un orden explícito de bloques para pruebas deterministas."""
	dt = datetime(2026, 11, 5, 17, 30)
	phrase = RadioPhrase("Sabiduría del río.", "fortuna")

	# Orden: contenido -> clima -> hora
	plan1 = build_radio_dialogue_plan(
		dt=dt,
		fortuna=phrase,
		weather_text="20 grados agradable",
		dialogue_mode=True,
		block_order=["contenido", "clima", "hora"],
	)
	assert _extract_block_order(plan1) == ["contenido", "clima", "hora"]
	assert plan1[0][2] == "intro"
	assert plan1[-1][2] == "salida"

	# Orden: clima -> hora -> contenido
	plan2 = build_radio_dialogue_plan(
		dt=dt,
		fortuna=phrase,
		weather_text="20 grados agradable",
		dialogue_mode=True,
		block_order=["clima", "hora", "contenido"],
	)
	assert _extract_block_order(plan2) == ["clima", "hora", "contenido"]


def test_permutations_without_weather():
	"""Cuando no hay clima, solo permuta entre hora y contenido."""
	dt = datetime(2026, 11, 5, 17, 30)
	phrase = RadioPhrase("Consejo del delta.", "fortuna")

	observed_orders: set[tuple[str, ...]] = set()
	for _ in range(30):
		plan = build_radio_dialogue_plan(
			dt=dt,
			fortuna=phrase,
			weather_text=None,
			dialogue_mode=True,
		)
		order = tuple(_extract_block_order(plan))
		assert "clima" not in order
		observed_orders.add(order)

	# Esperamos ver ambos órdenes: ('hora', 'contenido') y ('contenido', 'hora')
	assert ("hora", "contenido") in observed_orders
	assert ("contenido", "hora") in observed_orders


def _reaction_texts(plan):
	return [text for text, _voice, category, _cache in plan if category == "reaccion"]


def test_reactions_do_not_repeat_across_blocks_in_any_order():
	"""La anti-repetición de reacciones sigue el orden real: ni la primera repite la previa ni las dos entre sí."""
	dt = datetime(2026, 11, 5, 17, 30)
	phrase = RadioPhrase("Mensaje de oyente en el dial", "oyentes")
	pool = get_reactions_for_category("oyentes")
	previous = pool[0]

	for order in (["contenido", "clima", "hora"], ["clima", "hora", "contenido"], ["hora", "contenido", "clima"]):
		for _ in range(30):
			plan = build_radio_dialogue_plan(
				dt=dt,
				fortuna=phrase,
				weather_text="25 grados con sol",
				weather_condition="agradable",
				dialogue_mode=True,
				last_reaction=previous,
				block_order=order,
			)
			reactions = _reaction_texts(plan)
			assert len(reactions) == 2
			assert reactions[0] != previous
			assert reactions[0] != reactions[1]


def test_unknown_block_order_keys_are_logged(caplog):
	dt = datetime(2026, 11, 5, 17, 30)
	phrase = RadioPhrase("Consejo del delta.", "fortuna")
	with caplog.at_level(logging.WARNING, logger="RockolaCarpincho"):
		plan = build_radio_dialogue_plan(
			dt=dt, fortuna=phrase, weather_text=None, dialogue_mode=True, block_order=["hora", "bloque_fantasma"]
		)
	assert "bloque_fantasma" in caplog.text
	assert plan[0][2] == "intro" and plan[-1][2] == "salida"


def test_point1_context_filtering_applies_to_intros_outros_and_pases():
	"""Punto 1: build_radio_dialogue_plan debe pasar category a filter_by_context para intros, outros y pases."""
	from app.domain.radio.context import build_radio_context, phrase_fits_context

	# A las 9:00 AM (mañana) y a las 23:00 (noche), ni la intro ni el pase ni la salida deben violar las reglas de contexto
	for hour in (9, 23):
		dt = datetime(2026, 11, 5, hour, 0).astimezone()
		ctx = build_radio_context(dt)
		for _ in range(40):
			plan = build_radio_dialogue_plan(
				dt=dt,
				fortuna=RadioPhrase("Sabiduría del río.", "fortuna"),
				weather_text="En Tigre hacen 20 grados.",
				weather_condition="agradable",
				dialogue_mode=True,
				ctx=ctx,
			)
			for text, _voice, cat, _cache in plan:
				if cat in ("intro", "salida", "pase"):
					assert phrase_fits_context(text, ctx, category=cat), (
						f"Frase de categoría '{cat}' incompatible con hora {hour}: {text!r}"
					)


def test_point2_weather_handoff_matches_weather_condition():
	"""Punto 2: El pase al clima no debe contradecir la condición climática real."""
	dt = datetime(2026, 7, 15, 16, 0).astimezone()
	phrase = RadioPhrase("El mate bien cebado no se niega.", "fortuna")

	# Con clima agradable (22°C, sin lluvia ni calor pesado), no deben salir pases de frío extremo, lluvia/sudestada ni calor pesado
	forbidden_in_agradable = (
		"enfriando las patas",
		"sudestada",
		"humedad que te riza",
		"está tan pesada que ni los mosquitos",
	)
	for _ in range(50):
		plan = build_radio_dialogue_plan(
			dt=dt,
			fortuna=phrase,
			weather_text="En Tigre hacen 22 grados con cielo despejado.",
			weather_condition="agradable",
			dialogue_mode=True,
			block_order=["clima", "hora", "contenido"],
		)
		pase_texts = [t.lower() for t, _v, cat, _c in plan if cat == "pase"]
		assert len(pase_texts) == 1
		for bad in forbidden_in_agradable:
			assert bad not in pase_texts[0], f"Pase contradictorio para clima agradable: {pase_texts[0]!r}"

	# Con frío (8°C), no deben salir pases de calor pesado ni sudestada
	forbidden_in_frio = (
		"sudestada",
		"humedad que te riza",
		"está tan pesada que ni los mosquitos",
	)
	for _ in range(40):
		plan = build_radio_dialogue_plan(
			dt=dt,
			fortuna=phrase,
			weather_text="En Tigre hacen 8 grados.",
			weather_condition="frio",
			dialogue_mode=True,
			block_order=["clima", "hora", "contenido"],
		)
		pase_texts = [t.lower() for t, _v, cat, _c in plan if cat == "pase"]
		for bad in forbidden_in_frio:
			assert bad not in pase_texts[0], f"Pase contradictorio para clima frío: {pase_texts[0]!r}"


from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.radio.service import RadioAnnouncementResult, RadioService, create_radio_announcement


@pytest.mark.asyncio
async def test_point3_consume_pregenerated_does_not_fallback_to_wrong_outro_mode(tmp_path: Path):
	"""Punto 3: Si pre_mode != outro_mode y falla replace_announcement_outro (o no hay stem_segments), _consume_pregenerated debe retornar False."""
	svc = RadioService(db_path=tmp_path / "radio.db")
	pre_file = tmp_path / "pre.mp3"
	pre_file.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00FAKE_MP3_DATA" + b"\x00" * 128)
	target_ann = tmp_path / "ann.mp3"

	import time as _time

	pre_data = {
		"path": str(pre_file),
		"display_title": "Transmisión de Cabina",
		"display_artist": "Tomás 🎙️",
		"script": "Buenas tardes. Hacemos una pausita.",
		"created_at": _time.time(),
		"outro_mode": "pause",
		"host_voice": "es-AR-TomasNeural",
		"stem_segments": [(b"ID3...", "intro", "es-AR-TomasNeural", "Buenas tardes.", None)],
	}

	failed_swap = RadioAnnouncementResult(
		ok=False, display_title="", script="", error="Fallo TTS", outro_mode="continue"
	)

	with (
		patch("app.infrastructure.media.mixer.is_valid_mp3_file", return_value=True),
		patch("app.domain.radio.service.replace_announcement_outro", AsyncMock(return_value=failed_swap)),
		patch.object(svc, "apply_hot_mix_to_announcement", AsyncMock(return_value=True)) as mock_hot_mix,
	):
		ok, _title, _script = await svc._consume_pregenerated(
			pre=pre_data,
			target_ann_path=target_ann,
			next_track_path=None,
			bg_offset=0.0,
			outro_mode="continue",
		)
		assert ok is False
		mock_hot_mix.assert_not_called()

	# También si stem_segments está vacío y el modo difiere, no debe usar el audio con el cierre viejo
	pre_data_no_stems = {**pre_data, "stem_segments": []}
	with (
		patch("app.infrastructure.media.mixer.is_valid_mp3_file", return_value=True),
		patch.object(svc, "apply_hot_mix_to_announcement", AsyncMock(return_value=True)) as mock_hot_mix2,
	):
		ok2, _t2, _s2 = await svc._consume_pregenerated(
			pre=pre_data_no_stems,
			target_ann_path=target_ann,
			next_track_path=None,
			bg_offset=0.0,
			outro_mode="continue",
		)
		assert ok2 is False
		mock_hot_mix2.assert_not_called()


@pytest.mark.asyncio
async def test_point4_create_radio_announcement_drops_corrupted_weather_block_and_requires_boundaries(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
	"""
	Punto 4:
	- Si falla un turno del bloque de clima (ej. el reporte 'clima'), se descarta el bloque entero de clima
	  (no quedan 'pase' ni su 'reaccion' huérfanos).
	- Si falla el turno de salida ('salida'), la locución falla o garantiza que stem_segments nunca incluya un segmento que no sea tronco sin salida.
	"""
	from app.domain.radio import service as radio_service_mod

	monkeypatch.setattr(radio_service_mod, "HAS_EDGE_TTS", True)
	monkeypatch.setattr(radio_service_mod, "edge_tts", MagicMock())

	# Caso A: falla el segmento de categoría 'clima' -> el bloque de clima entero se descarta
	assembled_Inputs: list[list] = []

	def fake_assemble(segs, out_p, *_args, **_kwargs):
		assembled_Inputs.append(list(segs))
		Path(out_p).write_bytes(b"ID3" + b"\x00" * 64)
		return True

	async def synth_fail_clima(text, voice, category, **_kwargs):
		if category == "clima":
			raise RuntimeError("Fallo TTS en clima")
		return b"ID3" + b"\x00" * 32, [(0.0, 1.0, text)]

	monkeypatch.setattr(radio_service_mod, "synthesize_segment", synth_fail_clima)
	monkeypatch.setattr(radio_service_mod, "assemble_announcement_audio", fake_assemble)
	monkeypatch.setattr(
		radio_service_mod,
		"fetch_weather_json",
		lambda *_a, **_kw: {
			"current_condition": [{"temp_C": "22", "weatherCode": "113", "lang_es": [{"value": "Despejado"}]}],
			"weather": [{"mintempC": "14", "maxtempC": "25", "hourly": [{"time": "1200", "chanceofrain": "0"}]}],
		},
	)

	res = await create_radio_announcement(
		tmp_path / "ann_a.mp3",
		dt=datetime(2026, 11, 5, 16, 0).astimezone(),
		dialogue_mode=True,
		db_path=tmp_path / "r.db",
	)
	assert res.ok is True
	assert len(assembled_Inputs) == 1
	cats_assembled = [seg[1] for seg in assembled_Inputs[0]]
	assert "clima" not in cats_assembled
	assert "pase" not in cats_assembled, (
		f"Quedó un pase al clima huérfano cuando falló el reporte de clima: {cats_assembled}"
	)
	# El último segmento ensamblado debe ser siempre 'salida'
	assert cats_assembled[-1] == "salida"
	# stem_segments no debe contener 'salida'
	assert all(s[1] != "salida" for s in res.stem_segments)

	# Caso B: si falla el cierre obligatorio ('salida'), create_radio_announcement debe fallar limpiamente
	async def synth_fail_salida(text, voice, category, **_kwargs):
		if category == "salida":
			raise RuntimeError("Fallo TTS en salida")
		return b"ID3" + b"\x00" * 32, [(0.0, 1.0, text)]

	monkeypatch.setattr(radio_service_mod, "synthesize_segment", synth_fail_salida)
	res_b = await create_radio_announcement(
		tmp_path / "ann_b.mp3",
		dt=datetime(2026, 11, 5, 17, 0).astimezone(),
		dialogue_mode=True,
		db_path=tmp_path / "r2.db",
	)
	assert res_b.ok is False
