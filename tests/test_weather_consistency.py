from __future__ import annotations

import pytest

from scripts.radio_announcer import get_weather_info
from scripts.radio_banks import PRECIPITATING_CATEGORIES, RAIN_DESCRIPTIONS


def _sample_weather_data(current_desc="Thunderstorm", current_code=200, chance_today=0, chance_tomorrow=0):
	return {
		"current_condition": [
			{
				"temp_C": "24",
				"weatherCode": str(current_code),
				"weatherDesc": [{"value": current_desc}],
			}
		],
		"nearest_area": [
			{
				"areaName": [{"value": "San Miguel de Tucumán"}],
				"region": [{"value": "Tucuman"}],
				"country": [{"value": "Argentina"}],
			}
		],
		"weather": [
			{
				"mintempC": "18",
				"maxtempC": "28",
				"hourly": [
					{"time": "0", "chanceofrain": str(chance_today)},
					{"time": "300", "chanceofrain": str(chance_today)},
					{"time": "600", "chanceofrain": str(chance_today)},
					{"time": "900", "chanceofrain": str(chance_today)},
					{"time": "1200", "chanceofrain": str(chance_today)},
					{"time": "1500", "chanceofrain": str(chance_today)},
					{"time": "1800", "chanceofrain": str(chance_today)},
					{"time": "2100", "chanceofrain": str(chance_today)},
				],
			},
			{
				"mintempC": "19",
				"maxtempC": "29",
				"hourly": [
					{"time": "1200", "chanceofrain": str(chance_tomorrow)},
				],
			},
		],
	}


def test_thunderstorm_current_forces_rain_today_and_no_contradiction():
	"""When it is currently storming, the announcer must NOT say no rain is expected."""
	data = _sample_weather_data(current_desc="Thunderstorm", current_code=200, chance_today=10, chance_tomorrow=0)
	result = get_weather_info(data, current_hour=22)
	assert result is not None
	phrase, condition = result

	# Condition must reflect rain / storm, not dry
	assert condition == "lluvia"

	# Phrase must not claim no rain / clear skies
	contradictory_phrases = [
		"De lluvias ni hablemos",
		"cielo despejado",
		"ni miras de que caiga una gota",
		"Cero agua en el horizonte",
		"Olvidate del paraguas",
		"Sin una gota a la vista",
		"Ni una sola nube",
	]
	for forbidden in contradictory_phrases:
		assert forbidden.lower() not in phrase.lower(), f"Contradiction found: '{forbidden}' in '{phrase}'"


def test_precipitating_categories_exist_and_include_rain_and_storm():
	"""PRECIPITATING_CATEGORIES must contain standard rain/storm categories."""
	assert "thunderstorm" in PRECIPITATING_CATEGORIES
	assert "light_rain" in PRECIPITATING_CATEGORIES
	assert "heavy_rain" in PRECIPITATING_CATEGORIES
	assert "drizzle" in PRECIPITATING_CATEGORIES


@pytest.mark.parametrize(
	("desc", "code"),
	[
		("Thunderstorm", 200),
		("Patchy light rain with thunder", 386),
		("Moderate or heavy rain with thunder", 389),
		("Light rain", 296),
		("Heavy rain", 308),
		("Light drizzle", 263),
	],
)
def test_all_precipitating_conditions_force_rain_today(desc, code):
	"""Any active precipitation condition in current_condition forces llueve_hoy=True."""
	data = _sample_weather_data(current_desc=desc, current_code=code, chance_today=0, chance_tomorrow=0)
	result = get_weather_info(data, current_hour=14)
	assert result is not None
	phrase, _ = result
	assert "De lluvias ni hablemos" not in phrase
	assert "ni miras de que caiga una gota" not in phrase


def test_dry_rain_descriptions_do_not_falsely_claim_clear_sun_when_cloudy():
	"""RAIN_DESCRIPTIONS[(False, False)] should focus on absence of rain without asserting clear sunny skies."""
	for desc in RAIN_DESCRIPTIONS[(False, False)]:
		assert "sol pleno" not in desc
		assert "cielo limpito" not in desc
		assert "Ni una sola nube" not in desc
		assert "cielo abierto y despejado" not in desc
