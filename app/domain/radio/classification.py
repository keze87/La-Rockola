"""
Clasificación semántica de segmentos radiales y condiciones meteorológicas.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from app.domain.radio.phrase_banks.advertisements import CARPINCHO_ADS
from app.domain.radio.phrase_banks.fortunes import CARPINCHO_SABIDURIA
from app.domain.radio.phrase_banks.gossip import CHISMES_CARPINCHOS
from app.domain.radio.phrase_banks.listeners import (
	ALERTAS_INCOMODIDAD_CRIOLLA,
	DEDICATORIAS_OYENTES,
	TRANSITO_FLUVIAL_Y_CAMINOS,
)
from app.domain.radio.phrase_banks.soap_opera import NOVELA_VECINAL
from app.domain.radio.phrase_banks.weather import (
	WEATHER_CODE_TO_CATEGORY,
	WEATHER_DESC_TO_CATEGORY,
)


class RadioPhrase(NamedTuple):
	text: str
	category: str  # "fortuna" | "aviso" | "alerta_criolla" | "oyentes" | "chismes" | "novela"


CARPINCHO_PHRASES: tuple[RadioPhrase, ...] = (
	*(RadioPhrase(t, "fortuna") for t in CARPINCHO_SABIDURIA),
	*(RadioPhrase(t, "alerta_criolla") for t in ALERTAS_INCOMODIDAD_CRIOLLA),
	*(RadioPhrase(t, "alerta_criolla") for t in TRANSITO_FLUVIAL_Y_CAMINOS),
	*(RadioPhrase(t, "oyentes") for t in DEDICATORIAS_OYENTES),
	*(RadioPhrase(t, "aviso") for t in CARPINCHO_ADS),
	*(RadioPhrase(t, "chismes") for t in CHISMES_CARPINCHOS),
	*(RadioPhrase(t, "novela") for t in NOVELA_VECINAL),
)

PHRASE_TO_CATEGORY: dict[str, str] = {p.text: p.category for p in CARPINCHO_PHRASES}


def resolve_weather_desc_category(
	desc: str | None = None,
	code: int | str | None = None,
	lang_es: str | None = None,
) -> str:
	"""
	Determina la categoría canónica del clima según weatherCode o weatherDesc de wttr.in.
	Prioriza el código numérico estándar WWO (weatherCode), luego lookup por texto exacto
	(inglés o español) y finalmente coincidencias léxicas/semánticas con fallback seguro.
	"""
	if code is not None:
		try:
			code_int = int(code)
			if code_int in WEATHER_CODE_TO_CATEGORY:
				return WEATHER_CODE_TO_CATEGORY[code_int]
		except (ValueError, TypeError):
			pass

	raw = lang_es or desc
	if not raw or not isinstance(raw, str) or not raw.strip():
		return ""

	norm = raw.strip().lower()
	if norm in WEATHER_DESC_TO_CATEGORY:
		return WEATHER_DESC_TO_CATEGORY[norm]

	# Búsqueda semántica por palabras clave
	if any(k in norm for k in ("thunder", "torment", "truen", "rayo")):
		return "snow_thunder" if any(k in norm for k in ("nieve", "snow", "nevad")) else "thunderstorm"
	if any(k in norm for k in ("blizzard", "ventisca")):
		return "blizzard"
	if any(k in norm for k in ("granizo", "hail", "pellet", "perdigon", "piedra")):
		return "hail"
	if any(k in norm for k in ("sleet", "aguanieve")):
		return "sleet"
	if any(k in norm for k in ("freezing", "helad")):
		return "freezing_drizzle"
	if any(k in norm for k in ("snow", "nieve", "nevad", "nevisc")):
		return "snow"
	if any(k in norm for k in ("torren", "heavy", "fuerte", "aguacero")):
		return "heavy_rain"
	if "modera" in norm:
		return "moderate_rain"
	if any(k in norm for k in ("drizzle", "garua", "garúa", "llovizn")):
		return "drizzle"
	if any(k in norm for k in ("rain", "shower", "lluvia", "chubasco")):
		return "light_rain"
	if any(k in norm for k in ("fog", "niebla")):
		return "fog"
	if any(k in norm for k in ("mist", "bruma", "neblina")):
		return "mist"
	if any(k in norm for k in ("overcast", "cubierto", "encapotado")):
		return "overcast"
	if any(k in norm for k in ("partly", "parcial", "intervalo")):
		return "partly_cloudy"
	if any(k in norm for k in ("cloud", "nublado", "nube")):
		return "cloudy"
	if any(k in norm for k in ("sun", "soleado", "clear", "despejado")):
		return "sunny"
	if any(k in norm for k in ("squall", "racha", "viento")):
		return "wind_squalls"
	if any(k in norm for k in ("smoke", "humo", "dust", "polvo", "sand", "arena", "haze", "calina")):
		return "smoke_dust"

	return "default"


def resolve_segment_category(text: str | tuple[str, str] | RadioPhrase, default: str = "unknown") -> str:
	"""
	Clasifica el contenido radial en su categoría semántica:
	- 'oyentes': dedicatorias y pedidos de oyentes por WhatsApp/audio.
	- 'aviso': tanda publicitaria comercial, avisos parroquiales y tránsito fluvial.
	- 'alerta_criolla': reportes satíricos de clima extremo, mosquitos y viento norte.
	- 'chismes': secretos, fauna ribereña y radio pasillo.
	- 'novela': culebrón vecinal por capítulos y radioteatro.
	- 'fortuna': refranes, proverbios, máximas y reflexiones filosóficas.
	- 'unknown': contenido externo o ambiguo no reconocido (evita asumir erróneamente 'fortuna').

	Soporta duplas explícitas (RadioPhrase o tuple) retornando su categoría directamente,
	y mapeo O(1) vía PHRASE_TO_CATEGORY para frases de los bancos internos.
	Si no coincide con mapeos explícitos ni reglas heurísticas, retorna `default`.
	"""
	if isinstance(text, (tuple, RadioPhrase)):
		if len(text) >= 2 and text[1]:
			return str(text[1])
		text = text[0] if len(text) >= 1 else ""

	if not text or not isinstance(text, str):
		return default
	text_clean = text.strip()

	# 1. Pertenencia directa a mapeo explícito de bancos
	if text_clean in PHRASE_TO_CATEGORY:
		return PHRASE_TO_CATEGORY[text_clean]

	text_lower = text_clean.lower()

	# 3. Prefijos explícitos de avisos comerciales y comunitarios
	if any(
		text_clean.startswith(p)
		for p in (
			"Espacio publicitario",
			"Publicidad",
			"Aviso ",
			"Aviso parroquial",
			"Se busca ",
			"Atención vecinos",
			"Solidaridad ",
			"Objeto perdido",
			"Objeto hallado",
			"Extravío ",
			"Pérdida ",
			"Urgente del pueblo",
		)
	):
		return "aviso"

	# 4. Dedicatorias y mensajes de oyentes
	if any(
		text_clean.startswith(p)
		for p in ("WhatsApp", "Llega audio", "Mensajito", "Audio de", "Nos escriben", "Llega mensaje")
	) or any(
		k in text_lower
		for k in (
			"whatsapp",
			"audio de",
			"mandale un abrazo",
			"pide un chamamé",
			"piden cumbia",
			"piden cuarteto",
			"pedimos cumbia",
			"pedimos cuarteto",
			"que suene gilda",
		)
	):
		return "oyentes"

	# 5. Alertas criollas y tránsito fluvial (partes y cables remotos del delta, islas y litoral)
	if any(
		text_clean.startswith(p)
		for p in (
			"Reporte especial de mosquitos",
			"Alerta de jejenes",
			"Alerta por viento zonda",
			"Alerta meteorológico de los bañados",
			"Lancha colectiva",
			"Balsa ",
			"Corte de ruta",
			"Alerta de tránsito",
			"Tránsito ",
			"Camino ",
			"Reporte de caminos",
			"Demoras en ",
			"Estado de caminos",
		)
	) or any(
		k in text_lower
		for k in (
			"plaga de mosquitos",
			"nube de mosquitos",
			"invasión de mosquitos",
			"ataque de jejenes",
			"escuadrones de jejenes",
			"viento zonda",
			"viento norte",
			"humedad del 100%",
			"plaga de",
			"calor de siesta",
			"asfalto parece goma",
			"tránsito fluvial",
			"lancha colectiva",
			"balsa maroma",
			"puente viejo",
			"terraplén",
			"camino de ripio",
			"banco de arena",
			"barro greda",
			"camino isleño",
			"alerta para boteros",
		)
	):
		return "alerta_criolla"

	# 6. Avisos por palabras clave contextuales no ambiguas
	if any(
		k in text_lower
		for k in (
			"gomería",
			"ferretería",
			"emparchamos",
			"precios populares",
			"aviso comercial",
			"aviso parroquial",
			"se extravió",
			"se busca dueño",
			"se busca paradero",
			"gratificaré",
			"buena recompensa",
			"recompensa a quien",
		)
	):
		return "aviso"

	# 7. Prefijos y palabras clave de telenovela vecinal y radioteatro
	if any(
		text_clean.startswith(p)
		for p in (
			"Capítulo ",
			"Telenovela",
			"Radioteatro",
			"Novela vecinal",
			"¡Atención vecindario",
			"Bomba vecinal",
			"Crónica prohibida",
			"Se desató la telenovela",
		)
	) or any(
		k in text_lower
		for k in (
			"doña gladys",
			"don anselmo",
			"taller de pocho",
			"gordo walter",
			"profesor rodolfo",
			"telenovela",
			"radioteatro",
		)
	):
		return "novela"

	# 8. Prefijos y palabras clave de fauna ribereña y chismes de madriguera
	if any(
		text_clean.startswith(p)
		for p in (
			"Radio pasillo",
			"Secreto de la madriguera",
			"Chisme carpincho",
			"Conventillo ",
			"Archivo prohibido",
			"Bomba en el bañado",
			"Se filtró ",
			"El pacto de silencio",
		)
	) or any(
		k in text_lower
		for k in (
			"nordelta",
			"vida secreta",
			"pacto de silencio",
			"radio pasillo",
			"radiopasillo",
			"conventillo",
			"se filtró",
			"chisme",
			"chismes",
			"madriguera clandestina",
			"operación pata mojada",
		)
	):
		return "chismes"

	# 9. Citas literarias o filosóficas con atribución de autor (e.g. '— Heráclito', '— Proverbio')
	if " — " in text_clean or "— " in text_clean or re.search(r"—\s*[A-ZÁÉÍÓÚÑ]", text_clean):
		return "fortuna"

	return default
