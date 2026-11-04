from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SAMPLE_JWT = (
	"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
	"eyJpYXQiOjE3MDAwMDAwMDAsImV4cCI6MjAwMDAwMDAwMCwianRpIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwiaXAiOiIxMjcuMC4wLjEifQ."
	"c2lnbmF0dXJlX2V4YW1wbGVfdmFsdWU"
)

SAMPLE_CURL = (
	"curl 'https://lyrics.api.dacubeking.com/v2/lyrics' "
	"-X POST "
	f"--data-raw 'videoId=9vWNauaZAgg&song=Back+In+Black&artist=AC%2FDC&duration=255&album=Back+In+Black&token={SAMPLE_JWT}'"
)


@pytest.fixture
def client():
	app = create_app()
	return TestClient(app)


def test_lyrics_token_status_and_save_endpoint(client):
	response = client.post("/api/lyrics/token", json={"token": SAMPLE_CURL})
	assert response.status_code == 200
	data = response.json()
	assert data.get("success") is True
	assert "status_text" in data
	assert "hours_remaining" in data

	status_res = client.get("/api/lyrics/token")
	assert status_res.status_code == 200
	status_data = status_res.json()
	assert status_data["is_configured"] is True


def test_lyrics_search_real_betterlyrics_returns_converted_ass_providers(client, monkeypatch):
	client.post("/api/lyrics/token", json={"token": SAMPLE_CURL})

	fixture_file = Path(__file__).parent / "fixtures" / "betterlyrics_back_in_black.txt"
	fixture_text = fixture_file.read_text(encoding="utf-8")

	class MockResponse:
		status_code = 200
		text = fixture_text

		def raise_for_status(self):
			pass

	async def mock_post(*args, **kwargs):
		return MockResponse()

	monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

	response = client.get("/api/lyrics/search?title=Back+In+Black&artist=AC%2FDC&duration=255")
	assert response.status_code == 200
	data = response.json()
	assert "providers" in data
	assert isinstance(data["providers"], list)
	assert len(data["providers"]) >= 4

	# Cada proveedor debe traer las letras de Back In Black ya convertidas a ASS
	first = data["providers"][0]
	assert "provider" in first
	assert "ass" in first
	assert "[Script Info]" in first["ass"]
	assert "[Events]" in first["ass"]
	assert "Dialogue:" in first["ass"]
	assert "black" in first["ass"].lower()


def test_lyrics_content_endpoint(client, tmp_path):
	# 1. Cuando no existe .ass en disco, devuelve exists=False aunque exista un .lrc
	# (solo tiene sentido usar .ass para letras palabra por palabra, no inventar un .ass desde un .lrc simple)
	fake_audio = str(tmp_path / "song.mp3")
	lrc_file = tmp_path / "song.lrc"
	lrc_file.write_text("[00:01.00] Letra desde LRC\n[00:04.00] Segunda línea", encoding="utf-8")

	response = client.get(f"/api/lyrics/content?path={fake_audio}")
	assert response.status_code == 200
	data = response.json()
	assert data["exists"] is False
	assert data["content"] == ""

	# 2. Si existe un .ass en disco, se devuelve tal cual
	ass_file = tmp_path / "song.ass"
	ass_file.write_text(
		"[Script Info]\nTitle: Test\n[Events]\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\kf100}Hola",
		encoding="utf-8",
	)

	response = client.get(f"/api/lyrics/content?path={fake_audio}")
	assert response.status_code == 200
	data = response.json()
	assert data["exists"] is True
	assert "Hola" in data["content"]
	assert data["format"] == "ass"


def test_lyrics_save_endpoint_creates_complementary_lrc_if_missing(client, tmp_path):
	audio_path = str(tmp_path / "song.mp3")
	content = (
		"[Script Info]\nTitle: Saved\n"
		"[Events]\n"
		"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\kf50}Test syllable\n"
	)
	response = client.post(
		"/api/lyrics/save",
		json={
			"path": audio_path,
			"content": content,
			"format": "ass",
		},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["success"] is True

	# Se guardó el .ass
	saved_ass = tmp_path / "song.ass"
	assert saved_ass.exists()
	assert saved_ass.read_text(encoding="utf-8") == content

	# Al no existir un .lrc previo, genera automáticamente un .lrc complementario para otros reproductores
	saved_lrc = tmp_path / "song.lrc"
	assert saved_lrc.exists()
	lrc_text = saved_lrc.read_text(encoding="utf-8")
	assert "[00:01.00]Test syllable" in lrc_text
	assert "{\\kf" not in lrc_text


def test_lyrics_save_endpoint_preserves_existing_lrc(client, tmp_path):
	audio_path = str(tmp_path / "song.mp3")
	existing_lrc = tmp_path / "song.lrc"
	existing_lrc.write_text("[00:05.00]Letra original en disco", encoding="utf-8")

	content = (
		"[Script Info]\nTitle: Saved\n[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\kf50}Nuevo ASS"
	)
	response = client.post(
		"/api/lyrics/save",
		json={
			"path": audio_path,
			"content": content,
			"format": "ass",
		},
	)
	assert response.status_code == 200

	# El .lrc existente NO se debe sobreescribir
	assert existing_lrc.read_text(encoding="utf-8") == "[00:05.00]Letra original en disco"


def test_lyrics_search_supports_letras_api_prefix_and_spa_route(client, monkeypatch):
	fixture_file = Path(__file__).parent / "fixtures" / "betterlyrics_back_in_black.txt"
	fixture_text = fixture_file.read_text(encoding="utf-8")

	class MockResponse:
		status_code = 200
		text = fixture_text

		def raise_for_status(self):
			pass

	async def mock_post(*args, **kwargs):
		return MockResponse()

	monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

	# 1. Cualquier consulta enrutada a /letras/api/lyrics/search no debe dar 404
	response = client.get("/letras/api/lyrics/search?title=Back+In+Black&artist=AC%2FDC&duration=255")
	assert response.status_code == 200
	data = response.json()
	assert "providers" in data

	# 2. La ruta SPA directa a /letras debe servir index.html
	spa_res = client.get("/letras")
	assert spa_res.status_code == 200
	assert "text/html" in spa_res.headers.get("content-type", "")
