"""
Pruebas de regresión y auditoría para el lote 4 de remediaciones:
1. Seguridad y autorización en el endpoint /lrc.
2. Persistencia de configuración en primer arranque CLI.
3. Chequeo de dependencia runtime de pydantic-settings.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
	return TestClient(app)


# ==============================================================================
# 1. Pruebas de autorización y seguridad en /lrc
# ==============================================================================


def test_lrc_registered_track_existing_lrc(client, tmp_path):
	"""Canción registrada en la biblioteca con .lrc existente => 200 y cache de 600s."""
	audio_file = tmp_path / "song.mp3"
	audio_file.write_bytes(b"fake audio")
	lrc_file = tmp_path / "song.lrc"
	lrc_file.write_text("[00:01.00] Letra de prueba", encoding="utf-8")

	mock_state = MagicMock()
	mock_state.is_radio_announcement.return_value = False
	mock_state.path_to_id = {str(audio_file): 1}
	mock_state.tracks_cache = [{"path": str(audio_file)}]

	with patch("app.api.v1.media.get_state", return_value=mock_state):
		resp = client.get(f"/api/v1/lrc?path={audio_file}")
		assert resp.status_code == 200
		assert "[00:01.00]" in resp.text
		assert resp.headers.get("Cache-Control") == "public, max-age=600, must-revalidate"


def test_lrc_unregistered_audio_existing_lrc(client, tmp_path):
	"""Archivo existente en disco pero NO registrado en biblioteca => 404 (evita path traversal/divulgación)."""
	secret_audio = tmp_path / "secret.mp3"
	secret_audio.write_bytes(b"secret")
	secret_lrc = tmp_path / "secret.lrc"
	secret_lrc.write_text("[00:00.00] Secreto confidencial", encoding="utf-8")

	mock_state = MagicMock()
	mock_state.is_radio_announcement.return_value = False
	mock_state.path_to_id = {}
	mock_state.tracks_cache = []

	with patch("app.api.v1.media.get_state", return_value=mock_state):
		resp = client.get(f"/api/v1/lrc?path={secret_audio}")
		assert resp.status_code == 404


def test_lrc_radio_announcement_existing_lrc(client, tmp_path):
	"""Locución radial reconocida con .lrc propio => 200 y Cache-Control: no-cache."""
	radio_audio = tmp_path / "locucion.mp3"
	radio_audio.write_bytes(b"radio")
	radio_lrc = tmp_path / "locucion.lrc"
	radio_lrc.write_text("[00:00.00] Buenas tardes audiencia", encoding="utf-8")

	mock_state = MagicMock()
	mock_state.is_radio_announcement.side_effect = lambda p: str(p) == str(radio_audio)
	mock_state.path_to_id = {}
	mock_state.tracks_cache = []
	mock_state.radio_pregenerated_path = None

	with patch("app.api.v1.media.get_state", return_value=mock_state):
		resp = client.get(f"/api/v1/lrc?path={radio_audio}")
		assert resp.status_code == 200
		assert "Buenas tardes" in resp.text
		assert resp.headers.get("Cache-Control") == "no-cache"


def test_lrc_radio_announcement_pregenerated_fallback(client, tmp_path):
	"""Locución radial sin .lrc directo pero con fallback a pregenerado => 200 y Cache-Control: no-cache."""
	radio_audio = tmp_path / "locucion_sin_lrc.mp3"
	radio_audio.write_bytes(b"radio")

	pre_audio = tmp_path / "pregen.mp3"
	pre_audio.write_bytes(b"pregen")
	pre_lrc = tmp_path / "pregen.lrc"
	pre_lrc.write_text("[00:00.00] Clima en vivo", encoding="utf-8")

	mock_state = MagicMock()
	mock_state.is_radio_announcement.side_effect = lambda p: str(p) == str(radio_audio)
	mock_state.path_to_id = {}
	mock_state.tracks_cache = []
	mock_state.radio_pregenerated_path = str(pre_audio)

	with patch("app.api.v1.media.get_state", return_value=mock_state):
		resp = client.get(f"/api/v1/lrc?path={radio_audio}")
		assert resp.status_code == 200
		assert "Clima en vivo" in resp.text
		assert resp.headers.get("Cache-Control") == "no-cache"


# ==============================================================================
# 2. Pruebas de persistencia de configuración en primer arranque CLI
# ==============================================================================


def test_first_run_cli_persists_config(tmp_path, monkeypatch):
	"""Primer arranque sin wizard (--no-interactive --dir ...) debe crear y guardar rockola_config.json."""
	from app.cli.entrypoint import main
	from app.core.config import load_config

	config_file = tmp_path / "custom_config.json"
	assert not config_file.exists()

	test_dir = str(tmp_path / "MyMusic")
	test_dir2 = str(tmp_path / "ExtraMusic")
	Path(test_dir).mkdir()
	Path(test_dir2).mkdir()

	cli_args = [
		"larockola",
		"--config",
		str(config_file),
		"--no-interactive",
		"--dir",
		test_dir,
		"--dir2",
		test_dir2,
		"--port",
		"1888",
		"--host",
		"127.0.0.1",
		"--weather-location",
		"Rosario",
		"--log-level",
		"WARNING",
	]
	monkeypatch.setattr(sys, "argv", cli_args)

	# Mock de uvicorn.run para no bloquear levantando el servidor
	with patch("uvicorn.run") as mock_run:
		main()
		mock_run.assert_called_once()

	# El archivo de configuración debe haber sido creado con los valores suministrados
	assert config_file.is_file(), "El archivo rockola_config.json debe persistirse en el primer arranque"
	saved = load_config(config_file)
	assert saved["music_dir"] == test_dir
	assert saved["music_dir2"] == test_dir2
	assert saved["port"] == 1888
	assert saved["host"] == "127.0.0.1"
	assert saved["weather_location"] == "Rosario"
	assert saved["log_level"] == "WARNING"

	# Segundo arranque sin --dir debe mantener test_dir persistido
	cli_args_2 = [
		"larockola",
		"--config",
		str(config_file),
		"--no-interactive",
	]
	monkeypatch.setattr(sys, "argv", cli_args_2)

	with patch("uvicorn.run"):
		from app.core.config import get_settings

		main()
		active_settings = get_settings()
		assert active_settings.music_dir == test_dir
		assert active_settings.music_dir2 == test_dir2
		assert active_settings.port == 1888
		assert active_settings.weather_location == "Rosario"


def test_existing_config_is_not_overwritten_by_defaults(tmp_path, monkeypatch):
	"""Un archivo de configuración existente no debe ser sobreescrito involuntariamente."""
	from app.cli.entrypoint import main
	from app.core.config import load_config

	config_file = tmp_path / "existing_config.json"
	initial_data = {
		"music_dir": "/custom/music",
		"music_dir2": "/second/music",
		"port": 9999,
		"host": "192.168.1.50",
		"weather_location": "Córdoba",
		"log_level": "DEBUG",
	}
	config_file.write_text(json.dumps(initial_data), encoding="utf-8")

	cli_args = [
		"larockola",
		"--config",
		str(config_file),
		"--no-interactive",
	]
	monkeypatch.setattr(sys, "argv", cli_args)

	with patch("uvicorn.run"):
		main()

	# El archivo en disco debe mantener los valores iniciales intactos
	saved = load_config(config_file)
	assert saved["music_dir"] == "/custom/music"
	assert saved["port"] == 9999
	assert saved["weather_location"] == "Córdoba"


# ==============================================================================
# 3. Auditoría de pydantic-settings como dependencia runtime
# ==============================================================================


def test_check_python_packages_includes_pydantic_settings():
	"""_check_python_packages debe verificar pydantic_settings y reportar pip install pydantic-settings si falta."""
	from app.cli.entrypoint import _check_python_packages

	orig_find_spec = importlib.util.find_spec

	def fake_find_spec(name):
		if name == "pydantic_settings":
			return None
		return orig_find_spec(name)

	with patch("importlib.util.find_spec", side_effect=fake_find_spec):
		missing_req, _ = _check_python_packages(is_frozen=False)
		names = [m[0] for m in missing_req]
		assert "pydantic_settings" in names
		fix_cmd = dict(missing_req)["pydantic_settings"]
		assert "pip install pydantic-settings" in fix_cmd


def test_requirements_file_declares_pydantic_settings():
	"""requirements.txt debe declarar explícitamente pydantic-settings."""
	root_dir = Path(__file__).resolve().parents[1]
	req_file = root_dir / "requirements.txt"
	assert req_file.is_file()
	content = req_file.read_text(encoding="utf-8")
	assert "pydantic-settings" in content or "pydantic_settings" in content
