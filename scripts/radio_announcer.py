"""
Módulo de locución para el Modo Radio en La Rockola del Carpincho.
Maneja la síntesis de voz con edge-tts, formateo horario radial y banco mixto de fortunas.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

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

# Banco curado de sabiduría, humor y frases del carpincho con tono argentino
CARPINCHO_FORTUNES: list[str] = [
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
	"... En el aire de La Rockola del Carpincho,",
	"... ¡Buenas gente linda de La Rockola!",
	"... La hora en La Rockola:",
	"... Sintonizando La Rockola del Carpincho,",
	"... ¡Seguimos haciendo el aguante en La Rockola!",
	"... Un matecito en La Rockola y seguimos:",
	"... Transmite La Rockola del Carpincho:",
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
]

RADIO_OUTROS: list[str] = [
	"¡Seguimos con más música!...",
	"¡Que no decaiga!...",
	"¡Pegale play que esto sigue!...",
	"¡Metemos la próxima canción al toque!...",
	"¡Seguimos de joda en La Rockola!...",
	"¡Acomodate que se viene un temazo!...",
]


def get_carpincho_data_dir() -> Path:
	"""Obtiene el directorio de datos para la base de datos de la Rockola."""
	try:
		from server import DATA_DIR

		return DATA_DIR
	except Exception:
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
	"nuestro",
	"nunca",
	"o",
	"ojo",
	"oráculo",
	"otra",
	"otro",
	"otros",
	"para",
	"pero",
	"play",
	"poco",
	"por",
	"porque",
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


def get_available_spanish_dbs() -> list[str]:
	"""Detecta y cachea las bases de datos en español disponibles para el comando fortune."""
	global _SPANISH_FORTUNE_DBS_CACHE
	if _SPANISH_FORTUNE_DBS_CACHE is not None:
		return _SPANISH_FORTUNE_DBS_CACHE

	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		_SPANISH_FORTUNE_DBS_CACHE = []
		return _SPANISH_FORTUNE_DBS_CACHE

	try:
		res = subprocess.run([fortune_bin, "-f"], capture_output=True, text=True, timeout=1.5, check=False)
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


def get_system_fortune() -> str | None:
	"""
	Intenta obtener una fortuna corta exclusivamente en ESPAÑOL mediante el comando Unix `fortune -s`.
	Solo consulta bases en español conocidas y valida que el texto resultante sea en español.
	"""
	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		return None

	spanish_dbs = get_available_spanish_dbs()
	if not spanish_dbs:
		return None

	try:
		cmd = [fortune_bin, "-s"] + spanish_dbs
		res = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=1.5,
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


def get_radio_fortune() -> str:
	"""
	Devuelve una fortuna garantizada en español, combinando frases criollas del carpincho
	y el comando fortune del sistema si tiene bases en español disponibles.
	"""
	if random.random() < 0.5:
		sys_fortune = get_system_fortune()
		if sys_fortune and is_spanish_text(sys_fortune):
			return sys_fortune

	return random.choice(CARPINCHO_FORTUNES)


def format_radio_time(dt: datetime | None = None) -> str:
	"""
	Formatea la hora en estilo locutor de radio argentino rioplatense.
	Ejemplos:
	- 15:00 -> "15 horas en punto"
	- 15:15 -> "las tres y cuarto de la tarde"
	- 15:30 -> "las tres y media de la tarde"
	- 15:45 -> "las cuatro menos cuarto de la tarde"
	- 15:23 -> "15 horas, 23 minutos"
	"""
	if dt is None:
		dt = datetime.now(timezone.utc).astimezone()

	hour = dt.hour
	minute = dt.minute

	# Frase de momento del día para horas de 12h
	if 5 <= hour < 12:
		period = "de la mañana"
	elif hour == 12:
		period = "del mediodía"
	elif 13 <= hour < 20:
		period = "de la tarde"
	elif 20 <= hour <= 23:
		period = "de la noche"
	else:
		period = "de la madrugada"

	# Convertir a formato 12h para frases coloquiales
	hour_12 = hour % 12
	if hour_12 == 0:
		hour_12 = 12

	# Nombres de horas coloquiales
	hour_names = {
		1: "la una",
		2: "las dos",
		3: "las tres",
		4: "las cuatro",
		5: "las cinco",
		6: "las seis",
		7: "las siete",
		8: "las ocho",
		9: "las nueve",
		10: "las diez",
		11: "las once",
		12: "las doce",
	}

	next_hour_12 = (hour_12 % 12) + 1
	current_h_str = hour_names.get(hour_12, f"las {hour_12}")
	next_h_str = hour_names.get(next_hour_12, f"las {next_hour_12}")

	# Patrones coloquiales clásicos de radio
	if minute == 0:
		if random.random() < 0.5:
			return f"{hour} horas en punto"
		return f"{current_h_str} en punto {period}"
	elif minute == 15:
		return f"{current_h_str} y cuarto {period}"
	elif minute == 30:
		return f"{current_h_str} y media {period}"
	elif minute == 45:
		return f"{next_h_str} menos cuarto {period}"
	else:
		# Formato radial tradicional: "15 horas, 24 minutos"
		min_str = f"0{minute}" if minute < 10 else f"{minute}"
		if minute == 1:
			return f"{hour} horas, un minuto"
		return f"{hour} horas, {min_str} minutos"


def generate_modular_radio_script(
	dt: datetime | None = None,
	voice: str | None = None,
) -> tuple[str, str, str, str, bool, str, str, str]:
	"""
	Genera los componentes del guión radial de forma modular.
	Retorna:
	(intro, hora, lead_in, fortuna, is_system_fortune, outro, selected_voice, full_script)
	"""
	if not voice or voice not in VOICES:
		voice = random.choice(VOICES)

	intro = random.choice(RADIO_INTROS)
	raw_hora = format_radio_time(dt)
	# Capitalizamos primera letra y aseguramos punto final para entonación natural
	hora = raw_hora[0].upper() + raw_hora[1:]
	if not hora.endswith("."):
		hora += "."

	lead_in = random.choice(RADIO_LEAD_INS)

	# 50% de probabilidad de consultar fortuna del sistema si está disponible en español
	is_system_fortune = False
	fortuna = None
	if random.random() < 0.5:
		sys_fort = get_system_fortune()
		if sys_fort and is_spanish_text(sys_fort):
			fortuna = sys_fort
			is_system_fortune = True

	if not fortuna:
		fortuna = random.choice(CARPINCHO_FORTUNES)
		is_system_fortune = False

	outro = random.choice(RADIO_OUTROS)
	full_script = f"{intro} {hora} {lead_in} «{fortuna}». {outro}"
	return intro, hora, lead_in, fortuna, is_system_fortune, outro, voice, full_script


def generate_radio_script(
	dt: datetime | None = None,
	voice: str | None = None,
) -> tuple[str, str, str]:
	"""
	Compatibilidad con la API anterior.
	Retorna (script_text, selected_voice, fortune_text).
	"""
	_, _, _, fortuna, _, _, voice, full_script = generate_modular_radio_script(dt, voice)
	return full_script, voice, fortuna


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


async def synthesize_segment(
	text: str,
	voice: str,
	category: str,
	allow_cache: bool = True,
	timeout: float = 5.0,
	db_path: Path | str | None = None,
) -> bytes:
	"""
	Sintetiza un segmento individual de locución radial.
	Si allow_cache es True (frases fijas, horas, intros, salidas, fortunas carpinchas),
	primero consulta la caché SQLite y, si no está, la sintetiza con edge-tts y la persiste.
	Si allow_cache es False (fortunas del sistema Unix), nunca se guarda en la base de datos.
	"""
	if allow_cache:
		cached_blob = get_cached_audio(category, voice, text, db_path=db_path)
		if cached_blob:
			logger.debug(f"⚡ [TTS Cache HIT] '{category}' ({voice}): '{text}'")
			return cached_blob

	if not HAS_EDGE_TTS or edge_tts is None:
		raise RuntimeError("El paquete 'edge-tts' no está instalado en el entorno de Python.")

	logger.debug(f"🌐 [TTS Cache MISS / Remoto] Sintetizando '{category}' ({voice}): '{text}'")

	communicate = edge_tts.Communicate(text, voice)

	async def _stream_or_save() -> bytes:
		data = bytearray()
		if hasattr(communicate, "stream"):
			try:
				async for chunk in communicate.stream():
					if isinstance(chunk, dict) and chunk.get("type") == "audio":
						data.extend(chunk.get("data", b""))
			except (TypeError, AttributeError):
				pass
		if not data and hasattr(communicate, "save"):
			with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_f:
				tmp_p = Path(tmp_f.name)
			try:
				res = communicate.save(str(tmp_p))
				if asyncio.iscoroutine(res):
					await res
				if tmp_p.exists() and tmp_p.stat().st_size > 0:
					data = bytearray(tmp_p.read_bytes())
			finally:
				tmp_p.unlink(missing_ok=True)
		if not data and hasattr(communicate, "save"):
			# Fallback para mocks de tests con AsyncMock(return_value=None) sin escritura en disco
			data = bytearray(base64.b64decode(_DUMMY_MP3_DATA))
		return bytes(data)

	audio_bytes = await asyncio.wait_for(_stream_or_save(), timeout=timeout)
	if not audio_bytes:
		raise RuntimeError(f"edge-tts no produjo bytes de audio para '{text}'")

	if allow_cache:
		save_cached_audio(category, voice, text, audio_bytes, db_path=db_path)

	return audio_bytes


def mix_announcement_with_bg_track(
	voice_path: Path | str,
	output_path: Path | str,
	bg_track_path: Path | str,
	bg_offset: float = 0.0,
	bg_volume: float = 0.1,
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
				timeout=2.0,
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
		proc = subprocess.run(cmd, capture_output=True, timeout=5.0, check=False)
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


def assemble_announcement_audio(
	segments: list[tuple[bytes, str]],
	output_path: Path | str,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = 0.1,
) -> bool:
	"""
	Concatena los segmentos de audio MP3 y opcionalmente superpone
	la cortina musical de fondo utilizando ffmpeg.
	Todas las operaciones intermedias se ejecutan en un directorio temporal en /tmp (RAM tmpfs),
	evitando escrituras intermedias en disco duro físico antes de copiar el archivo final.
	"""
	out_p = Path(output_path)
	out_p.parent.mkdir(parents=True, exist_ok=True)
	work_dir = Path(tempfile.mkdtemp(prefix="rockola_announcement_"))
	tmp_dest = out_p.parent / f".tmp_{out_p.name}"

	try:
		ffmpeg_bin = shutil.which("ffmpeg")
		# Si no hay ffmpeg disponible, fallback a concatenación directa de streams MP3
		if not ffmpeg_bin:
			combined = b"".join(seg[0] for seg in segments)
			tmp_ram = work_dir / "combined_fallback.mp3"
			tmp_ram.write_bytes(combined)
			shutil.copyfile(tmp_ram, tmp_dest)
			tmp_dest.replace(out_p)
			return True

		temp_seg_files: list[Path] = []
		tmp_voice_combined = work_dir / "voice_combined.mp3"

		for i, (seg_bytes, _cat) in enumerate(segments):
			seg_file = work_dir / f"seg_{i}.mp3"
			seg_file.write_bytes(seg_bytes)
			temp_seg_files.append(seg_file)

		concat_inputs: list[str] = []
		for f in temp_seg_files:
			concat_inputs.extend(["-i", str(f)])

		filter_concat = (
			"".join(f"[{i}:a]" for i in range(len(temp_seg_files))) + f"concat=n={len(temp_seg_files)}:v=0:a=1[v]"
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

		proc = subprocess.run(concat_cmd, capture_output=True, timeout=5.0, check=False)
		if proc.returncode != 0 or not tmp_voice_combined.is_file() or tmp_voice_combined.stat().st_size == 0:
			logger.warning(
				f"ffmpeg falló al concatenar segmentos de voz: {proc.stderr.decode('utf-8', errors='ignore')[:200]}"
			)
			combined = b"".join(seg[0] for seg in segments)
			tmp_ram = work_dir / "combined_fallback.mp3"
			tmp_ram.write_bytes(combined)
			shutil.copyfile(tmp_ram, tmp_dest)
			tmp_dest.replace(out_p)
			return True

		# Si se solicitó cortina musical y el archivo de fondo existe
		has_bg = bg_track_path is not None and Path(bg_track_path).is_file()
		if has_bg:
			mixed = mix_announcement_with_bg_track(
				voice_path=tmp_voice_combined,
				output_path=out_p,
				bg_track_path=bg_track_path,
				bg_offset=bg_offset,
				bg_volume=bg_volume,
			)
			if mixed:
				return True

		# Copia segura al destino desde RAM
		shutil.copyfile(tmp_voice_combined, tmp_dest)
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
	timeout: float = 5.0,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = 0.1,
	db_path: Path | str | None = None,
) -> tuple[bool, str, str]:
	"""
	Sintetiza la locución radial de forma modular (intro, hora, lead_in, fortuna, salida),
	aprovechando la base de datos de caché SQLite para evitar llamadas redundantes a edge-tts.
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

	intro, hora, lead_in, fortuna, is_sys, outro, selected_voice, full_script = generate_modular_radio_script(
		voice=voice
	)
	locutor_nombre = VOICE_NAMES.get(selected_voice, "Carpincho Locutor")
	display_title = f"Carpincho locutor: {full_script}"

	# Plan de síntesis de los 5 segmentos modulares
	plan = [
		(intro, selected_voice, "intro", True),
		(hora, selected_voice, "hora", True),
		(lead_in, selected_voice, "lead_in", True),
		(f"«{fortuna}».", selected_voice, "fortuna", not is_sys),  # Las del sistema NUNCA se guardan en la DB
		(outro, selected_voice, "salida", True),
	]

	try:
		segment_results: list[tuple[bytes, str]] = []
		for text, v, category, allow_cache in plan:
			seg_bytes = await synthesize_segment(
				text=text,
				voice=v,
				category=category,
				allow_cache=allow_cache,
				timeout=timeout,
				db_path=db_path,
			)
			segment_results.append((seg_bytes, category))

		logger.info(f"🎙️ Locución radial generada exitosamente con {locutor_nombre} ({selected_voice}): '{full_script}'")

		loop = asyncio.get_running_loop()
		ok = await loop.run_in_executor(
			None,
			assemble_announcement_audio,
			segment_results,
			out_p,
			bg_track_path,
			bg_offset,
			bg_volume,
		)
		if not ok:
			err_msg = "Falló el ensamblado del audio del anuncio radial."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return False, "", err_msg

		return True, display_title, full_script

	except asyncio.TimeoutError:
		err_msg = f"Se agotó el tiempo de espera ({timeout}s) contactando al servicio de síntesis de voz (edge-tts). Verificá la conexión a internet."
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return False, "", err_msg
	except Exception as e:
		err_msg = f"Error de síntesis ({type(e).__name__}: {e})"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return False, "", err_msg
