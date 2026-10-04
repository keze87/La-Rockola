from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import CommandRequest, app, handle_command, state


@pytest.fixture(autouse=True)
def reset_weather_location_fixture():
	orig_loc = state.weather_location
	try:
		yield
	finally:
		state.weather_location = orig_loc


def test_get_full_state_dict_includes_weather_location():
	state.weather_location = "Córdoba, Argentina"
	full_state = state.get_full_state_dict()
	assert "weather_location" in full_state
	assert full_state["weather_location"] == "Córdoba, Argentina"


@pytest.mark.asyncio
async def test_set_weather_location_command(tmp_path):
	dummy_config_file = tmp_path / "rockola_config.json"
	with (
		patch("server.get_config_path", return_value=dummy_config_file),
		patch("scripts.radio_announcer.reset_weather_cache") as mock_reset_cache,
		patch("server.broadcast_state", new_callable=AsyncMock) as mock_broadcast,
	):
		req = CommandRequest(cmd="set_weather_location", location="-34.6037,-58.3816")
		res = await handle_command(req)
		assert res.get("status") == "ok"
		assert state.weather_location == "-34.6037,-58.3816"
		mock_reset_cache.assert_called_once()
		mock_broadcast.assert_awaited()

		# Verifica persistencia en el archivo JSON
		import asyncio
		import json

		def _read_cfg():
			with open(dummy_config_file, "r", encoding="utf-8") as f:
				return json.load(f)

		saved_cfg = await asyncio.to_thread(_read_cfg)
		assert saved_cfg.get("weather_location") == "-34.6037,-58.3816"


@pytest.mark.asyncio
async def test_weather_preview_endpoint():
	fake_wttr_data = {
		"nearest_area": [{"areaName": [{"value": "Constitución"}]}],
		"current_condition": [{"temp_C": "22", "weatherDesc": [{"value": "Sunny"}]}],
		"weather": [
			{"mintempC": "14", "maxtempC": "24", "hourly": []},
			{"mintempC": "15", "maxtempC": "25", "hourly": []},
		],
	}

	with patch("scripts.radio_announcer.fetch_weather_json", return_value=fake_wttr_data):
		transport = ASGITransport(app=app)
		async with AsyncClient(transport=transport, base_url="http://test") as client:
			resp = await client.get("/api/weather/preview?location=-34.6037,-58.3816")
			assert resp.status_code == 200
			body = resp.json()
			assert body["ok"] is True
			assert body["area_name"] == "Constitución"
			assert body["temp_c"] == 22
			assert "phrase" in body
			assert "Constitución" in body["phrase"]


@pytest.mark.asyncio
async def test_preview_weather_supports_head_request():
	fake_wttr_data = {
		"current_condition": [{"temp_C": "22"}],
		"nearest_area": [{"areaName": [{"value": "Constitución"}]}],
		"weather": [
			{
				"mintempC": "15",
				"maxtempC": "25",
				"hourly": [{"weatherDesc": [{"value": "Soleado"}]}],
			}
		],
	}

	with patch("scripts.radio_announcer.fetch_weather_json", return_value=fake_wttr_data):
		transport = ASGITransport(app=app)
		async with AsyncClient(transport=transport, base_url="http://test") as client:
			resp = await client.head("/api/weather/preview?location=-34.6037,-58.3816")
			assert resp.status_code == 200
