"""
Tests for cultural expansion of phrase banks in scripts/radio_banks.py
and scripts/radio_announcer.py.
"""

from __future__ import annotations

from scripts import radio_announcer, radio_banks


def test_transito_fluvial_y_caminos_exists_and_quality():
	"""Verifica existencia, tamaño mínimo (>=15) y validez del banco de tránsito fluvial y caminos."""
	assert hasattr(radio_banks, "TRANSITO_FLUVIAL_Y_CAMINOS")
	phrases = radio_banks.TRANSITO_FLUVIAL_Y_CAMINOS
	assert len(phrases) >= 15

	for phrase in phrases:
		assert isinstance(phrase, str) and len(phrase.split()) >= 4
		assert radio_announcer.is_spanish_text(phrase) is True
		assert not radio_announcer.contains_blacklisted_content(phrase)


def test_avisos_parroquiales_y_extravios_exists_and_quality():
	"""Verifica existencia, tamaño mínimo (>=15) y validez de avisos parroquiales y pérdidas insólitas."""
	assert hasattr(radio_banks, "AVISOS_PARROQUIALES_Y_EXTRAVIOS")
	phrases = radio_banks.AVISOS_PARROQUIALES_Y_EXTRAVIOS
	assert len(phrases) >= 15

	for phrase in phrases:
		assert isinstance(phrase, str) and len(phrase.split()) >= 4
		assert radio_announcer.is_spanish_text(phrase) is True
		assert not radio_announcer.contains_blacklisted_content(phrase)


def test_alertas_incomodidad_criolla_exists_and_quality():
	"""Verifica existencia, tamaño mínimo (>=15) y validez de alertas satíricas de mosquitos y clima."""
	assert hasattr(radio_banks, "ALERTAS_INCOMODIDAD_CRIOLLA")
	phrases = radio_banks.ALERTAS_INCOMODIDAD_CRIOLLA
	assert len(phrases) >= 15

	for phrase in phrases:
		assert isinstance(phrase, str) and len(phrase.split()) >= 4
		assert radio_announcer.is_spanish_text(phrase) is True
		assert not radio_announcer.contains_blacklisted_content(phrase)


def test_separadores_y_slogans_exists_and_quality():
	"""Verifica existencia, tamaño mínimo (>=15) y validez de separadores de tanda y jingles de cabina."""
	assert hasattr(radio_banks, "SEPARADORES_Y_SLOGANS")
	phrases = radio_banks.SEPARADORES_Y_SLOGANS
	assert len(phrases) >= 15

	for phrase in phrases:
		assert isinstance(phrase, str) and len(phrase.split()) >= 3
		assert radio_announcer.is_spanish_text(phrase) is True
		assert not radio_announcer.contains_blacklisted_content(phrase)


def test_dedicatorias_oyentes_exists_and_quality():
	"""Verifica existencia, tamaño mínimo (>=15) y validez de dedicatorias satíricas con pedidos musicales."""
	assert hasattr(radio_banks, "DEDICATORIAS_OYENTES")
	phrases = radio_banks.DEDICATORIAS_OYENTES
	assert len(phrases) >= 15

	for phrase in phrases:
		assert isinstance(phrase, str) and len(phrase.split()) >= 4
		assert radio_announcer.is_spanish_text(phrase) is True
		assert not radio_announcer.contains_blacklisted_content(phrase)
