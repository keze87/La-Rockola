"""
Pruebas para la simulación masiva y cobertura de locuciones y diálogo de radio.
Verifica que el script de simulación mock de radio no toque la base de datos real
y alcance el 100% de categorías y bancos de frases radiales sin efectos colaterales.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.radio.nlp import reset_radio_memory_state
from app.infrastructure.db.connection import get_default_db_path
from scripts.simulate_radio_locutions import (
	collect_all_radio_banks,
	run_mock_radio_simulation,
)


def test_collect_all_radio_banks_contains_all_categories():
	"""Verifica que todos los bancos y categorías requeridas estén catalogados."""
	banks = collect_all_radio_banks()

	expected_categories = {
		"carpincho_fortuna",
		"carpincho_aviso",
		"carpincho_oyentes",
		"carpincho_alerta_criolla",
		"carpincho_chismes",
		"carpincho_novela",
		"intros",
		"outros_continue",
		"outros_chismes",
		"outros_novela",
		"outros_dj",
		"outros_pause",
		"outros_break",
		"pases",
		"lead_ins_fortuna",
		"lead_ins_aviso",
		"lead_ins_oyentes",
		"lead_ins_alerta",
		"lead_ins_chismes",
		"lead_ins_novela",
		"reacciones_fortuna",
		"reacciones_aviso",
		"reacciones_oyentes",
		"reacciones_alerta",
		"reacciones_chismes",
		"reacciones_novela",
		"reacciones_clima_calor",
		"reacciones_clima_frio",
		"reacciones_clima_lluvia",
		"reacciones_clima_agradable",
	}

	assert expected_categories.issubset(set(banks.keys()))
	for cat, phrases in banks.items():
		assert len(phrases) > 0, f"El banco {cat} no tiene frases cargadas"


def test_simulation_does_not_modify_real_db(tmp_path: Path):
	"""Garantiza aislamiento estricto: la base de datos real de producción no debe ser alterada."""
	real_db = get_default_db_path()
	real_mtime = real_db.stat().st_mtime if real_db.exists() else None

	isolated_db = tmp_path / "mock_test.db"
	reset_radio_memory_state(clear_db=True, db_path=isolated_db)

	results = run_mock_radio_simulation(
		iterations=200,
		db_path=isolated_db,
		seed=42,
	)

	assert results["total_runs"] == 200
	assert isolated_db.exists(), "La base aislada debió recibir los registros de prueba."

	if real_db.exists() and real_mtime is not None:
		assert real_db.stat().st_mtime == real_mtime, "¡Ojo al piojo! Se modificó la base de datos real."


def test_simulation_reaches_high_coverage_and_all_categories(tmp_path: Path):
	"""Comprueba que la simulación cubra todas las categorías y supere el 98% de cobertura general."""
	isolated_db = tmp_path / "coverage_test.db"
	results = run_mock_radio_simulation(
		iterations=2500,
		db_path=isolated_db,
		seed=12345,
	)

	coverage_pct = results["coverage_percentage"]
	category_coverage = results["category_coverage"]

	# Todas las 30 categorías deben haber sido impactadas
	assert len(category_coverage) >= 30
	for cat, stats in category_coverage.items():
		assert stats["hit"] > 0, f"La categoría {cat} no tuvo ninguna reproducción registrada."

	# La cobertura global de plantillas debe ser prácticamente total (> 98%)
	assert coverage_pct >= 98.0, f"Cobertura insuficiente: {coverage_pct:.2f}%"
