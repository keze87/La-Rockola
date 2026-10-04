"""
AsyncMpvController: controlador asíncrono del reproductor MPV mediante IPC.
Soporta sockets Unix en Linux/macOS y Named Pipes en Windows con reconexión robusta.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from app.engine.audio_analysis import find_binary, get_clean_env

logger = logging.getLogger("RockolaCarpincho")


def _srv(name: str, fallback: Any = None) -> Any:
	"""Resuelve símbolos dinámicos desde server.py para soportar monkeypatching en tests."""
	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, name):
		return getattr(srv, name)
	return fallback


def ensure_display_env(env: dict[str, str]) -> None:
	"""Asegura variables mínimas de display para que MPV no falle en sesiones gráficas."""
	if sys.platform != "win32":
		if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
			# Modo headless sin display gráfico
			pass


class AsyncMpvController:
	"""Maneja el ciclo de vida del proceso MPV y la comunicación IPC bidireccional."""

	def __init__(
		self,
		callbacks: dict[str, Callable[..., Any]] | None = None,
		ipc_path: str | None = None,
		on_property_change: Callable[..., Any] | None = None,
		on_event: Callable[..., Any] | None = None,
		on_process_exit: Callable[..., Any] | None = None,
	) -> None:
		self.process: asyncio.subprocess.Process | None = None
		self.socket_path: str | None = ipc_path
		self.reader: asyncio.StreamReader | None = None
		self.writer: asyncio.StreamWriter | None = None
		self.is_windows = sys.platform == "win32"
		self.has_display = True
		self.callbacks = callbacks or {}
		if on_property_change:
			self.callbacks["property_change"] = on_property_change
		if on_event:
			self.callbacks["event"] = on_event
		if on_process_exit:
			self.callbacks["process_exit"] = on_process_exit

		self._start_lock = asyncio.Lock()

	@property
	def ipc_path(self) -> str | None:
		"""Ruta del socket o Named Pipe de IPC."""
		return self.socket_path

	@property
	def is_running(self) -> bool:
		"""Indica si el proceso de MPV se encuentra activo y respondiendo."""
		return self.process is not None and self.process.returncode is None

	async def stop(self) -> None:
		"""Finaliza el proceso de MPV de manera limpia y libera recursos de IPC."""
		if self.process and self.process.returncode is None:
			logger.info("Mandando a dormir al MPV...")
			try:
				self.process.kill()
				await asyncio.wait_for(self.process.wait(), timeout=1.0)
			except (TimeoutError, ProcessLookupError, OSError):
				pass
		self.process = None
		self.reader = None
		self.writer = None

	def _check_windows_pipe(self) -> bool:
		"""Verifica si el named pipe de Windows ya está disponible."""
		if not self.socket_path:
			return False
		try:
			with open(self.socket_path, "r+b"):
				return True
		except OSError:
			return False

	async def _check_and_raise_mpv_error(self) -> None:
		"""Chequea si MPV murió de entrada y levanta una excepción con la salida de stderr."""
		if self.process and self.process.returncode is not None:
			err_msg = ""
			if self.process.stderr:
				try:
					raw_err = await self.process.stderr.read()
					err_msg = raw_err.decode("utf-8", errors="replace").strip()
				except Exception:
					pass
			logger.error(
				f"MPV finalizó inesperadamente con código {self.process.returncode}. Detalle: {err_msg or 'Sin salida'}"
			)
			raise RuntimeError(
				f"MPV falló al iniciar (código {self.process.returncode}): {err_msg or 'proceso terminado'}"
			)

	async def start(self, is_restart: bool = False, state_ref: Any = None) -> None:
		"""Inicia el proceso MPV y establece la conexión IPC."""
		if self._start_lock.locked():
			async with self._start_lock:
				return

		async with self._start_lock:
			await self.stop()

			clean_env_fn = _srv("get_clean_env", get_clean_env)
			ensure_disp_fn = _srv("ensure_display_env", ensure_display_env)
			env = clean_env_fn()
			ensure_disp_fn(env)

			if self.socket_path is None:
				if self.is_windows:
					self.socket_path = rf"\\.\pipe\mpv_server_{id(self)}"
				else:
					tmp_dir = os.environ.get("TMPDIR", "/tmp")
					self.socket_path = os.path.join(tmp_dir, f"mpv_server_{id(self)}.sock")

			if not self.is_windows and os.path.exists(self.socket_path):
				try:
					os.remove(self.socket_path)
				except OSError:
					pass

			logger.info(f"Armando el socket de MPV en {self.socket_path}...")

			has_display = bool(self.is_windows or env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))
			self.has_display = has_display

			show_window = True
			if state_ref and hasattr(state_ref, "mpv_visible"):
				show_window = state_ref.mpv_visible

			srv_logger = _srv("logger", logger)
			is_debug = srv_logger.isEnabledFor(logging.DEBUG)
			finder = _srv("find_binary", find_binary)
			mpv_bin = finder("mpv") or "mpv"

			mpv_args = [mpv_bin, "--idle"]
			if not is_debug:
				mpv_args.append("--quiet")
			else:
				mpv_args.extend(["--terminal=yes", "--msg-level=all=v"])

			mpv_args.extend(
				[
					"--script-opts=osc-visibility=always,osc-layout=topbar",
					"--ytdl-raw-options=no-playlist=",
					f"--input-ipc-server={self.socket_path}",
				]
			)

			if show_window and has_display:
				mpv_args.extend(
					[
						"--autofit=33%x33%",
						"--geometry=-20-40",
						"--hwdec=auto",
						"--no-border",
						"--ontop",
						"--sub-scale-by-window=no",
						"--sub-scale-with-window=no",
					]
				)
				if not self.is_windows:
					mpv_args.extend(["--gpu-context=waylandvk,wayland,x11vk,x11egl,x11", "--vo=gpu-next,gpu,null"])
				else:
					mpv_args.append("--vo=gpu-next,gpu,null")
			else:
				mpv_args.extend(["--vo=null", "--no-audio-display", "--force-window=no"])

			ytdlp_bin = finder("yt-dlp")
			if ytdlp_bin:
				mpv_args.append(f"--script-opts-append=ytdl_hook-ytdl_path={ytdlp_bin}")

			logger.info("Despertando al carpincho reproductor (MPV)...")
			try:
				self.process = await asyncio.create_subprocess_exec(
					*mpv_args,
					stdin=asyncio.subprocess.DEVNULL,
					stdout=asyncio.subprocess.PIPE if is_debug else asyncio.subprocess.DEVNULL,
					stderr=asyncio.subprocess.PIPE,
					env=env,
				)
			except Exception as e:
				logger.error(f"¡Uy! No se encontró a MPV instalado o falló al ejecutar: {e}")
				sys.exit(1)

			for _ in range(20):
				await self._check_and_raise_mpv_error()
				if self.is_windows:
					if await asyncio.to_thread(self._check_windows_pipe):
						break
				elif os.path.exists(self.socket_path):
					break
				await asyncio.sleep(0.3)

			await self._check_and_raise_mpv_error()

			if not self.is_windows and not os.path.exists(self.socket_path):
				raise RuntimeError("MPV se quedó dormido y no armó el socket a tiempo.")

			if self.process and self.process.stdout:
				asyncio.create_task(self._drain_stdout())
			if self.process and self.process.stderr:
				asyncio.create_task(self._drain_stderr())

			if self.is_windows:
				logger.info("Conectados al Named Pipe de Windows.")
				asyncio.create_task(self._read_ipc_events_windows())
			else:
				self.reader, self.writer = await asyncio.open_unix_connection(self.socket_path)
				logger.info("Conectados al socket Unix de MPV.")
				asyncio.create_task(self._read_ipc_events())

			if not self.is_windows:
				await self._send(json.dumps({"command": ["observe_property", 1, "volume"]}))
				await self._send(json.dumps({"command": ["observe_property", 2, "pause"]}))
				await self._send(json.dumps({"command": ["observe_property", 3, "time-pos"]}))
				await self._send(json.dumps({"command": ["observe_property", 4, "duration"]}))
				await self._send(json.dumps({"command": ["observe_property", 5, "mute"]}))

			if is_restart and "mpv_restarted" in self.callbacks:
				asyncio.create_task(self.callbacks["mpv_restarted"]())

	async def _drain_stdout(self) -> None:
		try:
			while self.process and self.process.returncode is None and self.process.stdout:
				line = await self.process.stdout.readline()
				if not line:
					break
				decoded = line.decode("utf-8", errors="replace").rstrip()
				if decoded:
					logger.debug(f"[MPV stdout] {decoded}")
		except Exception:
			pass

	async def _drain_stderr(self) -> None:
		try:
			while self.process and self.process.returncode is None and self.process.stderr:
				line = await self.process.stderr.readline()
				if not line:
					break
				decoded = line.decode("utf-8", errors="replace").rstrip()
				if decoded:
					logger.debug(f"[MPV stderr] {decoded}")
		except Exception:
			pass

	async def _read_ipc_events_windows(self) -> None:
		main_loop = asyncio.get_running_loop()

		def read_pipe():
			try:
				with open(self.socket_path, "r+b") as pipe:
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
						asyncio.run_coroutine_threadsafe(self._process_event_line(line), main_loop)
			except Exception as e:
				logger.debug(f"Pifió algo leyendo la pipa en Windows: {e}")

		aio = _srv("asyncio", asyncio)
		await aio.to_thread(read_pipe)

	async def _read_ipc_events(self) -> None:
		while self.reader:
			try:
				line = await self.reader.readline()
				if not line:
					break
				await self._process_event_line(line)
			except Exception as e:
				logger.debug(f"Pifió algo leyendo IPC de MPV: {e}")
				break

		logger.debug("El socket Unix de MPV se cerró.")
		self.reader = None
		if self.writer:
			self.writer.close()
			self.writer = None

	async def _process_event_line(self, line: bytes) -> None:
		try:
			event_data = json.loads(line.decode("utf-8").strip())
			event_name = event_data.get("event")
			if logger.isEnabledFor(logging.DEBUG) and event_name:
				logger.debug(f"[MPV event] {event_data}")

			if event_name == "end-file":
				reason = event_data.get("reason")
				file_error = event_data.get("file_error")
				if reason in ("eof", "error") and "song_ended" in self.callbacks:
					cb = self.callbacks["song_ended"]
					try:
						asyncio.create_task(cb(reason=reason, file_error=file_error))
					except TypeError:
						asyncio.create_task(cb())
				elif reason in ("quit", "stop") and "track_stopped" in self.callbacks:
					asyncio.create_task(self.callbacks["track_stopped"]())
			elif event_name == "property-change":
				prop_name = event_data.get("name")
				prop_val = event_data.get("data")

				if prop_name == "volume" and prop_val is not None and "volume_update" in self.callbacks:
					asyncio.create_task(self.callbacks["volume_update"](prop_val))
				elif prop_name == "pause" and prop_val is not None and "pause_update" in self.callbacks:
					asyncio.create_task(self.callbacks["pause_update"](prop_val))
				elif prop_name == "time-pos" and "time_update" in self.callbacks:
					asyncio.create_task(self.callbacks["time_update"](prop_val))
				elif prop_name == "duration" and "duration_update" in self.callbacks:
					asyncio.create_task(self.callbacks["duration_update"](prop_val))
				elif prop_name == "mute" and prop_val is not None and "mute_update" in self.callbacks:
					asyncio.create_task(self.callbacks["mute_update"](prop_val))
		except json.JSONDecodeError:
			pass

	async def _send(self, cmd_payload: str) -> None:
		"""Envía un comando JSON a MPV de forma asíncrona."""
		if not self.is_running:
			return
		if logger.isEnabledFor(logging.DEBUG):
			logger.debug(f"[MPV send] {cmd_payload}")
		cmd_bytes = (cmd_payload + "\n").encode("utf-8")

		try:
			aio = _srv("asyncio", asyncio)
			if self.is_windows:

				def write_pipe():
					with open(self.socket_path, "r+b") as pipe:
						pipe.write(cmd_bytes)
						pipe.flush()

				await aio.to_thread(write_pipe)
			else:
				if not self.writer:
					await self.start()
				if self.writer:
					self.writer.write(cmd_bytes)
					await self.writer.drain()
		except Exception as e:
			logger.error(f"Se cortó la conexión con MPV ({e}). Reiniciando...")
			await self.start(is_restart=True)
			try:
				if self.is_windows:

					def write_pipe_retry():
						with open(self.socket_path, "r+b") as pipe:
							pipe.write(cmd_bytes)
							pipe.flush()

					await aio.to_thread(write_pipe_retry)
				else:
					if self.writer:
						self.writer.write(cmd_bytes)
						await self.writer.drain()
			except Exception as retry_e:
				logger.error(f"Reintento fallido: {retry_e}")

	async def command(self, *args: Any) -> None:
		"""Envía una tupla o lista de argumentos como comando de MPV."""
		cmd = json.dumps({"command": list(args)})
		await self._send(cmd)

	async def set_property(self, name: str, value: Any) -> None:
		"""Asigna el valor de una propiedad en MPV."""
		await self.command("set_property", name, value)
