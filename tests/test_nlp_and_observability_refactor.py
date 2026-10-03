"""
Tests for NLP morphological compaction, lightweight Spanish language detection,
exception unmasking, and subprocess observability in scripts/radio_announcer.py
and scripts/radio_banks.py.
"""

from __future__ import annotations

import io
import logging
import subprocess
import urllib.error
from unittest.mock import MagicMock, patch

from scripts import radio_announcer, radio_banks


def test_morphological_verb_detection_voseo_and_conjugations():
	"""Verifica detección de desinencias verbales en voseo y tiempos verbales."""
	# Voseo: -ás, -és, -ís, -ate, -ete
	assert radio_announcer.has_conjugated_verb(["vos", "cantás"]) is True
	assert radio_announcer.has_conjugated_verb(["vos", "tenés"]) is True
	assert radio_announcer.has_conjugated_verb(["vos", "decís"]) is True
	assert radio_announcer.has_conjugated_verb(["fijate", "bien"]) is True
	assert radio_announcer.has_conjugated_verb(["metete", "adentro"]) is True

	# Pretéritos, condicionales y subjuntivos
	assert radio_announcer.has_conjugated_verb(["ellos", "caminaron"]) is True
	assert radio_announcer.has_conjugated_verb(["nosotros", "cantaríamos"]) is True
	assert radio_announcer.has_conjugated_verb(["si", "viniesen"]) is True
	assert radio_announcer.has_conjugated_verb(["él", "aprendió"]) is True

	# Oración válida con voseo rioplatense
	sentence_voseo = "Si te relajás un toque, vas a ver que el agua siempre calma."
	assert radio_announcer.is_valid_spoken_sentence(sentence_voseo) is True


def test_compact_nlp_dictionaries_size():
	"""Verifica que los diccionarios estáticos se hayan compactado algorítmicamente."""
	# COMMON_SPANISH_WORDS debe ser una lista cerrada y compacta (menos de 65 palabras funcionales)
	assert len(radio_banks.COMMON_SPANISH_WORDS) <= 65
	# COMMON_VERB_ROOTS debe existir en radio_banks como base del generador morfológico
	assert hasattr(radio_banks, "COMMON_VERB_ROOTS")
	assert isinstance(radio_banks.COMMON_VERB_ROOTS, (set, frozenset, tuple, list))


def test_fetch_weather_json_http_429_observability(caplog):
	"""Verifica manejo y log de advertencia específico para HTTP 429 Rate Limit."""
	err_429 = urllib.error.HTTPError(
		url="https://wttr.in/Parana",
		code=429,
		msg="Too Many Requests",
		hdrs={},
		fp=io.BytesIO(b"Rate limit exceeded"),
	)
	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", side_effect=err_429):
			res = radio_announcer.fetch_weather_json("Parana_Test_429")
			assert res is None
			assert any("429" in record.message or "Rate Limit" in record.message for record in caplog.records)


def test_fetch_weather_json_http_503_observability(caplog):
	"""Verifica manejo y log de advertencia específico para HTTP 503 Service Unavailable."""
	err_503 = urllib.error.HTTPError(
		url="https://wttr.in/Parana",
		code=503,
		msg="Service Unavailable",
		hdrs={},
		fp=io.BytesIO(b"Service Unavailable"),
	)
	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", side_effect=err_503):
			res = radio_announcer.fetch_weather_json("Parana_Test_503")
			assert res is None
			assert any("503" in record.message or "Service Unavailable" in record.message for record in caplog.records)


def test_fetch_weather_json_malformed_json_observability(caplog):
	"""Verifica que respuestas no JSON o malformadas registren warning sin explotar."""
	mock_resp = MagicMock()
	mock_resp.status = 200
	mock_resp.read.return_value = b"<html><head><title>502 Bad Gateway</title></head></html>"
	mock_resp.__enter__.return_value = mock_resp

	with caplog.at_level(logging.WARNING):
		with patch("urllib.request.urlopen", return_value=mock_resp):
			res = radio_announcer.fetch_weather_json("Parana_Test_Malformed")
			assert res is None
			assert any(
				"malformad" in record.message.lower() or "json" in record.message.lower() for record in caplog.records
			)


def test_fortune_stderr_observability_on_failure(caplog):
	"""Verifica que el error en stderr de fortune se capture y registre en nivel warning."""
	mock_proc = subprocess.CompletedProcess(
		args=["fortune", "-s"],
		returncode=1,
		stdout="",
		stderr="fortune: memory fault / database corrupted",
	)
	with caplog.at_level(logging.WARNING):
		with patch("shutil.which", return_value="/usr/bin/fortune"):
			with patch("scripts.radio_announcer.get_available_spanish_dbs", return_value=["es"]):
				with patch("subprocess.run", return_value=mock_proc):
					res = radio_announcer.get_system_fortune()
					assert res is None
					assert any(
						"database corrupted" in record.message or "fortune falló" in record.message
						for record in caplog.records
					)


def test_get_audio_duration_ffprobe_failure_observability(tmp_path, caplog):
	"""Verifica que si mutagen y ffprobe fallan, se capture stderr o error con logger.warning."""
	dummy_file = tmp_path / "corrupt.mp3"
	dummy_file.write_bytes(b"NOT_A_REAL_MP3_STREAM")

	mock_proc = subprocess.CompletedProcess(
		args=["ffprobe"],
		returncode=1,
		stdout="",
		stderr="Invalid data found when processing input",
	)
	with caplog.at_level(logging.WARNING):
		with patch("shutil.which", return_value="/usr/bin/ffprobe"):
			with patch("subprocess.run", return_value=mock_proc):
				dur = radio_announcer.get_audio_duration(dummy_file)
				assert dur == 0.0
				assert any("ffprobe" in record.message.lower() for record in caplog.records)
