import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import radio_announcer


def test_clean_fortune_text():
	raw = '  "El éxito no es la clave."  \n\n  -- Albert Schweitzer  https://example.com  <nick>  '
	cleaned = radio_announcer.clean_fortune_text(raw)
	assert "El éxito no es la clave." in cleaned
	assert "https://" not in cleaned
	assert "<nick>" not in cleaned


def test_is_spanish_text():
	assert radio_announcer.is_spanish_text("En muerte y en boda, verás quien te honra.") is True
	assert radio_announcer.is_spanish_text("A borrico desconocido, no le toques la oreja.") is True
	assert radio_announcer.is_spanish_text("El que madruga encuentra todo cerrado.") is True
	assert radio_announcer.is_spanish_text("Tranquilo como carpincho en Nordelta.") is True

	# English text must be rejected
	assert radio_announcer.is_spanish_text("I had pancake makeup for brunch!") is False
	assert (
		radio_announcer.is_spanish_text("The universe is an island, surrounded by whatever surrounds universes.")
		is False
	)
	assert radio_announcer.is_spanish_text("Linux: Because Software Problems Should Not Cost Money.") is False
	assert radio_announcer.is_spanish_text("The wise shepherd never trusts his flock to a smiling wolf.") is False
	assert radio_announcer.is_spanish_text("") is False


def test_get_system_fortune_no_binary():
	with patch("shutil.which", return_value=None):
		assert radio_announcer.get_system_fortune() is None


def test_get_system_fortune_success():
	with (
		patch("shutil.which", return_value="/usr/bin/fortune"),
		patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["refranes"]),
		patch(
			"subprocess.run",
			return_value=MagicMock(returncode=0, stdout="En muerte y en boda, verás quien te honra.\n"),
		),
	):
		res = radio_announcer.get_system_fortune()
		assert res == "En muerte y en boda, verás quien te honra."
		assert radio_announcer.is_spanish_text(res) is True


def test_get_system_fortune_rejects_english():
	with (
		patch("shutil.which", return_value="/usr/bin/fortune"),
		patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["refranes"]),
		patch(
			"subprocess.run",
			return_value=MagicMock(returncode=0, stdout="A witty saying proves nothing at all.\n"),
		),
	):
		# English text must return None so fallback activates
		res = radio_announcer.get_system_fortune()
		assert res is None


def test_get_system_fortune_too_short_or_long():
	with (
		patch("shutil.which", return_value="/usr/bin/fortune"),
		patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["refranes"]),
		patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="Hola")),
	):
		# Menos de 15 caracteres
		assert radio_announcer.get_system_fortune() is None

	with (
		patch("shutil.which", return_value="/usr/bin/fortune"),
		patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["refranes"]),
		patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="Hola carpincho " * 20)),
	):
		# Más de 160 caracteres
		assert radio_announcer.get_system_fortune() is None


def test_get_radio_fortune_is_always_spanish():
	# Debe devolver una cadena no vacía y 100% en español siempre
	for _ in range(25):
		fortune = radio_announcer.get_radio_fortune()
		assert isinstance(fortune, str)
		assert len(fortune) > 0
		assert radio_announcer.is_spanish_text(fortune) is True


def test_select_fortune():
	with patch("scripts.radio_announcer.get_system_fortune", return_value="En muerte y en boda, verás quien te honra."):
		f, is_sys = radio_announcer.select_fortune(force_system_fortune=True)
		assert f == "En muerte y en boda, verás quien te honra."
		assert is_sys is True

	f, is_sys = radio_announcer.select_fortune(force_system_fortune=False)
	assert f in radio_announcer.CARPINCHO_FORTUNES
	assert is_sys is False


def test_get_modular_time_segments():
	# Especial 01:00
	dt_one = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_one)
	assert h_seg == "Las una en punto, es hora de mimir."
	assert m_seg is None
	assert full == "Las una en punto, es hora de mimir."

	# Especial 00:00 (medianoche)
	dt_mid = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_mid)
	assert "Las doce de la noche en punto" in h_seg
	assert m_seg is None

	# Modular 15:23
	dt_mod = datetime(2026, 9, 26, 15, 23, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_mod)
	assert h_seg == "15 horas,"
	assert m_seg == "23 minutos."
	assert full == "15 horas, 23 minutos."

	# Modular 09:01
	dt_one_min = datetime(2026, 9, 26, 9, 1, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_one_min)
	assert h_seg == "9 horas,"
	assert m_seg == "un minuto."
	assert full == "9 horas, un minuto."

	# Modular 01:45
	dt_one_forty_five = datetime(2026, 9, 26, 1, 45, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_one_forty_five)
	assert h_seg == "1 hora,"
	assert m_seg == "45 minutos."
	assert full == "1 hora, 45 minutos."

	# Las 24 horas especiales deben existir y ser válidas en español
	assert len(radio_announcer.SPECIAL_HOURS) == 24
	for phrase in radio_announcer.SPECIAL_HOURS.values():
		assert isinstance(phrase, str)
		assert radio_announcer.is_spanish_text(phrase) is True


@pytest.mark.asyncio
async def test_create_radio_announcement_no_edge_tts(tmp_path):
	with patch("scripts.radio_announcer.HAS_EDGE_TTS", False):
		out_p = tmp_path / "test.mp3"
		ok, title, _text = await radio_announcer.create_radio_announcement(out_p)
		assert ok is False
		assert title == ""


@pytest.mark.asyncio
async def test_create_radio_announcement_success(tmp_path):
	out_p = tmp_path / "test.mp3"
	db_p = tmp_path / "tts_cache.db"

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
	):
		ok, title, text = await radio_announcer.create_radio_announcement(
			out_p,
			voice=radio_announcer.VOICE_TOMAS,
			db_path=db_p,
		)
		assert ok is True
		assert "Carpincho locutor:" in title
		assert len(text) > 0
		assert radio_announcer.is_spanish_text(text) is True
		assert out_p.exists()


@pytest.mark.asyncio
async def test_create_radio_announcement_timeout(tmp_path):
	out_p = tmp_path / "test.mp3"
	db_p = tmp_path / "tts_cache_empty.db"

	async def slow_save(*args, **kwargs):
		await asyncio.sleep(1.0)

	mock_comm = MagicMock()
	mock_comm.save = slow_save

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
	):
		ok, _title, _text = await radio_announcer.create_radio_announcement(out_p, timeout=0.01, db_path=db_p)
		assert ok is False


@pytest.mark.asyncio
async def test_create_radio_announcement_with_bg_track(tmp_path):
	song_p = tmp_path / "song.mp3"
	out_p = tmp_path / "radio.mp3"
	db_p = tmp_path / "tts_cache.db"
	song_p.write_bytes(b"DUMMY_SONG_DATA")

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
		patch("scripts.radio_announcer.mix_announcement_with_bg_track", return_value=True) as mock_mix,
		patch("shutil.which", return_value="/usr/bin/ffmpeg"),
	):
		ok, title, _text = await radio_announcer.create_radio_announcement(
			out_p,
			voice=radio_announcer.VOICE_TOMAS,
			bg_track_path=song_p,
			bg_offset=45.0,
			bg_volume=0.1,
			db_path=db_p,
		)
		assert ok is True
		assert "Carpincho locutor:" in title
		mock_mix.assert_called_once()


@pytest.mark.asyncio
async def test_create_radio_announcement_with_bg_track_fallback(tmp_path):
	song_p = tmp_path / "song.mp3"
	out_p = tmp_path / "radio.mp3"
	db_p = tmp_path / "tts_cache.db"
	song_p.write_bytes(b"DUMMY_SONG_DATA")

	async def fake_save(dest):
		Path(dest).write_bytes(b"VOICE_AUDIO")

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(side_effect=fake_save)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
		patch("scripts.radio_announcer.mix_announcement_with_bg_track", return_value=False),
		patch("shutil.which", return_value="/usr/bin/ffmpeg"),
	):
		ok, title, _text = await radio_announcer.create_radio_announcement(
			out_p,
			voice=radio_announcer.VOICE_TOMAS,
			bg_track_path=song_p,
			bg_offset=45.0,
			bg_volume=0.1,
			db_path=db_p,
		)
		assert ok is True
		assert "Carpincho locutor:" in title
		assert out_p.exists()


def test_tts_cache_db_crud(tmp_path):
	db_path = tmp_path / "tts_cache.db"
	radio_announcer.init_tts_cache_db(db_path)
	assert db_path.exists()

	# Miss inicial
	cached = radio_announcer.get_cached_audio("intro", radio_announcer.VOICE_TOMAS, "Hola amigos", db_path=db_path)
	assert cached is None

	# Guardar audio
	audio_data = b"FAKE_AUDIO_DATA_FOR_CACHE"
	radio_announcer.save_cached_audio("intro", radio_announcer.VOICE_TOMAS, "Hola amigos", audio_data, db_path=db_path)

	# Hit posterior
	retrieved = radio_announcer.get_cached_audio("intro", radio_announcer.VOICE_TOMAS, "hola amigos  ", db_path=db_path)
	assert retrieved == audio_data


@pytest.mark.asyncio
async def test_synthesize_segment_caching(tmp_path):
	db_path = tmp_path / "tts_cache.db"
	voice = radio_announcer.VOICE_TOMAS
	text = "En el aire de La Rockola del Carpincho,"

	async def fake_save(dest):
		Path(dest).write_bytes(b"CACHED_AUDIO_TEST")

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(side_effect=fake_save)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm) as mock_comm_cls,
	):
		# Primera llamada: MISS, se sintetiza y se guarda en la base
		audio1 = await radio_announcer.synthesize_segment(text, voice, "intro", allow_cache=True, db_path=db_path)
		assert audio1 == b"CACHED_AUDIO_TEST"
		assert mock_comm_cls.call_count == 1

		# Segunda llamada: HIT, debe venir directo de SQLite sin llamar a edge_tts.Communicate
		audio2 = await radio_announcer.synthesize_segment(text, voice, "intro", allow_cache=True, db_path=db_path)
		assert audio2 == b"CACHED_AUDIO_TEST"
		assert mock_comm_cls.call_count == 1  # No se volvió a llamar


def test_get_fortune_voice():
	# Fortunas del sistema son exclusivas de Elena (podcast co-conducción)
	assert radio_announcer.get_fortune_voice(True, radio_announcer.VOICE_TOMAS) == radio_announcer.VOICE_ELENA
	assert radio_announcer.get_fortune_voice(True, radio_announcer.VOICE_MARIA) == radio_announcer.VOICE_ELENA
	assert radio_announcer.get_fortune_voice(True, radio_announcer.VOICE_VALENTINA) == radio_announcer.VOICE_ELENA
	assert radio_announcer.get_fortune_voice(True, radio_announcer.VOICE_ELENA) == radio_announcer.VOICE_ELENA

	# Fortunas carpinchas las lee el conductor principal
	assert radio_announcer.get_fortune_voice(False, radio_announcer.VOICE_TOMAS) == radio_announcer.VOICE_TOMAS
	assert radio_announcer.get_fortune_voice(False, radio_announcer.VOICE_MARIA) == radio_announcer.VOICE_MARIA


@pytest.mark.asyncio
async def test_system_fortune_read_by_elena_and_cached(tmp_path):
	db_path = tmp_path / "tts_cache.db"
	out_p = tmp_path / "radio.mp3"

	sys_fortune_text = "El ignorante afirma, el sabio duda y reflexiona."
	recorded_calls: list[tuple[str, str]] = []

	def fake_communicate(text, voice):
		recorded_calls.append((text, voice))
		mock_c = MagicMock()

		async def fake_save(dest):
			Path(dest).write_bytes(f"AUDIO_FOR_{voice}_{text[:10]}".encode())

		mock_c.save = AsyncMock(side_effect=fake_save)
		return mock_c

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.get_system_fortune", return_value=sys_fortune_text),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=fake_communicate),
	):
		# Generamos anuncio con conductor Tomás pero forzando fortuna de sistema
		ok, _title, text = await radio_announcer.create_radio_announcement(
			out_p,
			voice=radio_announcer.VOICE_TOMAS,
			db_path=db_path,
			force_system_fortune=True,
		)
		assert ok is True
		assert sys_fortune_text in text

		# Verificamos que los otros segmentos fueron hablados por Tomás, pero la fortuna por Elena
		fortuna_calls = [(t, v) for t, v in recorded_calls if sys_fortune_text in t]
		assert len(fortuna_calls) == 1
		assert fortuna_calls[0][1] == radio_announcer.VOICE_ELENA

		# Verificamos que la intro fue hablada por Tomás
		intro_calls = [(t, v) for t, v in recorded_calls if t in radio_announcer.RADIO_INTROS]
		assert len(intro_calls) == 1
		assert intro_calls[0][1] == radio_announcer.VOICE_TOMAS

		# Verificamos que la fortuna de sistema QUEDÓ GUARDADA en la base con la voz de Elena
		cached_elena = radio_announcer.get_cached_audio(
			"fortuna",
			radio_announcer.VOICE_ELENA,
			f"«{sys_fortune_text}».",
			db_path=db_path,
		)
		assert cached_elena is not None
		assert b"AUDIO_FOR_" in cached_elena

		# Y que NO se guardó para Tomás
		cached_tomas = radio_announcer.get_cached_audio(
			"fortuna",
			radio_announcer.VOICE_TOMAS,
			f"«{sys_fortune_text}».",
			db_path=db_path,
		)
		assert cached_tomas is None

		# Segunda llamada con conductora María: la fortuna de Elena debe ser un CACHE HIT
		out_p2 = tmp_path / "radio2.mp3"
		recorded_calls.clear()

		ok2, _title2, _text2 = await radio_announcer.create_radio_announcement(
			out_p2,
			voice=radio_announcer.VOICE_MARIA,
			db_path=db_path,
			force_system_fortune=True,
		)
		assert ok2 is True
		# En recorded_calls NUNCA debe haberse llamado a Communicate para la fortuna de Elena porque vino de caché
		fortuna_remote_calls = [(t, v) for t, v in recorded_calls if sys_fortune_text in t]
		assert len(fortuna_remote_calls) == 0


def test_generate_modular_radio_script():
	intro, hora, minuto, lead_in, fortuna, is_sys, outro, voice, full_script = (
		radio_announcer.generate_modular_radio_script(voice=radio_announcer.VOICE_TOMAS)
	)
	assert voice == radio_announcer.VOICE_TOMAS
	assert intro in radio_announcer.RADIO_INTROS
	assert len(hora) > 0
	assert minuto is None or len(minuto) > 0
	assert lead_in in radio_announcer.RADIO_LEAD_INS
	assert outro in radio_announcer.RADIO_OUTROS
	assert fortuna in full_script
	assert isinstance(is_sys, bool)
	assert radio_announcer.is_spanish_text(full_script) is True


def test_assemble_announcement_audio_fallback(tmp_path):
	out_p = tmp_path / "combined.mp3"
	segments = [
		(b"SEGMENT_1_", "intro"),
		(b"SEGMENT_2_", "hora"),
		(b"SEGMENT_3", "salida"),
	]
	with patch("shutil.which", return_value=None):
		ok = radio_announcer.assemble_announcement_audio(segments, out_p)
		assert ok is True
		assert out_p.exists()
		assert out_p.read_bytes() == b"SEGMENT_1_SEGMENT_2_SEGMENT_3"


def test_four_voices_available():
	assert len(radio_announcer.VOICES) == 4
	assert radio_announcer.VOICE_TOMAS in radio_announcer.VOICES
	assert radio_announcer.VOICE_ELENA in radio_announcer.VOICES
	assert radio_announcer.VOICE_MARIA in radio_announcer.VOICES
	assert radio_announcer.VOICE_VALENTINA in radio_announcer.VOICES

	for v in radio_announcer.VOICES:
		assert v in radio_announcer.VOICE_NAMES
		assert len(radio_announcer.VOICE_NAMES[v]) > 0


def test_carpincho_ads_in_fortunes():
	assert len(radio_announcer.CARPINCHO_ADS) >= 15
	for ad in radio_announcer.CARPINCHO_ADS:
		assert ad in radio_announcer.CARPINCHO_FORTUNES
		assert radio_announcer.is_spanish_text(ad) is True


@pytest.mark.asyncio
async def test_preload_tts_cache_skips_and_synthesizes(tmp_path):
	from scripts import preload_tts_cache

	db_path = tmp_path / "tts_cache.db"
	preload_tts_cache.init_tts_cache_db(db_path)

	# 1. Precargar manualmente un audio para simular que ya existe
	voice = radio_announcer.VOICE_TOMAS
	text_existente = "¡Buenas gente linda de La Rockola!"
	radio_announcer.save_cached_audio("intro", voice, text_existente, b"AUDIO_PREEXISTENTE", db_path=db_path)

	semaphore = asyncio.Semaphore(2)
	stats = {"skipped": 0, "synthesized": 0, "failed": 0}

	# Procesar el que ya existe -> debe incrementar skipped sin llamar a la red
	with patch("scripts.radio_announcer.edge_tts.Communicate") as mock_comm:
		await preload_tts_cache.process_item(
			semaphore=semaphore,
			category="intro",
			text=text_existente,
			voice=voice,
			db_path=db_path,
			delay=0.0,
			max_retries=2,
			stats=stats,
		)
		assert stats["skipped"] == 1
		assert stats["synthesized"] == 0
		assert mock_comm.call_count == 0

	# Procesar uno nuevo -> debe sintetizar e incrementar synthesized
	text_nuevo = "Un matecito en La Rockola y seguimos:"

	async def fake_save(dest):
		Path(dest).write_bytes(b"NUEVO_AUDIO")

	mock_comm_instance = MagicMock()
	mock_comm_instance.save = AsyncMock(side_effect=fake_save)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm_instance),
	):
		await preload_tts_cache.process_item(
			semaphore=semaphore,
			category="intro",
			text=text_nuevo,
			voice=voice,
			db_path=db_path,
			delay=0.0,
			max_retries=2,
			stats=stats,
		)
		assert stats["synthesized"] == 1
		assert stats["failed"] == 0
		# Verificar que quedó guardado en la base de datos
		cached = radio_announcer.get_cached_audio("intro", voice, text_nuevo, db_path=db_path)
		assert cached == b"NUEVO_AUDIO"


def test_preload_collect_phrases():
	from scripts import preload_tts_cache

	items = preload_tts_cache.collect_phrases()
	categories = {cat for cat, _ in items}
	assert "intro" in categories
	assert "lead_in" in categories
	assert "fortuna" in categories
	assert "salida" in categories
	assert "hora" in categories
	assert "minuto" in categories

	# Verificamos que contenga horas especiales y modulares
	horas = [text for cat, text in items if cat == "hora"]
	assert "Las una en punto, es hora de mimir." in horas
	assert "15 horas," in horas
	assert "1 hora," in horas
	assert len(horas) == 48  # 24 especiales + 24 modulares

	# Verificamos que contenga los 59 minutos
	minutos = [text for cat, text in items if cat == "minuto"]
	assert "un minuto." in minutos
	assert "59 minutos." in minutos
	assert len(minutos) == 59


@pytest.mark.asyncio
async def test_create_radio_announcement_with_special_and_modular_dt(tmp_path):
	out_p1 = tmp_path / "special.mp3"
	out_p2 = tmp_path / "modular.mp3"
	db_p = tmp_path / "tts_cache.db"

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
	):
		# 1. Hora especial 01:00
		dt_special = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)
		ok1, _title1, text1 = await radio_announcer.create_radio_announcement(
			out_p1,
			voice=radio_announcer.VOICE_TOMAS,
			db_path=db_p,
			dt=dt_special,
		)
		assert ok1 is True
		assert "Las una en punto, es hora de mimir." in text1

		# 2. Hora modular 15:23
		dt_modular = datetime(2026, 9, 26, 15, 23, tzinfo=timezone.utc)
		ok2, _title2, text2 = await radio_announcer.create_radio_announcement(
			out_p2,
			voice=radio_announcer.VOICE_ELENA,
			db_path=db_p,
			dt=dt_modular,
		)
		assert ok2 is True
		assert "15 horas, 23 minutos." in text2


def test_get_carpincho_cover_path():
	cover_p = radio_announcer.get_carpincho_cover_path()
	assert cover_p is not None
	assert cover_p.is_file()
	assert cover_p.name == "favicon.png"


def test_is_valid_mp3_stream():
	assert radio_announcer.is_valid_mp3_stream(b"ID3\x03\x00\x00") is True
	assert radio_announcer.is_valid_mp3_stream(b"\xff\xfb\x90\x64") is True
	assert radio_announcer.is_valid_mp3_stream(b"\xff\xe0\x00\x00") is True
	assert radio_announcer.is_valid_mp3_stream(b"RIFF") is False
	assert radio_announcer.is_valid_mp3_stream(b"") is False
	assert radio_announcer.is_valid_mp3_stream(b"abc") is False


def test_embed_cover_art_in_mp3(tmp_path):
	from mutagen.id3 import ID3

	dummy_mp3 = tmp_path / "test.mp3"
	# Valid MP3 sync frame + dummy audio bytes
	dummy_mp3.write_bytes(b"\xff\xfb\x90\x64" + b"\x00" * 1024)

	dummy_cover = tmp_path / "cover.png"
	dummy_cover.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")

	ok = radio_announcer.embed_cover_art_in_mp3(
		dummy_mp3,
		cover_image_path=dummy_cover,
		title="Test Carpincho",
		artist="El Carpincho",
		album="La Rockola",
	)
	assert ok is True

	tags = ID3(str(dummy_mp3))
	assert "TIT2" in tags and str(tags["TIT2"]) == "Test Carpincho"
	assert "TPE1" in tags and str(tags["TPE1"]) == "El Carpincho"
	assert "TALB" in tags and str(tags["TALB"]) == "La Rockola"
	assert "APIC:Cover" in tags
	apic = tags["APIC:Cover"]
	assert apic.mime == "image/png"
	assert apic.data == b"\x89PNG\r\n\x1a\nfakeimagebytes"

	# Non-existent file
	assert radio_announcer.embed_cover_art_in_mp3(tmp_path / "nope.mp3") is False

	# Non-mp3 file
	non_mp3 = tmp_path / "not_an_mp3.txt"
	non_mp3.write_text("just text")
	assert radio_announcer.embed_cover_art_in_mp3(non_mp3) is False


def test_modular_time_hour_zero_with_minutes():
	dt = datetime(2026, 9, 27, 0, 15, tzinfo=timezone.utc)
	hora_seg, minuto_seg, full_time_str = radio_announcer.get_modular_time_segments(dt)
	assert hora_seg == "Las doce de la noche,"
	assert minuto_seg == "15 minutos."
	assert full_time_str == "Las doce de la noche, 15 minutos."


@pytest.mark.asyncio
async def test_stream_error_falls_back_to_save(tmp_path):
	db_p = tmp_path / "tts.db"

	class StreamFailingCommunicator:
		def __init__(self, text, voice):
			self.text = text
			self.voice = voice

		async def stream(self):
			raise ConnectionResetError("Conexión reseteada por edge-tts")
			yield None

		async def save(self, dest):
			Path(dest).write_bytes(b"VALID_SAVED_AUDIO")

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=StreamFailingCommunicator),
	):
		blob = await radio_announcer.synthesize_segment(
			"Texto de prueba",
			radio_announcer.VOICE_TOMAS,
			"intro",
			allow_cache=False,
			db_path=db_p,
		)
		assert blob == b"VALID_SAVED_AUDIO"


@pytest.mark.asyncio
async def test_production_does_not_leak_dummy_audio(tmp_path):
	db_p = tmp_path / "tts.db"

	class EmptyFailingCommunicator:
		def __init__(self, text, voice):
			self.text = text
			self.voice = voice

		async def stream(self):
			return
			yield None

		async def save(self, dest):
			# Simula falla sin excepción pero sin escribir nada en disco
			pass

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=EmptyFailingCommunicator),
		patch("scripts.radio_announcer.ALLOW_TEST_DUMMY_AUDIO", False),
	):
		with pytest.raises(RuntimeError) as exc_info:
			await radio_announcer.synthesize_segment(
				"Texto sin audio",
				radio_announcer.VOICE_TOMAS,
				"intro",
				allow_cache=True,
				db_path=db_p,
			)
		assert "edge-tts no produjo bytes de audio" in str(exc_info.value)
		# Verificar que no se guardó nada en la caché
		assert (
			radio_announcer.get_cached_audio("intro", radio_announcer.VOICE_TOMAS, "Texto sin audio", db_path=db_p)
			is None
		)


@pytest.mark.asyncio
async def test_synthesize_segment_retry_success(tmp_path):
	db_p = tmp_path / "tts.db"
	call_count = 0

	class FlakyCommunicator:
		def __init__(self, text, voice):
			self.text = text
			self.voice = voice

		async def stream(self):
			nonlocal call_count
			call_count += 1
			if call_count == 1:
				raise OSError("Falla transitoria de red")
			yield {"type": "audio", "data": b"RETRY_SUCCESS_AUDIO"}

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=FlakyCommunicator),
	):
		blob = await radio_announcer.synthesize_segment(
			"Texto reintentado",
			radio_announcer.VOICE_TOMAS,
			"intro",
			allow_cache=False,
			db_path=db_p,
		)
		assert blob == b"RETRY_SUCCESS_AUDIO"
		assert call_count == 2


def test_get_carpincho_data_dir_fallback():
	import sys

	# Simular que server no existe
	with patch.dict(sys.modules, {"server": None}):
		data_dir = radio_announcer.get_carpincho_data_dir()
		assert data_dir.name == "DB"
		assert data_dir.is_dir()


def test_assemble_announcement_audio_concat_demuxer_fallback(tmp_path):
	out_p = tmp_path / "out_demux.mp3"
	segments = [
		(b"AUDIO_1_", "intro"),
		(b"AUDIO_2", "hora"),
	]

	orig_run = subprocess.run

	def fake_run(cmd, *args, **kwargs):
		if "-filter_complex" in cmd:
			return MagicMock(returncode=1, stderr=b"Filter complex error")
		elif "-f" in cmd and "concat" in cmd:
			dest = Path(cmd[-1])
			dest.write_bytes(b"DEMUX_CONCAT_RESULT")
			return MagicMock(returncode=0, stderr=b"")
		return orig_run(cmd, *args, **kwargs)

	with (
		patch("shutil.which", return_value="/usr/bin/ffmpeg"),
		patch("subprocess.run", side_effect=fake_run),
	):
		ok = radio_announcer.assemble_announcement_audio(segments, out_p)
		assert ok is True
		assert out_p.read_bytes() == b"DEMUX_CONCAT_RESULT"


def test_voice_prosody_mapping():
	"""Verifica que las 4 voces tengan prosodia fija definida y calibrada."""
	assert len(radio_announcer.VOICE_PROSODY) == 4
	for v in radio_announcer.VOICES:
		assert v in radio_announcer.VOICE_PROSODY
		p = radio_announcer.VOICE_PROSODY[v]
		assert "rate" in p and (p["rate"].endswith("%"))
		assert "pitch" in p and (p["pitch"].endswith("Hz"))
		assert "volume" in p and (p["volume"].endswith("%"))

	# Tomás y Elena tienen ritmo más pausado/solemne (rate negativo)
	assert radio_announcer.VOICE_PROSODY[radio_announcer.VOICE_TOMAS]["rate"].startswith("-")
	assert radio_announcer.VOICE_PROSODY[radio_announcer.VOICE_ELENA]["rate"].startswith("-")
	# María y Valentina tienen ritmo más ágil/vivaz (rate positivo)
	assert radio_announcer.VOICE_PROSODY[radio_announcer.VOICE_MARIA]["rate"].startswith("+")
	assert radio_announcer.VOICE_PROSODY[radio_announcer.VOICE_VALENTINA]["rate"].startswith("+")


@pytest.mark.asyncio
async def test_synthesize_segment_uses_prosody(tmp_path):
	"""Verifica que synthesize_segment pase los parámetros de prosodia a edge_tts.Communicate."""
	db_p = tmp_path / "tts.db"
	captured_kwargs = {}

	class ProsodyCheckingCommunicator:
		def __init__(self, text, voice, *args, **kwargs):
			nonlocal captured_kwargs
			captured_kwargs = kwargs
			self.text = text
			self.voice = voice

		async def stream(self):
			yield {"type": "audio", "data": b"PROSODY_AUDIO"}

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=ProsodyCheckingCommunicator),
	):
		blob = await radio_announcer.synthesize_segment(
			"Texto con prosodia",
			radio_announcer.VOICE_TOMAS,
			"intro",
			allow_cache=False,
			db_path=db_p,
		)
		assert blob == b"PROSODY_AUDIO"
		expected_prosody = radio_announcer.VOICE_PROSODY[radio_announcer.VOICE_TOMAS]
		assert captured_kwargs.get("rate") == expected_prosody["rate"]
		assert captured_kwargs.get("pitch") == expected_prosody["pitch"]
		assert captured_kwargs.get("volume") == expected_prosody["volume"]


def test_phrase_banks_cleaned_ellipses_and_slang():
	"""Verifica que los intros y outros no tengan '...' pegados y contengan modismos carpinchos."""
	for intro in radio_announcer.RADIO_INTROS:
		assert not intro.startswith("..."), f"Intro no debe empezar con '...': {intro}"
		assert radio_announcer.is_spanish_text(intro) is True

	for outro in radio_announcer.RADIO_OUTROS:
		assert not outro.endswith("..."), f"Outro no debe terminar con '...': {outro}"
		assert radio_announcer.is_spanish_text(outro) is True

	# Verificar presencia de modismos y jerga carpincha
	all_phrases = radio_announcer.RADIO_INTROS + radio_announcer.RADIO_LEAD_INS + radio_announcer.RADIO_OUTROS
	has_che = any("che" in p.lower() or "che," in p.lower() for p in all_phrases)
	has_posta = any("posta" in p.lower() for p in all_phrases)
	has_carpinchazo = any("carpinchazo" in p.lower() for p in all_phrases)
	assert has_che is True
	assert has_posta is True
	assert has_carpinchazo is True


def test_assemble_announcement_audio_acrossfade_and_pauses(tmp_path):
	"""Verifica que assemble_announcement_audio invoque acrossfade para hora+minuto de la misma voz y anullsrc para pausas."""
	out_p = tmp_path / "assembled.mp3"
	segments = [
		(b"AUDIO_INTRO", "intro", radio_announcer.VOICE_TOMAS),
		(b"AUDIO_HORA", "hora", radio_announcer.VOICE_TOMAS),
		(b"AUDIO_MINUTO", "minuto", radio_announcer.VOICE_TOMAS),
		(b"AUDIO_LEADIN", "lead_in", radio_announcer.VOICE_TOMAS),
		(b"AUDIO_FORTUNA", "fortuna", radio_announcer.VOICE_ELENA),
		(b"AUDIO_SALIDA", "salida", radio_announcer.VOICE_TOMAS),
	]

	invoked_commands: list[list[str]] = []
	orig_run = subprocess.run

	def tracking_run(cmd, *args, **kwargs):
		invoked_commands.append(cmd)
		# Si es comando acrossfade
		if any("acrossfade" in arg for arg in cmd):
			dest = Path(cmd[-1])
			dest.write_bytes(b"ACROSSFADED_TIME_AUDIO")
			return MagicMock(returncode=0, stderr=b"")
		# Si es generador de silencio
		elif any("anullsrc" in arg for arg in cmd):
			dest = Path(cmd[-1])
			dest.write_bytes(b"SILENCE_AUDIO")
			return MagicMock(returncode=0, stderr=b"")
		# Si es concatenación final
		elif "-filter_complex" in cmd and any("concat=n=" in arg for arg in cmd):
			dest = Path(cmd[-1])
			dest.write_bytes(b"FINAL_CONCATENATED_AUDIO")
			return MagicMock(returncode=0, stderr=b"")
		return orig_run(cmd, *args, **kwargs)

	with (
		patch("shutil.which", return_value="/usr/bin/ffmpeg"),
		patch("subprocess.run", side_effect=tracking_run),
	):
		ok = radio_announcer.assemble_announcement_audio(segments, out_p)
		assert ok is True
		assert out_p.exists()
		assert out_p.read_bytes() == b"FINAL_CONCATENATED_AUDIO"

		# Verificar llamada a acrossfade para hora + minuto
		fade_calls = [c for c in invoked_commands if any("acrossfade" in a for a in c)]
		assert len(fade_calls) == 1
		assert "acrossfade=d=0.05:c1=tri:c2=tri" in str(fade_calls[0])

		# Verificar llamadas a anullsrc para los silencios intercalados
		silence_calls = [c for c in invoked_commands if any("anullsrc" in a for a in c)]
		# Silencio inicial (0.20), tras intro (0.30), tras hora_minuto (0.25), tras lead-in (0.35), tras fortuna (0.25)
		assert len(silence_calls) >= 4


# --- Tests para Reporte del Clima (wttr.in) ---


def test_construir_url_json():
	url = radio_announcer.construir_url_json("San Miguel de Tucumán", "es")
	assert "wttr.in/San%20Miguel%20de%20Tucum%C3%A1n" in url
	assert "format=j1" in url
	assert "lang=es" in url

	url_empty = radio_announcer.construir_url_json("", "en")
	assert url_empty == "https://wttr.in/?format=j1&lang=en"


def test_fetch_weather_json_success():
	sample_data = {
		"current_condition": [{"temp_C": "25"}],
		"weather": [
			{"mintempC": "18", "maxtempC": "28", "hourly": [{"chanceofrain": "10"}]},
			{"mintempC": "17", "maxtempC": "27", "hourly": [{"chanceofrain": "20"}]},
		],
	}
	mock_resp = MagicMock()
	mock_resp.status = 200
	mock_resp.read.return_value = json.dumps(sample_data).encode("utf-8")
	mock_resp.__enter__.return_value = mock_resp

	with patch("urllib.request.urlopen", return_value=mock_resp):
		data = radio_announcer.fetch_weather_json("Buenos Aires")
		assert data is not None
		assert data["current_condition"][0]["temp_C"] == "25"


def test_fetch_weather_json_failure():
	with patch("urllib.request.urlopen", side_effect=Exception("Timeout / Connection reset")):
		data = radio_announcer.fetch_weather_json("LugarInvalido", timeout=0.1)
		assert data is None


def test_describir_lluvias():
	# Ninguno
	desc_none = radio_announcer.describir_lluvias(False, False)
	assert "De lluvias ni hablemos" in desc_none

	# Sólo hoy
	desc_today = radio_announcer.describir_lluvias(True, False)
	assert "hoy se esperan lluvias" in desc_today
	assert "mañana ya zafamos" in desc_today

	# Sólo mañana
	desc_tomorrow = radio_announcer.describir_lluvias(False, True)
	assert "Hoy zafamos del agua" in desc_tomorrow
	assert "mañana se vienen las lluvias" in desc_tomorrow

	# Ambos
	desc_both = radio_announcer.describir_lluvias(True, True)
	assert "tanto para hoy como para mañana" in desc_both


def test_build_weather_phrase_valid():
	sample = {
		"current_condition": [{"temp_C": "22.4"}],
		"weather": [
			{
				"mintempC": "15",
				"maxtempC": "28",
				"hourly": [{"chanceofrain": "10"}, {"chanceofrain": "30"}],
			},
			{
				"mintempC": "14",
				"maxtempC": "26",
				"hourly": [{"chanceofrain": "60"}, {"chanceofrain": "80"}],
			},
		],
	}
	phrase = radio_announcer.build_weather_phrase(sample, lead_in="Atenti:")
	assert phrase is not None
	assert "Atenti:" in phrase
	assert "22 grados" in phrase
	assert "mínima es de 15" in phrase
	assert "máxima alcanzará los 28" in phrase
	assert "entre 14 y 26 grados" in phrase
	assert "mañana se vienen las lluvias" in phrase


def test_build_weather_phrase_invalid():
	assert radio_announcer.build_weather_phrase({}) is None
	assert radio_announcer.build_weather_phrase({"current_condition": []}) is None
	assert radio_announcer.build_weather_phrase({"current_condition": [{"temp_C": "abc"}]}) is None


@pytest.fixture(autouse=True)
def reset_radio_memory_state_fixture():
	radio_announcer.reset_radio_memory_state()
	yield
	radio_announcer.reset_radio_memory_state()


def test_radio_state_get_and_set(tmp_path):
	db_p = tmp_path / "tts_cache.db"
	assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) is None
	assert radio_announcer.get_radio_state("last_weather_hour", default="0", db_path=db_p) == "0"

	radio_announcer.set_radio_state("last_weather_hour", "14", db_path=db_p)
	assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "14"

	# Update existing key
	radio_announcer.set_radio_state("last_weather_hour", "15", db_path=db_p)
	assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "15"

	radio_announcer.reset_radio_memory_state()
	assert radio_announcer.get_radio_state("last_weather_hour") is None


@pytest.mark.asyncio
async def test_create_radio_announcement_weather_once_per_hour(tmp_path):
	out1 = tmp_path / "announcement1.mp3"
	out2 = tmp_path / "announcement2.mp3"
	out3 = tmp_path / "announcement3.mp3"
	db_p = tmp_path / "tts_cache.db"

	mock_weather = {
		"current_condition": [{"temp_C": "20"}],
		"weather": [
			{"mintempC": "12", "maxtempC": "24", "hourly": [{"chanceofrain": "5"}]},
			{"mintempC": "13", "maxtempC": "25", "hourly": [{"chanceofrain": "5"}]},
		],
	}

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)

	dt_hour14_a = datetime(2026, 9, 27, 14, 5, tzinfo=timezone.utc)
	dt_hour14_b = datetime(2026, 9, 27, 14, 35, tzinfo=timezone.utc)
	dt_hour15 = datetime(2026, 9, 27, 15, 10, tzinfo=timezone.utc)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
		patch("scripts.radio_announcer.fetch_weather_json", return_value=mock_weather) as mock_fetch,
	):
		# 1era locución a las 14:05 -> DEBE tener reporte de clima
		ok1, _title1, text1 = await radio_announcer.create_radio_announcement(
			out1,
			db_path=db_p,
			dt=dt_hour14_a,
		)
		assert ok1 is True
		assert "20 grados" in text1
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "14"
		assert mock_fetch.call_count == 1

		# 2da locución en la misma hora (14:35) -> NO debe tener reporte de clima ni reintentar fetch
		ok2, _title2, text2 = await radio_announcer.create_radio_announcement(
			out2,
			db_path=db_p,
			dt=dt_hour14_b,
		)
		assert ok2 is True
		assert "20 grados" not in text2
		assert mock_fetch.call_count == 1  # No se volvió a llamar

		# 3ra locución en la siguiente hora (15:10) -> DEBE volver a incluir el clima
		ok3, _title3, text3 = await radio_announcer.create_radio_announcement(
			out3,
			db_path=db_p,
			dt=dt_hour15,
		)
		assert ok3 is True
		assert "20 grados" in text3
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "15"
		assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_create_radio_announcement_weather_failure_does_not_break_and_does_not_mark_hour(tmp_path):
	out = tmp_path / "announcement.mp3"
	db_p = tmp_path / "tts_cache.db"

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)
	dt_hour = datetime(2026, 9, 27, 16, 20, tzinfo=timezone.utc)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
		patch("scripts.radio_announcer.fetch_weather_json", return_value=None) as mock_fetch,
	):
		ok, _title, _text = await radio_announcer.create_radio_announcement(
			out,
			db_path=db_p,
			dt=dt_hour,
		)
		assert ok is True
		assert out.exists()
		# Al haber fallado, no debe figurar la hora como ya anunciada
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) is None
		assert mock_fetch.call_count == 1


def test_tts_default_constants():
	assert radio_announcer.DEFAULT_TTS_TIMEOUT == 12.0
	assert radio_announcer.DEFAULT_TTS_RETRIES == 3


@pytest.mark.asyncio
async def test_synthesize_segment_retry_multiple_attempts_success(tmp_path):
	db_p = tmp_path / "tts.db"
	call_count = 0

	class MultiRetryCommunicator:
		def __init__(self, text, voice):
			self.text = text
			self.voice = voice

		async def stream(self):
			nonlocal call_count
			call_count += 1
			if call_count < 3:
				raise OSError("Falla transitoria de red")
			yield {"type": "audio", "data": b"SUCCESS_ON_THIRD_TRY"}

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=MultiRetryCommunicator),
	):
		blob = await radio_announcer.synthesize_segment(
			"Texto reintentado múltiple",
			radio_announcer.VOICE_TOMAS,
			"intro",
			allow_cache=False,
			db_path=db_p,
		)
		assert blob == b"SUCCESS_ON_THIRD_TRY"
		assert call_count == 3
