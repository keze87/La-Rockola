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


@pytest.fixture
def music_dir(tmp_path, isolate_container):
	"""Carpeta de música autorizada para las rutas de letras (aislada por test)."""
	root = tmp_path / "music"
	root.mkdir()
	isolate_container.settings.music_dir = str(root)
	isolate_container.settings.music_dir2 = None
	return root


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


def test_lyrics_content_endpoint(client, music_dir):
	# 1. Cuando no existe .ass en disco, devuelve exists=False aunque exista un .lrc
	# (solo tiene sentido usar .ass para letras palabra por palabra, no inventar un .ass desde un .lrc simple)
	fake_audio = str(music_dir / "song.mp3")
	lrc_file = music_dir / "song.lrc"
	lrc_file.write_text("[00:01.00] Letra desde LRC\n[00:04.00] Segunda línea", encoding="utf-8")

	response = client.get(f"/api/lyrics/content?path={fake_audio}")
	assert response.status_code == 200
	data = response.json()
	assert data["exists"] is False
	assert data["content"] == ""

	# 2. Si existe un .ass en disco, se devuelve tal cual
	ass_file = music_dir / "song.ass"
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


def test_lyrics_save_endpoint_creates_complementary_lrc_if_missing(client, music_dir):
	audio_path = str(music_dir / "song.mp3")
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
	saved_ass = music_dir / "song.ass"
	assert saved_ass.exists()
	assert saved_ass.read_text(encoding="utf-8") == content

	# Al no existir un .lrc previo, genera automáticamente un .lrc complementario para otros reproductores
	saved_lrc = music_dir / "song.lrc"
	assert saved_lrc.exists()
	lrc_text = saved_lrc.read_text(encoding="utf-8")
	assert "[00:01.00]Test syllable" in lrc_text
	assert "{\\kf" not in lrc_text


def test_lyrics_save_endpoint_preserves_existing_lrc(client, music_dir):
	audio_path = str(music_dir / "song.mp3")
	existing_lrc = music_dir / "song.lrc"
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


def test_spa_route_letras_serves_index_and_has_no_duplicated_api_prefixes(client):
	# La ruta SPA directa a /letras debe servir index.html
	spa_res = client.get("/letras")
	assert spa_res.status_code == 200
	assert "text/html" in spa_res.headers.get("content-type", "")

	# Los prefijos duplicados fueron un parche: el frontend resuelve la base con apiUrl
	assert client.get("/letras/api/lyrics/token").status_code == 404
	assert client.get("/lyrics/api/lyrics/token").status_code == 404
	assert client.get("/lyrics/token").status_code == 404
	assert client.get("/api/lyrics/token").status_code == 200


def test_lyrics_save_rejects_path_outside_music_dirs(client, music_dir, tmp_path):
	outside = tmp_path / "outside" / "song.mp3"
	response = client.post(
		"/api/lyrics/save", json={"path": str(outside), "content": "[Script Info]\n[Events]\n", "format": "ass"}
	)
	assert response.status_code == 403
	assert not (tmp_path / "outside").exists()


def test_lyrics_save_rejects_traversal_with_dotdot(client, music_dir, tmp_path):
	sneaky = f"{music_dir}/../escaped/song.mp3"
	response = client.post("/api/lyrics/save", json={"path": sneaky, "content": "x", "format": "ass"})
	assert response.status_code == 403
	assert not (tmp_path / "escaped").exists()


def test_lyrics_save_rejects_symlink_escaping_music_dir(client, music_dir, tmp_path):
	target = tmp_path / "elsewhere"
	target.mkdir()
	(music_dir / "link").symlink_to(target, target_is_directory=True)
	response = client.post(
		"/api/lyrics/save", json={"path": str(music_dir / "link" / "song.mp3"), "content": "x", "format": "ass"}
	)
	assert response.status_code == 403
	assert list(target.iterdir()) == []


@pytest.mark.parametrize("bad_format", ["sh", "py", "../x", "mp3", ""])
def test_lyrics_save_rejects_unknown_formats(client, music_dir, bad_format):
	response = client.post(
		"/api/lyrics/save", json={"path": str(music_dir / "song.mp3"), "content": "x", "format": bad_format}
	)
	assert response.status_code == 422
	assert list(music_dir.iterdir()) == []


def test_lyrics_save_accepts_lrc_format(client, music_dir):
	response = client.post(
		"/api/lyrics/save", json={"path": str(music_dir / "song.mp3"), "content": "[00:01.00]Hola", "format": "lrc"}
	)
	assert response.status_code == 200
	assert (music_dir / "song.lrc").read_text(encoding="utf-8") == "[00:01.00]Hola"


def test_lyrics_content_rejects_path_outside_music_dirs(client, music_dir, tmp_path):
	(tmp_path / "secret.ass").write_text("[Script Info]\nsecreto", encoding="utf-8")
	response = client.get(f"/api/lyrics/content?path={tmp_path / 'secret.mp3'}")
	assert response.status_code == 403


def test_lyrics_allows_known_track_from_library_cache(client, music_dir, tmp_path, isolate_container):
	extra = tmp_path / "otra_carpeta"
	extra.mkdir()
	track = extra / "song.mp3"
	isolate_container.ensure_orchestrator().tracks_cache = [{"path": str(track)}]
	response = client.post("/api/lyrics/save", json={"path": str(track), "content": "[00:01.00]Hola", "format": "lrc"})
	assert response.status_code == 200
	assert (extra / "song.lrc").exists()
