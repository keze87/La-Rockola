"""
Definición de locutores de cabina, nombres, géneros y perfiles de prosodia para síntesis TTS.
"""

from __future__ import annotations

VOICE_TOMAS = "es-AR-TomasNeural"
VOICE_ELENA = "es-AR-ElenaNeural"
VOICE_MARIA = "es-CR-MariaNeural"
VOICE_VALENTINA = "es-UY-ValentinaNeural"
VOICES: list[str] = [VOICE_TOMAS, VOICE_ELENA, VOICE_MARIA, VOICE_VALENTINA]

VOICE_NAMES: dict[str, str] = {
	VOICE_TOMAS: "Tomás",
	VOICE_ELENA: "Elena",
	VOICE_MARIA: "María",
	VOICE_VALENTINA: "Valentina",
}

# Género gramatical de cada locutor (para concordar vocativos y adjetivos: compadre/comadre, filósofo/filósofa)
VOICE_GENDERS: dict[str, str] = {
	VOICE_TOMAS: "m",
	VOICE_ELENA: "f",
	VOICE_MARIA: "f",
	VOICE_VALENTINA: "f",
}
DEFAULT_GENDER: str = "m"

VOCATIVOS: dict[str, str] = {"m": "compadre", "f": "comadre"}
COMPANEROS: dict[str, str] = {"m": "compañero", "f": "compañera"}
FILOSOFOS: dict[str, str] = {"m": "filósofo", "f": "filósofa"}

# Prosodia fija por locutor (personajes con impronta propia para sonar naturales y no robóticos)
VOICE_PROSODY: dict[str, dict[str, str]] = {
	VOICE_TOMAS: {
		"rate": "-4%",
		"pitch": "-3Hz",
		"volume": "+0%",
	},
	VOICE_ELENA: {
		"rate": "-6%",
		"pitch": "-4Hz",
		"volume": "+0%",
	},
	VOICE_MARIA: {
		"rate": "+3%",
		"pitch": "+1Hz",
		"volume": "+0%",
	},
	VOICE_VALENTINA: {
		"rate": "+2%",
		"pitch": "+0Hz",
		"volume": "+0%",
	},
}

DEFAULT_TTS_TIMEOUT: float = 12.0
DEFAULT_TTS_RETRIES: int = 3
DEFAULT_BG_VOLUME: float = 0.1

DEFAULT_RADIO_ARTIST: str = "Transmisión de Cabina 🎙️"
DEFAULT_RADIO_ALBUM: str = "La Rockola del Carpincho"
DEFAULT_RADIO_TITLE: str = "Transmisión de Cabina"
DEFAULT_COHOST_NAME: str = "compadre"
DEFAULT_HOST_NAME: str = "Transmisión de Cabina"
DEFAULT_COHOST_DISPLAY_NAME: str = "Co-conductor"
