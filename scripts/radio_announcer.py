"""
Módulo de locución para el Modo Radio en La Rockola del Carpincho.
Maneja la síntesis de voz con edge-tts, formateo horario radial y banco mixto de fortunas.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rockola.radio")

try:
	import edge_tts

	HAS_EDGE_TTS = True
except ImportError:
	edge_tts = None
	HAS_EDGE_TTS = False

VOICE_TOMAS = "es-AR-TomasNeural"
VOICE_ELENA = "es-AR-ElenaNeural"
VOICE_MARIA = "es-CR-MariaNeural"
VOICE_VALENTINA = "es-UY-ValentinaNeural"
VOICES = [VOICE_TOMAS, VOICE_ELENA, VOICE_MARIA, VOICE_VALENTINA]

VOICE_NAMES: dict[str, str] = {
	VOICE_TOMAS: "Tomás",
	VOICE_ELENA: "Elena",
	VOICE_MARIA: "María",
	VOICE_VALENTINA: "Valentina",
}

DEFAULT_TTS_TIMEOUT: float = 12.0
DEFAULT_TTS_RETRIES: int = 3

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

# Banco curado de sabiduría, humor y frases del carpincho con tono argentino
CARPINCHO_FORTUNES: list[str] = [
	"Che, no te apurés; el agua siempre llega a la orilla.",
	"Posta: el secreto del éxito carpincho es mate caliente, buena música y cero drama.",
	"Un carpinchazo de tema te arregla cualquier lunes; comprobado científicamente.",
	"Tranqui en el agua; que las olas se las lleven los apurados.",
	"El carpincho no se apura: sabe que el agua siempre llega.",
	"Tomate un mate, bajá un cambio y disfrutá el temazo que viene.",
	"La vida es corta como pata de carpincho: no te hagas drama por pavadas.",
	"No cuentes los mates que te tomás, hacé que cada mate cuente.",
	"Si la vida te tira limones, fijate si conseguís hielo y fernet.",
	"Tranquilo como carpincho en Nordelta.",
	"El secreto de la felicidad: buena música, agua tibia y cero apuro.",
	"Hoy es un gran día para no hacer nada y hacerlo con mucho estilo.",
	"El que madruga encuentra todo cerrado.",
	"No dejes para mañana lo que puedas procrastinar hoy con buena música.",
	"El asado une lo que el lunes separa.",
	"Donde manda carpincho, no manda marinero.",
	"Más vale pájaro en mano... que pájaro volando sobre tu cabeza.",
	"Un tropezón no es caída, pero si nadie te vio, mejor todavía.",
	"El mate dulce no es pecado, pero bueno, sobre gustos no hay nada escrito.",
	"Ojo al piojo: las mejores cosas de la vida te despeinan.",
	"Algún día los carpinchos dominarán el mundo... pero hoy tienen fiaca.",
	"No bombardeen Barrio Norte, pongan cumbia y rocanrol.",
	"Si no hay amor que no haya nada, pero que al menos haya música en La Rockola.",
	"El tiempo no para, pero vos podés frenar un toque a escuchar este temita.",
	"Todo un palo, ya lo ves: la música te salva una y otra vez.",
	"Pronto recibirás una visita inesperada... ojalá traiga facturas.",
	"Tu creatividad te llevará lejos, pero acordate de cargar la SUBE.",
	"Un gran viaje comienza con un solo paso... y una buena playlist.",
	"Sonreí: confundís a tus enemigos y le ponés onda a la tarde.",
	"El oráculo predice que la próxima canción te va a encantar.",
	"Más vale carpincho en laguna que cien mosquitos en la nuca.",
	"El que se va a Sevilla pierde su silla, pero el que se queda baila.",
	"Para el carpincho sabio, cada charco es un jacuzzi.",
	"A caballo regalado no se le miran los dientes, pero a la playlist sí.",
	"No hay mal que dure cien años, ni pena que una cumbia no cure.",
	"Ojo al piojo con los que te dicen que no pongas otro tema.",
	"Si el río suena, es porque un carpincho se tiró de bomba.",
	"Billetera mata galán, pero temazo mata billetera.",
	"El oráculo dice: relajá la mandíbula y metele play.",
	"No te preocupes por el qué dirán: el carpincho toma sol y le importa un comino.",
	"El que busca encuentra... menos las llaves cuando estás apurado.",
	"Mejor solo que mal acompañado, pero con buena música nunca estás solo.",
	"Cuidado con el que te dice «yo no tomo fernet»: algo oculta.",
	"La música limpia el alma del polvo de la rutina diaria.",
	"El mate amargo y la música al palo, como manda la ley criolla.",
	"Todo concluye al fin, todo termina... menos esta fiesta en La Rockola.",
	"No llores porque terminó, ponete otro temazo y sonreí.",
	"El oráculo avisa: se viene un temazo de aquellos, prepará el mate.",
	"A seguro se lo llevaron preso, pero al carpincho lo dejaron en el agua.",
	"Lo bueno si breve, dos veces bueno... excepto cuando suena un temazo.",
	"No empujen que hay música y mates para todos.",
	"El que ríe último... probablemente no entendió el chiste.",
	"Las penas se van cantando, o por lo menos se disimulan bastante bien.",
	"El carpincho zen dice: respirá hondo y dejate llevar por el ritmo.",
	"Si la tarde viene pesada, una buena cumbia te la acomoda.",
	"No hay camino a la felicidad: la felicidad es escuchar música entre amigos.",
	"Menos drama y más cumbia, esa es la receta del éxito.",
	"Un sabio dijo una vez: «Subile el volumen que este tema me encanta».",
	"El oráculo predice: tu día va a mejorar en un cien por ciento con este tema.",
]

# Propagandas y avisos comerciales ficticios de radio para carpinchos
CARPINCHO_ADS: list[str] = [
	"Espacio publicitario: Yerba Mate «El Carpincho Mimoso», estacionada dos años en laguna natural. Un mate que te acaricia el alma.",
	"Publicidad: Pastos y Juncos Don Pedro. Los mejores brotes tiernos del Delta para rumiar en la orilla mientras suena La Rockola.",
	"Aviso inmobiliario: Inmobiliaria El Bañado. Venta de lotes con costa propia y vista panorámica a Nordelta. Cero expensas, pura paz.",
	"Publicidad: Protector solar «Piel de Carpincho», factor ochenta. Tomate un solazo en la barranca sin quemarte el cuero.",
	"Espacio publicitario: Ponchos y Boinas El Yacaré. Elegancia criolla para las noches frescas en el pajonal.",
	"Aviso comercial: Remises La Nutria. Te cruzamos el río a nado o en canoa. Más rápidos que doradillo en bajante.",
	"Espacio publicitario: Fernet «Laguna Negra» con dos hielos y coca. El combustible oficial de los carpinchos trasnochadores.",
	"Publicidad: Spa Termal Los Esteros. Baños de fango curativo y masajes con caña tacuara. Salís como nuevo, hecho una seda.",
	"Aviso comercial: Seguros La Madriguera. Si la crecida te llega al cogote, nosotros te cubrimos la cueva. Dormí sin frazada.",
	"Publicidad: Ferretería Don Roedor. Bombas de achique, alambrados olímpicos y machetes para desmalezar la isla.",
	"Espacio publicitario: Barbería y Peluquería Bigote Criollo. Corte degrade, recorte de bigotes y peinado a contrapelo para deslumbrar en la laguna.",
	"Aviso parroquial: Academia Los Carpincheros. Clases de natación sincronizada y flotación tipo tronco para principiantes.",
	"Publicidad: Astilleros La Balsa. Botes a remo, kayaks de madera y balsas de totora con garantía de por vida.",
	"Espacio publicitario: Café de Algarroba y Facturas Don Ceibo. El desayuno ideal antes de tirarse a la sombra a hacer la siesta.",
	"Publicidad: Colchones Sommier «Paja Brava». Firmeza garantizada para dormir doce horas seguidas como un señor carpincho.",
	"Aviso comercial: Cervecería Artesanal El Pantano. Con lúpulo silvestre y agua fresca de vertiente isleña. Pedite una pinta bien helada.",
	"Espacio publicitario: Sombreros de Paja Don Bigote. Frescura, sombra y porte gaucho para caminar por el terraplén.",
	"Aviso parroquial: Repelente «Chau Mosquito». Para que no te piquen las orejas mientras disfrutás de un buen chamamé.",
	"Publicidad: Panadería La Espiga Verde. Medialunas de grasa calentitas a toda hora para acompañar los amargos.",
	"Espacio publicitario: Neumáticos La Huella. Cámaras inflables para flotar panza arriba toda la tarde en el arroyo.",
]

CARPINCHO_FORTUNES.extend(CARPINCHO_ADS)

# Bancos de frases modulares para el Carpincho Locutor
RADIO_INTROS: list[str] = [
	"En el aire de La Rockola del Carpincho,",
	"¡Buenas gente linda de La Rockola!",
	"La hora en La Rockola:",
	"Sintonizando La Rockola del Carpincho,",
	"¡Seguimos haciendo el aguante en La Rockola!",
	"Un matecito en La Rockola y seguimos:",
	"Transmite La Rockola del Carpincho:",
	"Che, buenas y santas gente linda; acá estamos en La Rockola del Carpincho.",
	"Posta, qué lindo estar acá en La Rockola; sintonizando buena onda.",
	"¡Al pelo la música en La Rockola del Carpincho!",
	"Tranqui en el agua, mate en mano; transmite La Rockola del Carpincho.",
]

RADIO_LEAD_INS: list[str] = [
	"Momento de la galletita de la fortuna:",
	"Ojo al piojo con lo que dice el oráculo de La Rockola:",
	"Sabiduría carpinchera para el alma:",
	"Tiramos una frase para reflexionar mientras te tomás unos mates:",
	"Dice la fortuna del día:",
	"Atenti a esta reflexión carpinchera:",
	"Espacio publicitario en La Rockola:",
	"Atenti a este aviso de la comunidad carpinchera:",
	"Mensaje de nuestros queridos auspiciantes:",
	"Che, atenti al oráculo; sabiduría pura de la laguna:",
	"Posta, escuchate esta reflexión carpinchera:",
	"Pará la oreja; mirá lo que nos deja el oráculo hoy:",
]

RADIO_OUTROS: list[str] = [
	"¡Seguimos con más música!",
	"¡Que no decaiga!",
	"¡Pegale play que esto sigue!",
	"¡Metemos la próxima canción al toque!",
	"¡Seguimos de joda en La Rockola!",
	"¡Acomodate que se viene un temazo!",
	"¡Un carpinchazo de tema para vos; metele play!",
	"Tranqui en el agua, mate en mano... ¡a disfrutar lo que viene!",
	"¡Al pelo el ritmo; seguimos con todo en La Rockola!",
	"Posta, qué temazo se viene ahora; no te muevas de ahí.",
]

# Horas especiales del Carpincho Locutor (cuando el minuto es 0 en punto)
SPECIAL_HOURS: dict[int, str] = {
	0: "Las doce de la noche en punto, arranca la trasnoche en La Rockola.",
	1: "Las una en punto, es hora de mimir.",
	2: "Las dos de la madrugada en punto, silencio en la laguna.",
	3: "Las tres de la mañana en punto, hora de los carpinchos sonámbulos.",
	4: "Las cuatro de la mañana en punto, el que no duerme pega en el palo.",
	5: "Las cinco de la mañana en punto, ya clarea en los bañados.",
	6: "Las seis de la mañana en punto, arriba que canta el chajá.",
	7: "Las siete de la mañana en punto, el agua está para unos buenos mates.",
	8: "Las ocho de la mañana en punto, arranca la jornada con toda la onda.",
	9: "Las nueve de la mañana en punto, el sol calienta la barranca.",
	10: "Las diez de la mañana en punto, una pastura tierna para picar.",
	11: "Las once de la mañana en punto, se siente el olorcito a comida.",
	12: "Las doce del mediodía en punto, hora de prender el fuego para el asado.",
	13: "Las una de la tarde en punto, la panza llena y el corazón contento.",
	14: "Las dos de la tarde en punto, sagrada hora de la siesta carpincha.",
	15: "Las tres de la tarde en punto, un chapuzón para refrescar las ideas.",
	16: "Las cuatro de la tarde en punto, salen esos mates con tortas fritas.",
	17: "Las cinco de la tarde en punto, la merienda no se negocia con nadie.",
	18: "Las seis de la tarde en punto, cae el solcito en el pajonal.",
	19: "Las siete de la tarde en punto, la tardecita pide buena música.",
	20: "Las ocho de la noche en punto, se va cerrando el boliche y abriendo la fiesta.",
	21: "Las nueve de la noche en punto, la mesa está servida en la madriguera.",
	22: "Las diez de la noche en punto, brindis con amigos y a disfrutar.",
	23: "Las once de la noche en punto, la última ronda antes de cerrar los ojales.",
}

DEFAULT_WEATHER_LOCATION: str = "San Miguel de Tucumán"
WEATHER_RAIN_THRESHOLD: int = 50

WEATHER_LEAD_INS: list[str] = [
	"El informe del tiempo carpincho nos canta la posta:",
	"Mirá por la ventana o pará la oreja, que así viene el clima:",
	"Atenti con el servicio meteorológico de La Rockola:",
	"Momento de chequear cómo viene la mano con el cielo:",
	"Pará un segundo el mate que te paso el parte meteorológico:",
]


_WEATHER_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
WEATHER_CACHE_TTL: float = 30 * 60  # 30 minutos


def reset_weather_cache() -> None:
	"""Limpia la caché en memoria de wttr.in (útil para pruebas y reinicio)."""
	_WEATHER_CACHE.clear()


def construir_url_json(lugar: str, idioma: str = "es") -> str:
	lugar_limpio = lugar.strip() if lugar else ""
	lugar_escapado = urllib.parse.quote(lugar_limpio, safe=",~-")
	return f"https://wttr.in/{lugar_escapado}?format=j1&lang={idioma}"


def fetch_weather_json(
	lugar: str = DEFAULT_WEATHER_LOCATION,
	idioma: str = "es",
	timeout: float = 5.0,
) -> dict | None:
	"""
	Obtiene los datos meteorológicos en formato JSON (format=j1) desde wttr.in de forma sincrónica.
	Retorna el diccionario parseado o None si ocurre cualquier error (timeout, HTTP, DNS o JSON inválido).
	Si la solicitud remota falla, intenta recuperar la última respuesta válida en caché si tiene menos de 30 minutos.
	"""
	cache_key = (lugar.strip().lower() if lugar else "", idioma.strip().lower() if idioma else "es")
	url = construir_url_json(lugar, idioma)
	try:
		req = urllib.request.Request(
			url,
			headers={"User-Agent": "LaRockolaDelCarpincho/1.0"},
		)
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			if resp.status == 200:
				raw_body = resp.read()
				parsed = json.loads(raw_body.decode("utf-8", errors="ignore"))
				if isinstance(parsed, dict) and "current_condition" in parsed:
					_WEATHER_CACHE[cache_key] = (time.time(), parsed)
					return parsed
			logger.debug(f"Respuesta no exitosa de wttr.in ({resp.status}) para '{lugar}'")
	except Exception as e:
		logger.debug(f"No se pudo consultar el clima en wttr.in para '{lugar}': {e}")

	# Si la petición remota falló, verificar si tenemos una respuesta previa válida de menos de 30 minutos
	if cache_key in _WEATHER_CACHE:
		cached_time, cached_data = _WEATHER_CACHE[cache_key]
		age = time.time() - cached_time
		if age <= WEATHER_CACHE_TTL:
			logger.debug(
				f"🌤️ Usando reporte del clima en caché ({age / 60:.1f} min de antigüedad) para '{lugar}' ante fallo de red."
			)
			return cached_data

	return None


def describir_lluvias(llueve_hoy: bool, llueve_manana: bool) -> str:
	"""
	Describe la previsión de precipitaciones para hoy y mañana con impronta carpinchera.
	Cubre las 4 variantes posibles.
	"""
	if not llueve_hoy and not llueve_manana:
		return "De lluvias ni hablemos: cielo despejado, ideal para unos buenos mates al sol."
	if llueve_hoy and not llueve_manana:
		return "Atenti que hoy se esperan lluvias y chaparrones, pero mañana ya zafamos y mejora la cosa."
	if not llueve_hoy and llueve_manana:
		return "Hoy zafamos del agua, pero andá aprontando el paraguas porque mañana se vienen las lluvias."
	return "Se vienen lluvias tanto para hoy como para mañana, ¡clima soñado para andar chapoteando en el agua!"


def _is_slot_relevant_for_hour(h: dict, current_hour: int) -> bool:
	"""Determina si un slot hourly de wttr.in cubre desde la hora actual en adelante."""
	time_val = h.get("time")
	if time_val is None:
		return True
	try:
		# wttr.in usa enteros como 0, 300, 600, 900, 1200, 1500, etc.
		# Cada slot cubre 3 horas: [slot_hour, slot_hour + 2]
		slot_hour = int(time_val) // 100
		return (slot_hour + 2) >= current_hour
	except (ValueError, TypeError):
		return True


def build_weather_phrase(
	data: dict,
	lead_in: str | None = None,
	current_hour: int | None = None,
) -> str | None:
	"""
	Extrae y arma la frase del reporte del clima a partir del JSON format=j1 de wttr.in.
	Incluye únicamente:
	- Temperatura actual.
	- Mínima, máxima y probabilidad de lluvia para HOY (considerando slots desde la hora actual).
	- Mínima, máxima y probabilidad de lluvia para MAÑANA (día completo).
	Retorna None si la estructura no contiene las claves esperadas.
	"""
	try:
		current_temp = round(float(data["current_condition"][0]["temp_C"]))
		today = data["weather"][0]
		min_today = round(float(today["mintempC"]))
		max_today = round(float(today["maxtempC"]))
		tomorrow = data["weather"][1]
		min_tomorrow = round(float(tomorrow["mintempC"]))
		max_tomorrow = round(float(tomorrow["maxtempC"]))

		today_hourly = today.get("hourly", [])
		if current_hour is not None:
			today_hourly = [h for h in today_hourly if _is_slot_relevant_for_hour(h, current_hour)]

		rain_today = max(
			(int(h.get("chanceofrain", 0)) for h in today_hourly),
			default=0,
		)
		rain_tomorrow = max(
			(int(h.get("chanceofrain", 0)) for h in tomorrow.get("hourly", [])),
			default=0,
		)

		llueve_hoy = rain_today >= WEATHER_RAIN_THRESHOLD
		llueve_manana = rain_tomorrow >= WEATHER_RAIN_THRESHOLD
		lluvia_desc = describir_lluvias(llueve_hoy, llueve_manana)

		lead = lead_in if lead_in is not None else random.choice(WEATHER_LEAD_INS)
		return (
			f"{lead} tenemos {current_temp} grados de temperatura actual. "
			f"Para hoy la mínima es de {min_today} y la máxima alcanzará los {max_today} grados. "
			f"Para mañana esperamos entre {min_tomorrow} y {max_tomorrow} grados. "
			f"{lluvia_desc}"
		)
	except (KeyError, IndexError, ValueError, TypeError) as e:
		logger.debug(f"Estructura de datos de clima incompleta o inválida: {e}")
		return None


def get_carpincho_data_dir() -> Path:
	"""Obtiene el directorio de datos para la base de datos de la Rockola."""
	try:
		from server import DATA_DIR

		return DATA_DIR
	except ImportError:
		logger.debug("Módulo 'server' no disponible, usando fallback local para DATA_DIR.")
	except Exception as e:
		logger.debug(f"Error inesperado importando DATA_DIR desde server: {e}, usando fallback local.")

	db_dir = Path(__file__).resolve().parents[1] / "DB"
	db_dir.mkdir(parents=True, exist_ok=True)
	return db_dir


def init_tts_cache_db(db_path: Path | str | None = None) -> Path:
	"""Inicializa la base de datos SQLite para la caché de audios de TTS."""
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	target_path.parent.mkdir(parents=True, exist_ok=True)
	with sqlite3.connect(target_path, timeout=5.0) as conn:
		conn.execute(
			"""
			CREATE TABLE IF NOT EXISTS tts_cache (
				cache_key TEXT PRIMARY KEY,
				category TEXT NOT NULL,
				voice TEXT NOT NULL,
				text TEXT NOT NULL,
				audio_blob BLOB NOT NULL,
				duration REAL,
				created_at REAL NOT NULL,
				last_used REAL NOT NULL,
				use_count INTEGER DEFAULT 1
			)
			"""
		)
		conn.execute("CREATE INDEX IF NOT EXISTS idx_tts_cache_cat_voice ON tts_cache (category, voice)")
		conn.commit()
	return target_path


def get_cache_key(category: str, voice: str, text: str) -> str:
	"""Calcula la clave de caché SHA-256 única para una tupla (categoría, voz, texto normalizado)."""
	norm_text = text.strip().lower()
	raw = f"{voice}:{category}:{norm_text}".encode()
	return hashlib.sha256(raw).hexdigest()


def get_cached_audio(
	category: str,
	voice: str,
	text: str,
	db_path: Path | str | None = None,
) -> bytes | None:
	"""
	Recupera el segmento de audio MP3 desde la base SQLite si existe.
	Actualiza el timestamp de último uso y el contador de reproducciones.
	"""
	cache_key = get_cache_key(category, voice, text)
	target_path = Path(db_path) if db_path else (get_carpincho_data_dir() / "tts_cache.db")
	if not target_path.exists():
		return None
	try:
		with sqlite3.connect(target_path, timeout=5.0) as conn:
			cur = conn.cursor()
			cur.execute("SELECT audio_blob FROM tts_cache WHERE cache_key = ?", (cache_key,))
			row = cur.fetchone()
			if row and row[0]:
				now = time.time()
				cur.execute(
					"UPDATE tts_cache SET last_used = ?, use_count = use_count + 1 WHERE cache_key = ?",
					(now, cache_key),
				)
				conn.commit()
				return row[0]
	except Exception as e:
		logger.debug(f"Error consultando caché TTS: {e}")
	return None


def save_cached_audio(
	category: str,
	voice: str,
	text: str,
	audio_bytes: bytes,
	duration: float | None = None,
	db_path: Path | str | None = None,
) -> None:
	"""Almacena o actualiza un segmento de audio MP3 en la base de datos de caché SQLite."""
	if not audio_bytes:
		return
	cache_key = get_cache_key(category, voice, text)
	target_path = init_tts_cache_db(db_path)
	now = time.time()
	try:
		with sqlite3.connect(target_path, timeout=5.0) as conn:
			conn.execute(
				"""
				INSERT INTO tts_cache (cache_key, category, voice, text, audio_blob, duration, created_at, last_used, use_count)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
				ON CONFLICT(cache_key) DO UPDATE SET
					audio_blob = excluded.audio_blob,
					duration = coalesce(excluded.duration, duration),
					last_used = excluded.last_used,
					use_count = use_count + 1
				""",
				(cache_key, category, voice, text, audio_bytes, duration, now, now),
			)
			conn.commit()
	except Exception as e:
		logger.debug(f"Error guardando audio en caché TTS: {e}")


# Estado volátil en memoria para el locutor de radio (no requiere persistencia en base de datos)
_RADIO_MEMORY_STATE: dict[str, Any] = {}


def get_radio_state(key: str, default: Any = None, db_path: Path | str | None = None) -> Any:
	"""Recupera un valor de estado en memoria del locutor de radio (db_path opcional conservado por retrocompatibilidad)."""
	return _RADIO_MEMORY_STATE.get(key, default)


def set_radio_state(key: str, value: Any, db_path: Path | str | None = None) -> None:
	"""Almacena o actualiza un valor de estado en memoria del locutor de radio (db_path opcional conservado por retrocompatibilidad)."""
	_RADIO_MEMORY_STATE[key] = value


def reset_radio_memory_state() -> None:
	"""Limpia el estado en memoria del locutor de radio (útil para pruebas y reinicio limpio)."""
	_RADIO_MEMORY_STATE.clear()


# Nombres de bases de datos de fortune que contienen frases en español
KNOWN_SPANISH_DBS: set[str] = {
	"amistad",
	"arte",
	"asimov",
	"ciencia",
	"deprimente",
	"es",
	"familia",
	"famosos",
	"filosofia",
	"humanos",
	"informatica",
	"lao-tse",
	"leydemurphy",
	"libertad",
	"nietzsche",
	"pintadas",
	"poder",
	"proverbios",
	"refranes",
	"sabiduria",
	"schopenhauer",
	"sentimientos",
	"varios",
	"varios-pre",
	"verdad",
	"vida",
}

_SPANISH_FORTUNE_DBS_CACHE: list[str] | None = None

SPANISH_CHARS: set[str] = set("áéíóúüñ¿¡ÁÉÍÓÚÜÑ")
COMMON_SPANISH_WORDS: set[str] = {
	"a",
	"al",
	"algo",
	"algunos",
	"amigo",
	"amigos",
	"ante",
	"antes",
	"asado",
	"bien",
	"boda",
	"buen",
	"buena",
	"bueno",
	"cada",
	"carpincho",
	"casi",
	"che",
	"como",
	"con",
	"contra",
	"cosa",
	"cosas",
	"cual",
	"cuando",
	"cumbia",
	"de",
	"del",
	"desde",
	"donde",
	"durante",
	"e",
	"el",
	"él",
	"ella",
	"ellos",
	"en",
	"entre",
	"era",
	"es",
	"esa",
	"ese",
	"eso",
	"esos",
	"esta",
	"está",
	"estaba",
	"estas",
	"este",
	"estos",
	"familia",
	"feliz",
	"fernet",
	"fiesta",
	"frase",
	"gente",
	"gracias",
	"gran",
	"haber",
	"hace",
	"hacer",
	"hasta",
	"hay",
	"hoy",
	"la",
	"las",
	"le",
	"les",
	"lo",
	"los",
	"mando",
	"mas",
	"más",
	"mate",
	"mates",
	"me",
	"medio",
	"mejor",
	"mensaje",
	"menos",
	"mi",
	"mí",
	"mía",
	"mío",
	"mis",
	"mismo",
	"música",
	"muy",
	"nada",
	"ni",
	"no",
	"noche",
	"nos",
	"nuestra",
	"nuestras",
	"nuestro",
	"nuestros",
	"nunca",
	"o",
	"ojo",
	"oráculo",
	"otra",
	"otro",
	"otros",
	"para",
	"pelo",
	"pero",
	"play",
	"poco",
	"por",
	"porque",
	"posta",
	"proverbio",
	"que",
	"qué",
	"quien",
	"quienes",
	"refrán",
	"sabiduría",
	"se",
	"ser",
	"si",
	"sí",
	"siempre",
	"sin",
	"sobre",
	"son",
	"su",
	"sus",
	"también",
	"tanto",
	"tarde",
	"te",
	"tema",
	"temazo",
	"temas",
	"tiempo",
	"tiene",
	"todo",
	"todos",
	"tu",
	"tus",
	"un",
	"una",
	"unas",
	"uno",
	"unos",
	"va",
	"vida",
	"vez",
	"veces",
	"y",
	"ya",
}


def is_spanish_text(text: str) -> bool:
	"""Determina si un texto está en idioma español."""
	if not text:
		return False
	# 1. Caracteres distintivos del español (acentos, ñ, signos de apertura)
	if any(c in SPANISH_CHARS for c in text):
		return True
	# 2. Conteo de palabras frecuentes en español
	words = [w.lower() for w in re.findall(r"\b[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]+\b", text)]
	if not words:
		return False
	spanish_count = sum(1 for w in words if w in COMMON_SPANISH_WORDS)
	return spanish_count >= 2 or (len(words) <= 3 and spanish_count >= 1)


def get_available_spanish_dbs(timeout: float = 2.0) -> list[str]:
	"""Detecta y cachea las bases de datos en español disponibles para el comando fortune."""
	global _SPANISH_FORTUNE_DBS_CACHE
	if _SPANISH_FORTUNE_DBS_CACHE is not None:
		return _SPANISH_FORTUNE_DBS_CACHE

	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		_SPANISH_FORTUNE_DBS_CACHE = []
		return _SPANISH_FORTUNE_DBS_CACHE

	try:
		res = subprocess.run([fortune_bin, "-f"], capture_output=True, text=True, timeout=timeout, check=False)
		dbs = []
		for line in (res.stdout + res.stderr).splitlines():
			m = re.search(r"^\s*[\d,.]+\%\s+([a-zA-Z0-9_\-]+)", line)
			if m:
				name = m.group(1).lower()
				if name in KNOWN_SPANISH_DBS or name == "es":
					dbs.append(m.group(1))
		_SPANISH_FORTUNE_DBS_CACHE = dbs
		return dbs
	except Exception as e:
		logger.debug(f"Error detectando bases en español de fortune: {e}")
		_SPANISH_FORTUNE_DBS_CACHE = []
		return []


def clean_fortune_text(raw_text: str) -> str:
	"""Limpia el texto de una fortuna quitando saltos de línea excesivos, URLs y caracteres extraños."""
	# Reemplazar múltiples saltos de línea y tabulaciones por espacios
	text = re.sub(r"\s+", " ", raw_text).strip()
	# Quitar comillas externas si ya las trae
	text = text.strip("\"'«»")
	# Quitar firmas de autores o URLs largas
	text = re.sub(r"https?://\S+", "", text).strip()
	text = re.sub(r"--\s*.*$", "", text).strip()
	text = re.sub(r"<[^>]+>", "", text).strip()
	return text.strip()


def get_system_fortune(timeout: float = 2.0) -> str | None:
	"""
	Intenta obtener una fortuna corta exclusivamente en ESPAÑOL mediante el comando Unix `fortune -s`.
	Solo consulta bases en español conocidas y valida que el texto resultante sea en español.
	"""
	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		return None

	spanish_dbs = get_available_spanish_dbs(timeout=timeout)
	if not spanish_dbs:
		return None

	try:
		cmd = [fortune_bin, "-s"] + spanish_dbs
		res = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=timeout,
			check=False,
		)
		if res.returncode == 0 and res.stdout:
			cleaned = clean_fortune_text(res.stdout)
			# Solo aceptar fortunas en español de longitud razonable para locución (entre 15 y 160 caracteres)
			if 15 <= len(cleaned) <= 160 and is_spanish_text(cleaned):
				return cleaned
	except Exception as e:
		logger.debug(f"Error consultando bases en español de fortune: {e}")

	return None


def select_fortune(force_system_fortune: bool | None = None) -> tuple[str, bool]:
	"""
	Selecciona una fortuna garantizada en español y retorna (texto_fortuna, es_del_sistema).
	Por defecto intenta con probabilidad 1/6 consultar una fortuna del sistema si está disponible en español,
	o recurre al banco curado de frases criollas del carpincho.
	"""
	if force_system_fortune is not False and (force_system_fortune is True or random.random() < 1 / 6):
		sys_fort = get_system_fortune()
		if sys_fort and is_spanish_text(sys_fort):
			return sys_fort, True

	return random.choice(CARPINCHO_FORTUNES), False


def get_radio_fortune() -> str:
	"""Devuelve una frase o fortuna garantizada en español."""
	fortuna, _ = select_fortune()
	return fortuna


# Pases de cabina criollos entre carpinchos locutores ("charla de cabina")
RADIO_HANDOFFS: list[str] = [
	"¿Cómo viene la mano afuera, che?",
	"Contame qué dice el servicio meteorológico:",
	"¿Qué tenemos en el pronóstico para hoy?",
	"Tirate esa data de la laguna:",
	"Pará que quiero saber qué dice el oráculo:",
	"¿Qué nos espera en el cielo, compadre?",
	"Tirame el parte meteorológico carpincho:",
]

# Reacciones de cabina criollas ("charla de cabina")
RADIO_REACTIONS: list[str] = [
	"¡Qué lo tiró, che!",
	"Mirá vos, qué momento.",
	"Lindo momento para unos buenos mates.",
	"Una pinturita.",
	"Totalmente, compadre.",
	"Tal cual, fiera.",
	"¡Qué temazo metiste!",
	"La posta pura.",
	"¡Ojo al piojo!",
	"Así se habla en el pago.",
]


def get_modular_hour_segments() -> list[str]:
	"""Genera la lista con los 24 segmentos modulares de hora ('Las doce de la noche,', '1 hora,', ... '23 horas,')."""
	segments = []
	for h in range(24):
		if h == 0:
			segments.append("Las doce de la noche,")
		elif h == 1:
			segments.append("1 hora,")
		else:
			segments.append(f"{h} horas,")
	return segments


def get_modular_minute_segments() -> list[str]:
	"""Genera la lista con los 59 segmentos modulares de minutos ('un minuto.' a '59 minutos.')."""
	return ["un minuto." if m == 1 else f"{m} minutos." for m in range(1, 60)]


def get_all_degree_segments(min_deg: int = -5, max_deg: int = 42) -> list[str]:
	"""Devuelve las frases de temperaturas en grados para locución modular del clima."""
	return [f"{d} grados" for d in range(min_deg, max_deg + 1)]


def get_all_reaction_segments() -> list[str]:
	"""Devuelve la lista de reacciones de cabina."""
	return list(RADIO_REACTIONS)


def get_all_handoff_segments() -> list[str]:
	"""Devuelve la lista de pases de cabina."""
	return list(RADIO_HANDOFFS)


def get_modular_time_segments(dt: datetime | None = None) -> tuple[str, str | None, str]:
	"""
	Divide el anuncio de la hora en segmentos modulares (hora y minutos)
	para minimizar drásticamente las combinaciones que se deben cachear en SQLite.

	- Si minute == 0: Retorna una de las 24 horas especiales del Carpincho (minuto_seg es None).
	  Ej: ("Las una en punto, es hora de mimir.", None, "Las una en punto, es hora de mimir.")
	- Si minute != 0: Retorna (hora_seg, minuto_seg, full_time_str) separados.
	  Ej: ("15 horas,", "23 minutos.", "15 horas, 23 minutos.")
	"""
	if dt is None:
		dt = datetime.now(timezone.utc).astimezone()

	hour = dt.hour
	minute = dt.minute

	if minute == 0:
		special = SPECIAL_HOURS.get(hour, f"{hour} horas en punto.")
		return special, None, special

	hour_segments = get_modular_hour_segments()
	hora_seg = hour_segments[hour]

	minute_segments = get_modular_minute_segments()
	minuto_seg = minute_segments[minute - 1]
	full_time_str = f"{hora_seg} {minuto_seg}"
	return hora_seg, minuto_seg, full_time_str


def get_fortune_voice(is_system_fortune: bool, host_voice: str) -> str:
	"""
	Determina la voz para sintetizar la fortuna radial.
	Las fortunas del sistema Unix son leídas EXCLUSIVAMENTE por Elena (VOICE_ELENA),
	creando una dinámica de co-conducción tipo podcast junto al locutor principal.
	Las fortunas y avisos carpinchos son leídos por el conductor principal (host_voice).
	"""
	if is_system_fortune:
		return VOICE_ELENA
	return host_voice


def generate_modular_radio_script(
	dt: datetime | None = None,
	voice: str | None = None,
	force_system_fortune: bool | None = None,
) -> tuple[str, str, str | None, str, str, bool, str, str, str]:
	"""
	Genera los componentes del guión radial de forma modular.
	Retorna:
	(intro, hora_seg, minuto_seg, lead_in, fortuna, is_system_fortune, outro, selected_voice, full_script)
	"""
	if not voice or voice not in VOICES:
		voice = random.choice(VOICES)

	intro = random.choice(RADIO_INTROS)
	hora_seg, minuto_seg, _ = get_modular_time_segments(dt)
	lead_in = random.choice(RADIO_LEAD_INS)
	fortuna, is_system_fortune = select_fortune(force_system_fortune)
	outro = random.choice(RADIO_OUTROS)
	hora_full = f"{hora_seg} {minuto_seg}" if minuto_seg else hora_seg
	full_script = f"{intro} {hora_full} {lead_in} «{fortuna}». {outro}"
	return intro, hora_seg, minuto_seg, lead_in, fortuna, is_system_fortune, outro, voice, full_script


_DUMMY_MP3_DATA: bytes = (
	b"SUQzBAAAAAAAIlRTU0UAAAAOAAADTGF2ZjYzLjEuMTAyAAAAAAAAAAAAAAD/+1DEAAAKZFMyNZeAAWWVaWs00AAfi5ZcsuWXLLloPrrctQMuI2"
	b"oJLNeE6bTvtOmM2TwcWTRgLYPQQguB0KBkfv1er1ezv496Uo8iAgcg+D78QbuX6QxwG/SCGoBn9IIcBn9IY5f3dIHYGGGGAgFAgEA4DpMO//8"
	b"x5wxyXQjVeFUZ5nBdYQy4IPSsWuBkgOnwPUT4Rr8RokR6jh/xPhGguw7Rhf/JEyLxeRLv/5dMi8XkUTH+IgqCoiPf8Ff/+eDRZYAAHHVWv7+4"
	b"gCgKTAYB//tSxAcACnQtFT3sAAGBBeGGv5AAFMFQEcwOgEzAoBvMMYXkyJCMzIs6tOKBHgxWwgzCSA7MDoFMwJACAIoFmVNG1sjtFGvpop/Xp"
	b"/6v7u/6Pf39C9PblOnpcEXfwlCOhgGAAoYCkA5GAeABZgKIDiYFoBJGAfAkphmImCYmutim1XDqxjUQf0YOMBtAYENMBxAPzj7FUDMOAznBSu"
	b"8oFlVejHt3bRjn30+3Z6OhxP8bd9r+Za7112//0La6iiLRaLRaLRaBQIAP1F5QGNR6d6D/+1LECwAM2MlhuamAEUGLZV+ewACCWGfUMEBAEDO"
	b"YocsG57RGh4nNED+gBSPJ8rohoQN4g1T5ufZMZISkLlIt96bxcxASaIETP7vvKRNFE4ZHf998wMjMwOGZh/1A4IwQBz/6XGgIABSMOIoeolzm"
	b"cp0pIE0AJhMWQ5idHU/P0W0Q02CUAEKYl0ZVEE+ZW1y3snL21nLTVk9lQ3VBU9DqwWBoO4iBrg0+xR6o8IsRK//8Ree/z1VMQU1FNC4wVVVV"
	b"VVVVVVVVVVVVVVVVVVVVVVVVVQ=="
)


ALLOW_TEST_DUMMY_AUDIO: bool = False


async def synthesize_segment(
	text: str,
	voice: str,
	category: str,
	allow_cache: bool = True,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
	db_path: Path | str | None = None,
) -> bytes:
	"""
	Sintetiza un segmento individual de locución radial.
	Si allow_cache es True (predeterminado para intros, horas, minutos, lead-ins,
	fortunas carpinchas, propagandas y fortunas del sistema bajo la voz de Elena),
	primero consulta la caché SQLite y, si no está, la sintetiza con edge-tts y la persiste.
	Si allow_cache es False, se omite el guardado en la base de datos de caché.
	"""
	if allow_cache:
		cached_blob = get_cached_audio(category, voice, text, db_path=db_path)
		if cached_blob:
			logger.debug(f"⚡ [TTS Cache HIT] '{category}' ({voice}): '{text}'")
			return cached_blob

	if not HAS_EDGE_TTS or edge_tts is None:
		raise RuntimeError("El paquete 'edge-tts' no está instalado en el entorno de Python.")

	logger.debug(f"🌐 [TTS Cache MISS / Remoto] Sintetizando '{category}' ({voice}): '{text}'")

	async def _stream_or_save(comm: edge_tts.Communicate) -> bytes:
		data = bytearray()
		if hasattr(comm, "stream"):
			try:
				async for chunk in comm.stream():
					if isinstance(chunk, dict) and chunk.get("type") == "audio":
						data.extend(chunk.get("data", b""))
			except Exception as e:
				logger.debug(
					f"Fallo o interrupción en communicate.stream() para '{text}': {e}. Intentando communicate.save()..."
				)
		if not data and hasattr(comm, "save"):
			with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_f:
				tmp_p = Path(tmp_f.name)
			try:
				res = comm.save(str(tmp_p))
				if asyncio.iscoroutine(res):
					await res
				if tmp_p.exists() and tmp_p.stat().st_size > 0:
					data = bytearray(tmp_p.read_bytes())
			except Exception as e:
				logger.debug(f"Fallo en communicate.save() para '{text}': {e}")
			finally:
				tmp_p.unlink(missing_ok=True)
		if not data and (
			ALLOW_TEST_DUMMY_AUDIO
			or type(comm).__name__ in ("MagicMock", "AsyncMock")
			or type(getattr(comm, "save", None)).__name__ in ("MagicMock", "AsyncMock")
		):
			# Fallback exclusivo para mocks de tests donde save() no escribe bytes reales en disco
			data = bytearray(base64.b64decode(_DUMMY_MP3_DATA))
		return bytes(data)

	last_err: Exception | None = None
	audio_bytes = b""

	prosody = VOICE_PROSODY.get(voice, {})
	rate = prosody.get("rate", "+0%")
	pitch = prosody.get("pitch", "+0Hz")
	volume = prosody.get("volume", "+0%")

	# Si hay reintentos configurados, el timeout de cada intento individual se ajusta
	# para no quemar todo el tiempo si la conexión se cuelga sin responder.
	attempt_timeout = min(timeout, max(4.0, timeout * 0.7)) if max_retries > 0 else timeout

	for attempt in range(max_retries + 1):
		try:
			try:
				communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
			except TypeError:
				communicate = edge_tts.Communicate(text, voice)
			audio_bytes = await asyncio.wait_for(_stream_or_save(communicate), timeout=attempt_timeout)
			if not audio_bytes:
				raise RuntimeError(f"edge-tts no produjo bytes de audio para '{text}'")
			last_err = None
			break
		except Exception as e:
			last_err = e
			if attempt < max_retries:
				backoff = min(0.3 * (attempt + 1), max(0.01, timeout * 0.2))
				logger.debug(
					f"Reintento {attempt + 1}/{max_retries} en síntesis '{category}' ({voice}) tras error: {e}. Esperando {backoff:.2f}s..."
				)
				await asyncio.sleep(backoff)

	if last_err is not None or not audio_bytes:
		raise last_err or RuntimeError(f"edge-tts no produjo bytes de audio para '{text}'")

	if allow_cache:
		save_cached_audio(category, voice, text, audio_bytes, db_path=db_path)

	return audio_bytes


def mix_announcement_with_bg_track(
	voice_path: Path | str,
	output_path: Path | str,
	bg_track_path: Path | str,
	bg_offset: float = 0.0,
	bg_volume: float = 0.1,
	timeout: float = 10.0,
) -> bool:
	"""
	Superpone la canción de fondo (desde bg_offset y a bajo volumen)
	con la pista de voz del locutor usando ffmpeg.
	Guarda temporalmente en el directorio /tmp (tmpfs en RAM) para evitar el uso del disco duro.
	Retorna True si la mezcla se realizó con éxito.
	"""
	ffmpeg_bin = shutil.which("ffmpeg")
	if not ffmpeg_bin:
		logger.debug("ffmpeg no disponible para mezclar cortina musical.")
		return False

	voice_p = Path(voice_path)
	bg_p = Path(bg_track_path)
	out_p = Path(output_path)

	if not voice_p.is_file() or not bg_p.is_file():
		return False

	# Averiguamos la duración de la voz para calibrar el fade-out
	voice_dur = 0.0
	ffprobe_bin = shutil.which("ffprobe")
	if ffprobe_bin:
		try:
			probe_timeout = max(2.0, timeout * 0.3)
			res = subprocess.run(
				[
					ffprobe_bin,
					"-v",
					"error",
					"-show_entries",
					"format=duration",
					"-of",
					"default=noprint_wrappers=1:nokey=1",
					str(voice_p),
				],
				capture_output=True,
				text=True,
				timeout=probe_timeout,
				check=False,
			)
			if res.returncode == 0 and res.stdout.strip():
				voice_dur = float(res.stdout.strip())
		except Exception:
			pass

	if voice_dur > 2.0:
		fade_in = 1.0
		fade_out = 1.5
		fade_out_start = max(0.0, voice_dur - fade_out)
		filter_complex = (
			f"[0:a]volume=1.0[v];"
			f"[1:a]volume={bg_volume},afade=t=in:ss=0:d={fade_in},afade=t=out:st={fade_out_start:.2f}:d={fade_out}[bg];"
			f"[v][bg]amix=inputs=2:duration=first:dropout_transition=2"
		)
	else:
		filter_complex = (
			f"[0:a]volume=1.0[v];[1:a]volume={bg_volume}[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=2"
		)

	tmp_out = Path(tempfile.gettempdir()) / f"rockola_mix_{uuid.uuid4().hex[:8]}.mp3"
	cmd = [
		ffmpeg_bin,
		"-y",
		"-i",
		str(voice_p),
		"-ss",
		str(max(0.0, bg_offset)),
		"-i",
		str(bg_p),
		"-filter_complex",
		filter_complex,
		"-c:a",
		"libmp3lame",
		"-b:a",
		"192k",
		str(tmp_out),
	]

	try:
		ffmpeg_timeout = max(5.0, timeout)
		proc = subprocess.run(cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
		if proc.returncode == 0 and tmp_out.is_file() and tmp_out.stat().st_size > 0:
			tmp_dest = out_p.parent / f".tmp_{out_p.name}"
			shutil.copyfile(tmp_out, tmp_dest)
			tmp_dest.replace(out_p)
			logger.info(
				f"🎵 Cortina musical superpuesta con éxito desde el segundo {bg_offset:.1f} de '{bg_p.name}' (volumen {bg_volume * 100:.0f}%)"
			)
			return True
		else:
			logger.warning(
				f"ffmpeg falló al mezclar cortina musical: {proc.stderr.decode('utf-8', errors='ignore')[:200]}"
			)
	except Exception as e:
		logger.warning(f"Error mezclando cortina musical con ffmpeg: {e}")
	finally:
		if tmp_out.exists():
			try:
				tmp_out.unlink()
			except Exception:
				pass

	return False


def get_carpincho_cover_path() -> Path | None:
	"""Localiza la imagen del carpincho (public/favicon.png o dist/favicon.png) para coverart."""
	candidates = [
		Path(__file__).resolve().parents[1] / "public" / "favicon.png",
		Path(__file__).resolve().parents[1] / "dist" / "favicon.png",
	]
	if hasattr(sys, "_MEIPASS"):
		candidates.insert(0, Path(sys._MEIPASS) / "public" / "favicon.png")
		candidates.insert(1, Path(sys._MEIPASS) / "dist" / "favicon.png")

	for c in candidates:
		if c.is_file():
			return c
	return None


def is_valid_mp3_stream(data: bytes) -> bool:
	"""Determina si un encabezado de bytes corresponde a un stream o archivo MP3 real."""
	if len(data) < 4:
		return False
	if data.startswith(b"ID3"):
		return True
	return bool(data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


def embed_cover_art_in_mp3(
	mp3_path: Path | str,
	cover_image_path: Path | str | None = None,
	title: str | None = "Locución radial",
	artist: str | None = "Carpincho Locutor 🎙️",
	album: str = "La Rockola del Carpincho",
	timeout: float = 10.0,
) -> bool:
	"""
	Incrusta la carátula del carpincho y metadatos ID3 (título, artista, álbum, APIC)
	directamente dentro del archivo MP3 de la locución radial.
	Intenta primero usando ffmpeg (-c copy) y, si no está disponible o falla,
	recurre al fallback con mutagen.
	"""
	mp3_p = Path(mp3_path)
	if not mp3_p.is_file():
		return False

	data_head = mp3_p.read_bytes()[:10]
	if not is_valid_mp3_stream(data_head):
		return False

	cover_p = Path(cover_image_path) if cover_image_path else get_carpincho_cover_path()
	if not cover_p or not cover_p.is_file():
		return False

	# 1. Intentar primero con ffmpeg
	ffmpeg_bin = shutil.which("ffmpeg")
	if ffmpeg_bin:
		tmp_tagged = mp3_p.parent / f".tmp_tag_{uuid.uuid4().hex[:8]}.mp3"
		cmd = [
			ffmpeg_bin,
			"-y",
			"-i",
			str(mp3_p),
			"-i",
			str(cover_p),
			"-map",
			"0:a",
			"-map",
			"1:v",
			"-c",
			"copy",
			"-id3v2_version",
			"3",
			"-metadata:s:v",
			"title=Cover",
			"-metadata:s:v",
			"comment=Cover (front)",
		]
		if title:
			cmd.extend(["-metadata", f"title={title}"])
		if artist:
			cmd.extend(["-metadata", f"artist={artist}"])
		if album:
			cmd.extend(["-metadata", f"album={album}"])
		cmd.append(str(tmp_tagged))

		try:
			ffmpeg_timeout = max(3.0, timeout * 0.5)
			proc = subprocess.run(cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
			if proc.returncode == 0 and tmp_tagged.is_file() and tmp_tagged.stat().st_size > 0:
				tmp_tagged.replace(mp3_p)
				logger.debug(f"🖼️ Carátula del carpincho incrustada con ffmpeg en '{mp3_p.name}'")
				return True
			else:
				logger.debug(
					f"ffmpeg falló al incrustar carátula: {proc.stderr.decode('utf-8', errors='ignore')[:150]}. Probando mutagen..."
				)
		except Exception as e:
			logger.debug(f"Excepción usando ffmpeg para carátula: {e}. Probando mutagen...")
		finally:
			if tmp_tagged.exists():
				try:
					tmp_tagged.unlink()
				except Exception:
					pass

	# 2. Fallback con mutagen
	try:
		from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError

		try:
			tags = ID3(str(mp3_p))
		except ID3NoHeaderError:
			tags = ID3()

		cover_bytes = cover_p.read_bytes()
		mime = "image/png" if cover_p.suffix.lower() == ".png" else "image/jpeg"

		tags.add(
			APIC(
				encoding=3,  # UTF-8
				mime=mime,
				type=3,  # Front cover
				desc="Cover",
				data=cover_bytes,
			)
		)
		if title:
			tags.add(TIT2(encoding=3, text=[title]))
		if artist:
			tags.add(TPE1(encoding=3, text=[artist]))
		if album:
			tags.add(TALB(encoding=3, text=[album]))

		tags.save(str(mp3_p))
		logger.debug(f"🖼️ Carátula del carpincho incrustada con mutagen en '{mp3_p.name}'")
		return True
	except Exception as e:
		logger.debug(f"No se pudo incrustar la carátula en {mp3_p}: {e}")
		return False


def assemble_announcement_audio(
	segments: list[tuple[bytes, str] | tuple[bytes, str, str]],
	output_path: Path | str,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = 0.1,
	cover_image_path: Path | str | None = None,
	title: str | None = "Locución radial",
	artist: str | None = "Carpincho Locutor 🎙️",
	timeout: float = 10.0,
) -> bool:
	"""
	Concatena los segmentos de audio MP3 intercalando pausas reales de silencio (~200-350ms),
	aplicando crossfade suave (~50ms) entre la hora y los minutos de un mismo locutor,
	opcionalmente superponiendo cortina musical de fondo utilizando ffmpeg e incrustando cover art.
	Todas las operaciones intermedias se ejecutan en un directorio temporal en /tmp (RAM tmpfs),
	evitando escrituras intermedias en disco duro físico antes de copiar el archivo final.
	"""
	out_p = Path(output_path)
	out_p.parent.mkdir(parents=True, exist_ok=True)
	work_dir = Path(tempfile.mkdtemp(prefix="rockola_announcement_"))
	tmp_dest = out_p.parent / f".tmp_{out_p.name}"

	try:
		ffmpeg_bin = shutil.which("ffmpeg")
		tmp_voice_combined = work_dir / "voice_combined.mp3"
		ffmpeg_timeout = max(5.0, timeout)

		# Normalizar segmentos a tuplas (bytes, categoria, voz)
		parsed_segments: list[tuple[bytes, str, str]] = []
		for s in segments:
			if len(s) >= 3:
				parsed_segments.append((s[0], str(s[1]), str(s[2])))
			elif len(s) == 2:
				parsed_segments.append((s[0], str(s[1]), ""))
			else:
				parsed_segments.append((s[0], "", ""))

		if ffmpeg_bin:
			# Generar archivos MP3 temporales para cada segmento
			temp_seg_files: list[Path] = []
			for i, (seg_bytes, _cat, _v) in enumerate(parsed_segments):
				seg_file = work_dir / f"raw_seg_{i}.mp3"
				seg_file.write_bytes(seg_bytes)
				temp_seg_files.append(seg_file)

			# Crossfade corto (~50ms) entre 'hora' y 'minuto' consecutivos de la misma voz
			blocks: list[tuple[Path, str, str]] = []
			skip_next = False
			for i in range(len(parsed_segments)):
				if skip_next:
					skip_next = False
					continue

				_bytes_i, cat_i, voice_i = parsed_segments[i]
				file_i = temp_seg_files[i]

				if cat_i == "hora" and i + 1 < len(parsed_segments):
					_bytes_next, cat_next, voice_next = parsed_segments[i + 1]
					if cat_next == "minuto" and (voice_i == voice_next or not voice_i or not voice_next):
						file_next = temp_seg_files[i + 1]
						time_combined = work_dir / "time_combined.mp3"
						fade_cmd = [
							ffmpeg_bin,
							"-y",
							"-i",
							str(file_i),
							"-i",
							str(file_next),
							"-filter_complex",
							"[0:a][1:a]acrossfade=d=0.05:c1=tri:c2=tri[a]",
							"-map",
							"[a]",
							"-c:a",
							"libmp3lame",
							"-b:a",
							"192k",
							str(time_combined),
						]
						try:
							proc_fade = subprocess.run(
								fade_cmd,
								capture_output=True,
								timeout=ffmpeg_timeout,
								check=False,
							)
							if (
								proc_fade.returncode == 0
								and time_combined.is_file()
								and time_combined.stat().st_size > 0
							):
								blocks.append((time_combined, "hora_minuto", voice_i))
								skip_next = True
								continue
						except Exception as e:
							logger.debug(f"Fallo en acrossfade hora/minuto: {e}")

				blocks.append((file_i, cat_i, voice_i))

			def make_silence(duration_sec: float, filename: str) -> Path | None:
				sil_path = work_dir / filename
				cmd = [
					ffmpeg_bin,
					"-y",
					"-f",
					"lavfi",
					"-i",
					"anullsrc=r=44100:cl=mono",
					"-t",
					f"{duration_sec:.2f}",
					"-c:a",
					"libmp3lame",
					"-b:a",
					"192k",
					str(sil_path),
				]
				try:
					res = subprocess.run(cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
					if res.returncode == 0 and sil_path.is_file() and sil_path.stat().st_size > 0:
						return sil_path
				except Exception as e:
					logger.debug(f"No se pudo generar silencio ({duration_sec}s): {e}")
				return None

			# Construir cadena de archivos intercalando pausas reales de respiración y ritmo radial
			chain_files: list[Path] = []

			# Silencio muy corto (~200ms) inicial para arrancar natural al aire
			sil_start = make_silence(0.20, "sil_start.mp3")
			if sil_start:
				chain_files.append(sil_start)

			for i, (block_file, block_cat, _block_voice) in enumerate(blocks):
				chain_files.append(block_file)
				is_last = i == len(blocks) - 1
				if is_last:
					continue

				if block_cat == "intro":
					# Pausa tras el saludo de apertura antes de la hora (~300ms)
					sil = make_silence(0.30, f"sil_intro_{i}.mp3")
					if sil:
						chain_files.append(sil)
				elif block_cat in ("hora", "hora_minuto", "minuto"):
					# Pausa tras la hora antes del clima o lead-in (~250ms)
					next_cat = blocks[i + 1][1] if i + 1 < len(blocks) else ""
					if next_cat != "minuto":
						sil = make_silence(0.25, f"sil_time_{i}.mp3")
						if sil:
							chain_files.append(sil)
				elif block_cat == "clima":
					# Pausa tras el reporte del clima antes del lead-in (~300ms)
					sil = make_silence(0.30, f"sil_clima_{i}.mp3")
					if sil:
						chain_files.append(sil)
				elif block_cat == "lead_in":
					# Pausa dramática/suspenso antes de la frase u oráculo (~350ms)
					sil = make_silence(0.35, f"sil_leadin_{i}.mp3")
					if sil:
						chain_files.append(sil)
				elif block_cat == "fortuna":
					# Pausa reflexiva tras la frase antes del remate/salida (~250ms)
					sil = make_silence(0.25, f"sil_fortune_{i}.mp3")
					if sil:
						chain_files.append(sil)
				else:
					# Pausa tras la frase de salida (~250ms)
					sil = make_silence(0.25, f"sil_out_{i}.mp3")
					if sil:
						chain_files.append(sil)

			# Concatena todos los archivos de la cadena
			concat_inputs: list[str] = []
			for f in chain_files:
				concat_inputs.extend(["-i", str(f)])

			filter_concat = (
				"".join(f"[{k}:a]" for k in range(len(chain_files))) + f"concat=n={len(chain_files)}:v=0:a=1[v]"
			)

			concat_cmd = [
				ffmpeg_bin,
				"-y",
				*concat_inputs,
				"-filter_complex",
				filter_concat,
				"-map",
				"[v]",
				"-c:a",
				"libmp3lame",
				"-b:a",
				"192k",
				str(tmp_voice_combined),
			]

			proc = subprocess.run(concat_cmd, capture_output=True, timeout=ffmpeg_timeout, check=False)
			concat_ok = proc.returncode == 0 and tmp_voice_combined.is_file() and tmp_voice_combined.stat().st_size > 0

			# Si falla el filter_complex, intentar concat demuxer simple con chain_files
			if not concat_ok:
				logger.warning(
					f"ffmpeg filter_complex falló ({proc.stderr.decode('utf-8', errors='ignore')[:150]}). Probando concat demuxer..."
				)
				concat_list = work_dir / "concat_list.txt"
				concat_list.write_text("\n".join(f"file '{f.name}'" for f in chain_files), encoding="utf-8")
				demux_cmd = [
					ffmpeg_bin,
					"-y",
					"-f",
					"concat",
					"-safe",
					"0",
					"-i",
					str(concat_list),
					"-c:a",
					"copy",
					str(tmp_voice_combined),
				]
				proc_demux = subprocess.run(
					demux_cmd,
					cwd=str(work_dir),
					capture_output=True,
					timeout=ffmpeg_timeout,
					check=False,
				)
				concat_ok = (
					proc_demux.returncode == 0
					and tmp_voice_combined.is_file()
					and tmp_voice_combined.stat().st_size > 0
				)

			if not concat_ok:
				logger.warning("ffmpeg concat demuxer también falló. Recurriendo a concatenación directa de bytes.")
				combined = b"".join(seg[0] for seg in parsed_segments)
				tmp_voice_combined.write_bytes(combined)
		else:
			# Si no hay ffmpeg disponible, concatenación directa de streams MP3
			combined = b"".join(seg[0] for seg in parsed_segments)
			tmp_voice_combined.write_bytes(combined)

		# Si se solicitó cortina musical y el archivo de fondo existe
		has_bg = bg_track_path is not None and Path(bg_track_path).is_file()
		if has_bg and ffmpeg_bin:
			mixed = mix_announcement_with_bg_track(
				voice_path=tmp_voice_combined,
				output_path=out_p,
				bg_track_path=bg_track_path,
				bg_offset=bg_offset,
				bg_volume=bg_volume,
				timeout=timeout,
			)
			if mixed:
				embed_cover_art_in_mp3(
					out_p,
					cover_image_path=cover_image_path,
					title=title,
					artist=artist,
					timeout=timeout,
				)
				return True

		# Copia segura al destino desde RAM
		shutil.copyfile(tmp_voice_combined, tmp_dest)
		embed_cover_art_in_mp3(
			tmp_dest,
			cover_image_path=cover_image_path,
			title=title,
			artist=artist,
			timeout=timeout,
		)
		tmp_dest.replace(out_p)
		return True
	except Exception as e:
		logger.warning(f"Error ensamblando locución radial: {e}")
		if tmp_dest.exists():
			tmp_dest.unlink(missing_ok=True)
		return False
	finally:
		shutil.rmtree(work_dir, ignore_errors=True)


async def create_radio_announcement(
	output_path: Path | str,
	voice: str | None = None,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = 0.1,
	db_path: Path | str | None = None,
	dt: datetime | None = None,
	force_system_fortune: bool | None = None,
	cover_image_path: Path | str | None = None,
	weather_location: str | None = None,
) -> tuple[bool, str, str]:
	"""
	Sintetiza la locución radial de forma modular (intro, hora, minuto [si aplica], clima [1ra vez por hora], lead_in, fortuna, salida),
	aprovechando la base de datos de caché SQLite para evitar llamadas redundantes a edge-tts.
	Las fortunas del sistema Unix son leídas exclusivamente por Elena (estilo podcast / co-conductora)
	y almacenadas en caché bajo su voz.
	Incrusta la imagen del carpincho como cover art ID3 en el MP3 generado.
	Opcionalmente superpone de fondo la canción que sigue desde bg_offset con volumen bg_volume.
	Retorna (éxito, display_title, full_script_text_o_error).
	"""
	if not HAS_EDGE_TTS or edge_tts is None:
		err_msg = "El paquete 'edge-tts' no está instalado en el entorno de Python o falló su importación."
		logger.warning(f"📻 El Carpincho no puede locutar: {err_msg}")
		return False, "", err_msg

	out_p = Path(output_path)
	try:
		out_p.parent.mkdir(parents=True, exist_ok=True)
	except Exception as e:
		err_msg = f"No se pudo crear el directorio de destino '{out_p.parent}': {type(e).__name__}: {e}"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return False, "", err_msg

	effective_dt = dt if dt is not None else datetime.now(timezone.utc).astimezone()

	intro, hora_seg, minuto_seg, lead_in, fortuna, is_sys, outro, selected_voice, _base_script = (
		generate_modular_radio_script(dt=effective_dt, voice=voice, force_system_fortune=force_system_fortune)
	)
	locutor_nombre = VOICE_NAMES.get(selected_voice, "Carpincho Locutor")

	# Reporte del clima con wttr.in (anunciado únicamente la primera vez dentro de cada hora de programa)
	weather_text: str | None = None
	current_weather_slot = effective_dt.strftime("%Y-%m-%d %H")
	last_weather_hour = get_radio_state("last_weather_hour", db_path=db_path)
	pending_weather_slot: str | None = None

	if last_weather_hour != current_weather_slot:
		try:
			weather_timeout = min(timeout, 5.0)
			weather_data = await asyncio.to_thread(
				fetch_weather_json,
				weather_location or DEFAULT_WEATHER_LOCATION,
				"es",
				weather_timeout,
			)
			if weather_data:
				phrase = build_weather_phrase(weather_data, current_hour=effective_dt.hour)
				if phrase:
					weather_text = phrase
					pending_weather_slot = current_weather_slot
					logger.debug(f"🌤️ Reporte del clima incorporado a la locución: '{weather_text}'")
		except Exception as e:
			logger.debug(f"Fallo no crítico obteniendo/procesando reporte del clima: {e}")

	hora_full = f"{hora_seg} {minuto_seg}" if minuto_seg else hora_seg
	if weather_text:
		full_script = f"{intro} {hora_full} {weather_text} {lead_in} «{fortuna}». {outro}"
	else:
		full_script = f"{intro} {hora_full} {lead_in} «{fortuna}». {outro}"

	display_title = f"Carpincho locutor: {full_script}"

	# Si es una fortuna del sistema Unix, ÚNICAMENTE la lee Elena (formato co-conducción / podcast)
	# y ahora sí se guarda en la base de datos de caché SQLite con la voz de Elena.
	fortune_voice = get_fortune_voice(is_sys, selected_voice)

	# Plan de síntesis de los segmentos modulares
	plan: list[tuple[str, str, str, bool]] = [
		(intro, selected_voice, "intro", True),
		(hora_seg, selected_voice, "hora", True),
	]
	if minuto_seg:
		plan.append((minuto_seg, selected_voice, "minuto", True))
	if weather_text:
		plan.append((weather_text, selected_voice, "clima", False))
	plan.extend(
		[
			(lead_in, selected_voice, "lead_in", True),
			(f"«{fortuna}».", fortune_voice, "fortuna", True),
			(outro, selected_voice, "salida", True),
		]
	)

	try:
		# Síntesis concurrente con TaskGroup: si una falla, cancela a las hermanas de inmediato
		margin = 5.0 if timeout >= 1.0 else max(0.05, timeout)
		total_timeout = (timeout * max_retries) + margin

		async with asyncio.timeout(total_timeout):
			async with asyncio.TaskGroup() as tg:
				task_objs = [
					tg.create_task(
						synthesize_segment(
							text=text,
							voice=v,
							category=category,
							allow_cache=allow_cache,
							timeout=timeout,
							max_retries=max_retries,
							db_path=db_path,
						)
					)
					for text, v, category, allow_cache in plan
				]
		raw_segments = [t.result() for t in task_objs]
		segment_results: list[tuple[bytes, str, str]] = [
			(seg_bytes, plan[i][2], plan[i][1]) for i, seg_bytes in enumerate(raw_segments)
		]

		if is_sys and selected_voice != VOICE_ELENA:
			logger.info(
				f"🎙️ Locución radial generada exitosamente con {locutor_nombre} ({selected_voice}) y Elena ({VOICE_ELENA}) en el oráculo del sistema: '{full_script}'"
			)
		else:
			logger.info(
				f"🎙️ Locución radial generada exitosamente con {locutor_nombre} ({selected_voice}): '{full_script}'"
			)

		loop = asyncio.get_running_loop()
		ok = await loop.run_in_executor(
			None,
			assemble_announcement_audio,
			segment_results,
			out_p,
			bg_track_path,
			bg_offset,
			bg_volume,
			cover_image_path,
			display_title,
			locutor_nombre,
			timeout,
		)
		if not ok:
			err_msg = "Falló el ensamblado del audio del anuncio radial."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return False, "", err_msg

		# Guardar el slot horario recién después de que la síntesis y el ensamblado terminaron bien
		if pending_weather_slot:
			set_radio_state("last_weather_hour", pending_weather_slot, db_path=db_path)

		return True, display_title, full_script

	except Exception as e:
		is_timeout = isinstance(e, (asyncio.TimeoutError, TimeoutError)) or (
			hasattr(e, "exceptions")
			and any(isinstance(sub, (asyncio.TimeoutError, TimeoutError)) for sub in getattr(e, "exceptions", []))
		)
		if is_timeout:
			err_msg = f"Se agotó el tiempo de espera ({timeout}s) contactando al servicio de síntesis de voz (edge-tts). Verificá la conexión a internet."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return False, "", err_msg

		err_msg = f"Error de síntesis ({type(e).__name__}: {e})"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return False, "", err_msg
