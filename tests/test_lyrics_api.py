import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
	app = create_app()
	return TestClient(app)


def test_lyrics_token_status_endpoint(client):
	response = client.get("/api/lyrics/token")
	assert response.status_code == 200
	data = response.json()
	assert "is_configured" in data
	assert "status_text" in data
	assert "hours_remaining" in data


def test_lyrics_token_save_endpoint(client):
	response = client.post("/api/lyrics/token", json={"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock.token"})
	assert response.status_code == 200
	data = response.json()
	assert data.get("success") is True


def test_lyrics_search_mock_returns_converted_ass_providers(client):
	response = client.get("/api/lyrics/search?title=DANCE...&artist=Slayyyter")
	assert response.status_code == 200
	data = response.json()
	assert "providers" in data
	assert isinstance(data["providers"], list)
	assert len(data["providers"]) > 0

	# Each provider result must contain already converted ASS lyrics
	first = data["providers"][0]
	assert "provider" in first
	assert "ass" in first
	assert "[Script Info]" in first["ass"] or "[Events]" in first["ass"]


def test_lyrics_content_endpoint(client, tmp_path):
	# Test endpoint with non-existent path on disk returns mock ASS
	fake_audio = str(tmp_path / "song.mp3")
	response = client.get(f"/api/lyrics/content?path={fake_audio}")
	assert response.status_code == 200
	data = response.json()
	assert data["exists"] is True
	assert "[Events]" in data["content"]
	assert data["format"] == "ass"

	# Create an actual ASS file next to the fake audio
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


def test_lyrics_save_endpoint(client, tmp_path):
	audio_path = str(tmp_path / "song.mp3")
	content = "[Script Info]\nTitle: Saved\n[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\kf50}Test"
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
	saved_file = tmp_path / "song.ass"
	assert saved_file.exists()
	assert saved_file.read_text(encoding="utf-8") == content
