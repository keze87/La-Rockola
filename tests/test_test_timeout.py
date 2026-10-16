from unittest.mock import MagicMock

import pytest

from tests.conftest import (
	TestTimeoutError,
	_get_test_timeout,
)


def test_get_test_timeout_default():
	"""Verifica que el timeout por defecto sea de 30 segundos."""
	item = MagicMock()
	item.get_closest_marker.return_value = None
	item.config.getoption.return_value = None

	timeout = _get_test_timeout(item)
	assert timeout == 30.0


def test_get_test_timeout_from_marker():
	"""Verifica que el marker @pytest.mark.timeout tenga prioridad."""
	item = MagicMock()
	marker = MagicMock()
	marker.args = [15.0]
	item.get_closest_marker.return_value = marker

	timeout = _get_test_timeout(item)
	assert timeout == 15.0


def test_get_test_timeout_from_cli_option():
	"""Verifica que la opción CLI configure el timeout si no hay marker."""
	item = MagicMock()
	item.get_closest_marker.return_value = None
	item.config.getoption.side_effect = lambda opt, default=None: 45.0 if opt == "--test-timeout" else default

	timeout = _get_test_timeout(item)
	assert timeout == 45.0


@pytest.mark.timeout(0.1)
def test_sync_timeout_fires():
	"""Verifica que un test sincrónico excediendo su timeout falle con TestTimeoutError."""
	import time

	with pytest.raises(TestTimeoutError, match="excedió el límite"):
		# Simular operación larga que debe disparar el timeout
		time.sleep(0.5)


def test_async_timeout_fires():
	"""Verifica que pytest_pyfunc_call corte la ejecución cuando una corrutina excede el timeout."""
	import asyncio

	from tests.conftest import pytest_pyfunc_call

	async def slow_coro():
		await asyncio.sleep(0.5)

	pyfuncitem = MagicMock()
	pyfuncitem.obj = slow_coro
	pyfuncitem.funcargs = {}
	pyfuncitem._fixtureinfo.argnames = []
	pyfuncitem.get_closest_marker.side_effect = lambda m: MagicMock(args=[0.05]) if m == "timeout" else None
	pyfuncitem.config.getoption.return_value = None

	with pytest.raises((TimeoutError, TestTimeoutError)):
		pytest_pyfunc_call(pyfuncitem)
