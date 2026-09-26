import asyncio
from datetime import datetime, timezone
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
	# 15:15
	dt_quarter = datetime(2026, 9, 26, 15, 15, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_quarter)
	assert "tres y cuarto" in t_str
	assert "tarde" in t_str

	# 15:30
	dt_half = datetime(2026, 9, 26, 15, 30, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_half)
	assert "tres y media" in t_str

	# 15:45
	dt_three_q = datetime(2026, 9, 26, 15, 45, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_three_q)
	assert "cuatro menos cuarto" in t_str

	# 15:23
	dt_exact = datetime(2026, 9, 26, 15, 23, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_exact)
	assert "15 horas, 23 minutos" in t_str

	# 09:01
	dt_one_min = datetime(2026, 9, 26, 9, 1, tzinfo=timezone.utc)
	t_str = radio_announcer.format_radio_time(dt_one_min)
	assert "9 horas, un minuto" in t_str


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

	mock_comm = MagicMock()
	mock_comm.save = AsyncMock(return_value=None)

	with (
		patch("scripts.radio_announcer.HAS_EDGE_TTS", True),
		patch("scripts.radio_announcer.edge_tts.Communicate", return_value=mock_comm),
	):
		ok, title, text = await radio_announcer.create_radio_announcement(out_p, voice=radio_announcer.VOICE_TOMAS)
		assert ok is True
		assert "Tomás" in title
		assert len(text) > 0
		assert radio_announcer.is_spanish_text(text) is True
		mock_comm.save.assert_awaited_once_with(str(out_p))


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
