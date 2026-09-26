"""
Módulo de locución para el Modo Radio en La Rockola del Carpincho.
Maneja la síntesis de voz con edge-tts, formateo horario radial y banco mixto de fortunas.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import shutil
import subprocess
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
VOICES = [VOICE_TOMAS, VOICE_ELENA]

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


def generate_radio_script(
	dt: datetime | None = None,
	voice: str | None = None,
) -> tuple[str, str, str]:
	"""
	Genera el guión radial, seleccionando locutor (Tomás o Elena),
	formateando la hora y agregando la fortuna.
	Retorna (script_text, selected_voice, fortune_text).
	"""
	if not voice or voice not in VOICES:
		voice = random.choice(VOICES)

	fortune = get_radio_fortune()
	time_str = format_radio_time(dt)

	templates = [
		(
			f"En el aire de La Rockola del Carpincho, {time_str}. "
			f"Momento de la galletita de la fortuna: «{fortune}». "
			"¡Seguimos con más música!"
		),
		(
			f"{time_str} en toda la República Argentina. "
			f"Ojo al piojo con lo que dice el oráculo de La Rockola: «{fortune}». "
			"¡Que no decaiga!"
		),
		(
			f"¡Buenas gente linda! {time_str} en La Rockola. "
			f"Tiramos una frase para reflexionar mientras te tomás unos mates: «{fortune}». "
			"¡Pegale play que esto sigue!"
		),
		(
			f"La hora en La Rockola: {time_str}. "
			f"Dice la fortuna del día: «{fortune}». "
			"¡Metemos la próxima canción al toque!"
		),
		(f"{time_str}. Sabiduría carpinchera para el alma: «{fortune}». ¡Seguimos de joda en La Rockola!"),
	]

	script_text = random.choice(templates)
	return script_text, voice, fortune


async def create_radio_announcement(
	output_path: Path | str,
	voice: str | None = None,
	timeout: float = 5.0,
) -> tuple[bool, str, str]:
	"""
	Sintetiza la locución radial con edge-tts y la guarda en output_path.
	Retorna (éxito, título_para_display, script_text).
	"""
	if not HAS_EDGE_TTS or edge_tts is None:
		logger.warning("edge-tts no está disponible. No se puede generar la locución radial.")
		return False, "", ""

	out_p = Path(output_path)
	out_p.parent.mkdir(parents=True, exist_ok=True)

	script_text, selected_voice, _fortune = generate_radio_script(voice=voice)
	locutor_nombre = "Tomás" if selected_voice == VOICE_TOMAS else "Elena"
	display_title = f"Momento de la Fortuna 🥠 ({locutor_nombre})"

	try:
		communicate = edge_tts.Communicate(script_text, selected_voice)
		await asyncio.wait_for(communicate.save(str(out_p)), timeout=timeout)
		logger.info(f"🎙️ Locución radial generada exitosamente con {locutor_nombre} ({selected_voice}): '{script_text}'")
		return True, display_title, script_text
	except asyncio.TimeoutError:
		logger.warning(f"Timeout ({timeout}s) generando locución radial con edge-tts.")
	except Exception as e:
		logger.warning(f"Error generando locución radial con edge-tts: {e}")

	return False, "", ""
