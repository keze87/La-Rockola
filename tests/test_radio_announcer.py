import asyncio
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


def test_format_radio_time():
	# 01:00 - Hora especial
	dt_one = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_one)
	assert "Las una en punto, es hora de mimir." in t_str

	# 12:00 - Hora especial mediodía
	dt_noon = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_noon)
	assert "Las doce del mediodía en punto" in t_str

	# 15:23 - Modular minutos plural
	dt_exact = datetime(2026, 9, 26, 15, 23, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_exact)
	assert "15 horas, 23 minutos" in t_str

	# 09:01 - Modular minuto singular
	dt_one_min = datetime(2026, 9, 26, 9, 1, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_one_min)
	assert "9 horas, un minuto" in t_str

	# 01:15 - Modular hora singular
	dt_one_fifteen = datetime(2026, 9, 26, 1, 15, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_one_fifteen)
	assert "1 hora, 15 minutos" in t_str


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


def test_generate_radio_script():
	script, voice, fortune = radio_announcer.generate_radio_script(voice=radio_announcer.VOICE_TOMAS)
	assert voice == radio_announcer.VOICE_TOMAS
	assert fortune in script
	assert "La Rockola" in script
	assert radio_announcer.is_spanish_text(script) is True

	script_elena, voice_elena, _ = radio_announcer.generate_radio_script(voice=radio_announcer.VOICE_ELENA)
	assert voice_elena == radio_announcer.VOICE_ELENA
	assert len(script_elena) > 10
	assert radio_announcer.is_spanish_text(script_elena) is True


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

	async def slow_save(*args, **kwargs):
		await asyncio.sleep(1.0)

	mock_comm = MagicMock()
	mock_comm.save = slow_save

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
	):
		ok, _title, _text = await radio_announcer.create_radio_announcement(out_p, timeout=0.01)
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


@pytest.mark.asyncio
async def test_system_fortune_never_cached(tmp_path):
	db_path = tmp_path / "tts_cache.db"
	voice = radio_announcer.VOICE_TOMAS
	sys_fortune_text = "«El ignorante afirma, el sabio duda y reflexiona.»"

	async def fake_save(dest):
		Path(dest).write_bytes(b"SYS_FORTUNE_AUDIO")

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(side_effect=fake_save)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm) as mock_comm_cls,
	):
		# allow_cache=False (comportamiento estricto para fortunas de sistema)
		audio = await radio_announcer.synthesize_segment(
			sys_fortune_text,
			voice,
			"fortuna",
			allow_cache=False,
			db_path=db_path,
		)
		assert audio == b"SYS_FORTUNE_AUDIO"
		assert mock_comm_cls.call_count == 1

		# Comprobamos que NUNCA se guardó en la base de datos de caché
		cached = radio_announcer.get_cached_audio("fortuna", voice, sys_fortune_text, db_path=db_path)
		assert cached is None


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
