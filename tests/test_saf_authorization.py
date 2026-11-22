"""Tests de seguridad para restringir URIs SAF a la biblioteca autorizada en /stream, /cover, /lrc y lyrics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.core.container import get_container
from app.infrastructure.storage.backend import AndroidSafStorageBackend
from app.main import create_app

TREE_OK = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
VALID_TRACK = f"{TREE_OK}/document/ABCD-1234%3AMusic%2Fzamba.mp3"
OUTSIDE_SAME_PROVIDER = "content://com.android.externalstorage.documents/tree/ABCD-1234%3ADocuments/document/ABCD-1234%3ADocuments%2Fsecreto.txt"
FOLDER_URI = f"{TREE_OK}/document/ABCD-1234%3AMusic"
OTHER_PROVIDER = "content://com.android.providers.downloads.documents/document/42"
MISSING_IN_TREE = f"{TREE_OK}/document/ABCD-1234%3AMusic%2Fno_existe.mp3"
REVOKED_TRACK = f"{TREE_OK}/document/ABCD-1234%3AMusic%2Frevocado.mp3"


class _FakeBridge:
	def __init__(self, revoked: bool = False) -> None:
		self.revoked = revoked

	def isAuthorizedDocumentUri(self, doc_uri: str, _allowed_trees_json: str, _require_audio: bool = False) -> bool:
		if self.revoked:
			return False
		return doc_uri == VALID_TRACK

	def statFileJson(self, doc_uri: str) -> str:
		if doc_uri == VALID_TRACK and not self.revoked:
			return '{"exists": true, "mtime": 1700000000000, "size": 1024}'
		return '{"exists": false}'

	def openFileDescriptorForRead(self, doc_uri: str) -> int:
		if doc_uri != VALID_TRACK or self.revoked:
			raise PermissionError("URI SAF no autorizada")
		raise AssertionError("No debería llegar a abrir fd en este test mockeado")

	def readSiblingLyrics(self, doc_uri: str, _exts: str) -> str:
		if doc_uri != VALID_TRACK or self.revoked:
			return ""
		return '{"ext": ".lrc", "content": "[00:01.00]Zamba"}'


@pytest.mark.parametrize(
	("target_uri", "expected_status", "revoked"),
	[
		(OUTSIDE_SAME_PROVIDER, 403, False),
		(FOLDER_URI, 403, False),
		(OTHER_PROVIDER, 403, False),
		(MISSING_IN_TREE, 403, False),
		(REVOKED_TRACK, 403, True),
	],
)
def test_media_and_lyrics_endpoints_reject_unauthorized_saf_uris(
	monkeypatch: pytest.MonkeyPatch,
	target_uri: str,
	expected_status: int,
	revoked: bool,
) -> None:
	"""Las rutas /stream, /cover, /lrc y /api/v1/lyrics/content deben rechazar URIs SAF fuera de la biblioteca."""
	container = get_container()
	config_mod.set_settings(config_mod.Settings(music_dir=TREE_OK, music_dir_configured=True, no_mpv=True))
	fake_orch = SimpleNamespace(
		initial_dir=TREE_OK,
		secondary_dir=None,
		tracks_cache=[{"path": VALID_TRACK, "id": "t1"}],
		path_to_id={VALID_TRACK: "t1"},
		queue=[],
		current_track=VALID_TRACK,
		is_radio_announcement=lambda _p: False,
	)
	container.orchestrator = fake_orch
	bridge = _FakeBridge(revoked=revoked)

	app = create_app()
	client = TestClient(app)

	with patch("app.infrastructure.storage.backend.get_android_storage_bridge", return_value=bridge):
		assert client.get("/stream", params={"path": target_uri}).status_code == expected_status
		assert client.get("/cover", params={"path": target_uri}).status_code == expected_status
		assert client.get("/lrc", params={"path": target_uri}).status_code == expected_status
		assert client.get("/api/v1/lyrics/content", params={"path": target_uri}).status_code == expected_status


def test_saf_storage_backend_blocks_open_binary_and_stat_for_unauthorized_uri(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""AndroidSafStorageBackend debe rechazar stat_file y open_binary si el bridge niega autorización."""
	config_mod.set_settings(config_mod.Settings(music_dir=TREE_OK, music_dir_configured=True, no_mpv=True))
	get_container().orchestrator = SimpleNamespace(
		initial_dir=TREE_OK,
		secondary_dir=None,
		tracks_cache=[{"path": VALID_TRACK}],
		current_track=None,
		queue=[],
	)
	bridge = _FakeBridge(revoked=False)
	backend = AndroidSafStorageBackend()

	with patch("app.infrastructure.storage.backend.get_android_storage_bridge", return_value=bridge):
		assert backend.stat_file(OUTSIDE_SAME_PROVIDER) is None
		with pytest.raises(PermissionError):
			backend.open_binary(OUTSIDE_SAME_PROVIDER)
