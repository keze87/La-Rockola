import asyncio
import base64
import json
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import radio_announcer


def test_clean_fortune_text():
	# 1. URLs, tags HTML y firmas con guiones (firmas de autor preservadas)
	raw = '  "El éxito no es la clave."  \n\n  -- Albert Schweitzer  https://example.com  <nick>  '
	cleaned = radio_announcer.clean_fortune_text(raw)
	assert "El éxito no es la clave." in cleaned
	assert "Albert Schweitzer" in cleaned
	assert "https://" not in cleaned
	assert "<nick>" not in cleaned

	# 2. Comillas tipográficas, simples y dobles
	raw_quotes = "«El único modo de hacer un gran trabajo es amar lo que hacés»"
	assert radio_announcer.clean_fortune_text(raw_quotes) == (
		"El único modo de hacer un gran trabajo es amar lo que hacés."
	)

	# 3. Corchetes editoriales y paréntesis bibliográficos (años, tomos, páginas)
	raw_biblio = "La paciencia [de los sabios] es amarga (1890, pág. 12), pero sus frutos son dulces."
	cleaned_biblio = radio_announcer.clean_fortune_text(raw_biblio)
	assert "[de los sabios]" not in cleaned_biblio
	assert "(1890, pág. 12)" not in cleaned_biblio
	assert "La paciencia es amarga, pero sus frutos son dulces." == cleaned_biblio

	# 4. Atribuciones de autor preservadas
	raw_attrib = "No dejes para mañana lo que puedas hacer hoy (Refrán Popular)."
	assert radio_announcer.clean_fortune_text(raw_attrib) == (
		"No dejes para mañana lo que puedas hacer hoy (Refrán Popular)."
	)


def test_is_valid_spoken_sentence_positive():
	"""Verifica oraciones completas válidas para emisión radial."""
	assert radio_announcer.is_valid_spoken_sentence("El ignorante afirma, el sabio duda y reflexiona.") is True
	assert (
		radio_announcer.is_valid_spoken_sentence("La paciencia es amarga, pero sus frutos son siempre dulces.") is True
	)
	assert (
		radio_announcer.is_valid_spoken_sentence(
			"El carpincho no compite con la corriente, sino que flota con dignidad."
		)
		is True
	)
	assert (
		radio_announcer.is_valid_spoken_sentence("¿Qué podemos esperar del tiempo si no cuidamos el agua de la laguna?")
		is True
	)
	assert (
		radio_announcer.is_valid_spoken_sentence("¡Al mal tiempo buena cara y unos buenos mates bien calientes!")
		is True
	)


def test_is_valid_spoken_sentence_length_limits():
	"""Verifica los límites de longitud (5 a 88 palabras)."""
	# Menos de 5 palabras
	assert radio_announcer.is_valid_spoken_sentence("El agua siempre hierve.") is False
	assert radio_announcer.is_valid_spoken_sentence("Hola gente de la radio.") is False

	# Exactamente 5 palabras con verbo
	assert radio_announcer.is_valid_spoken_sentence("El carpincho nada muy bien.") is True

	# Más de 88 palabras
	long_text = "El carpincho sabe nadar muy bien en la laguna fresca y tranquila " * 10
	words = long_text.split()
	assert len(words) > 88
	assert radio_announcer.is_valid_spoken_sentence(long_text) is False


def test_is_valid_spoken_sentence_verb_requirement():
	"""Verifica que requiera al menos un verbo conjugado común en español."""
	# Frase nominal sin ningún verbo conjugado
	assert radio_announcer.is_valid_spoken_sentence("Tranquilo como carpincho en Nordelta y alrededores.") is False
	# Misma frase con verbo conjugado
	assert (
		radio_announcer.is_valid_spoken_sentence("El carpincho descansa tranquilo en Nordelta y alrededores.") is True
	)
	# Verbo detectado por sufijo morfológico (-aban)
	assert (
		radio_announcer.is_valid_spoken_sentence("Los carpinchos caminaban bajo el sol radiante del humedal.") is True
	)


def test_is_valid_spoken_sentence_rejects_lists():
	"""Verifica que descarte listas numeradas y viñetas."""
	assert radio_announcer.is_valid_spoken_sentence("1. Primero ponemos la pava para tomar el mate.") is False
	assert radio_announcer.is_valid_spoken_sentence("2) Segundo paso para nadar en el bañado profundo.") is False
	assert radio_announcer.is_valid_spoken_sentence("- Una opción interesante para disfrutar de la tarde.") is False
	assert radio_announcer.is_valid_spoken_sentence("* Otra alternativa para pasar la tarde en la orilla.") is False
	assert radio_announcer.is_valid_spoken_sentence("Opciones disponibles: 1) nadar 2) dormir 3) tomar mate.") is False


def test_is_valid_spoken_sentence_rejects_formatting_and_math():
	"""Verifica que descarte caracteres de formato, código y símbolos matemáticos."""
	assert radio_announcer.is_valid_spoken_sentence("El 50% de la laguna tiene juncos tiernos y frescos.") is False
	assert radio_announcer.is_valid_spoken_sentence("Tomar mate / tereré es lo mejor de toda la tarde.") is False
	assert (
		radio_announcer.is_valid_spoken_sentence("La suma de esfuerzos 1+1 da los mejores resultados posibles.")
		is False
	)
	assert radio_announcer.is_valid_spoken_sentence("El carpincho | la nutria | el yacaré en el agua.") is False
	assert radio_announcer.is_valid_spoken_sentence("El valor del junco es > que cualquier pastura seca.") is False
	assert (
		radio_announcer.is_valid_spoken_sentence("Texto con *énfasis exagerado* en la locución radial comunitaria.")
		is False
	)


def test_is_valid_spoken_sentence_rejects_broken_poetry():
	"""Verifica que descarte versos aislados o poesía rota con cláusulas cortas."""
	# 5 cláusulas de 2 palabras cada una
	assert (
		radio_announcer.is_valid_spoken_sentence("Rosa roja, flor hermosa, tarde gris, viento sur, lluvia leve.")
		is False
	)
	# Lista de números aislados
	assert radio_announcer.is_valid_spoken_sentence("Uno, dos, tres, cuatro, cinco.") is False


def test_is_valid_spoken_sentence_rejects_truncated_and_lowercase():
	"""Verifica que descarte textos truncados, iniciados en minúscula o terminados en dos puntos."""
	assert radio_announcer.is_valid_spoken_sentence("...y nada más que agregar a esta charla de radio.") is False
	assert radio_announcer.is_valid_spoken_sentence("y nada más que agregar a esta linda charla de radio.") is False
	assert radio_announcer.is_valid_spoken_sentence("Dice el viejo refrán carpincho en la orilla del arroyo:") is False
	assert radio_announcer.is_valid_spoken_sentence("El hombre propone y la naturaleza en su inmensidad,") is False


def test_is_valid_spoken_sentence_rejects_blacklists():
	"""Verifica el filtrado de mal gusto y jerga robótica o de asistente IA."""
	# 1. Mal gusto / profanidad
	assert radio_announcer.is_valid_spoken_sentence("Ese tipo es un pelotudo que no entiende nada de radio.") is False
	assert radio_announcer.is_valid_spoken_sentence("Me importa una mierda lo que digan en el pueblo cercano.") is False
	assert radio_announcer.is_valid_spoken_sentence("Qué concha pasa con la música en esta estación isleña.") is False
	assert (
		radio_announcer.is_valid_spoken_sentence("No seas hijo de puta y compartí los mates con los amigos.") is False
	)

	# 2. Jerga robótica o asistente IA (Filtro anti-robot)
	assert (
		radio_announcer.is_valid_spoken_sentence(
			"Como modelo de lenguaje, no poseo opiniones personales sobre la música."
		)
		is False
	)
	assert (
		radio_announcer.is_valid_spoken_sentence("¡Buenas tardes! ¿En qué puedo ayudarte hoy en la sintonía radial?")
		is False
	)
	assert (
		radio_announcer.is_valid_spoken_sentence("El error 404 indica que la melodía no fue encontrada en el servidor.")
		is False
	)
	assert (
		radio_announcer.is_valid_spoken_sentence(
			"Estamos procesando datos para optimizar la lista de reproducción musical."
		)
		is False
	)
	assert (
		radio_announcer.is_valid_spoken_sentence(
			"El sistema operativo de la emisora funciona a la perfección en la máquina."
		)
		is False
	)
	assert (
		radio_announcer.is_valid_spoken_sentence(
			"El algoritmo seleccionó las mejores canciones para disfrutar la tarde."
		)
		is False
	)


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
		# Sin verbos o longitud excesiva
		assert radio_announcer.get_system_fortune() is None


def test_get_system_fortune_retries_on_invalid_sentence():
	"""Verifica que get_system_fortune reintente si el primer resultado no es una oración hablada válida."""
	mock_call_1 = MagicMock(
		returncode=0,
		stdout="Rosa roja, flor hermosa, tarde gris, viento sur, lluvia leve.\n",
	)
	mock_call_2 = MagicMock(
		returncode=0,
		stdout="El ignorante afirma, el sabio duda y reflexiona.\n",
	)

	with (
		patch("shutil.which", return_value="/usr/bin/fortune"),
		patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["refranes"]),
		patch("subprocess.run", side_effect=[mock_call_1, mock_call_2]),
	):
		res = radio_announcer.get_system_fortune(max_attempts=3)
		assert res == "El ignorante afirma, el sabio duda y reflexiona."

	# Si todos los intentos devuelven jerga robótica o inválida, retorna None
	mock_ai = MagicMock(
		returncode=0,
		stdout="Como modelo de lenguaje, no poseo opiniones personales sobre la música.\n",
	)
	with (
		patch("shutil.which", return_value="/usr/bin/fortune"),
		patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["refranes"]),
		patch("subprocess.run", return_value=mock_ai),
	):
		assert radio_announcer.get_system_fortune(max_attempts=2) is None


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
	# Especial 01:00 (en punto, min 0)
	dt_one = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_one)
	assert h_seg == "Las una en punto, es hora de mimir."
	assert m_seg is None
	assert full == "Las una en punto, es hora de mimir."

	# Especial 00:00 (medianoche en punto, min 0)
	dt_mid = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_mid)
	assert "Las doce de la noche en punto" in h_seg
	assert m_seg is None

	# Intervalo: y veinticinco (15:23 -> min 23 cae en rango 23..27)
	dt_mod = datetime(2026, 9, 26, 15, 23, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_mod)
	assert h_seg == "Las tres"
	assert m_seg == "y veinticinco."
	assert full == "Las tres y veinticinco."

	# Intervalo: en punto (09:01 -> min 1 cae en rango 0..2 / especial)
	dt_one_min = datetime(2026, 9, 26, 9, 1, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_one_min)
	assert h_seg == "Las nueve de la mañana en punto, el sol calienta la barranca."
	assert m_seg is None

	# Intervalo: menos cuarto (01:45 -> min 45 cae en rango 43..47, apunta a hora 2)
	dt_one_forty_five = datetime(2026, 9, 26, 1, 45, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_one_forty_five)
	assert h_seg == "Las dos"
	assert m_seg == "menos cuarto."
	assert full == "Las dos menos cuarto."

	# Intervalo: y cuarto (10:15 -> min 15 cae en rango 13..17)
	dt_quarter = datetime(2026, 9, 26, 10, 15, tzinfo=timezone.utc)
	h_seg, m_seg, full = radio_announcer.get_modular_time_segments(dt_quarter)
	assert h_seg == "Las diez"
	assert m_seg == "y cuarto."
	assert full == "Las diez y cuarto."

	# Intervalos adicionales cada 5 minutos
	intervals = [
		(5, "Las diez", "y cinco.", "Las diez y cinco."),
		(10, "Las diez", "y diez.", "Las diez y diez."),
		(20, "Las diez", "y veinte.", "Las diez y veinte."),
		(30, "Las diez", "y media.", "Las diez y media."),
		(35, "Las diez", "y treinta y cinco.", "Las diez y treinta y cinco."),
		(40, "Las once", "menos veinte.", "Las once menos veinte."),
		(50, "Las once", "menos diez.", "Las once menos diez."),
		(55, "Las once", "menos cinco.", "Las once menos cinco."),
	]
	for m, exp_h, exp_m, exp_f in intervals:
		dt_test = datetime(2026, 9, 26, 10, m, tzinfo=timezone.utc)
		h, m_res, f = radio_announcer.get_modular_time_segments(dt_test)
		assert h == exp_h
		assert m_res == exp_m
		assert f == exp_f

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
		# Primera llamada: edge-tts en vivo sintetiza y persiste en caché
		audio1 = await radio_announcer.synthesize_segment(text, voice, "intro", allow_cache=True, db_path=db_path)
		assert audio1 == b"CACHED_AUDIO_TEST"
		assert mock_comm_cls.call_count == 1

	# Segunda llamada: edge-tts falla o no tiene internet -> Fallback a la caché SQLite
	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=RuntimeError("Sin conexión a internet")),
	):
		audio2 = await radio_announcer.synthesize_segment(
			text, voice, "intro", allow_cache=True, max_retries=0, db_path=db_path
		)
		assert audio2 == b"CACHED_AUDIO_TEST"


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
		intro_calls = [(t, v) for t, v in recorded_calls if any(intro in t for intro in radio_announcer.RADIO_INTROS)]
		assert len(intro_calls) >= 1
		assert intro_calls[0][1] == radio_announcer.VOICE_TOMAS

		# Verificamos que la fortuna de sistema QUEDÓ GUARDADA en la base con la voz de Elena
		cached_elena = radio_announcer.get_cached_audio(
			"fortuna",
			radio_announcer.VOICE_ELENA,
			radio_announcer.format_fortune_for_speech(sys_fortune_text),
			db_path=db_path,
		)
		assert cached_elena is not None
		assert b"AUDIO_FOR_" in cached_elena

		# Y que NO se guardó para Tomás
		cached_tomas = radio_announcer.get_cached_audio(
			"fortuna",
			radio_announcer.VOICE_TOMAS,
			radio_announcer.format_fortune_for_speech(sys_fortune_text),
			db_path=db_path,
		)
		assert cached_tomas is None

		# Segunda llamada con conductora María: si edge-tts falla, la fortuna de Elena debe ser un CACHE HIT de fallback
		out_p2 = tmp_path / "radio2.mp3"
		recorded_calls.clear()

		def failing_communicate(text, voice):
			if sys_fortune_text in text and voice == radio_announcer.VOICE_ELENA:
				raise RuntimeError("Simulated edge-tts offline error for Elena")
			return fake_communicate(text, voice)

		with patch("scripts.radio_announcer.edge_tts.Communicate", side_effect=failing_communicate):
			ok2, _title2, text2 = await radio_announcer.create_radio_announcement(
				out_p2,
				voice=radio_announcer.VOICE_MARIA,
				db_path=db_path,
				force_system_fortune=True,
			)
			assert ok2 is True
			assert sys_fortune_text in text2


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

	# Verificamos que contenga horas especiales y combinaciones unificadas
	horas = [text for cat, text in items if cat == "hora"]
	assert "Las una en punto, es hora de mimir." in horas
	assert "Las nueve y media." in horas
	assert "Las tres y veinticinco." in horas
	assert "Las tres" in horas
	assert "Las una" in horas
	assert len(horas) >= 168  # 24 especiales + 144 combinaciones cada 5 minutos (+ retrocompatibilidad)

	# Verificamos que contenga los 12 intervalos cada 5 minutos
	minutos = [text for cat, text in items if cat == "minuto"]
	assert "en punto." in minutos
	assert "y cinco." in minutos
	assert "y diez." in minutos
	assert "y cuarto." in minutos
	assert "y veinte." in minutos
	assert "y veinticinco." in minutos
	assert "y media." in minutos
	assert "y treinta y cinco." in minutos
	assert "menos veinte." in minutos
	assert "menos cuarto." in minutos
	assert "menos diez." in minutos
	assert "menos cinco." in minutos
	assert len(minutos) == 12


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

		# 2. Hora modular 15:23 -> redonda a 'y veinticinco.'
		dt_modular = datetime(2026, 9, 26, 15, 23, tzinfo=timezone.utc)
		ok2, _title2, text2 = await radio_announcer.create_radio_announcement(
			out_p2,
			voice=radio_announcer.VOICE_ELENA,
			db_path=db_p,
			dt=dt_modular,
		)
		assert ok2 is True
		assert "Las tres y veinticinco." in text2


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
	assert hora_seg == "Las doce"
	assert minuto_seg == "y cuarto."
	assert full_time_str == "Las doce y cuarto."


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
		# Si es generador de ruido de sala o silencio
		elif any("anoisesrc" in arg or "anullsrc" in arg for arg in cmd):
			dest = Path(cmd[-1])
			dest.write_bytes(b"ROOM_TONE_AUDIO")
			return MagicMock(returncode=0, stderr=b"")
		# Si es normalización dynaudnorm
		elif any("dynaudnorm" in arg for arg in cmd):
			dest = Path(cmd[-1])
			dest.write_bytes(b"NORM_AUDIO")
			return MagicMock(returncode=0, stderr=b"")
		# Si es mastering final con highpass o concatenación final
		elif any("highpass" in arg for arg in cmd) or (
			"-filter_complex" in cmd and any("concat=n=" in arg for arg in cmd)
		):
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

		# Verificar llamadas a anoisesrc / anullsrc para los tonos de sala intercalados
		tone_calls = [c for c in invoked_commands if any("anoisesrc" in a or "anullsrc" in a for a in c)]
		# Presencia inicial (0.15) y pausas entre bloques
		assert len(tone_calls) >= 4
		assert any("anoisesrc" in str(c) for c in tone_calls)


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
	# Variante clásica (variant_idx=0)
	desc_none = radio_announcer.describir_lluvias(False, False, variant_idx=0)
	assert "De lluvias ni hablemos" in desc_none

	desc_today = radio_announcer.describir_lluvias(True, False, variant_idx=0)
	assert "hoy se esperan lluvias" in desc_today
	assert "mañana ya zafamos" in desc_today

	desc_tomorrow = radio_announcer.describir_lluvias(False, True, variant_idx=0)
	assert "Hoy zafamos del agua" in desc_tomorrow
	assert "mañana se vienen las lluvias" in desc_tomorrow

	desc_both = radio_announcer.describir_lluvias(True, True, variant_idx=0)
	assert "tanto para hoy como para mañana" in desc_both

	# Todas las variantes para cada condición deben existir y ser texto válido en español
	for cond, descs in radio_announcer.RAIN_DESCRIPTIONS.items():
		assert len(descs) >= 5
		for i, text in enumerate(descs):
			retrieved = radio_announcer.describir_lluvias(*cond, variant_idx=i)
			assert retrieved == text
			assert radio_announcer.is_spanish_text(retrieved) is True
			assert len(retrieved) > 10

	# Verificación con selección aleatoria (variant_idx=None)
	for cond in radio_announcer.RAIN_DESCRIPTIONS:
		random_desc = radio_announcer.describir_lluvias(*cond)
		assert random_desc in radio_announcer.RAIN_DESCRIPTIONS[cond]

	# Helper de precarga consolidada
	all_rains = radio_announcer.get_all_rain_descriptions()
	assert len(all_rains) >= 20
	for d in all_rains:
		assert radio_announcer.is_spanish_text(d) is True


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
	phrase = radio_announcer.build_weather_phrase(sample, lead_in="Atenti:", template_idx=0)
	assert phrase is not None
	assert "Atenti:" in phrase
	assert "San Miguel de Tucumán" in phrase
	assert "22 grados" in phrase
	assert "mínima es de 15" in phrase
	assert "máxima alcanzará los 28" in phrase
	assert "entre 14 y 26 grados" in phrase
	assert "mañana se vienen las lluvias" in phrase

	# Prueba con ubicaciones personalizadas y diferentes plantillas
	phrase_rosario = radio_announcer.build_weather_phrase(sample, lead_in="Atenti:", template_idx=0, location="Rosario")
	assert phrase_rosario is not None
	assert "En Rosario" in phrase_rosario

	phrase_ba = radio_announcer.build_weather_phrase(sample, lead_in="Atenti:", template_idx=1, location="Buenos Aires")
	assert phrase_ba is not None
	assert "Para Buenos Aires" in phrase_ba

	phrase_cba = radio_announcer.build_weather_phrase(sample, lead_in="Atenti:", template_idx=2, location="Córdoba")
	assert phrase_cba is not None
	assert "en Córdoba" in phrase_cba

	# Limpieza de caracteres de URL (+ y _)
	phrase_url = radio_announcer.build_weather_phrase(sample, template_idx=0, location="San+Fernando_del_Valle")
	assert phrase_url is not None
	assert "En San Fernando del Valle" in phrase_url


def test_build_weather_phrase_invalid():
	assert radio_announcer.build_weather_phrase({}) is None
	assert radio_announcer.build_weather_phrase({"current_condition": []}) is None
	assert radio_announcer.build_weather_phrase({"current_condition": [{"temp_C": "abc"}]}) is None


def test_extract_location_from_weather_data():
	"""Verifica la extracción de localidad resuelta por wttr.in desde nearest_area."""
	# 1. Por areaName
	data_area = {"nearest_area": [{"areaName": [{"value": "Tucumán"}]}]}
	assert radio_announcer.extract_location_from_weather_data(data_area) == "Tucumán"

	# 2. Por region
	data_region = {"nearest_area": [{"region": [{"value": "Santa Fe"}]}]}
	assert radio_announcer.extract_location_from_weather_data(data_region) == "Santa Fe"

	# 3. Por country
	data_country = {"nearest_area": [{"country": [{"value": "Argentina"}]}]}
	assert radio_announcer.extract_location_from_weather_data(data_country) == "Argentina"

	# 4. Datos vacíos o inválidos
	assert radio_announcer.extract_location_from_weather_data({}) is None
	assert radio_announcer.extract_location_from_weather_data({"nearest_area": []}) is None
	assert radio_announcer.extract_location_from_weather_data({"nearest_area": [{}]}) is None


def test_build_weather_phrase_prioritizes_json_location():
	"""Verifica que la ubicación provista por el JSON de wttr.in tenga prioridad sobre el fallback."""
	sample_with_area = {
		"nearest_area": [{"areaName": [{"value": "Villa Crespo"}]}],
		"current_condition": [{"temp_C": "20.0"}],
		"weather": [
			{"mintempC": "12", "maxtempC": "22", "hourly": []},
			{"mintempC": "11", "maxtempC": "21", "hourly": []},
		],
	}
	# Aunque se pase location="Buenos Aires", debe decir "Villa Crespo" que es lo que devolvió wttr.in
	phrase = radio_announcer.build_weather_phrase(
		sample_with_area,
		lead_in="Buenas:",
		template_idx=0,
		location="Buenos Aires",
	)
	assert phrase is not None
	assert "Villa Crespo" in phrase


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
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "2026-09-27 14"
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
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "2026-09-27 15"
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


def test_fetch_weather_json_cache_success_and_ttl(monkeypatch):
	"""Verifica que fetch_weather_json almacena en caché y recurre a ella ante fallas de red."""
	radio_announcer.reset_weather_cache()

	sample_data = {
		"current_condition": [{"temp_C": "25"}],
		"weather": [{"mintempC": "18", "maxtempC": "30", "hourly": []}],
	}

	# 1. Petición exitosa -> guarda en caché
	mock_resp = MagicMock()
	mock_resp.status = 200
	mock_resp.read.return_value = json.dumps(sample_data).encode("utf-8")
	mock_resp.__enter__.return_value = mock_resp

	with patch("urllib.request.urlopen", return_value=mock_resp):
		data = radio_announcer.fetch_weather_json("Tucumán", timeout=2.0)
		assert data == sample_data

	# 2. Fallo de red dentro de los 30 min -> debe devolver la caché
	with patch("urllib.request.urlopen", side_effect=OSError("Network down")):
		cached = radio_announcer.fetch_weather_json("Tucumán", timeout=2.0)
		assert cached == sample_data

	# 3. Fallo de red pero la caché expiró (más de 30 minutos) -> debe devolver None
	fake_now = time.time() + radio_announcer.WEATHER_CACHE_TTL + 10
	monkeypatch.setattr(time, "time", lambda: fake_now)
	with patch("urllib.request.urlopen", side_effect=OSError("Network down")):
		expired = radio_announcer.fetch_weather_json("Tucumán", timeout=2.0)
		assert expired is None


def test_build_weather_phrase_with_current_hour_filtering():
	"""Verifica que los slots horarios de lluvia pasados se descarten y solo apliquen los de la hora actual en adelante."""
	# Slot de las 9:00 tuvo 90% lluvia, slots de las 12:00, 15:00, 18:00 tuvieron 10%
	weather_data = {
		"current_condition": [{"temp_C": "21"}],
		"weather": [
			{
				"mintempC": "14",
				"maxtempC": "25",
				"hourly": [
					{"time": "900", "chanceofrain": "90"},
					{"time": "1200", "chanceofrain": "10"},
					{"time": "1500", "chanceofrain": "10"},
					{"time": "1800", "chanceofrain": "10"},
				],
			},
			{
				"mintempC": "15",
				"maxtempC": "26",
				"hourly": [{"time": "1200", "chanceofrain": "10"}],
			},
		],
	}

	# Si son las 14:00 (current_hour=14), el slot de las 9:00 ya pasó (9 + 2 = 11 < 14) -> NO llueve hoy
	phrase_afternoon = radio_announcer.build_weather_phrase(weather_data, current_hour=14, template_idx=0)
	assert phrase_afternoon is not None
	assert any(opt in phrase_afternoon for opt in radio_announcer.RAIN_NO_RAIN)
	assert "De lluvias ni hablemos" in phrase_afternoon

	# Si son las 8:00 (current_hour=8), el slot de las 9:00 está vigente (9 + 2 = 11 >= 8) -> SÍ llueve hoy
	phrase_morning = radio_announcer.build_weather_phrase(weather_data, current_hour=8, template_idx=0)
	assert phrase_morning is not None
	assert any(opt in phrase_morning for opt in radio_announcer.RAIN_TODAY_ONLY)
	assert "Atenti que hoy se esperan lluvias" in phrase_morning


@pytest.mark.asyncio
async def test_create_radio_announcement_assembly_failure_does_not_mark_weather(tmp_path):
	"""Verifica que si el ensamblado final falla, la hora del clima NO se marque en el estado."""
	out = tmp_path / "announcement.mp3"
	db_p = tmp_path / "tts_cache.db"
	dt_hour = datetime(2026, 9, 27, 18, 15, tzinfo=timezone.utc)

	mock_weather = {
		"current_condition": [{"temp_C": "20"}],
		"weather": [
			{"mintempC": "12", "maxtempC": "24", "hourly": []},
			{"mintempC": "13", "maxtempC": "25", "hourly": []},
		],
	}

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
		patch("scripts.radio_announcer.fetch_weather_json", return_value=mock_weather),
		patch("scripts.radio_announcer.assemble_announcement_audio", return_value=False),
	):
		ok, _title, err = await radio_announcer.create_radio_announcement(out, db_path=db_p, dt=dt_hour)
		assert ok is False
		assert "Falló el ensamblado" in err
		# El estado no debe haber sido guardado porque falló el ensamblado
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) is None


def test_modular_helpers_and_preload_integration():
	"""Verifica los helpers modulares de horas, minutos, grados, pases y reacciones."""
	hours = radio_announcer.get_modular_hour_segments()
	assert len(hours) == 24
	assert hours[0] == "Las doce"
	assert hours[1] == "Las una"
	assert hours[2] == "Las dos"

	minutes = radio_announcer.get_modular_minute_segments()
	assert len(minutes) == 12
	assert minutes[0] == "en punto."
	assert minutes[1] == "y cinco."
	assert minutes[2] == "y diez."
	assert minutes[3] == "y cuarto."
	assert minutes[4] == "y veinte."
	assert minutes[5] == "y veinticinco."
	assert minutes[6] == "y media."
	assert minutes[7] == "y treinta y cinco."
	assert minutes[8] == "menos veinte."
	assert minutes[9] == "menos cuarto."
	assert minutes[10] == "menos diez."
	assert minutes[11] == "menos cinco."

	degrees = radio_announcer.get_all_degree_segments(0, 10)
	assert len(degrees) == 11
	assert degrees[0] == "0 grados"
	assert degrees[10] == "10 grados"

	assert len(radio_announcer.RADIO_HANDOFFS) > 0
	assert len(radio_announcer.RADIO_REACTIONS) > 0

	# Preload collect_phrases
	from scripts import preload_tts_cache

	all_times = radio_announcer.get_all_time_segments()
	assert len(all_times) == 168  # 24 especiales en punto + 144 combinaciones (12 horas x 12 intervalos)
	assert "Las una en punto, es hora de mimir." in all_times
	assert "Las nueve y media." in all_times
	assert "Las tres y veinticinco." in all_times
	assert "Las diez menos cuarto." in all_times

	phrases = preload_tts_cache.collect_phrases()
	categories = {cat for cat, _ in phrases}
	assert "hora" in categories
	assert "minuto" in categories
	assert "pase" in categories
	assert "reaccion" in categories
	assert any(text == "Las nueve y media." for cat, text in phrases if cat == "hora")
	assert any(text == "Las doce" for cat, text in phrases if cat == "hora")
	assert any(text == "y media." for cat, text in phrases if cat == "minuto")


def test_select_radio_hosts():
	"""Verifica que host y cohost sean siempre diferentes y respeten las reglas de la fortuna del sistema."""
	# 1. 100 llamadas aleatorias garantizan host != cohost
	for _ in range(100):
		host, cohost = radio_announcer.select_radio_hosts()
		assert host in radio_announcer.VOICES
		assert cohost in radio_announcer.VOICES
		assert host != cohost

	# 2. Con host específico
	host_tomas, cohost_tomas = radio_announcer.select_radio_hosts(
		host_voice=radio_announcer.VOICE_TOMAS,
		is_system_fortune=False,
	)
	assert host_tomas == radio_announcer.VOICE_TOMAS
	assert cohost_tomas != radio_announcer.VOICE_TOMAS

	# 3. Fortuna del sistema: si el host no es Elena, el cohost DEBE ser Elena
	host_m, cohost_m = radio_announcer.select_radio_hosts(
		host_voice=radio_announcer.VOICE_MARIA,
		is_system_fortune=True,
	)
	assert host_m == radio_announcer.VOICE_MARIA
	assert cohost_m == radio_announcer.VOICE_ELENA

	# 4. Fortuna del sistema: si el host es Elena, el cohost es otra voz distinta
	host_e, cohost_e = radio_announcer.select_radio_hosts(
		host_voice=radio_announcer.VOICE_ELENA,
		is_system_fortune=True,
	)
	assert host_e == radio_announcer.VOICE_ELENA
	assert cohost_e != radio_announcer.VOICE_ELENA


def test_format_temperature_singular_and_negatives():
	"""Verifica concordancia singular y temperaturas negativas / bajo cero."""
	assert radio_announcer.format_temperature(1) == "1 grado"
	assert radio_announcer.format_temperature(0) == "0 grados"
	assert radio_announcer.format_temperature(25) == "25 grados"
	assert radio_announcer.format_temperature(-1) == "1 grado bajo cero"
	assert radio_announcer.format_temperature(-4) == "4 grados bajo cero"

	assert radio_announcer.format_temperature_range(14, 26) == "entre 14 y 26 grados"
	assert radio_announcer.format_temperature_range(0, 1) == "entre 0 y 1 grado"
	assert radio_announcer.format_temperature_range(-5, -1) == "entre 5 y 1 grado bajo cero"
	assert radio_announcer.format_temperature_range(-3, 4) == "entre 3 grados bajo cero y 4 grados"

	# Prueba build_weather_phrase con 1 grado y grados bajo cero
	data_singular = {
		"current_condition": [{"temp_C": "1"}],
		"weather": [
			{"mintempC": "0", "maxtempC": "1", "hourly": []},
			{"mintempC": "0", "maxtempC": "1", "hourly": []},
		],
	}
	phrase_sing = radio_announcer.build_weather_phrase(data_singular, template_idx=0)
	assert phrase_sing is not None
	assert "1 grado de temperatura actual" in phrase_sing
	assert "máxima alcanzará los 1 grado" in phrase_sing

	data_negative = {
		"current_condition": [{"temp_C": "-2"}],
		"weather": [
			{"mintempC": "-5", "maxtempC": "-1", "hourly": []},
			{"mintempC": "-4", "maxtempC": "-2", "hourly": []},
		],
	}
	phrase_neg = radio_announcer.build_weather_phrase(data_negative, template_idx=0)
	assert phrase_neg is not None
	assert "2 grados bajo cero de temperatura actual" in phrase_neg


def test_weather_condition_mapping():
	"""Verifica la clasificación de condiciones climáticas para reacciones de cabina."""
	assert radio_announcer.get_weather_condition(32, False, False) == "calor"
	assert radio_announcer.get_weather_condition(30, False, False) == "calor"
	assert radio_announcer.get_weather_condition(8, False, False) == "frio"
	assert radio_announcer.get_weather_condition(10, False, False) == "frio"
	assert radio_announcer.get_weather_condition(22, False, False) == "agradable"
	# Lluvia tiene prioridad
	assert radio_announcer.get_weather_condition(35, True, False) == "lluvia"
	assert radio_announcer.get_weather_condition(5, False, True) == "lluvia"


def test_booth_chat_segment_order():
	"""Verifica el orden estricto de los segmentos de diálogo en la charla de cabina."""
	plan_with_weather = radio_announcer.build_radio_dialogue_plan(
		intro="Buenas gente",
		hora_seg="Las tres",
		minuto_seg="y media.",
		lead_in="Momento oráculo:",
		fortuna="Mate amargo y cumbia",
		outro="¡Seguimos!",
		host_voice=radio_announcer.VOICE_TOMAS,
		cohost_voice=radio_announcer.VOICE_ELENA,
		weather_text="tenemos 20 grados",
		weather_condition="agradable",
		dialogue_mode=True,
	)

	categories = [cat for _text, _v, cat, _c in plan_with_weather]
	expected_categories = [
		"intro",
		"hora",
		"pase",
		"clima",
		"reaccion",
		"lead_in",
		"fortuna",
		"reaccion",
		"salida",
	]
	assert categories == expected_categories
	assert plan_with_weather[1][0] == "Las tres y media."

	# Verificamos asignación de voces
	voices = [v for _text, v, _cat, _c in plan_with_weather]
	# pase hablado por host (Tomás), clima hablado por cohost (Elena), reacción hablada por host (Tomás)
	assert voices[2] == radio_announcer.VOICE_TOMAS
	assert voices[3] == radio_announcer.VOICE_ELENA
	assert voices[4] == radio_announcer.VOICE_TOMAS

	# Pase debe incluir el nombre del cohost (Elena)
	pase_text = plan_with_weather[2][0]
	assert "Elena" in pase_text

	# Fortuna hablada por cohost (Elena)
	assert voices[6] == radio_announcer.VOICE_ELENA

	# Las dos reacciones del plan deben ser distintas
	reaccion_clima_text = plan_with_weather[4][0]
	reaccion_fortuna_text = plan_with_weather[7][0]
	assert reaccion_clima_text != reaccion_fortuna_text

	# Plan sin clima
	plan_no_weather = radio_announcer.build_radio_dialogue_plan(
		intro="Buenas gente",
		hora_seg="Las tres",
		minuto_seg=None,
		lead_in="Momento oráculo:",
		fortuna="Mate amargo",
		outro="¡Seguimos!",
		host_voice=radio_announcer.VOICE_TOMAS,
		cohost_voice=radio_announcer.VOICE_ELENA,
		weather_text=None,
		dialogue_mode=True,
	)
	categories_no_w = [cat for _text, _v, cat, _c in plan_no_weather]
	assert categories_no_w == ["intro", "hora", "lead_in", "fortuna", "reaccion", "salida"]


@pytest.mark.asyncio
async def test_weather_30_min_cooldown(tmp_path):
	"""Verifica que no se anuncie el clima con menos de 30 minutos de diferencia (ej: 13:58 y 14:02)."""
	out1 = tmp_path / "out1.mp3"
	out2 = tmp_path / "out2.mp3"
	out3 = tmp_path / "out3.mp3"
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

	dt_13_58 = datetime(2026, 9, 28, 13, 58, tzinfo=timezone.utc)
	dt_14_02 = datetime(2026, 9, 28, 14, 2, tzinfo=timezone.utc)  # Solo 4 min después
	dt_14_35 = datetime(2026, 9, 28, 14, 35, tzinfo=timezone.utc)  # 37 min después

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
		patch("scripts.radio_announcer.fetch_weather_json", return_value=mock_weather) as mock_fetch,
	):
		# 1. 13:58 -> Clima anunciado
		ok1, _title1, text1 = await radio_announcer.create_radio_announcement(
			out1,
			db_path=db_p,
			dt=dt_13_58,
			dialogue_mode=True,
		)
		assert ok1 is True
		assert "20 grados" in text1
		assert mock_fetch.call_count == 1
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "2026-09-28 13"

		# 2. 14:02 -> Nueva hora ("2026-09-28 14"), pero solo pasaron 4 min (< 30 min) -> SKIPPED
		ok2, _title2, text2 = await radio_announcer.create_radio_announcement(
			out2,
			db_path=db_p,
			dt=dt_14_02,
			dialogue_mode=True,
		)
		assert ok2 is True
		assert "20 grados" not in text2
		assert mock_fetch.call_count == 1  # No se volvió a llamar

		# 3. 14:35 -> Pasaron 37 min desde 13:58 (>= 30 min) -> Clima anunciado
		ok3, _title3, text3 = await radio_announcer.create_radio_announcement(
			out3,
			db_path=db_p,
			dt=dt_14_35,
			dialogue_mode=True,
		)
		assert ok3 is True
		assert "20 grados" in text3
		assert mock_fetch.call_count == 2
		assert radio_announcer.get_radio_state("last_weather_hour", db_path=db_p) == "2026-09-28 14"


def test_group_plan_into_speech_turns_preserves_no_merge_categories():
	"""Verifica que 'intro', 'hora', 'minuto', 'clima' y 'salida' nunca se fundan entre sí ni con segmentos contiguos."""
	v = radio_announcer.VOICE_TOMAS
	plan = [
		("Buenas tardes carpinchos...", v, "intro", True),
		("Las tres", v, "hora", True),
		("y veinticinco.", v, "minuto", True),
		("Clima agradable en la laguna.", v, "clima", False),
		("Che, escuchá esto:", v, "lead_in", True),
		("Seguimos con buena música.", v, "salida", True),
	]

	turns = radio_announcer.group_plan_into_speech_turns(plan)
	assert len(turns) == 6
	assert turns[0] == ("Buenas tardes carpinchos...", v, "intro", True)
	assert turns[1] == ("Las tres", v, "hora", True)
	assert turns[2] == ("y veinticinco.", v, "minuto", True)
	assert turns[3] == ("Clima agradable en la laguna.", v, "clima", False)
	assert turns[4] == ("Che, escuchá esto:", v, "lead_in", True)
	assert turns[5] == ("Seguimos con buena música.", v, "salida", True)


def test_group_plan_into_speech_turns_merges_allowed_categories():
	"""Verifica que segmentos consecutivos de la misma voz fuera de NO_MERGE se agrupen con la categoría del primer segmento."""
	v_elena = radio_announcer.VOICE_ELENA
	plan = [
		("Che, mirá lo que encontré:", v_elena, "lead_in", True),
		("En muerte y en boda, verás quien te honra.", v_elena, "fortuna", True),
	]

	turns = radio_announcer.group_plan_into_speech_turns(plan)
	assert len(turns) == 1
	merged_text, merged_v, merged_cat, merged_cache = turns[0]
	assert merged_text == "Che, mirá lo que encontré: En muerte y en boda, verás quien te honra."
	assert merged_v == v_elena
	assert merged_cat == "lead_in"
	assert merged_cache is True

	# Si un segmento tiene allow_cache=False, el turno agrupado resultante no se cachea
	plan_no_cache = [
		("Reacción inicial.", v_elena, "reaccion", True),
		("Comentario dinámico.", v_elena, "comentario", False),
	]
	turns_no_cache = radio_announcer.group_plan_into_speech_turns(plan_no_cache)
	assert len(turns_no_cache) == 1
	assert turns_no_cache[0][2] == "reaccion"
	assert turns_no_cache[0][3] is False


def test_group_plan_into_speech_turns_cuts_on_speaker_change():
	"""Verifica que el cambio de locutor siempre fuerce un corte de turno."""
	v1 = radio_announcer.VOICE_TOMAS
	v2 = radio_announcer.VOICE_VALENTINA
	plan = [
		("Pase a cabina.", v1, "pase", True),
		("El clima está lindo.", v2, "clima", False),
		("Qué alegría.", v1, "reaccion", True),
	]

	turns = radio_announcer.group_plan_into_speech_turns(plan)
	assert len(turns) == 3
	assert turns[0][1] == v1
	assert turns[1][1] == v2
	assert turns[2][1] == v1


def test_weather_desc_category_resolution():
	"""Verifica la resolución canónica de códigos y descripciones en inglés y español de wttr.in."""
	resolve = radio_announcer.resolve_weather_desc_category

	# 1. Códigos WWO numéricos
	assert resolve(code=113) == "sunny"
	assert resolve(code="113") == "sunny"
	assert resolve(code="116") == "partly_cloudy"
	assert resolve(code=119) == "cloudy"
	assert resolve(code="122") == "overcast"
	assert resolve(code=143) == "mist"
	assert resolve(code=248) == "fog"
	assert resolve(code=266) == "drizzle"
	assert resolve(code=296) == "light_rain"
	assert resolve(code=308) == "heavy_rain"
	assert resolve(code=389) == "thunderstorm"
	assert resolve(code=338) == "snow"
	assert resolve(code=350) == "hail"
	assert resolve(code=230) == "blizzard"

	# 2. Descripciones en inglés
	assert resolve(desc="Sunny") == "sunny"
	assert resolve(desc="Partly cloudy") == "partly_cloudy"
	assert resolve(desc="Patchy light drizzle") == "drizzle"
	assert resolve(desc="Moderate or heavy rain shower") == "heavy_rain"
	assert resolve(desc="Thundery outbreaks possible") == "thunderstorm"
	assert resolve(desc="Blizzard") == "blizzard"

	# 3. Descripciones en español (lang_es o desc)
	assert resolve(lang_es="Soleado") == "sunny"
	assert resolve(lang_es="Parcialmente nublado") == "partly_cloudy"
	assert resolve(lang_es="Cielo cubierto") == "overcast"
	assert resolve(lang_es="Niebla") == "fog"
	assert resolve(lang_es="Llovizna") == "drizzle"
	assert resolve(lang_es="Lluvia moderada") == "moderate_rain"
	assert resolve(lang_es="Tormenta") == "thunderstorm"

	# 4. Heurísticas por palabras clave
	assert resolve(desc="Una tormenta eléctrica inesperada") == "thunderstorm"
	assert resolve(desc="Fuerte granizo en la zona") == "hail"
	assert resolve(desc="Nevisca suave en la costa") == "snow"

	# 5. Vacíos o None
	assert resolve(desc=None, code=None, lang_es=None) == ""
	assert resolve(desc="", code="", lang_es="") == ""


def test_weather_desc_phrase_selection():
	"""Verifica la selección de frases según condición meteorológica y estabilidad con variant_idx."""
	# Determinismo con variant_idx
	p0 = radio_announcer.get_weather_desc_phrase(code=113, variant_idx=0)
	p1 = radio_announcer.get_weather_desc_phrase(code=113, variant_idx=1)
	assert p0 in radio_announcer.WEATHER_DESC_PHRASES["sunny"]
	assert p1 in radio_announcer.WEATHER_DESC_PHRASES["sunny"]
	assert p0 == radio_announcer.WEATHER_DESC_PHRASES["sunny"][0]
	assert p1 == radio_announcer.WEATHER_DESC_PHRASES["sunny"][1]

	# Por código
	phrase_fog = radio_announcer.get_weather_desc_phrase(code=248)
	assert phrase_fog in radio_announcer.WEATHER_DESC_PHRASES["fog"]

	# Por texto en inglés
	phrase_rain = radio_announcer.get_weather_desc_phrase(desc="Heavy rain")
	assert phrase_rain in radio_announcer.WEATHER_DESC_PHRASES["heavy_rain"]

	# Por texto en español
	phrase_drizzle = radio_announcer.get_weather_desc_phrase(lang_es="Llovizna")
	assert phrase_drizzle in radio_announcer.WEATHER_DESC_PHRASES["drizzle"]

	# Sin datos meteorológicos retorna string vacío
	assert radio_announcer.get_weather_desc_phrase(desc=None, code=None, lang_es=None) == ""
	assert radio_announcer.get_weather_desc_phrase(desc="", code=None, lang_es="") == ""


def test_get_all_weather_desc_phrases_integrity():
	"""Verifica que todas las frases de condición climática sean válidas en español y no violen la moderación."""
	all_phrases = radio_announcer.get_all_weather_desc_phrases()
	assert len(all_phrases) == 20 * 6  # 20 categorías x 6 variaciones
	for phrase in all_phrases:
		assert phrase and phrase.strip()
		assert radio_announcer.is_spanish_text(phrase), f"Frase no reconocida como español: '{phrase}'"
		assert not radio_announcer.contains_blacklisted_content(phrase), f"Frase con contenido vetado: '{phrase}'"


def test_build_weather_phrase_with_weather_desc():
	"""Verifica que build_weather_phrase incorpore fluidamente la frase de condición climática de wttr.in."""
	sample_sunny = {
		"current_condition": [
			{
				"temp_C": "23",
				"weatherCode": "113",
				"weatherDesc": [{"value": "Sunny"}],
			}
		],
		"weather": [
			{"mintempC": "14", "maxtempC": "25", "hourly": []},
			{"mintempC": "15", "maxtempC": "26", "hourly": []},
		],
	}

	phrase = radio_announcer.build_weather_phrase(sample_sunny, template_idx=0, location="Tigre")
	assert phrase is not None
	expected_sunny_p0 = radio_announcer.WEATHER_DESC_PHRASES["sunny"][0]
	assert expected_sunny_p0 in phrase
	assert "23 grados de temperatura actual. " + expected_sunny_p0 in phrase

	# Prueba con lang_es en español (Tormenta)
	sample_storm = {
		"current_condition": [
			{
				"temp_C": "19",
				"weatherCode": "389",
				"lang_es": [{"value": "Tormenta"}],
			}
		],
		"weather": [
			{"mintempC": "16", "maxtempC": "21", "hourly": []},
			{"mintempC": "14", "maxtempC": "20", "hourly": []},
		],
	}
	phrase_storm = radio_announcer.build_weather_phrase(sample_storm, template_idx=2, location="Paraná")
	assert phrase_storm is not None
	expected_storm_p2 = radio_announcer.WEATHER_DESC_PHRASES["thunderstorm"][2]
	assert expected_storm_p2 in phrase_storm


def test_radio_announcement_result_dataclass_and_unpacking():
	"""Verifica la estructura y retrocompatibilidad de RadioAnnouncementResult."""
	# Caso de éxito
	res_ok = radio_announcer.RadioAnnouncementResult(
		ok=True,
		display_title="Carpincho: Hola",
		script="Hola a todos",
		error=None,
	)
	assert res_ok.ok is True
	assert res_ok.display_title == "Carpincho: Hola"
	assert res_ok.script == "Hola a todos"
	assert res_ok.error is None

	# Desempaquetado como 3-tupla compatible (ok, display_title, script)
	ok, title, text = res_ok
	assert ok is True
	assert title == "Carpincho: Hola"
	assert text == "Hola a todos"
	assert len(res_ok) == 3
	assert res_ok[0] is True
	assert res_ok[1] == "Carpincho: Hola"
	assert res_ok[2] == "Hola a todos"

	# Caso de error
	res_err = radio_announcer.RadioAnnouncementResult(
		ok=False,
		display_title="",
		script="",
		error="Sin internet",
	)
	assert res_err.ok is False
	assert res_err.error == "Sin internet"
	ok_e, title_e, err_e = res_err
	assert ok_e is False
	assert title_e == ""
	assert err_e == "Sin internet"


def test_is_valid_mp3_stream_and_file(tmp_path):
	"""Verifica la detección robusta de streams y archivos MP3 válidos y corruptos."""
	# Streams en memoria
	assert radio_announcer.is_valid_mp3_stream(b"ID3\x03\x00\x00\x00") is True
	assert radio_announcer.is_valid_mp3_stream(b"\xff\xfb\x90\x64\x00") is True
	assert radio_announcer.is_valid_mp3_stream(b"\xff\xf3\x40\x00") is True
	assert radio_announcer.is_valid_mp3_stream(b"RIFF\x00\x00\x00") is False
	assert radio_announcer.is_valid_mp3_stream(b"") is False
	assert radio_announcer.is_valid_mp3_stream(b"\xff\x00") is False

	# Archivos en disco
	non_existent = tmp_path / "nope.mp3"
	assert radio_announcer.is_valid_mp3_file(non_existent) is False

	empty_file = tmp_path / "empty.mp3"
	empty_file.write_bytes(b"")
	assert radio_announcer.is_valid_mp3_file(empty_file) is False

	corrupt_file = tmp_path / "corrupt.mp3"
	corrupt_file.write_bytes(b"bad_data_trunc")
	assert radio_announcer.is_valid_mp3_file(corrupt_file) is False

	valid_id3_file = tmp_path / "valid_id3.mp3"
	valid_id3_file.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00\xff\xfb\x90")
	assert radio_announcer.is_valid_mp3_file(valid_id3_file) is True

	valid_raw_file = tmp_path / "valid_raw.mp3"
	valid_raw_file.write_bytes(b"\xff\xfb\x90\x64\x00\x11\x22\x33")
	assert radio_announcer.is_valid_mp3_file(valid_raw_file) is True


def test_estimate_mp3_duration():
	"""Verifica la estimación de duración en segundos de streams MP3 en memoria."""
	dummy_bytes = base64.b64decode(radio_announcer._DUMMY_MP3_DATA)
	dur = radio_announcer.estimate_mp3_duration(dummy_bytes)
	assert dur is not None
	assert isinstance(dur, float)
	assert dur > 0.0

	# Streams inválidos o vacíos
	assert radio_announcer.estimate_mp3_duration(b"") is None
	assert radio_announcer.estimate_mp3_duration(b"RIFF\x00\x00\x00") is None
	assert radio_announcer.estimate_mp3_duration(b"not_an_mp3_data") is None


def test_save_cached_audio_stores_duration(tmp_path):
	"""Verifica que save_cached_audio guarde la duración explícita y calculada en tts_cache.db."""
	db_p = tmp_path / "tts_cache_test.db"
	dummy_bytes = base64.b64decode(radio_announcer._DUMMY_MP3_DATA)

	# 1. Guardar con duración explícita
	radio_announcer.save_cached_audio(
		category="intro",
		voice=radio_announcer.VOICE_TOMAS,
		text="Hola carpinchos",
		audio_bytes=dummy_bytes,
		duration=3.5,
		db_path=db_p,
	)

	# 2. Guardar sin duración explícita (debe auto-estimar)
	radio_announcer.save_cached_audio(
		category="salida",
		voice=radio_announcer.VOICE_ELENA,
		text="Chau gente",
		audio_bytes=dummy_bytes,
		duration=None,
		db_path=db_p,
	)

	with sqlite3.connect(db_p) as conn:
		cur = conn.cursor()
		cur.execute("SELECT category, duration FROM tts_cache ORDER BY category ASC")
		rows = cur.fetchall()

	assert len(rows) == 2
	# intro tiene 3.5
	assert rows[0][0] == "intro"
	assert rows[0][1] == 3.5
	# salida tiene duración auto-estimada mayor a 0
	assert rows[1][0] == "salida"
	assert rows[1][1] is not None
	assert rows[1][1] > 0.0


def test_prune_tts_cache_db(tmp_path):
	"""Verifica la poda de caché SQLite por antigüedad y límite de registros con compactación VACUUM."""
	db_p = tmp_path / "tts_cache_prune.db"
	radio_announcer.init_tts_cache_db(db_p)

	now = time.time()
	dummy_bytes = base64.b64decode(radio_announcer._DUMMY_MP3_DATA)

	# Insertamos 5 entradas con distintos timestamps de last_used
	entries = [
		("item_very_old_1", now - (45 * 86400)),  # 45 días
		("item_very_old_2", now - (35 * 86400)),  # 35 días
		("item_recent_1", now - 200),
		("item_recent_2", now - 100),
		("item_recent_3", now),
	]
	with sqlite3.connect(db_p) as conn:
		for key, last_used in entries:
			conn.execute(
				"""
				INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
				VALUES (?, 'test', 'tomas', ?, ?, 1.0, ?, ?, 1)
				""",
				(key, key, dummy_bytes, last_used, last_used),
			)
		conn.commit()

	# 1. Poda por antigüedad: max_age_days=30, max_entries=10
	# Debe borrar item_very_old_1 e item_very_old_2 (2 eliminados)
	deleted = radio_announcer.prune_tts_cache_db(max_entries=10, max_age_days=30.0, db_path=db_p)
	assert deleted == 2

	with sqlite3.connect(db_p) as conn:
		cur = conn.cursor()
		cur.execute("SELECT count(*) FROM tts_cache")
		assert cur.fetchone()[0] == 3

	# 2. Poda por cantidad máxima: quedan 3, pedimos max_entries=2
	# Debe borrar el más antiguo de los recientes (item_recent_1)
	deleted_excess = radio_announcer.prune_tts_cache_db(max_entries=2, max_age_days=30.0, db_path=db_p)
	assert deleted_excess == 1

	with sqlite3.connect(db_p) as conn:
		cur = conn.cursor()
		cur.execute("SELECT cache_key FROM tts_cache ORDER BY last_used ASC")
		remaining = [r[0] for r in cur.fetchall()]
		assert remaining == ["item_recent_2", "item_recent_3"]

	# 3. Base de datos inexistente retorna 0 sin fallar
	non_existent = tmp_path / "ghost.db"
	assert radio_announcer.prune_tts_cache_db(db_path=non_existent) == 0
