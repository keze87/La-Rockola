"""
Definición de locutores de cabina, nombres, géneros y perfiles de prosodia para síntesis TTS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GenderVariant:
	"""Variante de frase según el género gramatical (masculino/femenino) del locutor o destinatario."""

	m: str
	f: str
	key: str | None = None

	def for_gender(self, gender: str) -> str:
		return self.f if gender == "f" else self.m

	def all_variants(self) -> tuple[str, ...]:
		return (self.m, self.f)


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


def resolve_voice_gender(voice: str | None) -> str:
	"""Resuelve el género gramatical ('m' o 'f') de una voz de cabina."""
	return VOICE_GENDERS.get(voice or "", DEFAULT_GENDER)


# Perfiles editoriales de cabina: definen la personalidad, afinidades y registro de cada voz
HOST_PROFILES: dict[str, dict[str, Any]] = {
	VOICE_TOMAS: {
		"name": "Tomás",
		"role": "Conductor de piso e histórico de la ribera",
		"style": "Cálido, pausado, observador y con humor seco; conoce cada arroyo, muelle y vecino del Delta.",
		"register": "sereno_costero",
		"preferred_categories": ("alerta_criolla", "aviso", "fortuna"),
		"pacing": "pausado",
	},
	VOICE_ELENA: {
		"name": "Elena",
		"role": "Conductora principal y voz de compañía",
		"style": "Serena, empática, reflexiva y precisa en los servicios a la comunidad y reportes fluviales.",
		"register": "calido_comunitario",
		"preferred_categories": ("aviso", "oyentes", "fortuna"),
		"pacing": "sereno",
	},
	VOICE_VALENTINA: {
		"name": "Valentina",
		"role": "Co-conductora rioplatense y cronista de aire",
		"style": "Ágil, espontánea, irónica sin perder cercanía; ideal para el ida y vuelta con oyentes y el radiopasillo.",
		"register": "espontaneo_rioplatense",
		"preferred_categories": ("chismes", "novela", "oyentes"),
		"pacing": "agil",
	},
	VOICE_MARIA: {
		"name": "María",
		"role": "Locutora de musicalización y enlace comunitario",
		"style": "Clara, entusiasta medida, atenta al ritmo de la tanda musical y a las historias cotidianas del pueblo.",
		"register": "fresco_musical",
		"preferred_categories": ("oyentes", "fortuna"),
		"pacing": "dinamico",
	},
}

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
FALLBACK_HOST_NAME: str = "Tomás"
DEFAULT_SPEAKER_NAME: str = FALLBACK_HOST_NAME
DEFAULT_COHOST_DISPLAY_NAME: str = "Co-conductor"
