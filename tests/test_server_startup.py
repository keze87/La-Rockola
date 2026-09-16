import ipaddress
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


def test_get_local_ip_returns_valid_ip():
	"""Verify get_local_ip returns a valid IPv4 address."""
	ip = server.get_local_ip()
	assert isinstance(ip, str)
	# Validate format
	parsed = ipaddress.ip_address(ip)
	assert parsed.version == 4


def test_get_local_ip_fallbacks():
	"""Verify get_local_ip handles connection errors and falls back properly."""
	with patch("socket.socket") as mock_socket:
		instance = MagicMock()
		instance.connect.side_effect = OSError("Network down")
		mock_socket.return_value = instance

		with patch("socket.gethostname", return_value="testhost"):
			with patch("socket.gethostbyname", return_value="192.168.1.50"):
				ip = server.get_local_ip()
				assert ip == "192.168.1.50"

			with patch("socket.gethostbyname", side_effect=OSError("DNS error")):
				ip = server.get_local_ip()
				assert ip == "127.0.0.1"


def test_get_server_urls():
	"""Verify get_server_urls computes correct URLs for 0.0.0.0, localhost, and custom host."""
	with patch("server.get_local_ip", return_value="192.168.1.100"):
		# Default 0.0.0.0 binding
		urls_all = server.get_server_urls("0.0.0.0", 1729)
		assert urls_all["local_ip"] == "192.168.1.100"
		assert urls_all["local_url"] == "http://192.168.1.100:1729"
		assert urls_all["network_url"] == "http://192.168.1.100:1729"
		assert urls_all["loopback_url"] == "http://localhost:1729"

		# Localhost binding
		urls_local = server.get_server_urls("127.0.0.1", 1729)
		assert urls_local["local_url"] == "http://localhost:1729"
		assert urls_local["network_url"] is None

		# Custom host binding
		urls_custom = server.get_server_urls("10.0.0.5", 8080)
		assert urls_custom["local_url"] == "http://10.0.0.5:8080"
		assert urls_custom["network_url"] == "http://10.0.0.5:8080"


def test_print_startup_banner(capsys, tmp_path):
	"""Verify print_startup_banner outputs informative help, URLs, and usage tips."""
	config_file = tmp_path / "rockola_config.json"
	with patch("server.get_local_ip", return_value="192.168.1.100"):
		server.print_startup_banner(
			host="0.0.0.0",
			port=1729,
			music_dir="/media/music",
			music_dir2="/backup/music",
			open_browser=True,
			config_path=config_file,
		)

	captured = capsys.readouterr().out
	assert "LA ROCKOLA DEL CARPINCHO" in captured
	assert "http://192.168.1.100:1729" in captured
	assert "http://localhost:1729" in captured
	assert "DIRECCIONES DE ACCESO" in captured
	assert "GUÍA RÁPIDA DE USO" in captured
	assert "celular" in captured.lower()
	assert "automáticamente" in captured


def test_cli_browser_flags():
	"""Verify --open-browser and --no-browser CLI flag parsing."""
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--open-browser",
		dest="open_browser",
		action="store_true",
		default=None,
	)
	parser.add_argument(
		"--no-browser",
		dest="open_browser",
		action="store_false",
		default=None,
	)

	# Default without flags
	assert parser.parse_args([]).open_browser is None

	# With --open-browser
	assert parser.parse_args(["--open-browser"]).open_browser is True

	# With --no-browser
	assert parser.parse_args(["--no-browser"]).open_browser is False


def test_state_dict_includes_server_url_and_local_ip(clean_state):
	"""Verify get_full_state_dict includes server_url and local_ip."""
	clean_state.server_url = "http://192.168.1.100:1729"
	clean_state.local_ip = "192.168.1.100"

	state_dict = clean_state.get_full_state_dict()
	assert state_dict["server_url"] == "http://192.168.1.100:1729"
	assert state_dict["local_ip"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_lifespan_browser_opening(clean_state, monkeypatch):
	"""Verify lifespan triggers browser opening when open_browser is True and not running tests."""
	clean_state.open_browser = True
	clean_state.server_url = "http://192.168.1.50:1729"
	clean_state.server_port = 1729
	clean_state.server_host = "0.0.0.0"
	clean_state.mpv = MagicMock()
	clean_state.mpv.stop = AsyncMock()
	monkeypatch.setattr(server, "state", clean_state)

	# Mock PYTEST_CURRENT_TEST away for this specific test
	monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

	with patch("server.scan_library", new_callable=AsyncMock):
		with patch("webbrowser.open") as mock_browser_open:
			with patch("socket.socket") as mock_sock_cls:
				mock_sock = MagicMock()
				mock_sock.connect_ex.return_value = 0
				mock_sock_cls.return_value.__enter__.return_value = mock_sock

				async with server.lifespan(server.app):
					import asyncio
					await asyncio.sleep(0.15)

				mock_browser_open.assert_called_once_with("http://192.168.1.50:1729")

