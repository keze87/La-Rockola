"""
Tests TDD para app.cli (parser de argumentos y asistente interactivo).
"""

import argparse

from app.cli.entrypoint import build_arg_parser


def test_build_arg_parser():
	parser = build_arg_parser()
	assert isinstance(parser, argparse.ArgumentParser)

	# Probar parseo de defaults
	args = parser.parse_args([])
	assert args.port is None
	assert args.host is None
	assert args.setup is False
	assert args.debug is False

	# Probar argumentos específicos
	args2 = parser.parse_args(["--port", "8080", "--host", "127.0.0.1", "--debug", "--setup"])
	assert args2.port == 8080
	assert args2.host == "127.0.0.1"
	assert args2.debug is True
	assert args2.setup is True


def test_configure_console_encoding(monkeypatch):
	from app.cli.entrypoint import configure_console_encoding

	reconfigured = []

	class DummyStream:
		def reconfigure(self, **kwargs):
			reconfigured.append(kwargs)

	dummy = DummyStream()
	monkeypatch.setattr("sys.platform", "win32")
	monkeypatch.setattr("sys.stdout", dummy)
	monkeypatch.setattr("sys.stderr", dummy)

	configure_console_encoding()
	assert len(reconfigured) == 2
	assert reconfigured[0]["encoding"] == "utf-8"
	assert reconfigured[0]["errors"] == "replace"
