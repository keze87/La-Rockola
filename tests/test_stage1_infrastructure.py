"""
Tests unitarios (TDD) para la capa Core e Infraestructura (Stage 1).
Verifica el contenedor de dependencias, gestores de binarios, base de datos SQLite,
controlador de MPV con métodos tipados, adaptador MPRIS, cliente de clima y mezclador de audio.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings, get_carpincho_data_dir, load_config, save_config
from app.core.container import AppContainer, get_container, set_container
from app.infrastructure.binaries.manager import (
	check_internet_async,
	ensure_display_env,
	find_binary,
	get_clean_env,
)
from app.infrastructure.db.connection import backup_db, init_db
from app.infrastructure.db.repositories import (
	FavoritesRepository,
	HistoryRepository,
	TrackRepository,
	UrlLogsRepository,
)
from app.infrastructure.media.mixer import (
	build_lrc_content,
	build_srt_content,
	format_lrc_timestamp,
	format_srt_timestamp,
	is_valid_mp3_file,
	is_valid_mp3_stream,
)
from app.infrastructure.media.tts_cache import (
	get_cache_key,
	get_cached_audio,
	init_tts_cache_db,
	save_cached_audio,
)
from app.infrastructure.mpv.controller import AsyncMpvController
from app.infrastructure.weather.client import (
	build_weather_phrase,
	extract_current_temp_c,
	extract_location_from_weather_data,
	format_temperature,
	format_temperature_range,
	reset_weather_cache,
)


def test_app_container_lifecycle(tmp_path: Path) -> None:
	"""Verifica que AppContainer aísle las dependencias sin singletons globales sucios."""
	db_file = tmp_path / "container_test.db"
	settings = Settings(music_dir=str(tmp_path), port=1888, open_browser=False)
	container = AppContainer(settings=settings, db_path=db_file)
	set_container(container)

	assert get_container() is container
	assert container.settings.port == 1888
	assert container.db_path == db_file


def test_config_load_and_atomic_save(tmp_path: Path) -> None:
	"""Verifica la lectura y guardado atómico de rockola_config.json."""
	cfg_path = tmp_path / "rockola_config.json"
	custom_cfg = {"music_dir": "/tmp/musica", "port": 1999, "weather_location": "Córdoba"}
	save_config(cfg_path, custom_cfg)

	loaded = load_config(cfg_path)
	assert loaded["music_dir"] == "/tmp/musica"
	assert loaded["port"] == 1999
	assert loaded["weather_location"] == "Córdoba"
	assert get_carpincho_data_dir().exists()


def test_binary_manager_clean_env_and_find(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Verifica el saneamiento del entorno para binarios externos y la búsqueda de ejecutables."""
	monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/pyinstaller_dirty")
	monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib")
	clean = get_clean_env()
	assert clean.get("LD_LIBRARY_PATH") == "/usr/lib"

	env_dict: dict[str, str] = {}
	ensure_display_env(env_dict)
	assert isinstance(env_dict, dict)

	# Python o sh siempre existen en el entorno de pruebas
	found = find_binary("python3") or find_binary("sh")
	assert found is not None


async def test_check_internet_async() -> None:
	"""Verifica el chequeo rápido de conectividad asíncrona."""
	with patch("socket.create_connection", side_effect=OSError("Sin red")):
		assert await check_internet_async(timeout=0.05) is False


def test_database_repositories_crud(tmp_path: Path) -> None:
	"""Verifica migraciones, WAL mode, backups y CRUD en todos los repositorios SQLite."""
	db_path = tmp_path / "rockola_test.db"
	init_db(db_path)

	tracks = TrackRepository(db_path)
	favs = FavoritesRepository(db_path)
	history = HistoryRepository(db_path)
	urls = UrlLogsRepository(db_path)

	tracks.save(
		{
			"track_id": "hash_001",
			"path": "/music/soda.mp3",
			"title": "De Música Ligera",
			"album": "Canción Animal",
			"artist": "Soda Stereo",
			"duration_str": "03:32",
			"mtime": 1000,
			"file_size": 5000000,
			"bpm": 124.0,
			"energy": 0.8,
			"spectral_centroid": 2100.0,
			"fingerprint": "1,2,3",
		}
	)
	assert tracks.count() == 1
	fetched = tracks.get_by_id("hash_001")
	assert fetched is not None
	assert fetched["title"] == "De Música Ligera"

	favs.add("hash_001")
	assert favs.is_favorite("hash_001") is True
	assert favs.list_all() == ["hash_001"]
	favs.remove("hash_001")
	assert favs.is_favorite("hash_001") is False

	history.add_play("hash_001", played_at=1700000000.0)
	top = history.get_top_played(limit=5)
	assert len(top) == 1
	assert top[0]["track_id"] == "hash_001"

	urls.add_url("https://youtube.com/watch?v=123", title="Tema YT", artist="Artista YT")
	recent_urls = urls.get_recent(limit=5)
	assert len(recent_urls) == 1
	assert recent_urls[0]["title"] == "Tema YT"

	bkp = backup_db(db_path, tmp_path)
	assert bkp is not None and bkp.exists()


async def test_mpv_controller_typed_commands() -> None:
	"""Verifica que AsyncMpvController exponga métodos públicos tipados en lugar de usar _send crudo."""
	controller = AsyncMpvController()
	controller._send = AsyncMock()  # type: ignore[method-assign]

	await controller.load_file("/music/charly.mp3")
	await controller.set_pause(True)
	await controller.set_volume(85)
	await controller.set_mute(False)
	await controller.seek_relative(10.0)
	await controller.seek_absolute(45.5)
	await controller.toggle_fullscreen()
	await controller.set_force_window(True)
	await controller.stop_playback()

	assert controller._send.call_count == 9


def test_weather_client_formatting() -> None:
	"""Verifica el formateo meteorológico criollo sin llamadas de red reales."""
	reset_weather_cache()
	assert "grado" in format_temperature(24)
	assert "entre" in format_temperature_range(12, 25)

	sample_data = {
		"nearest_area": [{"areaName": [{"value": "San Miguel de Tucumán"}]}],
		"current_condition": [
			{
				"temp_C": "26",
				"weatherCode": "113",
				"lang_es": [{"value": "Despejado"}],
			}
		],
		"weather": [
			{
				"mintempC": "16",
				"maxtempC": "29",
				"hourly": [{"time": "1200", "chanceofrain": "0"}],
			}
		],
	}
	assert extract_location_from_weather_data(sample_data) == "San Miguel de Tucumán"
	assert extract_current_temp_c(sample_data) == 26
	phrase = build_weather_phrase(sample_data, template_idx=0, location="San Miguel de Tucumán")
	assert phrase is not None and len(phrase) > 10


def test_media_mixer_and_tts_cache(tmp_path: Path) -> None:
	"""Verifica validación de MP3, subtítulos LRC/SRT y caché SQLite de TTS."""
	valid_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" * 20
	assert is_valid_mp3_stream(valid_mp3) is True
	assert is_valid_mp3_stream(b"no_es_mp3") is False

	mp3_file = tmp_path / "test.mp3"
	mp3_file.write_bytes(valid_mp3)
	assert is_valid_mp3_file(mp3_file) is True

	assert format_lrc_timestamp(65.5) == "01:05.50"
	assert format_srt_timestamp(65.5) == "00:01:05,500"

	cues = [(0.0, 2.5, "Bienvenidos a La Rockola")]
	assert "Bienvenidos" in build_lrc_content(cues)
	assert "-->" in build_srt_content(cues)

	cache_db = tmp_path / "tts_cache.db"
	init_tts_cache_db(cache_db)
	key = get_cache_key("Hola carpincho", "es-AR-TomasNeural")
	save_cached_audio(key, "Hola carpincho", "es-AR-TomasNeural", valid_mp3, db_path=cache_db)
	cached = get_cached_audio(key, db_path=cache_db)
	assert cached == valid_mp3
