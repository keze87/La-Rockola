from unittest.mock import MagicMock

import pytest

from tests.conftest import pytest_addoption, pytest_collection_modifyitems


def test_download_marker_skipped_by_default():
	"""Verifica que los tests con el marker 'download' se salteen por defecto si no se pasa --run-downloads."""
	# Simular configuración sin el flag --run-downloads
	mock_config = MagicMock()
	mock_config.getoption.side_effect = lambda opt: False if opt == "--run-downloads" else None

	# Simular un test con el marker download y otro normal
	download_item = MagicMock()
	download_item.keywords = {"download": True}
	normal_item = MagicMock()
	normal_item.keywords = {}

	items = [download_item, normal_item]
	pytest_collection_modifyitems(mock_config, items)

	# El test con 'download' debe recibir el marker de skip
	assert download_item.add_marker.called
	args, _ = download_item.add_marker.call_args
	marker = args[0]
	assert marker.name == "skip"
	assert "run-downloads" in marker.kwargs.get("reason", "")

	# El test normal no debe modificarse
	assert not normal_item.add_marker.called


def test_download_marker_runs_when_flag_enabled():
	"""Verifica que con --run-downloads los tests con 'download' no se salteen."""
	mock_config = MagicMock()
	mock_config.getoption.side_effect = lambda opt: True if opt == "--run-downloads" else None

	download_item = MagicMock()
	download_item.keywords = {"download": True}

	items = [download_item]
	pytest_collection_modifyitems(mock_config, items)

	# No debe agregar marker de skip
	assert not download_item.add_marker.called


def test_pytest_addoption_registers_run_downloads():
	"""Verifica que pytest_addoption registre el flag --run-downloads en el parser."""
	mock_parser = MagicMock()
	pytest_addoption(mock_parser)
	download_call = next((call for call in mock_parser.addoption.call_args_list if "--run-downloads" in call[0]), None)
	assert download_call is not None
	assert download_call[1].get("action") == "store_true"
	assert download_call[1].get("default") is False


@pytest.mark.download
def test_dummy_download_marked_function():
	"""Test señuelo marcado con download que debe saltearse por defecto en la suite."""
