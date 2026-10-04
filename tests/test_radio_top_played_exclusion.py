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

	# Direct registration attempts on the temp announcement path should be ignored
	test_state._register_play_stat(announcement_path)

	with sqlite3.connect(server.DB_PATH) as conn:
		count = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
	assert count == 0


def test_legitimate_library_track_named_radio_announcement_is_tracked(clean_db, tmp_path):
	test_state = APIState()
	user_track = tmp_path / "radio_announcement.mp3"
	user_track.write_bytes(b"user music file")
	str_user_track = str(user_track)

	# Registered in user library
	test_state.path_to_id[str_user_track] = "track_hash_123"
	test_state.id_to_current_path["track_hash_123"] = str_user_track

	# Legitimate track must be recorded in play history
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

	# Even if path is unusual, flag prevents tracking
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
		# Insert rows for both announcement and real song
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
	# Insert legacy row into database
	with sqlite3.connect(server.DB_PATH) as conn:
		conn.execute(
			"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
			("/tmp/legacy/radio_announcement.mp3", time.time()),
		)
		conn.commit()

	# Re-run init_db
	server.init_db()

	with sqlite3.connect(server.DB_PATH) as conn:
		count = conn.execute(
			"SELECT COUNT(*) FROM play_history WHERE track_id LIKE '%radio_announcement.mp3%'"
		).fetchone()[0]

	assert count == 0
