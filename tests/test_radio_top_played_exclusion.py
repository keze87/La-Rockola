import sqlite3
import time
from unittest.mock import AsyncMock, patch

import pytest

import server
from server import APIState


@pytest.fixture
def clean_db(tmp_path):
	db_file = tmp_path / "test_rockola.db"
	orig_db = server.DB_PATH
	server.DB_PATH = str(db_file)
	server.init_db()
	yield db_file
	server.DB_PATH = orig_db


def test_register_play_stat_ignores_radio_announcement(clean_db):
	test_state = APIState()
	announcement_path = test_state.radio_announcement_path

	# Los intentos de registrar reproducciones en la ruta temporal de locución deben ser ignorados
	test_state._register_play_stat(announcement_path)

	with sqlite3.connect(server.DB_PATH) as conn:
		count = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
	assert count == 0


def test_legitimate_library_track_named_radio_announcement_is_tracked(clean_db, tmp_path):
	test_state = APIState()
	user_track = tmp_path / "radio_announcement.mp3"
	user_track.write_bytes(b"user music file")
	str_user_track = str(user_track)

	# Registrada en la biblioteca del usuario
	test_state.path_to_id[str_user_track] = "track_hash_123"
	test_state.id_to_current_path["track_hash_123"] = str_user_track

	# La pista legítima del usuario debe registrarse en el historial de reproducción
	test_state._register_play_stat(str_user_track)

	with sqlite3.connect(server.DB_PATH) as conn:
		row = conn.execute("SELECT track_id, COUNT(*) FROM play_history").fetchone()
	assert row[0] == "track_hash_123"
	assert row[1] == 1

	top = test_state.get_top_played()
	assert len(top) == 1
	assert top[0]["path"] == str_user_track


def test_register_play_stat_ignores_when_flag_active(clean_db):
	test_state = APIState()
	test_state.is_playing_radio_announcement = True

	# Aunque la ruta sea inusual, la bandera activa evita registrar estadísticas
	test_state._register_play_stat("/tmp/custom_announcement.wav")

	with sqlite3.connect(server.DB_PATH) as conn:
		count = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
	assert count == 0


@pytest.mark.asyncio
async def test_handle_song_ended_does_not_track_radio_announcement(clean_db):
	test_state = APIState()
	test_state.current_track = test_state.radio_announcement_path
	test_state.is_playing_radio_announcement = True

	with (
		patch.object(test_state, "play_next", new_callable=AsyncMock) as mock_play_next,
		patch("server.broadcast_state", new_callable=AsyncMock),
	):
		await test_state.handle_song_ended(reason="eof")
		mock_play_next.assert_awaited_once_with(skipped_by_user=False)

	with sqlite3.connect(server.DB_PATH) as conn:
		count = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
	assert count == 0


def test_get_top_played_excludes_radio_announcement(clean_db, tmp_path):
	test_state = APIState()
	announcement_path = tmp_path / "radio_announcement.mp3"
	announcement_path.write_bytes(b"dummy mp3")
	test_state.radio_announcement_path = str(announcement_path)

	real_track = tmp_path / "cancion.mp3"
	real_track.write_bytes(b"dummy track")

	now = time.time()
	with sqlite3.connect(server.DB_PATH) as conn:
		# Insertar filas tanto para la locución como para la canción real
		conn.execute(
			"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
			(str(announcement_path), now),
		)
		conn.execute(
			"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
			(str(announcement_path), now),
		)
		conn.execute(
			"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
			(str(real_track), now),
		)
		conn.commit()

	top = test_state.get_top_played()
	top_paths = [item["path"] for item in top]

	assert str(announcement_path) not in top_paths
	assert str(real_track) in top_paths


def test_init_db_cleans_legacy_radio_announcements(clean_db):
	# Insertar fila legacy en la base de datos
	with sqlite3.connect(server.DB_PATH) as conn:
		conn.execute(
			"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
			("/tmp/legacy/radio_announcement.mp3", time.time()),
		)
		conn.commit()

	# Re-ejecutar init_db
	server.init_db()

	with sqlite3.connect(server.DB_PATH) as conn:
		count = conn.execute(
			"SELECT COUNT(*) FROM play_history WHERE track_id LIKE '%radio_announcement.mp3%'"
		).fetchone()[0]

	assert count == 0


@pytest.mark.asyncio
async def test_cover_endpoint_does_not_hijack_user_song_named_radio_announcement(tmp_path):
	"""Garantiza que /cover no sirva la mascota del Carpincho para una canción legítima del usuario."""
	user_track = tmp_path / "radio_announcement.mp3"
	user_track.write_bytes(b"USER_AUDIO")
	str_track = str(user_track)

	server.state.path_to_id[str_track] = "hash_radio_song"
	server.state.id_to_current_path["hash_radio_song"] = str_track

	# Al solicitar cover para esta pista de usuario sin arte incrustado, debe responder 404 en vez del ícono del carpincho
	res = await server.serve_cover(path=str_track)
	assert res.status_code == 404, "serve_cover secuestró una pista legítima del usuario con la mascota del carpincho"


@pytest.mark.asyncio
async def test_stream_endpoint_rejects_unscanned_file_named_radio_announcement(tmp_path):
	"""Garantiza que /stream no permita archivos arbitrarios del sistema solo porque se llamen radio_announcement.mp3."""
	arbitrary_file = tmp_path / "radio_announcement.mp3"
	arbitrary_file.write_bytes(b"SECRET_DATA")
	str_file = str(arbitrary_file)

	# No está en la biblioteca del usuario ni coincide con la ruta temporal de la locución del servidor
	if str_file in server.state.path_to_id:
		del server.state.path_to_id[str_file]

	res = await server.stream_audio(path=str_file)
	assert res.status_code == 404, "stream_audio permitió un archivo no autorizado basado únicamente en el nombre"
