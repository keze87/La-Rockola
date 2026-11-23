"""Tests TDD para streaming SAF, seekability real (_NamedBinaryStream) y HTTP Range."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.core.container import get_container
from app.infrastructure.storage.backend import _NamedBinaryStream
from app.main import create_app

TREE_OK = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
TRACK_URI = f"{TREE_OK}/document/ABCD-1234%3AMusic%2Ftema.mp3"


def _setup_saf_client(monkeypatch: pytest.MonkeyPatch, bridge: object) -> TestClient:
	config_mod.set_settings(config_mod.Settings(music_dir=TREE_OK, music_dir_configured=True, no_mpv=True))
	get_container().orchestrator = SimpleNamespace(
		initial_dir=TREE_OK,
		secondary_dir=None,
		tracks_cache=[{"path": TRACK_URI, "id": "t1"}],
		path_to_id={TRACK_URI: "t1"},
		queue=[],
		current_track=TRACK_URI,
		is_radio_announcement=lambda _p: False,
	)
	app = create_app()
	return TestClient(app)


def test_named_binary_stream_reflects_real_seekable_on_pipe() -> None:
	"""_NamedBinaryStream.seekable() debe reflejar la capacidad real del descriptor (False en pipes)."""
	r_fd, w_fd = os.pipe()
	try:
		os.write(w_fd, b"hola pipe")
		os.close(w_fd)
		with os.fdopen(r_fd, "rb") as raw_pipe:
			wrapped = _NamedBinaryStream(raw_pipe, "pipe.mp3")
			assert wrapped.seekable() is False
	except Exception:
		try:
			os.close(r_fd)
		except OSError:
			pass
		raise


def test_saf_stream_supports_initial_open_suffix_and_invalid_ranges(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""Soporta bytes=0-9, bytes=10-, bytes=-5 y rechaza rangos inválidos con 416."""
	payload = bytes(range(200))
	real_file = tmp_path / "tema.mp3"
	real_file.write_bytes(payload)

	class _SeekableBridge:
		def isAuthorizedDocumentUri(self, doc: str, *_a: object) -> bool:
			return doc == TRACK_URI

		def statDocumentJson(self, _doc: str) -> str:
			return f'{{"name": "tema.mp3", "size": {len(payload)}, "mtime": 1000.0}}'

		def openFileDescriptorForRead(self, _doc: str) -> int:
			return os.open(real_file, os.O_RDONLY)

	client = _setup_saf_client(monkeypatch, _SeekableBridge())
	with patch("app.infrastructure.storage.backend.get_android_storage_bridge", return_value=_SeekableBridge()):
		r1 = client.get("/stream", params={"path": TRACK_URI}, headers={"Range": "bytes=0-9"})
		assert r1.status_code == 206
		assert r1.content == payload[0:10]
		assert r1.headers["content-range"] == f"bytes 0-9/{len(payload)}"

		r2 = client.get("/stream", params={"path": TRACK_URI}, headers={"Range": "bytes=190-"})
		assert r2.status_code == 206
		assert r2.content == payload[190:]
		assert r2.headers["content-range"] == f"bytes 190-199/{len(payload)}"

		r3 = client.get("/stream", params={"path": TRACK_URI}, headers={"Range": "bytes=-5"})
		assert r3.status_code == 206
		assert r3.content == payload[-5:]
		assert r3.headers["content-range"] == f"bytes 195-199/{len(payload)}"

		r4 = client.get("/stream", params={"path": TRACK_URI}, headers={"Range": "bytes=500-600"})
		assert r4.status_code == 416


def test_saf_stream_handles_non_seekable_unknown_size_zero_size_and_missing_file(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Maneja streams no seekables (pipe), tamaño desconocido (None), 0 bytes y desaparición al abrir."""
	payload = b"AUDIO_STREAM_DATA_1234567890"

	class _NonSeekableUnknownSizeBridge:
		def isAuthorizedDocumentUri(self, doc: str, *_a: object) -> bool:
			return doc == TRACK_URI

		def statDocumentJson(self, _doc: str) -> str:
			return '{"name": "tema.mp3", "size": null, "mtime": null}'

		def openFileDescriptorForRead(self, _doc: str) -> int:
			r_fd, w_fd = os.pipe()
			os.write(w_fd, payload)
			os.close(w_fd)
			return r_fd

	client = _setup_saf_client(monkeypatch, _NonSeekableUnknownSizeBridge())
	with patch(
		"app.infrastructure.storage.backend.get_android_storage_bridge", return_value=_NonSeekableUnknownSizeBridge()
	):
		r_full = client.get("/stream", params={"path": TRACK_URI})
		assert r_full.status_code == 200
		assert r_full.content == payload
		assert r_full.headers.get("accept-ranges") == "none"
		assert "content-length" not in r_full.headers

		# Aunque llegue Range con tamaño desconocido no-seekable, responde 200 secuencial sin inventar Content-Length
		for rng in ("bytes=0-", "bytes=100-200", "bytes=-5"):
			r_rng = client.get("/stream", params={"path": TRACK_URI}, headers={"Range": rng})
			assert r_rng.status_code == 200
			assert r_rng.content == payload
			assert r_rng.headers.get("accept-ranges") == "none"
			assert "content-length" not in r_rng.headers

	class _ZeroSizeBridge:
		def isAuthorizedDocumentUri(self, doc: str, *_a: object) -> bool:
			return doc == TRACK_URI

		def statDocumentJson(self, _doc: str) -> str:
			return '{"name": "tema.mp3", "size": 0, "mtime": 1000.0}'

		def openFileDescriptorForRead(self, _doc: str) -> int:
			return os.open("/dev/null", os.O_RDONLY)

	with patch("app.infrastructure.storage.backend.get_android_storage_bridge", return_value=_ZeroSizeBridge()):
		r_zero = client.get("/stream", params={"path": TRACK_URI})
		assert r_zero.status_code == 200
		assert r_zero.content == b""
		assert r_zero.headers["content-length"] == "0"
		r_zero_range = client.get("/stream", params={"path": TRACK_URI}, headers={"Range": "bytes=0-1"})
		assert r_zero_range.status_code == 416

	class _VanishedBridge:
		def isAuthorizedDocumentUri(self, doc: str, *_a: object) -> bool:
			return doc == TRACK_URI

		def statDocumentJson(self, _doc: str) -> str:
			return '{"name": "tema.mp3", "size": 100, "mtime": 1000.0}'

		def openFileDescriptorForRead(self, _doc: str) -> int:
			return -1

	with patch("app.infrastructure.storage.backend.get_android_storage_bridge", return_value=_VanishedBridge()):
		r_gone = client.get("/stream", params={"path": TRACK_URI})
		assert r_gone.status_code == 404
