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
]


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
	"""Intenta obtener una fortuna corta mediante el comando Unix `fortune -s` si está disponible."""
	fortune_bin = shutil.which("fortune")
	if not fortune_bin:
		return None

	try:
		res = subprocess.run(
			[fortune_bin, "-s"],
			capture_output=True,
			text=True,
			timeout=1.5,
			check=False,
		)
		if res.returncode == 0 and res.stdout:
			cleaned = clean_fortune_text(res.stdout)
			# Solo aceptar fortunas de longitud razonable para locución radial (entre 15 y 160 caracteres)
			if 15 <= len(cleaned) <= 160:
				return cleaned
	except Exception as e:
		logger.debug(f"Error consultando comando fortune del sistema: {e}")

	return None


def get_radio_fortune() -> str:
	"""
	Devuelve una fortuna combinando frases criollas del carpincho y el comando fortune del sistema.
	Si el comando del sistema está presente, hay un 50% de probabilidad de usarlo.
	"""
	if random.random() < 0.5:
		sys_fortune = get_system_fortune()
		if sys_fortune:
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
