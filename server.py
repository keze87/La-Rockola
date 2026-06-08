#!/usr/bin/env python3
import sys
import shutil
import importlib.util


def check_dependencies():
	"""
	Revisa que esté todo piola para arrancar la Rockola del Carpincho.
	Falla temprano pero con buena onda si falta algo.
	"""
	missing_python = []
	# Define expected Python packages and their installation hints
	python_deps = {
		"fastapi": "pip install fastapi",
		"uvicorn": "pip install uvicorn",
		"mutagen": "pip install mutagen",
		"pydantic": "pip install pydantic",
	}

	is_win = sys.platform == "win32"
	is_mac = sys.platform == "darwin"

	# Solo en Linux pedimos DBus para controlar los botones multimedia
	if not is_win and not is_mac:
		python_deps["dbus_next"] = "pip install dbus-next"

	for module, fix in python_deps.items():
		if importlib.util.find_spec(module) is None:
			missing_python.append((module, fix))

	missing_system = []
	# Determine OS for OS-specific system binary hints
	mpv_fix = (
		"winget install mpv"
		if is_win
		else (
			"brew install mpv"
			if is_mac
			else "sudo apt install mpv (o lo que use tu distro)"
		)
	)
	ytdlp_fix = (
		"pip install yt-dlp (o bajate el binario de https://github.com/yt-dlp/yt-dlp)"
	)

	system_deps = {"mpv": mpv_fix, "yt-dlp": ytdlp_fix}

	for bin_name, fix in system_deps.items():
		if shutil.which(bin_name) is None:
			missing_system.append((bin_name, fix))

	# Si falta algo, frenamos acá y le decimos al usuario qué onda
	if missing_python or missing_system:
		print(
			"🦦 ¡Pará un cacho, che! La Rockola del Carpincho no puede arrancar así 🧉\n",
			file=sys.stderr,
		)

		if missing_python:
			print("📦 Paquetes de Python que faltan en la ronda:", file=sys.stderr)
			for mod, fix in missing_python:
				print(f"  - {mod:<10} -> Mandale un: {fix}", file=sys.stderr)

		if missing_system:
			print(
				"\n🛠️ Herramientas del sistema (sin esto el carpincho no canta):",
				file=sys.stderr,
			)
			for bin_name, fix in missing_system:
				print(f"  - {bin_name:<10} -> Fijate con: {fix}", file=sys.stderr)

		print(
			"\nTranqui, instalá eso, cambiale la yerba al mate y volvé a correr el script. ¡Te espero! 🦦🧉🎶",
			file=sys.stderr,
		)
		sys.exit(1)


# --- 1. PRIMERO LOS MATES Y LAS DEPENDENCIAS ---
check_dependencies()

# --- 2. AHORA SÍ, IMPORTAMOS TRANQUIS ---
import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uvicorn
import tempfile
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile
from pathlib import Path
from pydantic import BaseModel

# --- 3. INICIALIZAMOS LA BASE DE DATOS (SQLITE) ---
DB_PATH = Path.home() / ".carpincho.db"


def init_db():
	with sqlite3.connect(DB_PATH) as conn:
		c = conn.cursor()

		# La tabla maestra de canciones (una fila por tema, con su hash único y metadata básica)
		c.execute("""CREATE TABLE IF NOT EXISTS tracks
					 (track_id TEXT PRIMARY KEY,
					  path TEXT,
					  title TEXT,
					  album TEXT,
					  artist TEXT,
					  duration_str TEXT)""")

		# Historial de reproducciones (múltiples entradas por tema)
		c.execute("""CREATE TABLE IF NOT EXISTS play_history
					 (id INTEGER PRIMARY KEY AUTOINCREMENT,
					  track_id TEXT,
					  played_at REAL)""")

		# Favoritos (una fila por tema)
		c.execute("""CREATE TABLE IF NOT EXISTS favorites
					 (track_id TEXT PRIMARY KEY)""")

		# URLs de YouTube
		c.execute("""CREATE TABLE IF NOT EXISTS url_logs
					 (id INTEGER PRIMARY KEY AUTOINCREMENT,
					  url TEXT,
					  title TEXT,
					  artist TEXT,
					  played_at TEXT)""")
		conn.commit()


init_db()


# --- 4. Y DBUS, SI ESTAMOS EN LINUX Y LO TENEMOS INSTALADO ---
DBUS_AVAILABLE = False
if sys.platform == "linux":
	try:
		from dbus_next.aio import MessageBus
		from dbus_next.service import ServiceInterface, method, dbus_property, signal
		from dbus_next.constants import PropertyAccess
		from dbus_next import Variant

		DBUS_AVAILABLE = True
	except ImportError:
		pass

logging.basicConfig(
	level=logging.DEBUG,  # Set to DEBUG to see everything
	format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
)
logger = logging.getLogger("RockolaCarpincho")


def truncate_text(text: str, max_len: int) -> str:
	text = str(text)
	return text[: max_len - 1] + "…" if len(text) > max_len else text


def highlight_json(json_data):
	"""Formats and applies ANSI syntax highlighting to a JSON string or dict."""

	# Parse to ensure valid JSON and apply standard indentation
	if isinstance(json_data, str):
		try:
			parsed = json.loads(json_data)
		except json.JSONDecodeError as e:
			return f"Invalid JSON: {e}"
	else:
		parsed = json_data

	formatted_json = json.dumps(parsed, indent=2, ensure_ascii=False)

	# ANSI color codes for the terminal
	colors = {
		"key": "\033[94m",  # Blue
		"string": "\033[92m",  # Green
		"number": "\033[93m",  # Yellow
		"boolean": "\033[95m",  # Magenta
		"null": "\033[91m",  # Red
		"reset": "\033[0m",  # Reset to default
	}

	# Regex pattern to identify distinct JSON data types
	# Group 1: Keys (string followed by a colon)
	# Group 2: String values
	# Group 3: Numbers (integers, floats, scientific notation)
	# Group 4: Booleans (true/false)
	# Group 5: Null
	pattern = r'("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b)|(\bnull\b)'

	def replacer(match):
		if match.group(1):  # Key
			key_str = match.group(1)
			colon_idx = key_str.rfind(":")
			# Color the key, but leave the colon default
			return (
				colors["key"]
				+ key_str[:colon_idx]
				+ colors["reset"]
				+ key_str[colon_idx:]
			)
		elif match.group(2):  # String value
			return colors["string"] + match.group(2) + colors["reset"]
		elif match.group(3):  # Number
			return colors["number"] + match.group(3) + colors["reset"]
		elif match.group(4):  # Boolean
			return colors["boolean"] + match.group(4) + colors["reset"]
		elif match.group(5):  # Null
			return colors["null"] + match.group(5) + colors["reset"]

		return match.group(0)

	# Apply the regex substitution
	return re.sub(pattern, replacer, formatted_json)


def get_cover_art_uri(path: str) -> str:
	"""Extrae la tapa a la carpeta temporal y devuelve la URI para MPRIS."""
	if not path or path.startswith("http"):
		return ""
	try:
		path_hash = hashlib.md5(path.encode("utf-8")).hexdigest()
		tmp_dir = os.path.join(tempfile.gettempdir(), "carpincho_covers")
		os.makedirs(tmp_dir, exist_ok=True)

		try:  # Evitamos que se junten más de 50 tapas en el disco
			covers = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)]
			if len(covers) > 50:
				# Ordenamos de más vieja a más nueva
				covers.sort(key=os.path.getmtime)
				# Borramos las más viejitas hasta que queden solo 30
				for old_cover in covers[:-30]:
					os.remove(old_cover)
		except Exception as e:
			logger.debug(f"Pifió pasando la escoba por las tapas: {e}")

		tmp_cover = os.path.join(tmp_dir, f"{path_hash}.jpg")

		if os.path.exists(tmp_cover):
			return f"file://{tmp_cover}"

		audio = MutagenFile(path)
		if not audio:
			return ""
		cover_data = None

		# Buscar portada
		if hasattr(audio, "pictures") and audio.pictures:
			cover_data = audio.pictures[0].data
		elif hasattr(audio, "tags") and audio.tags:
			for key, tag in audio.tags.items():
				if key.startswith("APIC"):
					cover_data = tag.data
					break
			if not cover_data and "covr" in audio.tags:
				cover_data = audio.tags["covr"][0]

		if cover_data:
			with open(tmp_cover, "wb") as f:
				f.write(cover_data)
			return f"file://{tmp_cover}"
	except Exception:
		pass
	return ""


def generate_smart_hash(filepath, chunk_size=1024 * 1024):
	"""
	Lee 1MB cerca del principio y 1MB cerca del final (esquivando metadatos).
	Genera un Hash único basado puramente en las ondas de audio.
	"""
	try:
		file_size = os.path.getsize(filepath)

		# Si el archivo es ridículamente chico (menos de 3MB), leemos un pedacito del medio
		if file_size < chunk_size * 3:
			with open(filepath, "rb") as f:
				f.seek(file_size // 2)
				data = f.read(file_size // 4)
				return hashlib.md5(data).hexdigest()

		with open(filepath, "rb") as f:
			# Leer 1MB al 15% del archivo (pasando de largo cualquier tapa o tag gigante)
			f.seek(int(file_size * 0.15))
			chunk1 = f.read(chunk_size)

			# Leer 1MB al 85% del archivo (antes de los tags finales)
			f.seek(int(file_size * 0.85))
			chunk2 = f.read(chunk_size)

			# Armamos el Hash con los dos pedazos + el tamaño total para evitar colisiones
			hasher = hashlib.md5()
			hasher.update(chunk1)
			hasher.update(chunk2)
			hasher.update(str(file_size).encode("utf-8"))

			return hasher.hexdigest()
	except Exception as e:
		logger.debug(f"Pifió el hash inteligente para {filepath}: {e}")
		# Fallback por si el archivo está corrupto o bloqueado
		return hashlib.md5(str(filepath).encode("utf-8")).hexdigest()


class Track:
	"""Guarda la data y la ruta del temita."""

	def __init__(self, path: Path):
		self.path = path
		self.title = path.stem
		self.artist = "Desconocido"
		self.album = "Desconocido"
		self.duration_str = "0:00"
		self._extract_metadata()

	def _extract_metadata(self):
		try:
			audio = MutagenFile(self.path, easy=True)
			if audio is None:
				audio = MutagenFile(self.path)
			if audio and getattr(audio, "tags", None):
				tags = {k.lower(): v for k, v in audio.tags.items()}
				for k in ["title", "©nam", "tit2"]:
					if k in tags:
						val = tags[k]
						self.title = val[0] if isinstance(val, list) else str(val)
						break
				for k in ["artist", "©art", "tpe1"]:
					if k in tags:
						val = tags[k]
						self.artist = val[0] if isinstance(val, list) else str(val)
						break
				for k in ["album", "©alb", "talb"]:
					if k in tags:
						val = tags[k]
						self.album = val[0] if isinstance(val, list) else str(val)
						break
			if audio and hasattr(audio, "info") and hasattr(audio.info, "length"):
				length = audio.info.length
				if length:
					mins = int(length // 60)
					secs = int(length % 60)
					self.duration_str = f"{mins}:{secs:02d}"
		except Exception as e:
			logger.warning(f"No le pude leer la mente (metadata) a {self.path}: {e}")

		self.search_string = f"{self.artist} {self.title}".lower()
		self.track_hash = str(generate_smart_hash(self.path))

	def to_dict(self):
		return {
			"path": str(self.path),
			"display_title": self.title,
			"display_artist": self.artist,
			"album": self.album,
			"duration_str": self.duration_str,
			"search_string": self.search_string,
			"title": self.title,
			"artist": self.artist,
		}


class AsyncMpvController:
	"""Maneja al reproductor (MPV) por atrás."""

	def __init__(self, callbacks):
		self.process = None
		self.socket_path = None
		self.reader = None
		self.writer = None
		self.is_windows = sys.platform == "win32"
		self.callbacks = callbacks  # Dict mapping event names to async handlers
		self._start_lock = asyncio.Lock()

	async def stop(self):
		"""Mata el proceso de MPV cuando cerramos el servidor."""
		if self.process and self.process.returncode is None:
			logger.info("Apagando la Rockola... mandando a dormir al MPV.")
			try:
				self.process.kill()
				await asyncio.wait_for(self.process.wait(), timeout=1.0)
			except Exception:
				pass

	async def start(self):
		# Si ya hay otro proceso reiniciando MPV, nos quedamos en el molde y salimos
		if self._start_lock.locked():
			async with self._start_lock:
				return

		async with self._start_lock:
			# Cleanup any zombie process if it exists
			await self.stop()

			env = os.environ.copy()

			# 1. Handle OS-Specific IPC Socket Paths
			if self.is_windows:
				self.socket_path = rf"\\.\pipe\mpv_server_{id(self)}"
			else:
				if "WAYLAND_DISPLAY" not in env:
					env["WAYLAND_DISPLAY"] = "wayland-0"
				tmp_dir = os.environ.get("TMPDIR", "/tmp")
				self.socket_path = os.path.join(tmp_dir, f"mpv_server_{id(self)}.sock")

				if os.path.exists(self.socket_path):
					try:
						os.remove(self.socket_path)
					except OSError:
						pass

			logger.info(f"Armando el socket de MPV en {self.socket_path}...")

			# Determinar si mostramos la ventana en base al estado (si existe)
			show_window = True
			if "APIState" in globals() and hasattr(state, "mpv_visible"):
				show_window = state.mpv_visible

			# Si logramos registrar nuestro propio MPRIS en DBus, silenciamos el nativo de MPV.
			# Si falló (ej. no hay DBus o se rompió), dejamos que MPV use su MPRIS de rescate.
			own_mpris_active = getattr(state, "mpris_registered", False)
			mpris_opt = "no" if own_mpris_active else "yes"
			keys_opt = "no" if own_mpris_active else "yes"

			mpv_args = [
				"mpv",
				"--autofit=33%x33%",
				"--fs",
				"--geometry=-20-40",
				"--hwdec=auto",
				"--idle",
				"--no-border",
				"--ontop",
				"--quiet",
				"--script-opts=osc-visibility=always,osc-layout=topbar",
				f"--load-scripts={mpris_opt}",
				f"--input-media-keys={keys_opt}",
				"--sub-color=#FF00FF",
				"--sub-font-size=100",
				"--sub-font=Pacifico",
				"--sub-scale-by-window=no",
				"--sub-scale-with-window=no",
				"--ytdl-raw-options=no-playlist=",
				f"--{'quiet' if show_window else 'no-audio-display'}",
				f"--input-ipc-server={self.socket_path}",
			]

			if not self.is_windows:
				mpv_args.extend(["--wayland-app-id=mpvpip", "--x11-name=mpvpip"])

			logger.info("Despertando al carpincho reproductor (MPV)...")
			try:
				self.process = await asyncio.create_subprocess_exec(
					*mpv_args,
					stdin=asyncio.subprocess.DEVNULL,
					stdout=asyncio.subprocess.DEVNULL,
					stderr=asyncio.subprocess.DEVNULL,
					env=env,
				)
			except Exception:
				logger.error(
					"¡Uy! No se encontró a MPV instalado. El carpincho está triste."
				)
				sys.exit(1)

			for i in range(20):
				if self.is_windows:
					# Named pipes appear instantly in the OS namespace if MPV created it successfully
					try:
						with open(self.socket_path, "r+b"):
							break
					except FileNotFoundError:
						pass
				elif os.path.exists(self.socket_path):
					break
				await asyncio.sleep(0.3)

			if not self.is_windows and not os.path.exists(self.socket_path):
				raise RuntimeError("MPV se quedó dormido y no armó el socket a tiempo.")

			# 2. Handle OS-Specific Socket Connections
			if self.is_windows:
				logger.info("Conectados al Named Pipe de Windows (pipa lista).")
				asyncio.create_task(self._read_ipc_events_windows())
			else:
				self.reader, self.writer = await asyncio.open_unix_connection(
					self.socket_path
				)
				logger.info("Conectados al socket Unix de MPV (todo legal).")
				asyncio.create_task(self._read_ipc_events())

			if (
				not self.is_windows
			):  # En Unix mandamos la suscripción por acá porque la conexión es única y no se cierra.
				# Request MPV to broadcast volume and pause changes
				await self._send(
					json.dumps({"command": ["observe_property", 1, "volume"]})
				)
				await self._send(
					json.dumps({"command": ["observe_property", 2, "pause"]})
				)
				await self._send(
					json.dumps({"command": ["observe_property", 3, "time-pos"]})
				)
				await self._send(
					json.dumps({"command": ["observe_property", 4, "duration"]})
				)
				await self._send(
					json.dumps({"command": ["observe_property", 5, "mute"]})
				)

			# Si hay un callback de reinicio, avisamos que ya estamos listos para recibir los datos de nuevo
			if "mpv_restarted" in self.callbacks:
				asyncio.create_task(self.callbacks["mpv_restarted"]())

	async def _read_ipc_events_windows(self):
		"""Threaded reader for Windows Named Pipes to prevent blocking."""

		# BUGFIX: Grab the main event loop BEFORE entering the thread!
		main_loop = asyncio.get_running_loop()

		def read_pipe():
			try:
				# Cambiamos "rb" por "r+b" para poder leer y escribir
				with open(self.socket_path, "r+b") as pipe:

					# Nos suscribimos a los eventos en LA MISMA pipa que va a quedarse leyendo
					pipe.write(b'{"command": ["observe_property", 1, "volume"]}\n')
					pipe.write(b'{"command": ["observe_property", 2, "pause"]}\n')
					pipe.write(b'{"command": ["observe_property", 3, "time-pos"]}\n')
					pipe.write(b'{"command": ["observe_property", 4, "duration"]}\n')
					pipe.write(b'{"command": ["observe_property", 5, "mute"]}\n')
					pipe.flush()

					while True:
						line = pipe.readline()
						if not line:
							break
						# BUGFIX: Use the captured main_loop instead of get_running_loop()
						asyncio.run_coroutine_threadsafe(
							self._process_event_line(line), main_loop
						)
			except Exception as e:
				logger.debug(f"Pifió algo leyendo la pipa en Windows: {e}")

		await asyncio.to_thread(read_pipe)

	async def _read_ipc_events(self):
		while self.reader:
			try:
				line = await self.reader.readline()
				if not line:
					break
				await self._process_event_line(line)
			except Exception as e:
				logger.debug(f"Pifió algo leyendo IPC de MPV: {e}")
				break

		# Si llegamos acá es porque se cerró el socket (MPV murió o se cerró)
		logger.debug(
			"El socket Unix de MPV se cerró. Limpiando conexión para forzar reinicio..."
		)
		self.reader = None
		if self.writer:
			self.writer.close()
			self.writer = None

	async def _process_event_line(self, line: bytes):
		try:
			event_data = json.loads(line.decode("utf-8").strip())
			event_name = event_data.get("event")

			# Handle Track End
			if event_name == "end-file":
				reason = event_data.get("reason")
				if reason in ("eof", "error") and "song_ended" in self.callbacks:
					asyncio.create_task(self.callbacks["song_ended"]())
				elif reason in ("quit", "stop") and "track_stopped" in self.callbacks:
					asyncio.create_task(self.callbacks["track_stopped"]())
			elif event_name == "property-change":
				prop_name = event_data.get("name")
				prop_val = event_data.get("data")

				if (
					prop_name == "volume"
					and prop_val is not None
					and "volume_update" in self.callbacks
				):
					asyncio.create_task(self.callbacks["volume_update"](prop_val))
				elif (
					prop_name == "pause"
					and prop_val is not None
					and "pause_update" in self.callbacks
				):
					asyncio.create_task(self.callbacks["pause_update"](prop_val))
				elif prop_name == "time-pos" and "time_update" in self.callbacks:
					asyncio.create_task(self.callbacks["time_update"](prop_val))
				elif prop_name == "duration" and "duration_update" in self.callbacks:
					asyncio.create_task(self.callbacks["duration_update"](prop_val))
				elif (
					prop_name == "mute"
					and prop_val is not None
					and "mute_update" in self.callbacks
				):
					asyncio.create_task(self.callbacks["mute_update"](prop_val))
		except json.JSONDecodeError:
			pass

	async def _send(self, cmd_payload: str):
		# logger.debug(f"Tirándole comando al MPV: \n {highlight_json(cmd_payload)}")
		cmd_bytes = (cmd_payload + "\n").encode("utf-8")

		try:
			if self.is_windows:
				# Direct file write for Windows Named Pipes
				def write_pipe():
					with open(self.socket_path, "a+b") as pipe:
						pipe.write(cmd_bytes)

				await asyncio.to_thread(write_pipe)
			else:
				if not self.writer:
					await self.start()
				self.writer.write(cmd_bytes)
				await self.writer.drain()
		except Exception as e:
			logger.error(f"Se cortó la conexión con MPV ({e}). Reiniciando el motor...")
			await self.start()

			# ¡REINTENTO! Para no perder el comando que estábamos por mandar
			try:
				if self.is_windows:

					def write_pipe_retry():
						with open(self.socket_path, "a+b") as pipe:
							pipe.write(cmd_bytes)

					await asyncio.to_thread(write_pipe_retry)
				else:
					if self.writer:
						self.writer.write(cmd_bytes)
						await self.writer.drain()
			except Exception as retry_e:
				logger.error(
					f"Pifió fiero. No quiso agarrar viaje ni reiniciando: {retry_e}"
				)


# --- DBUS / MPRIS Classes ---
if DBUS_AVAILABLE:

	class MPRISRoot(ServiceInterface):
		def __init__(self):
			super().__init__("org.mpris.MediaPlayer2")

		@method()
		def Quit(self):  # type: ignore
			pass

		@method()
		def Raise(self):  # type: ignore
			pass

		@dbus_property(access=PropertyAccess.READ)
		def CanQuit(self) -> "b":  # type: ignore
			return False

		@dbus_property(access=PropertyAccess.READ)
		def Fullscreen(self) -> "b":  # type: ignore
			return False

		@dbus_property(access=PropertyAccess.READ)
		def CanSetFullscreen(self) -> "b":  # type: ignore
			return False

		@dbus_property(access=PropertyAccess.READ)
		def CanRaise(self) -> "b":  # type: ignore
			return False

		@dbus_property(access=PropertyAccess.READ)
		def HasTrackList(self) -> "b":  # type: ignore
			return False

		@dbus_property(access=PropertyAccess.READ)
		def Identity(self) -> "s":  # type: ignore
			return "La Rockola del Carpincho"

		@dbus_property(access=PropertyAccess.READ)
		def DesktopEntry(self) -> "s":  # type: ignore
			return "carpincho"

		@dbus_property(access=PropertyAccess.READ)
		def SupportedUriSchemes(self) -> "as":  # type: ignore
			return ["file", "http", "https"]

		@dbus_property(access=PropertyAccess.READ)
		def SupportedMimeTypes(self) -> "as":  # type: ignore
			return ["audio/mpeg", "audio/x-flac", "audio/ogg"]

	class MPRISPlayer(ServiceInterface):
		def __init__(self, state_ref):
			super().__init__("org.mpris.MediaPlayer2.Player")
			self.state = state_ref

		@method()
		def Next(self):  # type: ignore
			asyncio.create_task(handle_command(CommandRequest(cmd="skip")))

		@method()
		def Previous(self):  # type: ignore
			asyncio.create_task(handle_command(CommandRequest(cmd="prev")))

		@method()
		def Pause(self):  # type: ignore
			if not self.state.mpv_paused:
				asyncio.create_task(handle_command(CommandRequest(cmd="pause")))

		@method()
		def PlayPause(self):  # type: ignore
			asyncio.create_task(handle_command(CommandRequest(cmd="pause")))

		@method()
		def Stop(self):  # type: ignore
			asyncio.create_task(handle_command(CommandRequest(cmd="stop")))

		@method()
		def Play(self):  # type: ignore
			if self.state.mpv_paused:
				asyncio.create_task(handle_command(CommandRequest(cmd="pause")))

		@method()
		def Seek(self, Offset: "x"):  # type: ignore
			amount = Offset / 1000000.0
			asyncio.create_task(
				handle_command(CommandRequest(cmd="seek", amount=amount))
			)

		@method()
		def SetPosition(self, TrackId: "o", Position: "x"):  # type: ignore
			amount = Position / 1000000.0
			asyncio.create_task(
				handle_command(CommandRequest(cmd="seek_absolute", amount=amount))
			)

		@method()
		def OpenUri(self, Uri: "s"):  # type: ignore
			asyncio.create_task(handle_command(CommandRequest(cmd="play", path=Uri)))

		@dbus_property(access=PropertyAccess.READ)
		def PlaybackStatus(self) -> "s":  # type: ignore
			if not self.state.current_track:
				return "Stopped"
			return "Paused" if self.state.mpv_paused else "Playing"

		@dbus_property(access=PropertyAccess.READ)
		def LoopStatus(self) -> "s":  # type: ignore
			return "None"

		@dbus_property(access=PropertyAccess.READ)
		def Rate(self) -> "d":  # type: ignore
			return 1.0

		@dbus_property(access=PropertyAccess.READ)
		def Shuffle(self) -> "b":  # type: ignore
			return False

		@dbus_property(access=PropertyAccess.READ)
		def Metadata(self) -> "a{sv}":  # type: ignore
			if not self.state.current_track:
				return {
					"mpris:trackid": Variant(
						"o", "/org/mpris/MediaPlayer2/TrackList/NoTrack"
					)
				}

			title = "Desconocido"
			artist = "Desconocido"
			album = "Desconocido"
			dur_usec = 0

			for t in self.state.tracks_cache:
				if t["path"] == self.state.current_track:
					title = t.get("display_title", title)
					artist = t.get("display_artist", artist)
					album = t.get("album", album)
					break

			if self.state.current_track in self.state.url_metadata:
				meta = self.state.url_metadata[self.state.current_track]
				title = meta.get("display_title", title)
				artist = meta.get("display_artist", artist)
				album = meta.get("album", album)

			if self.state.duration:
				dur_usec = int(self.state.duration * 1000000)

			cover_uri = get_cover_art_uri(self.state.current_track)

			meta_dict = {
				"mpris:trackid": Variant(
					"o", "/org/mpris/MediaPlayer2/TrackList/Track0"
				),
				"xesam:title": Variant("s", title),
				"xesam:artist": Variant("as", [artist]),
				"xesam:album": Variant("s", album),
				"mpris:length": Variant("x", dur_usec),
			}

			if cover_uri:
				meta_dict["mpris:artUrl"] = Variant("s", cover_uri)

			return meta_dict

		@dbus_property(access=PropertyAccess.READWRITE)
		def Volume(self) -> "d":  # type: ignore
			return self.state.volume / 100.0

		@Volume.setter
		def Volume(self, val: "d"):  # type: ignore
			vollevel = int(val * 100)
			asyncio.create_task(
				handle_command(CommandRequest(cmd="set_volume", vollevel=vollevel))
			)

		@dbus_property(access=PropertyAccess.READ)
		def Position(self) -> "x":  # type: ignore
			return int(self.state.time_pos * 1000000)

		@dbus_property(access=PropertyAccess.READ)
		def MinimumRate(self) -> "d":  # type: ignore
			return 1.0

		@dbus_property(access=PropertyAccess.READ)
		def MaximumRate(self) -> "d":  # type: ignore
			return 1.0

		@dbus_property(access=PropertyAccess.READ)
		def CanGoNext(self) -> "b":  # type: ignore
			return True

		@dbus_property(access=PropertyAccess.READ)
		def CanGoPrevious(self) -> "b":  # type: ignore
			return True

		@dbus_property(access=PropertyAccess.READ)
		def CanPlay(self) -> "b":  # type: ignore
			return True

		@dbus_property(access=PropertyAccess.READ)
		def CanPause(self) -> "b":  # type: ignore
			return True

		@dbus_property(access=PropertyAccess.READ)
		def CanSeek(self) -> "b":  # type: ignore
			return True

		@dbus_property(access=PropertyAccess.READ)
		def CanControl(self) -> "b":  # type: ignore
			return True


# --- Websocket Connection Manager ---
class ConnectionManager:
	def __init__(self):
		self.active_connections: list[WebSocket] = []
		self.local_player_ws: WebSocket | None = (
			None  # El cliente que está reproduciendo localmente
		)

	async def connect(self, websocket: WebSocket):
		await websocket.accept()
		self.active_connections.append(websocket)

	def disconnect(self, websocket: WebSocket):
		if websocket in self.active_connections:
			self.active_connections.remove(websocket)
		if self.local_player_ws is websocket:
			self.local_player_ws = None
			logger.info("El cliente reproductor local se desconectó.")

	def claim_local_player(self, websocket: WebSocket) -> bool:
		"""Intenta registrar este WS como el reproductor local. Devuelve True si lo logró."""
		if self.local_player_ws is not None and self.local_player_ws is not websocket:
			return False  # Ya hay otro cliente reproduciendo localmente
		self.local_player_ws = websocket
		logger.info("Nuevo cliente registrado como reproductor local.")
		return True

	def release_local_player(self, websocket: WebSocket):
		if self.local_player_ws is websocket:
			self.local_player_ws = None
			logger.info("Cliente liberó el rol de reproductor local.")

	async def broadcast(self, message: dict):
		log_msg = message.copy()
		if "library" in log_msg:
			log_msg["library"] = (
				f"<Librería omitida del log ({len(log_msg['library'])} temas)>"
			)

		logger.debug(f"AVISANDO A LA MUCHACHADA:\n{highlight_json(log_msg)}")
		for connection in self.active_connections.copy():
			try:
				await connection.send_json(message)
			except Exception:
				self.disconnect(connection)


manager = ConnectionManager()


# --- App State & Server Logic ---
class APIState:
	def __init__(self, initial_dir=None, secondary_dir=None):
		self.current_track = None
		self.dj_carpincho_enabled = False
		self.history = []
		self.id_to_current_path = {}
		self.initial_dir = initial_dir
		self.is_scanning = False
		self.last_broadcast = {}
		self.mpv_paused = False
		self.path_to_id = {}
		self.pause_after_path = None
		self.processing_eof = False
		self.queue = []
		self.secondary_dir = secondary_dir

		# Track state
		self.time_pos = 0
		self.duration = 0
		self.last_time_broadcast = 0

		# Files
		self.track_cache_by_path = {}
		self.tracks_cache = []

		self.url_metadata = {}
		self.volume = 100
		self.server_muted = False
		self.dj_next_track = None  # El tema que el DJ eligió para sonar después
		self.dj_countdown_task = None  # Task del countdown de 10s del DJ (cancelable)
		self.mpv_visible = True

		self.favorites = self._load_favs_from_db()

		self.mpris_bus = None
		self.mpris_root = None
		self.mpris_player = None

		self.mpv = AsyncMpvController(
			{
				"duration_update": self.handle_duration_update,
				"mpv_restarted": self.handle_mpv_restarted,
				"mute_update": self.handle_mute_update,
				"pause_update": self.handle_pause_update,
				"song_ended": self.handle_song_ended,
				"time_update": self.handle_time_update,
				"track_stopped": self.handle_track_stopped,
				"volume_update": self.handle_volume_update,
			}
		)

	def get_full_state_dict(self, include_library=False):
		"""Genera un diccionario con el estado completo actual (creando copias listas/diccionarios)"""
		active_favs = []
		for fav_id in self.favorites:
			if fav_id in self.id_to_current_path:
				active_favs.append(self.id_to_current_path[fav_id])
			else:
				active_favs.append(fav_id)

		d = {
			"current_track": self.current_track,
			"dj_carpincho_enabled": self.dj_carpincho_enabled,
			"dj_next_track": self.dj_next_track,
			"duration": self.duration,
			"favorites": active_favs,
			"history": list(self.history),
			"is_scanning": self.is_scanning,
			"mpv_visible": self.mpv_visible,
			"pause_after_path": self.pause_after_path,
			"paused": self.mpv_paused,
			"queue": list(self.queue),
			"server_muted": self.server_muted,
			"time_pos": self.time_pos,
			"top_played": self.get_top_played(),
			"url_metadata": dict(self.url_metadata),
			"volume": self.volume,
		}
		if include_library:
			d["library"] = list(self.tracks_cache)
		return d

	def notify_mpris(self):
		if self.mpris_player:
			try:
				changed = {}
				new_status = self.mpris_player.PlaybackStatus
				new_meta = self.mpris_player.Metadata
				new_vol = self.mpris_player.Volume

				if getattr(self, "_last_mpris_status", None) != new_status:
					changed["PlaybackStatus"] = new_status
					self._last_mpris_status = new_status

				meta_repr = repr(new_meta)
				if getattr(self, "_last_mpris_meta", None) != meta_repr:
					changed["Metadata"] = new_meta
					self._last_mpris_meta = meta_repr

				if getattr(self, "_last_mpris_vol", None) != new_vol:
					changed["Volume"] = new_vol
					self._last_mpris_vol = new_vol

				if changed:
					self.mpris_player.emit_properties_changed(changed)
			except Exception as e:
				logger.debug(f"Pifió actualizando propiedades MPRIS: {e}")

	def _load_favs_from_db(self):
		try:
			with sqlite3.connect(DB_PATH) as conn:
				c = conn.cursor()
				c.execute("SELECT track_id FROM favorites")
				return [row[0] for row in c.fetchall()]
		except Exception as e:
			logger.error(f"Error cargando favoritos de la DB: {e}")
			return []

	def _register_play_stat(self, path):
		str_path = str(path)
		if not (str_path.startswith("http://") or str_path.startswith("https://")):
			track_id = self.path_to_id.get(str_path, str_path)
			now = time.time()

			try:
				with sqlite3.connect(DB_PATH) as conn:
					# Agregamos la reproducción actual
					conn.execute(
						"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
						(track_id, now),
					)

					# PODA AUTOMÁTICA: Borramos reproducciones de más de 60 días en 1 milisegundo
					# two_months_ago = now - (30 * 24 * 3600 * 2)
					# conn.execute("DELETE FROM play_history WHERE played_at < ?", (two_months_ago,))
					# conn.commit()

				logger.debug(f"Tema completado, sumando +1 al top: {str_path}")
			except Exception as e:
				logger.error(f"Error guardando stat en DB: {e}")

	def _log_url(self, url):
		"""Guarda un registro de los links que sonaron, con su metadata si existe."""
		try:
			meta = self.url_metadata.get(
				url,
				{"display_title": "Link directo", "display_artist": "Desconocido"},
			)
			title = meta.get("title", meta.get("display_title"))
			artist = meta.get("artist", meta.get("display_artist"))
			played_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

			with sqlite3.connect(DB_PATH) as conn:
				# Borramos si existía antes para no duplicar y que vuelva a aparecer arriba
				conn.execute("DELETE FROM url_logs WHERE url = ?", (url,))

				# Insertamos la entrada fresca
				conn.execute(
					"INSERT INTO url_logs (url, title, artist, played_at) VALUES (?, ?, ?, ?)",
					(url, title, artist, played_at),
				)

				# Mantenemos el log cortito (ej: máximo 200 links) para que no sea infinito
				# conn.execute("""
				# 	DELETE FROM url_logs
				# 	WHERE id NOT IN (
				# 		SELECT id FROM url_logs ORDER BY id DESC LIMIT 200
				# 	)
				# """)
				# conn.commit()
		except Exception as e:
			logger.error(f"Error guardando el log de URLs en DB: {e}")

	def scan_directory(self, target_dirs: list):
		logger.info(f"Pegando una ojeada por estas carpetas: {target_dirs}")
		extensions = [
			"*.flac",
			"*.m4a",
			"*.mp3",
			"*.ogg",
			"*.wav",
			"*.mp4",
			"*.mkv",
			"*.avi",
			"*.webm",
		]
		raw_files = []

		for target_dir in target_dirs:
			if not target_dir:
				continue

			music_dir = Path(target_dir).expanduser()
			if not music_dir.exists():
				logger.warning(
					f"Che, este lugar está más pelado que la nada misma: {music_dir}"
				)
				continue

			for ext in extensions:
				raw_files.extend(list(music_dir.rglob(ext)))

		logger.info(
			f"Encontré {len(raw_files)} archivos en total. Revisando cuáles son nuevos o cambiaron..."
		)
		raw_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

		tracks = []
		self.id_to_current_path.clear()
		self.path_to_id.clear()
		new_cache = {}

		for i, f in enumerate(raw_files):
			if i > 0 and i % 100 == 0:
				logger.info(f"Ya procesé la data de {i}/{len(raw_files)} joyitas...")

			file_str = str(f)
			try:
				current_mtime = f.stat().st_mtime
			except Exception:
				continue

			if (
				file_str in self.track_cache_by_path
				and self.track_cache_by_path[file_str]["mtime"] == current_mtime
			):
				track_dict = self.track_cache_by_path[file_str]["data"]
				track_hash = track_dict.get("track_hash")
			else:
				track_obj = Track(f)
				track_dict = track_obj.to_dict()
				track_hash = track_obj.track_hash
				track_dict["track_hash"] = track_hash

			new_cache[file_str] = {"mtime": current_mtime, "data": track_dict}
			tracks.append(track_dict)

			self.id_to_current_path[track_hash] = track_dict["path"]
			self.path_to_id[track_dict["path"]] = track_hash

		self.track_cache_by_path = new_cache

		# Guardamos el diccionario de pistas en la DB para poder hacer JOINs ---
		try:
			with sqlite3.connect(DB_PATH) as conn:
				for t in tracks:
					conn.execute('''
						INSERT OR REPLACE INTO tracks (track_id, path, title, album, artist, duration_str)
						VALUES (?, ?, ?, ?, ?, ?)
					''', (t["track_hash"], t["path"], t["title"], t.get("album", "Desconocido"), t["artist"], t["duration_str"]))
				conn.commit()
		except Exception as e:
			logger.error(f"Error guardando tracks en la DB: {e}")

		logger.info("¡Listo el escaneo, maestro!")
		return tracks

	async def fetch_yt_dlp_metadata(self, url):
		"""Obtiene asincrónicamente la data de yt-dlp y avisa a los clientes"""
		if url in self.url_metadata:
			return

		try:
			logger.info(f"Che yt-dlp, averiguate la data de este link: {url}")
			proc = await asyncio.create_subprocess_exec(
				"yt-dlp",
				"--dump-json",
				"--no-warnings",
				"--no-playlist",
				url,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.DEVNULL,
			)
			stdout, _ = await proc.communicate()

			if stdout:
				data = json.loads(stdout.decode("utf-8"))
				title = data.get("title", "Título Misterioso")
				artist = data.get("uploader", "Artista NN")
				duration = data.get("duration", 0)

				mins = int(duration // 60) if duration else 0
				secs = int(duration % 60) if duration else 0

				self.url_metadata[url] = {
					"path": url,
					"display_title": title,
					"display_artist": artist,
					"album": "Internet",
					"duration_str": f"{mins}:{secs:02d}",
					"search_string": f"{artist} {title}".lower(),
					"title": title,
					"artist": artist,
				}

				self.id_to_current_path[url] = url
				self.path_to_id[url] = url

				logger.info(f"Data fresquita conseguida: {artist} - {title}")
				await broadcast_state()
		except Exception as e:
			logger.error(f"Pifió yt-dlp sacando la info de {url}, se empacó: {e}")

	# Event handlers update the state, which clients will see on their next poll
	async def handle_song_ended(self):
		# Si MPV nos mandó múltiples "canción terminada" al mismo tiempo, los ignoramos
		if getattr(self, "processing_eof", False):
			logger.debug("Ignorando evento EOF concurrente para no sumar puntos doble.")
			return

		self.processing_eof = True
		try:
			if self.current_track:
				self._register_play_stat(self.current_track)
			await self.play_next(skipped_by_user=False)
			await broadcast_state()
		finally:
			self.processing_eof = False

	async def handle_mpv_restarted(self):
		"""Si MPV se muere y revive, le devolvemos la memoria de lo que estaba sonando."""
		if self.current_track:
			logger.info(
				"El MPV revivió. Volviéndole a cargar el temita que estaba sonando..."
			)

			# Volvemos a cargar la pista sin tocar el historial
			await self.mpv._send(
				json.dumps(
					{"command": ["loadfile", str(self.current_track)]},
					ensure_ascii=False,
				)
			)
			# Le devolvemos su estado de pausa y volumen
			await self.mpv._send(
				json.dumps({"command": ["set_property", "pause", self.mpv_paused]})
			)
			await self.mpv._send(
				json.dumps({"command": ["set_property", "volume", self.volume]})
			)
			await self.mpv._send(
				json.dumps({"command": ["set_property", "mute", self.server_muted]})
			)
			if self.time_pos > 0:
				await self.mpv._send(
					json.dumps({"command": ["seek", self.time_pos, "absolute"]})
				)

	async def handle_track_stopped(self):
		# Si cambiamos de tema hace menos de medio segundo,
		# este "stop" es del tema viejo muriendo. Lo ignoramos.
		if time.time() - getattr(self, "last_track_change", 0) < 0.5:
			logger.info(
				"Recibí un 'stop' pero el tema cambió hace menos de 0.5s, asumo que es el viejo muriendo, ignoro."
			)
			return
		self.current_track = None
		self.mpv_paused = False
		self.time_pos = 0
		self.duration = 0
		await broadcast_state()

	async def handle_volume_update(self, vol):
		self.volume = vol
		await broadcast_state()

	async def handle_pause_update(self, paused):
		self.mpv_paused = paused
		await broadcast_state()

	async def handle_time_update(self, pos):
		# Mientras hay un reproductor local activo, el cliente es la fuente de verdad para
		# time_pos. Ignoramos los ticks del MPV para evitar que sobreescriban el valor del
		# cliente y creen jitter en todos los demás clientes.
		if manager.local_player_ws is not None:
			return
		self.time_pos = pos or 0
		now = time.time()
		# Solo triggereamos broadcast cada ~5 seg para no fundir el WebSocket
		if now - self.last_time_broadcast >= 5.0:
			self.last_time_broadcast = now
			await broadcast_state()

	async def handle_duration_update(self, dur):
		# Igual que handle_time_update: el cliente local reporta su propia duración.
		if manager.local_player_ws is not None:
			return
		self.duration = dur or 0
		await broadcast_state()

	async def handle_mute_update(self, is_muted):
		self.server_muted = is_muted
		await broadcast_state()

	async def play_track(self, path):
		# Cancelar el countdown del DJ si el usuario eligió un tema manualmente
		if self.dj_countdown_task and not self.dj_countdown_task.done():
			self.dj_countdown_task.cancel()
			self.dj_countdown_task = None
			logger.info(
				"Countdown del DJ Carpincho cancelado por nueva acción del usuario."
			)

		# Si MPV está cerrado o en coma, lo forzamos a arrancar ANTES de tocar el estado (current_track)
		# Así evitamos que handle_mpv_restarted se maree y mande doble loadfile.
		if not self.mpv.writer and not self.mpv.is_windows:
			await self.mpv.start()

		self.current_track = path
		self.mpv_paused = False
		self.time_pos = 0
		self.last_track_change = time.time()

		str_path = str(path)
		if str_path.startswith("http://") or str_path.startswith("https://"):
			# Si es un link de YouTube o internet, lo mandamos al log especial apenas arranca
			self._log_url(str_path)

		if state.mpv_visible:
			await self.mpv._send('{"command": ["set_property", "force-window", "yes"]}')

		# Usamos json.dumps() con ensure_ascii=False para mandar acentos (ñ, tildes) en crudo y evitar marear a MPV
		cmd_payload = json.dumps(
			{"command": ["loadfile", str_path]}, ensure_ascii=False
		)
		await self.mpv._send(cmd_payload)
		await self.mpv._send(json.dumps({"command": ["set_property", "pause", False]}))

	async def play_next(self, skipped_by_user=False):
		# Si hay un countdown del DJ corriendo en otra task que no sea esta, lo matamos
		if (
			self.dj_countdown_task
			and not self.dj_countdown_task.done()
			and self.dj_countdown_task != asyncio.current_task()
		):
			self.dj_countdown_task.cancel()
			self.dj_countdown_task = None

		just_finished = self.current_track
		if self.current_track:
			self.history.append(self.current_track)
			self.current_track = None

		# Verificamos si tocaba pausar después del track que acaba de terminar
		should_pause = (self.pause_after_path is not None) and (
			just_finished == self.pause_after_path
		)
		if should_pause:
			self.pause_after_path = None

		if self.queue:
			next_path = self.queue.pop(0)
			self.dj_next_track = (
				None  # Limpiamos (si la fila tenía temas, el DJ no pre-eligió)
			)
			await self.play_track(next_path)
			if should_pause:
				self.mpv_paused = True
				await self.mpv._send(
					json.dumps({"command": ["set_property", "pause", True]})
				)
		elif self.dj_carpincho_enabled and self.tracks_cache:
			# Usamos la pre-elección del DJ si existe; sino elegimos ahora
			import random

			if self.dj_next_track:
				chosen = self.dj_next_track
			else:
				played_paths = set(self.history)
				unplayed = [
					t for t in self.tracks_cache if t["path"] not in played_paths
				]
				chosen = random.choice(unplayed) if unplayed else None

			self.dj_next_track = None  # Consumimos la pre-elección

			if chosen:
				logger.info(
					f"🦦 DJ Carpincho salvó las papas con un clásico: {chosen['display_title']} {'(al toque)' if skipped_by_user else '(arranca en 10 segundos...)'}"
				)

				# Durante el countdown mostramos el tema elegido en dj_next_track
				# para que todos los clientes vean qué viene — lo borramos recién cuando arranca.
				self.dj_next_track = chosen
				await broadcast_state()

				if not skipped_by_user:
					# Guardamos el countdown como task cancelable
					self.dj_countdown_task = asyncio.current_task()
					try:
						await self.mpv._send(
							json.dumps({"command": ["set_property", "pause", True]})
						)
						await asyncio.sleep(
							10
						)  # Pausa de 10 segundos antes de que el DJ arranque
						await self.mpv._send(
							json.dumps({"command": ["set_property", "pause", False]})
						)
					except asyncio.CancelledError:
						logger.info(
							"Countdown del DJ cancelado, no se reproduce el tema pre-elegido."
						)
						if self.dj_next_track == chosen:
							self.dj_next_track = None
						return
					finally:
						self.dj_countdown_task = None

				self.dj_next_track = (
					None  # Ahora sí borramos: el tema está por arrancar
				)

				await self.play_track(chosen["path"])
				if should_pause:
					self.mpv_paused = True
					await self.mpv._send(
						json.dumps({"command": ["set_property", "pause", True]})
					)
				# Pre-elegimos el siguiente para el front
				self._pick_dj_next()
				return
			else:
				logger.info("DJ Carpincho se quedó sin temas nuevos esta sesión.")
				self.dj_carpincho_enabled = False
				self.dj_next_track = None
				self.current_track = None
				await self.mpv._send('{"command": ["stop"]}')
				await self.mpv._send(
					'{"command": ["set_property", "force-window", "no"]}'
				)
		else:
			# Sin fila ni DJ: frena
			self.dj_next_track = None
			self.current_track = None
			await self.mpv._send('{"command": ["stop"]}')
			await self.mpv._send('{"command": ["set_property", "force-window", "no"]}')
		self._pick_dj_next()  # Actualiza la preview después de tocar la fila

	async def play_prev(self):
		if self.history:
			prev_path = self.history.pop()
			if self.current_track:
				self.queue.insert(0, self.current_track)
				self.current_track = None
			await self.play_track(prev_path)
		elif self.current_track:
			# Restart the current track from the beginning if there's no history
			await self.play_track(self.current_track)

	def _pick_dj_next(self):
		"""Elige (o limpia) el próximo tema del DJ Carpincho según el estado actual."""
		if self.dj_carpincho_enabled and not self.queue and self.tracks_cache:
			import random

			played_paths = set(self.history)
			if self.current_track:
				played_paths.add(self.current_track)
			unplayed = [t for t in self.tracks_cache if t["path"] not in played_paths]
			if unplayed:
				chosen = random.choice(unplayed)
				self.dj_next_track = chosen
				logger.info(f"🦦 DJ Carpincho pre-eligió: {chosen['display_title']}")
				return
		self.dj_next_track = None

	async def toggle_queue(self, path):
		if path in self.queue:
			self.queue.remove(path)
		else:
			self.queue.append(path)
			if not self.current_track:
				await self.play_next()
				return
		self._pick_dj_next()  # Actualiza la pre-elección del DJ cuando cambia la fila

	async def jump(self, target_type, index):
		if target_type == "queue":
			# Fast-forward to a queued track
			skipped = self.queue[:index]
			if self.current_track:
				self.history.append(self.current_track)
				self.current_track = None
			self.history.extend(skipped)
			self.queue = self.queue[index:]
			await self.play_next(skipped_by_user=True)
		elif target_type == "history":
			# Rewind to a historical track
			rewound = self.history[index + 1 :]
			if self.current_track:
				rewound.append(self.current_track)
				self.current_track = None
			self.queue = rewound + self.queue
			target = self.history[index]
			self.history = self.history[:index]
			await self.play_track(target)

	def get_top_played(self):
		now = time.time()
		two_months_ago = now - (30 * 24 * 3600 * 2)

		try:
			with sqlite3.connect(DB_PATH) as conn:
				c = conn.cursor()
				# SQL hace todo el trabajo pesado: cuenta y ordena los más escuchados
				c.execute(
					"""
					SELECT track_id, COUNT(*) as count
					FROM play_history
					WHERE played_at >= ?
					GROUP BY track_id
					ORDER BY count DESC
					LIMIT 50
				""",
					(two_months_ago,),
				)
				results = c.fetchall()
		except Exception as e:
			logger.error(f"Error calculando el top played: {e}")
			return []

		top_played = []
		for track_id, count in results:
			if "\\" in track_id or "/" in track_id or track_id.startswith("http"):
				current_path = track_id
			else:
				current_path = self.id_to_current_path.get(track_id)

			if current_path and os.path.exists(current_path):
				top_played.append({"path": current_path, "count": count})

		return top_played


# --- FastAPI Setup ---
state = APIState()


async def broadcast_state(include_library=False):
	"""Helper que manda POR WEBSOCKET SOLAMENTE LOS DATOS QUE CAMBIARON"""
	new_state = state.get_full_state_dict(include_library=include_library)

	# Preparamos un diccionario 'diff' con los cambios
	diff = {"type": "state_update"}

	for key, value in new_state.items():
		if state.last_broadcast.get(key) != value:
			diff[key] = value

	# Si diff tiene más cosas que solo "type", mandamos la actualización
	if len(diff) > 1:
		state.last_broadcast = new_state
		await manager.broadcast(diff)
		state.notify_mpris()


@asynccontextmanager
async def lifespan(app: FastAPI):
	state.mpris_registered = False

	if DBUS_AVAILABLE:
		try:
			bus = await MessageBus().connect()
			state.mpris_root = MPRISRoot()
			state.mpris_player = MPRISPlayer(state)
			bus.export("/org/mpris/MediaPlayer2", state.mpris_root)
			bus.export("/org/mpris/MediaPlayer2", state.mpris_player)
			await bus.request_name(
				f"org.mpris.MediaPlayer2.carpincho.instance{os.getpid()}"
			)
			state.mpris_bus = bus
			state.mpris_registered = True
			logger.info(
				"Carpincho registrado en DBus MPRIS. Podés controlarlo con las teclas multimedia."
			)
		except Exception as e:
			logger.warning(
				f"No se pudo registrar DBus MPRIS (quizás corrés sin entorno de escritorio). MPV usará su sistema nativo. Error: {e}"
			)

	# Startup logic - Arrancamos MPV DESPUÉS de saber si DBus funciona para pasarle los flags correctos
	await state.mpv.start()

	# Le metemos un escaneo de fondo para que ya tenga todo cacheado al inicio
	asyncio.create_task(scan_library())

	yield  # Acá el servidor se queda corriendo y escuchando a los clientes

	# Shutdown logic: Todo lo que pasa acá abajo es cuando apretás Ctrl+C
	logger.info("Cerrando el chiringuito. ¡Nos vimos!")
	if state.mpris_bus:
		state.mpris_bus.disconnect()
	await state.mpv.stop()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)


# --- Serving the HTML File ---
@app.get("/")
async def serve_index():
	# Get the absolute directory where server.py is located
	base_dir = Path(__file__).resolve().parent

	html_path = base_dir / "index.html"

	if not html_path.exists():
		return {"error": f"Falta el archivo {html_path}, se me cayó el mate encima"}

	return FileResponse(html_path)


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
	base_dir = Path(__file__).resolve().parent
	favicon_path = base_dir / "favicon.ico"

	if not favicon_path.exists():
		return {"error": f"No encuentro el favicon en {favicon_path}"}

	return FileResponse(favicon_path)


@app.post("/mpv/hide")
async def mpv_hide():
	"""Reinicia MPV con la ventana oculta."""
	state.mpv_visible = False
	logger.info("Reiniciando MPV para ocultar la ventana...")
	await state.mpv.start()  # start() matará el proceso viejo y leerá mpv_visible
	await broadcast_state()
	return {"status": "ok"}


@app.post("/mpv/show")
async def mpv_show():
	"""Reinicia MPV con la ventana visible."""
	state.mpv_visible = True
	logger.info("Reiniciando MPV para mostrar la ventana...")
	await state.mpv.start()  # start() matará el proceso viejo y leerá mpv_visible
	await broadcast_state()
	return {"status": "ok"}


# --- API Routes ---
@app.get("/library")
async def get_library():
	"""Returns the already cached library without triggering a new disk scan."""
	while state.is_scanning:
		await asyncio.sleep(0.5)
	return {"data": state.tracks_cache}


@app.get("/scan")
async def scan_library(dir: str = None, dir2: str = None):
	while state.is_scanning:
		logger.info(
			"Alguien pidió escanear pero ya hay un escaneo en curso, esperando un toque..."
		)
		await asyncio.sleep(0.5)

	target1_raw = dir or state.initial_dir or "~/Music"
	target2_raw = dir2 or state.secondary_dir

	target_dirs = [str(Path(target1_raw).expanduser().resolve())]
	if target2_raw:
		target_dirs.append(str(Path(target2_raw).expanduser().resolve()))

	logger.info(
		f"Escaneando {target_dirs} (Aprovechando el caché inteligente por archivo)..."
	)

	# Prendemos el "Cargando" y le avisamos al front
	state.is_scanning = True
	await broadcast_state()

	# Guardamos el tamaño anterior para detectar cambios
	prev_count = len(state.tracks_cache)

	# Hacemos el trabajo pesado
	state.tracks_cache = await asyncio.to_thread(state.scan_directory, target_dirs)

	# Si la librería cambió, la incluimos en el broadcast para que todos los clientes la actualicen sin hacer un GET /library
	library_changed = len(state.tracks_cache) != prev_count
	state.is_scanning = False
	await broadcast_state(include_library=library_changed)

	return {"data": state.tracks_cache}


@app.get("/cover")
async def serve_cover(path: str = Query(...)):
	try:
		# Extraemos los metadatos completos con Mutagen
		audio = MutagenFile(path)
		if not audio:
			return Response(status_code=404)

		cover_data = None
		mime_type = "image/jpeg"

		# Magia negra para sacar la tapa según el formato (FLAC, MP3 o M4A)
		if hasattr(audio, "pictures") and audio.pictures:
			cover_data = audio.pictures[0].data
			mime_type = audio.pictures[0].mime
		elif hasattr(audio, "tags") and audio.tags:
			for key, tag in audio.tags.items():
				if key.startswith("APIC"):  # MP3 ID3 Tag
					cover_data = tag.data
					mime_type = tag.mime
					break
			if not cover_data and "covr" in audio.tags:  # M4A Tag
				cover_data = audio.tags["covr"][0]
				mime_type = (
					"image/jpeg" if cover_data.startswith(b"\xff\xd8") else "image/png"
				)

		if cover_data:
			return Response(content=cover_data, media_type=mime_type)
	except Exception as e:
		logger.debug(f"Pifió sacando la tapa de {path}: {e}")

	return Response(status_code=404)


@app.get("/stream")
async def stream_audio(path: str = Query(...)):
	"""Endpoint para mandarle la música al navegador del cliente si quiere escuchar ahí."""
	# Validar que el path exista en nuestra librería para no servir archivos confidenciales
	if path not in state.path_to_id and not any(
		t["path"] == path for t in state.tracks_cache
	):
		return Response(status_code=404)
	# FileResponse en Starlette maneja encabezados 'Range' si el browser los pide
	return FileResponse(path)


@app.get("/lrc")
async def serve_lrc(path: str = Query(...)):
	"""Sirve el archivo .lrc local si existe junto a la pista original."""
	if path not in state.path_to_id and not any(
		t["path"] == path for t in state.tracks_cache
	):
		return Response(status_code=404)

	lrc_path = Path(path).with_suffix(".lrc")

	if not lrc_path.exists():
		return Response(status_code=404)

	return FileResponse(lrc_path, media_type="text/plain")


class CommandRequest(BaseModel):
	cmd: str
	path: str = None
	type: str = None
	index: int = None
	vollevel: int = None
	new_index: int = None
	amount: float = None
	state: bool = None


@app.post("/command")
async def handle_command(req: CommandRequest):
	logger.info(f"LLEGÓ COMANDO: {req.cmd} | Path: {req.path} | Index: {req.index}")

	cmd = req.cmd

	if cmd == "play":
		if state.current_track:
			state.history.append(state.current_track)
			state.current_track = None
		await state.play_track(req.path)
	elif cmd == "pause":
		if not state.current_track and state.queue:
			# Si no hay tema sonando pero hay fila, arranca la joda
			await state.play_next(skipped_by_user=True)
		else:
			# Comportamiento normal: pausa o despausa el tema actual
			state.mpv_paused = not state.mpv_paused
			cmd_payload = json.dumps(
				{"command": ["set_property", "pause", state.mpv_paused]}
			)
			await state.mpv._send(cmd_payload)
	elif cmd == "skip":
		await state.play_next(skipped_by_user=True)
	elif cmd == "prev":
		await state.play_prev()
	elif cmd == "stop":
		if state.current_track:
			state.history.append(state.current_track)
			state.current_track = None
		state.mpv_paused = False
		state.dj_carpincho_enabled = False
		state.time_pos = 0
		await state.mpv._send('{"command": ["stop"]}')
		await state.mpv._send('{"command": ["set_property", "force-window", "no"]}')
	elif cmd == "clear_queue":
		state.queue.clear()
		state.history.clear()
	elif cmd == "vol_up":
		state.volume = min(110, state.volume + 5)
		cmd_payload = json.dumps({"command": ["set_property", "volume", state.volume]})
		await state.mpv._send(cmd_payload)
	elif cmd == "vol_down":
		state.volume = max(0, state.volume - 5)
		cmd_payload = json.dumps({"command": ["set_property", "volume", state.volume]})
		await state.mpv._send(cmd_payload)
	elif cmd == "set_volume":
		if req.vollevel is not None:
			state.volume = max(0, min(110, req.vollevel))
			cmd_payload = json.dumps(
				{"command": ["set_property", "volume", state.volume]}
			)
			await state.mpv._send(cmd_payload)
	elif cmd == "set_mute":
		if req.state is not None:
			state.server_muted = req.state
			cmd_payload = json.dumps(
				{"command": ["set_property", "mute", state.server_muted]}
			)
			await state.mpv._send(cmd_payload)
	elif cmd == "fullscreen":
		await state.mpv._send('{"command": ["cycle", "fullscreen"]}')
	elif cmd == "toggle_queue":
		await state.toggle_queue(req.path)
	elif cmd == "add_url":
		if req.path:
			state.queue.append(req.path)
			state._pick_dj_next()
			if not state.current_track:
				await state.play_next(skipped_by_user=True)
			asyncio.create_task(state.fetch_yt_dlp_metadata(req.path))
	elif cmd == "jump":
		await state.jump(req.type, req.index)
	elif cmd == "seek":
		if req.amount is not None:
			if manager.local_player_ws is not None:
				# Hay un reproductor local activo — le mandamos el seek relativo
				await manager.local_player_ws.send_json(
					{
						"type": "local_player_seek",
						"mode": "relative",
						"amount": req.amount,
					}
				)
			else:
				cmd_payload = json.dumps({"command": ["seek", req.amount]})
				await state.mpv._send(cmd_payload)
	elif cmd == "seek_absolute":
		if req.amount is not None:
			if manager.local_player_ws is not None:
				# Hay un reproductor local activo — le mandamos el seek absoluto directamente
				await manager.local_player_ws.send_json(
					{
						"type": "local_player_seek",
						"mode": "absolute",
						"amount": req.amount,
					}
				)
				# También buscamos en MPV para mantenerlo en sincronía
				await state.mpv._send(
					json.dumps({"command": ["seek", req.amount, "absolute"]})
				)
				state.time_pos = req.amount
			else:
				cmd_payload = json.dumps({"command": ["seek", req.amount, "absolute"]})
				await state.mpv._send(cmd_payload)
	elif cmd == "toggle_favorite":
		if req.path:
			track_id = state.path_to_id.get(req.path, req.path)
			try:
				with sqlite3.connect(DB_PATH) as conn:
					if track_id in state.favorites:
						state.favorites.remove(track_id)
						conn.execute(
							"DELETE FROM favorites WHERE track_id = ?", (track_id,)
						)
					else:
						state.favorites.append(track_id)
						conn.execute(
							"INSERT OR IGNORE INTO favorites (track_id) VALUES (?)",
							(track_id,),
						)
					conn.commit()
			except Exception as e:
				logger.error(f"Error guardando favorito: {e}")
	elif cmd == "toggle_dj_carpincho":
		state.dj_carpincho_enabled = not state.dj_carpincho_enabled
		logger.info(f"DJ Carpincho cambiado a: {state.dj_carpincho_enabled}")
		if state.dj_carpincho_enabled and not state.current_track:
			logger.info(
				"DJ Carpincho se activó y no hay tema sonando, arrancando la música..."
			)
			await state.play_next(skipped_by_user=True)
		else:
			state._pick_dj_next()  # Actualiza (o limpia) la pre-elección inmediatamente
	elif cmd == "pause_after":
		state.pause_after_path = req.path
	elif cmd == "remove_history_item":
		if req.index is not None and 0 <= req.index < len(state.history):
			state.history.pop(req.index)
	elif cmd == "remove_queue_item":
		if req.index is not None and 0 <= req.index < len(state.queue):
			state.queue.pop(req.index)
			state._pick_dj_next()
	elif cmd == "move_queue_item":
		if req.index is not None and req.new_index is not None:
			if 0 <= req.index < len(state.queue) and 0 <= req.new_index < len(
				state.queue
			):
				item = state.queue.pop(req.index)
				state.queue.insert(req.new_index, item)
			state._pick_dj_next()

	# Notify clients of state change
	await broadcast_state()
	return {"status": "ok"}


# --- Websocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
	client_host = websocket.client.host if websocket.client else "un fantasma"
	logger.info(f"NUEVO CLIENTE: Cayó alguien desde {client_host}")

	await manager.connect(websocket)
	try:
		# Send initial state immediately (full state needed for fresh clients), including the library
		full_state = state.get_full_state_dict(include_library=False)
		full_state["type"] = "state_update"
		await websocket.send_json(full_state)

		while True:
			raw = await websocket.receive_text()
			try:
				msg = json.loads(raw)
			except json.JSONDecodeError:
				logger.debug(f"WS mensaje no-JSON de {client_host}: {raw}")
				continue

			msg_type = msg.get("type")

			if msg_type == "local_player_claim":
				# El cliente quiere convertirse en el reproductor local
				ok = manager.claim_local_player(websocket)
				await websocket.send_json(
					{"type": "local_player_claim_result", "ok": ok}
				)
				if not ok:
					logger.info(
						f"Rechazamos solicitud de reproductor local de {client_host}: ya hay otro."
					)

			elif msg_type == "local_player_release":
				# El cliente deja de reproducir localmente
				manager.release_local_player(websocket)

			elif (
				msg_type == "local_player_update"
				and manager.local_player_ws is websocket
			):
				# El reproductor local nos manda su estado — lo aplicamos al estado global
				# y lo rebroadcasteamos a todos sin mandárselo al MPV.
				changed = False

				if "time_pos" in msg:
					new_pos = msg["time_pos"]
					state.time_pos = new_pos or 0
					now = time.time()
					# Seguimos al cliente: MPV sigue la posición del reproductor local.
					# El cliente manda actualizaciones cada ~5s, así que el seek es infrecuente
					# y MPV (que está mutado) no produce ningún glitch audible al recibir el seek.
					await state.mpv._send(
						json.dumps({"command": ["seek", new_pos, "absolute"]})
					)
					if now - state.last_time_broadcast >= 5.0:
						state.last_time_broadcast = now
						changed = True

				if "duration" in msg and msg["duration"] != state.duration:
					state.duration = msg["duration"] or 0
					changed = True

				if "paused" in msg and msg["paused"] != state.mpv_paused:
					state.mpv_paused = msg["paused"]
					changed = True

				if msg.get("song_ended"):
					# La canción terminó en el browser — avanzamos la fila igual que cuando termina en MPV
					logger.info(
						"El reproductor local avisó que terminó la canción. Avanzando fila..."
					)
					if state.current_track:
						state._register_play_stat(state.current_track)
					await state.play_next(skipped_by_user=False)
					await broadcast_state()
					continue  # play_next ya hizo broadcast, no hace falta otro

				if changed:
					await broadcast_state()

			else:
				logger.debug(f"WS Mensajito de {client_host}: {raw}")

	except WebSocketDisconnect:
		logger.info(
			f"CLIENTE DESCONECTADO: Se nos fue {client_host}, se habrá quedado sin agua en el termo."
		)
		manager.disconnect(websocket)


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--host", type=str, default="0.0.0.0")
	parser.add_argument("--port", type=int, default=9696)
	parser.add_argument("--dir", type=str, default=None)
	parser.add_argument("--dir2", type=str, default=None)
	args = parser.parse_args()

	if args.dir:
		state.initial_dir = args.dir
	if args.dir2:
		state.secondary_dir = args.dir2

	uvicorn.run(app, host=args.host, port=args.port)
