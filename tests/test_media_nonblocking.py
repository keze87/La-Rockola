"""Verifica que /cover y /lrc no bloqueen el event loop de asyncio durante I/O lento (SAF/Mutagen)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.api import media as media_mod
from app.main import app


@pytest.mark.anyio
async def test_serve_cover_does_not_block_event_loop(tmp_path: Path) -> None:
	audio_file = tmp_path / "lento.mp3"
	audio_file.write_bytes(b"fake-audio")
	media_mod._COVER_MEM_CACHE.clear()
	loop = asyncio.get_running_loop()
	callback_delays: list[float] = []

	def _slow_mutagen(*_args, **_kwargs):
		t0 = time.perf_counter()
		loop.call_soon_threadsafe(lambda: callback_delays.append(time.perf_counter() - t0))
		time.sleep(0.15)

	transport = httpx.ASGITransport(app=app)
	with patch.object(media_mod, "MutagenFile", side_effect=_slow_mutagen):
		async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
			res = await client.get(f"/cover?path={audio_file}&size=256")

	assert res.status_code == 404
	assert callback_delays, "No se ejecutó el callback del event loop"
	assert callback_delays[0] < 0.08, f"serve_cover bloqueó el event loop ({callback_delays[0]:.3f}s)"


@pytest.mark.anyio
async def test_serve_lrc_does_not_block_event_loop() -> None:
	saf_uri = "content://com.android.externalstorage.documents/tree/primary%3AMusic/document/primary%3AMusic%2Ftema.mp3"
	loop = asyncio.get_running_loop()
	callback_delays: list[float] = []

	class _SlowBackend:
		def read_sibling_lyrics(self, *_args, **_kwargs):
			t0 = time.perf_counter()
			loop.call_soon_threadsafe(lambda: callback_delays.append(time.perf_counter() - t0))
			time.sleep(0.15)

	class _FakeState:
		def __init__(self) -> None:
			self.path_to_id = {saf_uri: "id-1"}
			self.tracks_cache: list = []

		@staticmethod
		def is_radio_announcement(_path: str) -> bool:
			return False

	transport = httpx.ASGITransport(app=app)
	with (
		patch.object(media_mod, "get_container") as mock_container,
		patch.object(media_mod, "is_saf_uri", return_value=True),
		patch.object(media_mod, "get_storage_backend", return_value=_SlowBackend()),
	):
		mock_container.return_value.ensure_orchestrator.return_value = _FakeState()
		async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
			res = await client.get("/lrc", params={"path": saf_uri})

	assert res.status_code == 404
	assert callback_delays, "No se ejecutó el callback del event loop"
	assert callback_delays[0] < 0.08, f"serve_lrc bloqueó el event loop ({callback_delays[0]:.3f}s)"
