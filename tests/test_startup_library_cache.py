"""Pruebas de precarga instantánea de biblioteca desde SQLite al iniciar."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.core.container import get_container
from app.domain.library.service import LibraryService
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.infrastructure.db.migrations import apply_migrations
from app.infrastructure.db.repositories import TrackRepository
from app.main import create_app


def test_preload_cached_tracks_populates_state_filtered_by_music_dirs(tmp_path: Path) -> None:
	"""preload_cached_tracks debe cargar tracks desde SQLite filtrando por carpetas configuradas."""
	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)
	repo = TrackRepository(db_path)

	tree = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
	other_tree = "content://com.android.externalstorage.documents/tree/primary%3AOtra"
	song_ok = f"{tree}/document/primary%3AMusic%2Fzamba.mp3"
	song_other = f"{other_tree}/document/primary%3AOtra%2Ftango.mp3"
	repo.save_many(
		[
			("id-1", song_ok, "Zamba", "Folklore", "Carpincho", "03:10", 100.0, 4096, 110.0, 0.5, 1000.0, None, "ah-1"),
			("id-2", song_other, "Tango", "Ciudad", "Otro", "02:50", 100.0, 4096, 95.0, 0.4, 900.0, None, "ah-2"),
		]
	)

	orch = PlaybackOrchestrator(initial_dir=tree, db_path=db_path, use_mpv=False)
	count = LibraryService(db_path=db_path).preload_cached_tracks(orch, music_dirs=[tree])

	assert count == 1
	assert len(orch.tracks_cache) == 1
	assert orch.tracks_cache[0]["path"] == song_ok
	assert orch.tracks_cache[0]["display_title"] == "Zamba"
	assert orch.path_to_id[song_ok] == "id-1"
	assert orch.id_to_current_path["id-1"] == song_ok
	assert song_ok in orch.track_cache_by_path


def test_lifespan_serves_cached_library_before_background_scan_finishes(tmp_path: Path, monkeypatch) -> None:
	"""Al arrancar FastAPI lifespan, tracks_cache debe estar poblado desde DB antes de terminar scan_library."""
	music_dir = tmp_path / "music"
	music_dir.mkdir()
	song = music_dir / "tema.mp3"
	song.write_bytes(b"ID3")

	db_path = tmp_path / "rockola.db"
	apply_migrations(db_path)
	TrackRepository(db_path).save_many(
		[("id-cached", str(song), "Tema Cacheado", "Album", "Artista", "03:00", 1.0, 3, 0.0, 0.0, 0.0, None, "ah")]
	)

	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(tmp_path))
	config_mod.set_settings(config_mod.Settings(music_dir=str(music_dir), music_dir_configured=True, no_mpv=True))
	container = get_container()
	container.db_path = db_path

	async def slow_scan() -> None:
		await asyncio.sleep(5.0)

	monkeypatch.setattr("app.main.scan_library", slow_scan)

	app = create_app()
	with TestClient(app):
		orch = get_container().orchestrator
		assert orch is not None
		assert len(orch.tracks_cache) == 1
		assert orch.tracks_cache[0]["path"] == str(song)
		assert orch.path_to_id.get(str(song)) == "id-cached"
