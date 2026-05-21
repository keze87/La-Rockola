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

	for module, fix in python_deps.items():
		if importlib.util.find_spec(module) is None:
			missing_python.append((module, fix))

	missing_system = []
	# Determine OS for OS-specific system binary hints
	is_win = sys.platform == "win32"
	is_mac = sys.platform == "darwin"

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
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile
from pathlib import Path
from pydantic import BaseModel

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
				"--sub-color=#FF00FF",
				"--sub-font-size=100",
				"--sub-font=Pacifico",
				"--sub-scale-by-window=no",
				"--sub-scale-with-window=no",
				"--ytdl-raw-options=no-playlist=",
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
				await self._send(json.dumps({"command": ["observe_property", 1, "volume"]}))
				await self._send(json.dumps({"command": ["observe_property", 2, "pause"]}))

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
		logger.debug("El socket Unix de MPV se cerró. Limpiando conexión para forzar reinicio...")
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
		except json.JSONDecodeError:
			pass

	async def _send(self, cmd_payload: str):
		logger.debug(f"Tirándole comando al MPV: \n {highlight_json(cmd_payload)}")
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


# --- Websocket Connection Manager ---
class ConnectionManager:
	def __init__(self):
		self.active_connections: list[WebSocket] = []

	async def connect(self, websocket: WebSocket):
		await websocket.accept()
		self.active_connections.append(websocket)

	def disconnect(self, websocket: WebSocket):
		if websocket in self.active_connections:
			self.active_connections.remove(websocket)

	async def broadcast(self, message: dict):
		logger.debug(f"AVISANDO A LA MUCHACHADA:\n{highlight_json(message)}")
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
		self.stats_file = Path.home() / ".carpincho_stats.json"
		self.track_cache_by_path = {}
		self.tracks_cache = []
		self.url_log_file = Path.home() / ".carpincho_urls.json"
		self.url_metadata = {}
		self.volume = 100

		self.play_history = self._load_stats()
		self.mpv = AsyncMpvController(
			{
				"song_ended": self.handle_song_ended,
				"track_stopped": self.handle_track_stopped,
				"volume_update": self.handle_volume_update,
				"pause_update": self.handle_pause_update,
				"mpv_restarted": self.handle_mpv_restarted,
			}
		)

	def get_full_state_dict(self):
		"""Genera un diccionario con el estado completo actual (creando copias listas/diccionarios)"""
		return {
			"current_track": self.current_track,
			"dj_carpincho_enabled": self.dj_carpincho_enabled,
			"history": list(self.history),
			"is_scanning": self.is_scanning,
			"paused": self.mpv_paused,
			"pause_after_path": self.pause_after_path,
			"queue": list(self.queue),
			"top_played": self.get_top_played(),
			"url_metadata": dict(self.url_metadata),
			"volume": self.volume,
		}

	def _load_stats(self):
		try:
			if os.path.exists(self.stats_file):
				with open(self.stats_file, "r", encoding="utf-8") as f:
					return json.load(f)
		except Exception as e:
			logger.error(f"Error cargando la memoria del carpincho: {e}")
		return {}

	def _save_stats(self):
		try:
			with open(self.stats_file, "w", encoding="utf-8") as f:
				json.dump(self.play_history, f)
		except Exception as e:
			logger.error(f"Error guardando los stats: {e}")

	def _log_url(self, url):
		"""Guarda un registro de los links que sonaron, con su metadata si existe."""
		try:
			logs = []
			if self.url_log_file.exists():
				with open(self.url_log_file, "r", encoding="utf-8") as f:
					try:
						logs = json.load(f)
					except json.JSONDecodeError:
						pass

			# Filtramos la lista para sacar el link si ya estaba guardado antes
			# (así evitamos duplicados y la nueva entrada queda al final con fecha fresca)
			logs = [log for log in logs if log.get("url") != url]

			# Rescatamos la metadata que haya sacado yt-dlp
			meta = self.url_metadata.get(
				url,
				{"path": url, "display_title": "Link directo", "artist": "Desconocido"},
			)

			log_entry = {
				"played_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
				"url": url,
				"title": meta.get("title", meta.get("display_title")),
				"artist": meta.get("artist", meta.get("display_artist")),
			}

			logs.append(log_entry)

			with open(self.url_log_file, "w", encoding="utf-8") as f:
				json.dump(logs, f, indent=4, ensure_ascii=False)
		except Exception as e:
			logger.error(f"Error guardando el log de URLs: {e}")

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
			await self.play_next()
			await broadcast_state()
		finally:
			self.processing_eof = False

	def _register_play_stat(self, path):
		str_path = str(path)
		if not (str_path.startswith("http://") or str_path.startswith("https://")):
			track_id = self.path_to_id.get(str_path, str_path)
			if track_id not in self.play_history:
				self.play_history[track_id] = []
			self.play_history[track_id].append(time.time())
			self._save_stats()
			logger.debug(f"Tema completado, sumando +1 al top: {str_path}")

	async def handle_mpv_restarted(self):
		"""Si MPV se muere y revive, le devolvemos la memoria de lo que estaba sonando."""
		if self.current_track:
			logger.info(
				"El MPV revivió. Volviéndole a cargar el temita que estaba sonando..."
			)

			# Volvemos a cargar la pista sin tocar el historial
			await self.mpv._send(
				json.dumps({"command": ["loadfile", str(self.current_track)]}, ensure_ascii=False)
			)
			# Le devolvemos su estado de pausa y volumen
			await self.mpv._send(
				json.dumps({"command": ["set_property", "pause", self.mpv_paused]})
			)
			await self.mpv._send(
				json.dumps({"command": ["set_property", "volume", self.volume]})
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
		await broadcast_state()

	async def handle_volume_update(self, vol):
		self.volume = vol
		await broadcast_state()

	async def handle_pause_update(self, paused):
		self.mpv_paused = paused
		await broadcast_state()

	async def play_track(self, path):
		# Si MPV está cerrado o en coma, lo forzamos a arrancar ANTES de tocar el estado (current_track)
		# Así evitamos que handle_mpv_restarted se maree y mande doble loadfile.
		if not self.mpv.writer and not self.mpv.is_windows:
			await self.mpv.start()

		self.current_track = path
		self.mpv_paused = False
		self.last_track_change = time.time()

		str_path = str(path)
		if str_path.startswith("http://") or str_path.startswith("https://"):
			# Si es un link de YouTube o internet, lo mandamos al log especial apenas arranca
			self._log_url(str_path)

		await self.mpv._send('{"command": ["set_property", "force-window", "yes"]}')

		# Usamos json.dumps() con ensure_ascii=False para mandar acentos (ñ, tildes) en crudo y evitar marear a MPV
		cmd_payload = json.dumps({"command": ["loadfile", str_path]}, ensure_ascii=False)
		await self.mpv._send(cmd_payload)
		await self.mpv._send(json.dumps({"command": ["set_property", "pause", False]}))

	async def play_next(self):
		just_finished = self.current_track
		if self.current_track:
			self.history.append(self.current_track)
			self.current_track = None

		# Verificamos si tocaba pausar después del track que acaba de terminar
		should_pause = (self.pause_after_path is not None) and (just_finished == self.pause_after_path)
		if should_pause:
			self.pause_after_path = None

		if self.queue:
			next_path = self.queue.pop(0)
			await self.play_track(next_path)
			if should_pause:
				self.mpv_paused = True
				await self.mpv._send(json.dumps({"command": ["set_property", "pause", True]}))
		else:
			# --- AUTOMATIZACIÓN DEL DJ CARPINCHO ---
			if self.dj_carpincho_enabled and state.tracks_cache:
				import random

				# Filtramos la biblioteca quedándonos solo con temas invictos
				played_paths = set(self.history)
				unplayed = [
					t for t in state.tracks_cache if t["path"] not in played_paths
				]

				if unplayed:
					chosen = random.choice(unplayed)
					logger.info(
						f"🦦 DJ Carpincho salvó las papas con un clásico: {chosen['display_title']}"
					)
					await self.play_track(chosen["path"])
					if should_pause:
						self.mpv_paused = True
						await self.mpv._send(json.dumps({"command": ["set_property", "pause", True]}))
					return  # Salimos temprano porque ya pusimos a sonar música
				else:
					logger.info("DJ Carpincho se quedó sin temas nuevos esta sesión.")
					self.dj_carpincho_enabled = False

			# Si el DJ está apagado o no hay más temas, frena el reproductor de forma normal
			self.current_track = None
			await self.mpv._send('{"command": ["stop"]}')
			await self.mpv._send('{"command": ["set_property", "force-window", "no"]}')

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

	async def toggle_queue(self, path):
		if path in self.queue:
			self.queue.remove(path)
		else:
			self.queue.append(path)
			if not self.current_track:
				await self.play_next()

	async def jump(self, target_type, index):
		if target_type == "queue":
			# Fast-forward to a queued track
			skipped = self.queue[:index]
			if self.current_track:
				self.history.append(self.current_track)
				self.current_track = None
			self.history.extend(skipped)
			self.queue = self.queue[index:]
			await self.play_next()
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
		one_month_ago = now - (30 * 24 * 3600)
		monthly_counts = {}

		for track_id, timestamps in self.play_history.items():
			recent_plays = [ts for ts in timestamps if ts >= one_month_ago]
			if recent_plays:
				# Mantenemos compatibilidad con el historial viejo (rutas) o URLs
				if "\\" in track_id or "/" in track_id or track_id.startswith("http"):
					current_path = track_id
				else:
					current_path = self.id_to_current_path.get(track_id)

				if current_path and os.path.exists(current_path):
					monthly_counts[current_path] = len(recent_plays)

		return sorted(
			[{"path": k, "count": v} for k, v in monthly_counts.items()],
			key=lambda x: x["count"],
			reverse=True,
		)[:20]


# --- FastAPI Setup ---
state = APIState()


async def broadcast_state():
	"""Helper que manda POR WEBSOCKET SOLAMENTE LOS DATOS QUE CAMBIARON"""
	new_state = state.get_full_state_dict()

	# Preparamos un diccionario 'diff' con los cambios
	diff = {"type": "state_update"}

	for key, value in new_state.items():
		if state.last_broadcast.get(key) != value:
			diff[key] = value

	# Si diff tiene más cosas que solo "type", mandamos la actualización
	if len(diff) > 1:
		state.last_broadcast = new_state
		await manager.broadcast(diff)


@asynccontextmanager
async def lifespan(app: FastAPI):
	# Startup logic
	await state.mpv.start()
	# Le metemos un escaneo de fondo para que ya tenga todo cacheado al inicio
	asyncio.create_task(scan_library())

	yield  # Acá el servidor se queda corriendo y escuchando a los clientes

	# Shutdown logic: Todo lo que pasa acá abajo es cuando apretás Ctrl+C
	logger.info("Cerrando el chiringuito. ¡Nos vimos!")
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

	# Hacemos el trabajo pesado
	state.tracks_cache = await asyncio.to_thread(state.scan_directory, target_dirs)

	# Apagamos el "Cargando" y le avisamos al front
	state.is_scanning = False
	await broadcast_state()

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


class CommandRequest(BaseModel):
	cmd: str
	path: str = None
	type: str = None
	index: int = None
	vollevel: int = None
	new_index: int = None
	amount: int = None


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
			await state.play_next()
		else:
			# Comportamiento normal: pausa o despausa el tema actual
			state.mpv_paused = not state.mpv_paused
			cmd_payload = json.dumps(
				{"command": ["set_property", "pause", state.mpv_paused]}
			)
			await state.mpv._send(cmd_payload)
	elif cmd == "skip":
		await state.play_next()
	elif cmd == "prev":
		await state.play_prev()
	elif cmd == "stop":
		if state.current_track:
			state.history.append(state.current_track)
			state.current_track = None
		state.mpv_paused = False
		state.dj_carpincho_enabled = False
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
	elif cmd == "fullscreen":
		await state.mpv._send('{"command": ["cycle", "fullscreen"]}')
	elif cmd == "toggle_queue":
		await state.toggle_queue(req.path)
	elif cmd == "add_url":
		if req.path:
			state.queue.append(req.path)
			if not state.current_track:
				await state.play_next()
			asyncio.create_task(state.fetch_yt_dlp_metadata(req.path))
	elif cmd == "remove_queue_item":
		if req.index is not None and 0 <= req.index < len(state.queue):
			state.queue.pop(req.index)
	elif cmd == "move_queue_item":
		if req.index is not None and req.new_index is not None:
			if 0 <= req.index < len(state.queue) and 0 <= req.new_index < len(
				state.queue
			):
				# Saca el tema de su lugar viejo y lo mete en el nuevo
				item = state.queue.pop(req.index)
				state.queue.insert(req.new_index, item)
	elif cmd == "jump":
		await state.jump(req.type, req.index)
	elif cmd == "seek":
		if req.amount is not None:
			cmd_payload = json.dumps({"command": ["seek", req.amount]})
			await state.mpv._send(cmd_payload)
	elif cmd == "toggle_dj_carpincho":
		state.dj_carpincho_enabled = not state.dj_carpincho_enabled
		logger.info(f"DJ Carpincho cambiado a: {state.dj_carpincho_enabled}")
		if state.dj_carpincho_enabled and not state.current_track:
			logger.info(
				"DJ Carpincho se activó y no hay tema sonando, arrancando la música..."
			)
			await state.play_next()
	elif cmd == "pause_after":
		state.pause_after_path = req.path
	elif cmd == "remove_history_item":
		if req.index is not None and 0 <= req.index < len(state.history):
			state.history.pop(req.index)

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
		# Send initial state immediately (full state needed for fresh clients)
		full_state = state.get_full_state_dict()
		full_state["type"] = "state_update"
		await websocket.send_json(full_state)

		while True:
			# Keep connection alive, listen for text but we don't process incoming WS cmds currently
			data = await websocket.receive_text()
			logger.debug(f"WS Mensajito de {client_host}: {data}")
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
