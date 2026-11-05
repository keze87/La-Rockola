"""
Pruebas para la permutación aleatoria y modular de bloques de locución radial.
Garantiza que el orden de los bloques (hora, clima, contenido) varíe de forma natural
manteniendo siempre la intro al inicio, el outro al final y la coherencia del diálogo.
"""

from datetime import datetime

from app.domain.radio.classification import RadioPhrase
from app.domain.radio.dialogue import (
	build_radio_dialogue_plan,
	group_plan_into_speech_turns,
)


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
