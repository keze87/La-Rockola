"""
Pruebas TDD para almacenamiento Android SAF (content://), fd streaming,
letras/metadatos sin copiar biblioteca y detección honesta de carpeta inicial.
"""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.websocket import ConnectionManager
from app.core import config as config_mod
from app.core.container import AppContainer, set_container
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.infrastructure.db.migrations import apply_migrations
from app.main import create_app


def _build_minimal_mp3_with_id3(path: Path, title: str, artist: str) -> Path:
	"""Crea un archivo MP3 mínimo válido con tags ID3v2.3 (TIT2 y TPE1) y frames MPEG."""

	def _text_frame(frame_id: str, text: str) -> bytes:
		payload = b"\x03" + text.encode("utf-8")
		return frame_id.encode("ascii") + struct.pack(">I", len(payload)) + b"\x00\x00" + payload

	frames = _text_frame("TIT2", title) + _text_frame("TPE1", artist)
	size = len(frames)
	syncsafe = bytes(
		[
			(size >> 21) & 0x7F,
			(size >> 14) & 0x7F,
			(size >> 7) & 0x7F,
			size & 0x7F,
		]
	)
	id3_header = b"ID3\x03\x00\x00" + syncsafe + frames
	# Frame MPEG1 Layer3 128kbps 44100Hz (~417 bytes cada uno)
	mp3_frame = b"\xff\xfb\x90\x00" + (b"\x00" * 413)
	path.write_bytes(id3_header + (mp3_frame * 20))
	return path


class _FakeAndroidStorageBridge:
	"""Simula AndroidStorageBridge.kt usando archivos reales y file descriptors POSIX."""

	def __init__(self, trees: dict[str, dict[str, object]]) -> None:
		self.trees = trees
		self.docs: dict[str, Path] = {}
		self.siblings: dict[str, tuple[str, str]] = {}
		self.validation_status: dict[str, str] = {}
		for tree_uri, meta in trees.items():
			self.validation_status[tree_uri] = str(meta.get("status", "ok"))
			for item in meta.get("files", []):  # type: ignore[union-attr]
				self.docs[str(item["uri"])] = item["real_path"]  # type: ignore[index]
				if "sibling_lyrics" in item:
					self.siblings[str(item["uri"])] = item["sibling_lyrics"]  # type: ignore[index]

	def validateTreeUriJson(self, uri: str | None) -> str:
		if not uri:
			return json.dumps({"status": "unconfigured", "uri": "", "display_name": None, "error": None})
		if not uri.startswith("content://"):
			return json.dumps(
				{
					"status": "unsupported_provider",
					"uri": uri,
					"display_name": None,
					"error": "URI no soportada",
				}
			)
		status = self.validation_status.get(uri, "permission_denied")
		meta = self.trees.get(uri, {})
		return json.dumps(
			{
				"status": status,
				"uri": uri,
				"display_name": meta.get("display_name"),
				"error": None if status == "ok" else f"Estado: {status}",
			}
		)

	def listAudioFilesJson(self, tree_uri: str) -> str:
		if self.validation_status.get(tree_uri) != "ok":
			return "[]"
		meta = self.trees.get(tree_uri, {})
		entries = []
		for item in meta.get("files", []):  # type: ignore[union-attr]
			real_p: Path = item["real_path"]  # type: ignore[assignment]
			st = real_p.stat()
			entries.append(
				{
					"uri": item["uri"],
					"name": item["name"],
					"relative_path": item["relative_path"],
					"size": st.st_size,
					"mtime": int(st.st_mtime * 1000),
					"mime_type": "audio/mpeg",
				}
			)
		return json.dumps(entries)

	def statDocumentJson(self, doc_uri: str) -> str | None:
		p = self.docs.get(doc_uri)
		if p is None or not p.is_file():
			return None
		st = p.stat()
		return json.dumps(
			{"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime * 1000), "mime_type": "audio/mpeg"}
		)

	def openFileDescriptorForRead(self, doc_uri: str) -> int:
		p = self.docs.get(doc_uri)
		if p is None or not p.is_file():
			return -1
		return os.open(str(p), os.O_RDONLY)

	def findSiblingTextJson(self, doc_uri: str, extensions_csv: str) -> str | None:
		sib = self.siblings.get(doc_uri)
		if not sib:
			return None
		ext, content = sib
		allowed = [e.strip().lower() for e in extensions_csv.split(",") if e.strip()]
		if ext.lower() not in allowed:
			return None
		return json.dumps({"ext": ext, "content": content})


def test_fresh_android_install_leaves_music_dir_unconfigured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""En Android nuevo sin carpeta legible no debe fingir ~/Music ni una ruta inexistente."""
	from app import android_entry

	monkeypatch.setenv("ANDROID_ROOT", "/system")
	monkeypatch.setattr(sys, "platform", "linux")
	monkeypatch.setattr(config_mod, "_ANDROID_MUSIC_CANDIDATES", (str(tmp_path / "missing_music"),))

	assert config_mod.get_default_music_dir() == ""

	data_dir = tmp_path / "data"
	dist_dir = tmp_path / "dist"
	(dist_dir / "assets").mkdir(parents=True)
	data_dir.mkdir()

	info = android_entry.configure_android_environment(
		data_dir=str(data_dir),
		dist_dir=str(dist_dir),
		music_dir="",
		port=1830,
	)
	assert info["music_dir"] == ""
	assert info["music_dir_configured"] is False
	saved = json.loads((data_dir / "rockola_config.json").read_text(encoding="utf-8"))
	assert saved["music_dir"] == ""
	assert saved["music_dir_configured"] is False


def test_legacy_explicit_music_dir_preserves_configured_flag(tmp_path: Path) -> None:
	"""Un rockola_config.json previo con music_dir explícito conserva music_dir_configured=True."""
	legacy_music = tmp_path / "MiMusica"
	legacy_music.mkdir()
	cfg_path = tmp_path / "rockola_config.json"
	cfg_path.write_text(json.dumps({"music_dir": str(legacy_music)}), encoding="utf-8")

	settings = config_mod.Settings.from_config_file(cfg_path)
	assert settings.music_dir == str(legacy_music)
	assert settings.music_dir_configured is True


def test_saf_storage_scan_stream_range_lyrics_and_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	"""Verifica escaneo SAF, Mutagen por fd, HTTP 206 Range en /stream, letras y estado de carpeta."""
	from app.infrastructure.storage import backend as storage_mod

	mp3_real = _build_minimal_mp3_with_id3(tmp_path / "zamba_del_delta.mp3", "Zamba del Delta", "Los Carpinchos")
	tree_uri = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
	doc_uri = f"{tree_uri}/document/ABCD-1234%3AMusic%2Fzamba_del_delta.mp3"

	fake_bridge = _FakeAndroidStorageBridge(
		trees={
			tree_uri: {
				"status": "ok",
				"display_name": "Musica SD",
				"files": [
					{
						"uri": doc_uri,
						"name": "zamba_del_delta.mp3",
						"relative_path": "zamba_del_delta.mp3",
						"real_path": mp3_real,
						"sibling_lyrics": (".lrc", "[00:02.00]Río Paraná"),
					}
				],
			}
		}
	)
	monkeypatch.setenv("ANDROID_ROOT", "/system")
	monkeypatch.setattr(storage_mod, "get_android_storage_bridge", lambda: fake_bridge)

	db_path = tmp_path / "saf.db"
	apply_migrations(db_path)
	cfg_file = tmp_path / "rockola_config.json"
	monkeypatch.setattr(config_mod, "get_config_path", lambda: cfg_file)
	monkeypatch.setenv("ROCKOLA_DIST_DIR", str(tmp_path / "dist"))
	(tmp_path / "dist").mkdir()

	orch = PlaybackOrchestrator(initial_dir=tree_uri, db_path=db_path, open_browser=False, use_mpv=False)
	set_container(AppContainer(db_path=db_path, orchestrator=orch, ws_manager=ConnectionManager()))

	scanned = orch.scan_directory([tree_uri], extract_mood=False, extract_fingerprint=False)
	assert len(scanned) == 1
	assert scanned[0]["path"] == doc_uri
	assert scanned[0]["title"] == "Zamba del Delta"
	assert scanned[0]["artist"] == "Los Carpinchos"
	orch.tracks_cache = scanned
	orch.path_to_id[doc_uri] = scanned[0]["track_hash"]

	app = create_app()
	client = TestClient(app)

	# POST /system/music-dir acepta content:// SAF URI sin corromperlo con Path()
	with patch("app.api.system.scan_library", new_callable=AsyncMock):
		dir_res = client.post("/api/v1/system/music-dir", json={"dir": tree_uri})
	assert dir_res.status_code == 200
	assert dir_res.json()["music_dir"] == tree_uri
	assert dir_res.json()["folder_status"] == "ok"

	# GET /system/info expone estado y display_name
	sys_info = client.get("/api/v1/system/info")
	assert sys_info.status_code == 200
	info_body = sys_info.json()
	assert info_body["music_dir"] == tree_uri
	assert info_body["music_dir_configured"] is True
	assert info_body["folder_status"] == "ok"
	assert info_body["folder_display_name"] == "Musica SD"

	# GET /stream con Range devuelve 206 Partial Content desde el fd
	raw_bytes = mp3_real.read_bytes()
	stream_res = client.get("/api/v1/stream", params={"path": doc_uri}, headers={"Range": "bytes=0-15"})
	assert stream_res.status_code == 206
	assert stream_res.content == raw_bytes[:16]
	assert stream_res.headers["content-range"] == f"bytes 0-15/{len(raw_bytes)}"

	# GET /lrc sirve letra hermana .lrc vía SAF
	lrc_res = client.get("/api/v1/lrc", params={"path": doc_uri})
	assert lrc_res.status_code == 200
	assert "Río Paraná" in lrc_res.text

	# Simula revocación de permiso o extracción de tarjeta SD
	fake_bridge.validation_status[tree_uri] = "permission_denied"
	revoked_info = client.get("/api/v1/system/info")
	assert revoked_info.status_code == 200
	assert revoked_info.json()["folder_status"] == "permission_denied"

	fake_bridge.validation_status[tree_uri] = "storage_unavailable"
	unavail_info = client.get("/api/v1/system/info")
	assert unavail_info.status_code == 200
	assert unavail_info.json()["folder_status"] == "storage_unavailable"
