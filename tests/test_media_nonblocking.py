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
	from app.core import config as config_mod

	config_mod.set_settings(config_mod.Settings(music_dir=str(tmp_path), music_dir_configured=True))
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
	from app.core import config as config_mod
	from app.core.container import get_container

	tree_uri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
	saf_uri = f"{tree_uri}/document/primary%3AMusic%2Ftema.mp3"
	config_mod.set_settings(config_mod.Settings(music_dir=tree_uri, music_dir_configured=True))
	loop = asyncio.get_running_loop()
	callback_delays: list[float] = []

	class _SlowBackend:
		def read_sibling_lyrics(self, *_args, **_kwargs):
			t0 = time.perf_counter()
			loop.call_soon_threadsafe(lambda: callback_delays.append(time.perf_counter() - t0))
			time.sleep(0.15)

	class _FakeState:
		def __init__(self) -> None:
			self.initial_dir = tree_uri
			self.secondary_dir = None
			self.path_to_id = {saf_uri: "id-1"}
			self.tracks_cache: list = []

		@staticmethod
		def is_radio_announcement(_path: str) -> bool:
			return False

	get_container().orchestrator = _FakeState()
	transport = httpx.ASGITransport(app=app)
	with (
		patch.object(media_mod, "is_saf_uri", return_value=True),
		patch.object(media_mod, "get_storage_backend", return_value=_SlowBackend()),
	):
		async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
			res = await client.get("/lrc", params={"path": saf_uri})

	assert res.status_code == 404
	assert callback_delays, "No se ejecutó el callback del event loop"
	assert callback_delays[0] < 0.08, f"serve_lrc bloqueó el event loop ({callback_delays[0]:.3f}s)"


def test_cover_path_locks_reused_while_held_and_collected_when_released() -> None:
	"""_COVER_PATH_LOCKS (WeakValueDictionary) conserva el lock en uso y libera entradas sin referencias."""
	import gc

	media_mod._COVER_PATH_LOCKS.clear()
	lock_a = media_mod._get_cover_path_lock("/music/a.mp3")
	assert media_mod._get_cover_path_lock("/music/a.mp3") is lock_a
	del lock_a
	gc.collect()
	assert "/music/a.mp3" not in media_mod._COVER_PATH_LOCKS
