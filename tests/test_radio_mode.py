from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server import CommandRequest, app, handle_command, state


@pytest.fixture(autouse=True)
def reset_radio_state(tmp_path):
	orig_radio = state.radio_mode_enabled
	orig_counter = state.radio_track_counter
	orig_until = state.radio_tracks_until_next
	orig_playing = state.is_playing_radio_announcement
	orig_path = state.radio_announcement_path
	state.radio_mode_enabled = True
	state.radio_track_counter = 0
	state.radio_tracks_until_next = 2
	state.is_playing_radio_announcement = False
	state.radio_announcement_path = str(tmp_path / "radio.mp3")
	state.radio_pregenerated_path = str(tmp_path / "radio_pregenerated.mp3")
	state.pregenerated_radio_announcement = None
	state._cancel_radio_pregeneration()
	state.queue = []

	state.history = []
	state.current_track = None
	state.mpv = MagicMock()
	state.mpv._send = AsyncMock()
	state.mpv.is_running = True
	try:
		yield
	finally:
		state._cancel_radio_pregeneration()
		state.radio_mode_enabled = orig_radio
		state.radio_track_counter = orig_counter
		state.radio_tracks_until_next = orig_until
		state.is_playing_radio_announcement = orig_playing
		state.radio_announcement_path = orig_path


@pytest.mark.asyncio
async def test_toggle_radio_mode_command():
	req = CommandRequest(cmd="toggle_radio_mode")
	# Starts enabled -> toggle turns it off
	await handle_command(req)
	assert state.radio_mode_enabled is False

	# Toggle back on
	await handle_command(req)
	assert state.radio_mode_enabled is True
	assert state.radio_track_counter == 0
	assert 1 <= state.radio_tracks_until_next <= 2

	# Explicit state to False
	req_explicit = CommandRequest(cmd="toggle_radio_mode", state=False)
	await handle_command(req_explicit)
	assert state.radio_mode_enabled is False


def test_state_to_dict_includes_radio_fields():
	d = state.get_full_state_dict()
	assert "radio_mode_enabled" in d
	assert "is_synthesizing_radio" in d
	assert "is_playing_radio_announcement" in d
	assert "has_edge_tts" in d
	assert d["radio_mode_enabled"] is True


@pytest.mark.asyncio
async def test_play_next_increments_counter_and_triggers_radio():
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/song2.mp3"]
	state.current_track = "/music/song1.mp3"

	mock_create = AsyncMock(return_value=(True, "Momento de la Fortuna 🥠 (Tomás)", "Son las 15 horas..."))

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", side_effect=fake_play_track) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# Normal track was appended to history
		assert "/music/song1.mp3" in state.history

		# Radio announcement was triggered
		mock_create.assert_awaited_once_with(
			state.radio_announcement_path,
			bg_track_path="/music/song2.mp3",
			bg_offset=0.0,
			bg_volume=0.1,
			weather_location=state.weather_location,
		)
		assert state.is_playing_radio_announcement is True
		assert state.current_track == state.radio_announcement_path
		mock_play.assert_awaited_once_with(state.radio_announcement_path)

		# Counter reset and new random threshold
		assert state.radio_track_counter == 0
		assert 2 <= state.radio_tracks_until_next <= 3


@pytest.mark.asyncio
async def test_radio_announcement_finished_does_not_enter_history():
	state.radio_mode_enabled = True
	state.current_track = state.radio_announcement_path
	state.is_playing_radio_announcement = True
	state.queue = ["/music/next_song.mp3"]

	with (
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		# Announcement finishes naturally
		await state.play_next(skipped_by_user=False)

		# Announcement must NOT be in history
		assert state.radio_announcement_path not in state.history
		assert state.is_playing_radio_announcement is False

		# Next track in queue plays
		mock_play.assert_awaited_once_with("/music/next_song.mp3")


@pytest.mark.asyncio
async def test_skip_during_radio_announcement():
	state.radio_mode_enabled = True
	state.current_track = state.radio_announcement_path
	state.is_playing_radio_announcement = True
	state.queue = ["/music/next_song.mp3"]

	with (
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		# User presses skip
		await state.play_next(skipped_by_user=True)

		assert state.radio_announcement_path not in state.history
		assert state.is_playing_radio_announcement is False
		mock_play.assert_awaited_once_with("/music/next_song.mp3")


@pytest.mark.asyncio
async def test_stop_cleans_up_radio_announcement():
	state.current_track = state.radio_announcement_path
	state.is_playing_radio_announcement = True

	req = CommandRequest(cmd="stop")
	await handle_command(req)

	assert state.radio_announcement_path not in state.history
	assert state.current_track is None
	assert state.is_playing_radio_announcement is False


@pytest.mark.asyncio
async def test_stream_allows_radio_announcement(tmp_path):
	from httpx import ASGITransport, AsyncClient

	audio_file = tmp_path / "radio.mp3"
	audio_file.write_bytes(b"ID3fakeaudiocontent")
	state.radio_announcement_path = str(audio_file)

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
		res = await ac.get(f"/stream?path={state.radio_announcement_path}")
		assert res.status_code == 200
		assert res.content == b"ID3fakeaudiocontent"


@pytest.mark.asyncio
async def test_cover_serves_favicon_for_radio_announcement(tmp_path):
	from httpx import ASGITransport, AsyncClient

	state.radio_announcement_path = str(tmp_path / "radio.mp3")

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
		res = await ac.get(f"/cover?path={state.radio_announcement_path}")
		# Si existe public/favicon.png retorna 200 con imagen png
		favicon_p = Path("public/favicon.png")
		if favicon_p.exists():
			assert res.status_code == 200
			assert res.headers.get("content-type") == "image/png"


@pytest.mark.asyncio
async def test_radio_announcement_failure_logs_reason(caplog):
	import logging

	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/song2.mp3"]
	state.current_track = "/music/song1.mp3"

	mock_create = AsyncMock(return_value=(False, "", "Fallo simulado de conexión"))

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
		caplog.at_level(logging.WARNING),
	):
		await state.play_next(skipped_by_user=False)

		# Synthesizing flag should be cleared
		assert state.is_synthesizing_radio is False
		assert state.is_playing_radio_announcement is False

		# The warning log must explain the failure reason
		assert any("Fallo simulado de conexión" in record.message for record in caplog.records)

		# Next track in queue plays because radio failed
		mock_play.assert_awaited_once_with("/music/song2.mp3")


@pytest.mark.asyncio
async def test_toggle_queue_initial_playback_does_not_trigger_radio():
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 1
	state.current_track = None
	state.queue = []

	mock_create = AsyncMock()

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.toggle_queue("/music/song1.mp3")

		# Locutor should NOT speak before any song has started playing
		mock_create.assert_not_called()
		mock_play.assert_awaited_once_with("/music/song1.mp3")


def test_radio_announcement_path_is_in_temp_dir():
	import tempfile

	from server import APIState

	new_state = APIState()
	assert Path(new_state.radio_announcement_path).parent == Path(tempfile.gettempdir())
	assert Path(new_state.radio_announcement_path).name == "radio_announcement.mp3"


def test_get_cover_art_uri_for_radio():
	from server import get_cover_art_uri, state

	uri = get_cover_art_uri(state.radio_announcement_path)
	assert uri.startswith("file://")
	assert uri.endswith("favicon.png")


@pytest.mark.asyncio
async def test_play_next_skips_radio_locution_when_no_internet():
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/song2.mp3"]
	state.current_track = "/music/song1.mp3"

	mock_create = AsyncMock()

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch("server.check_internet_async", AsyncMock(return_value=False)),
		patch.object(state, "play_track", AsyncMock()) as mock_play,
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# create_radio_announcement no debe llamarse
		mock_create.assert_not_called()
		# is_synthesizing_radio debe permanecer en False
		assert state.is_synthesizing_radio is False
		# El contador se reinicia y se sortea el próximo intervalo
		assert state.radio_track_counter == 0
		assert state.radio_tracks_until_next in (2, 3)
		# Pasa directamente al siguiente tema de la cola
		mock_play.assert_awaited_once_with("/music/song2.mp3")


@pytest.mark.asyncio
async def test_play_next_passes_configured_weather_location():
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/song2.mp3"]
	state.current_track = "/music/song1.mp3"
	state.weather_location = "Rosario, Santa Fe"

	mock_create = AsyncMock(return_value=(True, "Carpincho Locutor", "Locución"))

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch("server.check_internet_async", AsyncMock(return_value=True)),
		patch.object(state, "play_track", AsyncMock()),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		mock_create.assert_awaited_once_with(
			state.radio_announcement_path,
			bg_track_path="/music/song2.mp3",
			bg_offset=0.0,
			bg_volume=0.1,
			weather_location="Rosario, Santa Fe",
		)


@pytest.mark.asyncio
async def test_radio_pregeneration_starts_at_song_start(tmp_path):
	"""Verifica que si la próxima canción requerirá locutor, se dispare la pregeneración de fondo."""
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2  # (1 + 1) >= 2 -> Dispara pregeneración anticipada
	state.queue = ["/music/next_song.mp3"]

	mock_create = AsyncMock(return_value=(True, "Carpincho Pregenerado", "Discurso anticipado"))

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_track("/music/current_song.mp3")

		assert state.radio_pregeneration_task is not None
		await state.radio_pregeneration_task

		assert state.pregenerated_radio_announcement is not None
		assert state.pregenerated_radio_announcement["display_title"] == "Carpincho Pregenerado"
		mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_play_next_uses_pregenerated_announcement(tmp_path):
	"""Verifica que play_next use la locución pregenerada con 0 ms de latencia."""
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/next_song.mp3"]
	state.current_track = "/music/song1.mp3"

	# Simular locución pregenerada lista en disco
	pre_file = Path(state.radio_pregenerated_path)
	valid_mp3_payload = b"ID3\x04\x00\x00\x00\x00\x00\x00PREGENERATED_AUDIO_BYTES"
	pre_file.write_bytes(valid_mp3_payload)
	state.pregenerated_radio_announcement = {
		"path": state.radio_pregenerated_path,
		"display_title": "Carpincho Instantáneo",
		"script": "Texto pregenerado",
	}

	mock_create_live = AsyncMock()

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create_live),
		patch.object(state, "play_track", side_effect=fake_play_track),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# create_radio_announcement en vivo NO debe ser llamado porque ya estaba pregenerado
		mock_create_live.assert_not_called()
		assert state.is_playing_radio_announcement is True
		assert state.current_track == state.radio_announcement_path
		assert Path(state.radio_announcement_path).read_bytes() == valid_mp3_payload


@pytest.mark.asyncio
async def test_hot_bg_track_mixing_on_queue_change(tmp_path):
	"""Verifica que la mezcla de cortina musical se realice en caliente con la canción real si cambió la cola."""
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.current_track = "/music/song1.mp3"

	# Canción que se agrega en caliente a la cola antes de terminar la canción actual
	new_song = tmp_path / "new_chosen_song.mp3"
	new_song.write_bytes(b"NEW_SONG_AUDIO")
	state.queue = [str(new_song)]

	# Audio limpio pregenerado
	pre_file = Path(state.radio_pregenerated_path)
	pre_file.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00CLEAN_SPEECH_AUDIO")
	state.pregenerated_radio_announcement = {
		"path": state.radio_pregenerated_path,
		"display_title": "Carpincho en Vivo",
		"script": "Texto limpio",
	}

	mock_mix = MagicMock(return_value=True)
	mock_embed = MagicMock(return_value=True)

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.mix_announcement_with_bg_track", mock_mix),
		patch("server.embed_cover_art_in_mp3", mock_embed),
		patch.object(state, "play_track", side_effect=fake_play_track),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# Debe haberse ejecutado la mezcla en caliente con la nueva canción elegida
		mock_mix.assert_called_once()
		call_args = mock_mix.call_args
		# args: voice_file, out_file, next_track_path, bg_offset, bg_volume, timeout
		assert str(call_args[0][0]) == state.radio_pregenerated_path
		assert str(call_args[0][1]) == state.radio_announcement_path
		assert str(call_args[0][2]) == str(new_song)

		# Debe haberse embebido la portada del carpincho
		mock_embed.assert_called_once()
		assert state.is_playing_radio_announcement is True
		assert state.current_track == state.radio_announcement_path


@pytest.mark.asyncio
async def test_pregenerated_announcement_copies_subtitles_to_radio_announcement(tmp_path):
	"""Verifica que los subtítulos .lrc y .srt de la locución pregenerada se copien a radio_announcement."""
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.current_track = "/music/song1.mp3"

	new_song = tmp_path / "song.mp3"
	new_song.write_bytes(b"SONG_AUDIO")
	state.queue = [str(new_song)]

	# Audio y subtítulos pregenerados
	pre_file = Path(state.radio_pregenerated_path)
	pre_file.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00CLEAN_SPEECH_AUDIO")
	pre_lrc = pre_file.with_suffix(".lrc")
	pre_lrc.write_text("[00:00.15] Subtítulo pregenerado")
	pre_srt = pre_file.with_suffix(".srt")
	pre_srt.write_text("1\n00:00:00,150 --> 00:00:02,000\nSubtítulo pregenerado\n")

	state.pregenerated_radio_announcement = {
		"path": state.radio_pregenerated_path,
		"display_title": "Carpincho en Vivo",
		"script": "Texto limpio",
	}

	mock_mix = MagicMock(return_value=True)

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.mix_announcement_with_bg_track", mock_mix),
		patch("server.embed_cover_art_in_mp3", MagicMock()),
		patch.object(state, "play_track", AsyncMock()),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		announcement_lrc = Path(state.radio_announcement_path).with_suffix(".lrc")
		announcement_srt = Path(state.radio_announcement_path).with_suffix(".srt")

		assert announcement_lrc.is_file(), "El archivo .lrc de radio_announcement no fue copiado"
		assert announcement_lrc.read_text(encoding="utf-8") == "[00:00.15] Subtítulo pregenerado"
		assert announcement_srt.is_file(), "El archivo .srt de radio_announcement no fue copiado"


@pytest.mark.asyncio
async def test_pregenerated_announcement_expires_after_15_minutes(tmp_path):
	"""Verifica que una locución pregenerada con más de 15 minutos (ej. pausa prolongada) sea descartada y se re-sintetice fresca."""
	import time

	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/next_song.mp3"]
	state.current_track = "/music/song1.mp3"

	# Locución vieja generada hace 16 minutos (960 segundos)
	old_pre = Path(state.radio_pregenerated_path)
	old_pre.write_bytes(b"OLD_STALE_AUDIO")
	state.pregenerated_radio_announcement = {
		"path": state.radio_pregenerated_path,
		"display_title": "Carpincho Viejo",
		"script": "Texto viejo",
		"created_at": time.time() - 960.0,
	}

	mock_create_live = AsyncMock(return_value=(True, "Carpincho Fresco", "Texto fresco"))

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create_live),
		patch.object(state, "play_track", side_effect=fake_play_track),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# Debe descartar la locución vieja y disparar create_radio_announcement en vivo para audio fresco
		mock_create_live.assert_awaited_once()
		assert state.is_playing_radio_announcement is True
		assert state.current_track == state.radio_announcement_path
		assert state.pregenerated_radio_announcement is None


def test_cancel_radio_pregeneration_deletes_partial_file(tmp_path):
	"""Verifica que cancelar la pregeneración elimine cualquier archivo parcial dejado en disco."""
	partial_file = tmp_path / "radio_partial.mp3"
	partial_file.write_bytes(b"partial_ffmpeg_output")
	assert partial_file.exists()

	state.radio_pregenerated_path = str(partial_file)
	state._cancel_radio_pregeneration()

	assert not partial_file.exists()
	assert state.radio_pregeneration_task is None
	assert state.pregenerated_radio_announcement is None


@pytest.mark.asyncio
async def test_pregenerated_corrupt_file_rejected_falls_back_to_live(tmp_path):
	"""Verifica que un archivo pregenerado corrupto o truncado sea descartado por validación de stream MP3."""
	import time

	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/next_song.mp3"]
	state.current_track = "/music/song1.mp3"

	# Archivo con bytes que NO son MP3 válido
	corrupt_pre = tmp_path / "corrupt_pregenerated.mp3"
	corrupt_pre.write_bytes(b"NOT_A_VALID_MP3_STREAM_HEADER")
	state.radio_pregenerated_path = str(corrupt_pre)

	state.pregenerated_radio_announcement = {
		"path": str(corrupt_pre),
		"display_title": "Carpincho Corrupto",
		"script": "Texto corrupto",
		"created_at": time.time(),
	}

	from scripts.radio_announcer import RadioAnnouncementResult

	mock_create_live = AsyncMock(
		return_value=RadioAnnouncementResult(
			ok=True, display_title="Carpincho Fresco", script="Texto fresco", error=None
		)
	)

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create_live),
		patch.object(state, "play_track", side_effect=fake_play_track),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		# Debe descartar el pregenerado corrupto y disparar la síntesis en vivo
		mock_create_live.assert_awaited_once()
		assert state.is_playing_radio_announcement is True
		assert state.current_track == state.radio_announcement_path
		assert state.pregenerated_radio_announcement is None


def test_archive_radio_announcement_creates_txt_without_mp3(tmp_path):
	"""Verifica que _archive_radio_announcement guarde el guion .txt y no almacene MP3s en /tmp."""
	state.radio_archive_dir = tmp_path / "archive_test"
	sample_mp3 = tmp_path / "source_announcement.mp3"
	sample_mp3.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00SPEECH_DATA")

	dest_txt = state._archive_radio_announcement(
		src_mp3_path=sample_mp3,
		script_text="Buenas tardes carpinchos, son las cuatro.",
		display_title="Carpincho Locutor: Edición Central",
	)

	assert dest_txt is not None
	assert dest_txt.is_file()
	assert dest_txt.name.startswith("radio_")
	assert dest_txt.name.endswith(".txt")

	content = dest_txt.read_text(encoding="utf-8")
	assert "Buenas tardes carpinchos, son las cuatro." in content
	assert "Carpincho Locutor: Edición Central" in content

	# Confirmar que no se almacena ningún MP3 en el directorio de archivo histórico (/tmp)
	assert len(list(state.radio_archive_dir.glob("*.mp3"))) == 0


def test_prune_radio_archive_retention_limit(tmp_path):
	"""Verifica que la poda de retención elimine los guiones más viejos por encima del límite y limpie mp3s residuales."""
	import os
	import time

	state.radio_archive_dir = tmp_path / "archive_prune_test"
	state.radio_archive_dir.mkdir(parents=True, exist_ok=True)
	state.radio_archive_max_files = 3

	base_time = time.time() - 1000.0
	for i in range(5):
		txt = state.radio_archive_dir / f"radio_2026-09-30_10-00-0{i}.txt"
		txt.write_text(f"Guion {i}", encoding="utf-8")
		file_time = base_time + (i * 10.0)
		os.utime(txt, (file_time, file_time))

	# MP3 residual para asegurar que sea eliminado durante la poda
	residual_mp3 = state.radio_archive_dir / "radio_residual.mp3"
	residual_mp3.write_bytes(b"OLD_MP3")

	assert len(list(state.radio_archive_dir.glob("radio_*.txt"))) == 5
	assert residual_mp3.exists()

	pruned = state._prune_radio_archive(max_files=3)
	assert pruned == 2

	remaining_txts = sorted(state.radio_archive_dir.glob("radio_*.txt"))
	assert len(remaining_txts) == 3
	# Los 2 más viejos (0 y 1) fueron borrados; quedan 2, 3 y 4
	assert not any("10-00-00" in p.name for p in remaining_txts)
	assert not any("10-00-01" in p.name for p in remaining_txts)
	assert any("10-00-04" in p.name for p in remaining_txts)
	# MP3 residual eliminado
	assert not residual_mp3.exists()


@pytest.mark.asyncio
async def test_play_next_archives_announcement_and_script(tmp_path):
	"""Verifica que al sonar una locución en play_next se archive el guion sin duplicar MP3s en disco."""
	state.radio_archive_dir = tmp_path / "play_next_archive"
	state.radio_mode_enabled = True
	state.radio_track_counter = 1
	state.radio_tracks_until_next = 2
	state.queue = ["/music/next_song.mp3"]
	state.current_track = "/music/song1.mp3"

	Path(state.radio_announcement_path).write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00PLAY_NEXT_AUDIO")

	from scripts.radio_announcer import RadioAnnouncementResult

	mock_create = AsyncMock(
		return_value=RadioAnnouncementResult(
			ok=True,
			display_title="Carpincho Histórico",
			script="Guion histórico archivado",
			error=None,
		)
	)

	async def fake_play_track(path):
		state.current_track = path

	with (
		patch("server.HAS_EDGE_TTS", True),
		patch("server.create_radio_announcement", mock_create),
		patch.object(state, "play_track", side_effect=fake_play_track),
		patch("server.broadcast_state", AsyncMock()),
	):
		await state.play_next(skipped_by_user=False)

		archived_mp3s = list(state.radio_archive_dir.glob("radio_*.mp3"))
		archived_txts = list(state.radio_archive_dir.glob("radio_*.txt"))
		assert len(archived_mp3s) == 0
		assert len(archived_txts) == 1
		assert "Guion histórico archivado" in archived_txts[0].read_text(encoding="utf-8")
