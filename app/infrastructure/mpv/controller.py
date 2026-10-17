"""
AsyncMpvController: controlador asíncrono del reproductor MPV mediante JSON IPC.
Expone métodos públicos fuertemente tipados sin exponer el transporte de bajo nivel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.infrastructure.binaries.manager import ensure_display_env, find_binary, get_clean_env

logger = logging.getLogger("RockolaCarpincho")


class AsyncMpvController:
	"""Maneja el ciclo de vida del proceso MPV y la comunicación IPC bidireccional."""

	def __init__(
		self,
		callbacks: dict[str, Callable[..., Any]] | None = None,
		ipc_path: str | None = None,
		on_property_change: Callable[..., Any] | None = None,
		on_event: Callable[..., Any] | None = None,
		on_process_exit: Callable[..., Any] | None = None,
		state_ref: Any = None,
	) -> None:
		self.process: asyncio.subprocess.Process | None = None
		self.socket_path: str | None = ipc_path
		self.reader: asyncio.StreamReader | None = None
		self.writer: asyncio.StreamWriter | None = None
		self.is_windows = sys.platform == "win32"
		self.callbacks = callbacks or {}
		if on_property_change:
			self.callbacks["property_change"] = on_property_change
		if on_event:
			self.callbacks["event"] = on_event
		if on_process_exit:
			self.callbacks["process_exit"] = on_process_exit

		self.state_ref: Any = state_ref
		self._is_running_override: bool | None = None
		self._start_lock = asyncio.Lock()
		env = get_clean_env()
		self.has_display = bool(self.is_windows or env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))

	@property
	def ipc_path(self) -> str | None:
		"""Ruta del socket Unix o Named Pipe de IPC."""
		return self.socket_path

	@property
	def is_running(self) -> bool:
		"""Indica si el proceso de MPV se encuentra activo."""
		if self._is_running_override is not None:
			return self._is_running_override
		return self.process is not None and self.process.returncode is None

	@is_running.setter
	def is_running(self, value: bool | None) -> None:
		self._is_running_override = value

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
		self._is_running_override = None
		self.reader = None
		self.writer = None

	def _check_windows_pipe(self) -> bool:
		"""Verifica si el Named Pipe de Windows ya está disponible."""
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
				except Exception as exc:
					logger.debug(f"Error al leer stderr de MPV: {exc}")
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

			env = get_clean_env()
			ensure_display_env(env)

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

			if state_ref is not None:
				self.state_ref = state_ref
			state = getattr(self, "state_ref", None)
			if state is None:
				try:
					from app.core.container import get_container

					state = get_container().ensure_orchestrator()
					if state is not None:
						self.state_ref = state
				except Exception:
					state = None

			show_window = getattr(state, "mpv_visible", True) if state else True
			if not has_display:
				show_window = False
				if state and hasattr(state, "mpv_visible"):
					state.mpv_visible = False

			own_mpris_active = getattr(state, "mpris_registered", False) if state else False
			mpris_opt = "no" if own_mpris_active else "yes"
			keys_opt = "no" if own_mpris_active else "yes"

			is_debug = logger.isEnabledFor(logging.DEBUG)
			mpv_bin = find_binary("mpv") or "mpv"

			mpv_args = [mpv_bin, "--idle"]
			if not is_debug:
				mpv_args.append("--quiet")
			else:
				mpv_args.extend(["--terminal=yes", "--msg-level=all=v"])

			mpv_args.extend(
				[
					"--script-opts=osc-visibility=always,osc-layout=topbar",
					f"--load-scripts={mpris_opt}",
					f"--input-media-keys={keys_opt}",
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
						"--sub-color=#FF00FF",
						"--sub-font-size=100",
						"--sub-font=Pacifico",
						"--sub-scale-by-window=no",
						"--sub-scale-with-window=no",
					]
				)
				if not self.is_windows:
					mpv_args.extend(["--gpu-context=waylandvk,wayland,x11vk,x11egl,x11", "--vo=gpu-next,gpu,null"])
				else:
					mpv_args.append("--vo=gpu-next,gpu,null")
			else:
				if state and hasattr(state, "mpv_visible"):
					state.mpv_visible = False
				mpv_args.extend(["--vo=null", "--no-audio-display", "--force-window=no"])

			ytdlp_bin = find_binary("yt-dlp")
			if ytdlp_bin:
				mpv_args.append(f"--script-opts-append=ytdl_hook-ytdl_path={ytdlp_bin}")
				ytdlp_dir = str(Path(ytdlp_bin).parent)
				current_path = env.get("PATH", "")
				if ytdlp_dir not in current_path.split(os.pathsep):
					env["PATH"] = f"{ytdlp_dir}{os.pathsep}{current_path}" if current_path else ytdlp_dir

			if not self.is_windows and has_display:
				mpv_args.extend(["--wayland-app-id=mpvpip", "--x11-name=mpvpip"])

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

			if self.process and getattr(self.process, "stdout", None):
				asyncio.create_task(self._drain_stdout())
			if self.process and getattr(self.process, "stderr", None):
				asyncio.create_task(self._drain_stderr())

			if self.is_windows:
				logger.info("Conectados al Named Pipe de Windows.")
				asyncio.create_task(self._read_ipc_events_windows())
			else:
				self.reader, self.writer = await asyncio.open_unix_connection(self.socket_path)
				logger.info("Conectados al socket Unix de MPV.")
				asyncio.create_task(self._read_ipc_events())

			if not self.is_windows:
				for idx, prop in enumerate(("volume", "pause", "time-pos", "duration", "mute", "current-vo"), start=1):
					await self.command("observe_property", idx, prop)

			if is_restart and "mpv_restarted" in self.callbacks:
				asyncio.create_task(self.callbacks["mpv_restarted"]())

	async def _drain_stdout(self) -> None:
		try:
			while self.process and self.process.returncode is None and self.process.stdout:
				line = await self.process.stdout.readline()
				if not line or not isinstance(line, (bytes, bytearray)):
					break
				decoded = line.decode("utf-8", errors="replace").rstrip()
				if decoded:
					logger.debug(f"[MPV stdout] {decoded}")
		except Exception as exc:
			logger.debug(f"Lectura de MPV stdout finalizada: {exc}")

	async def _drain_stderr(self) -> None:
		try:
			while self.process and self.process.returncode is None and self.process.stderr:
				line = await self.process.stderr.readline()
				if not line or not isinstance(line, (bytes, bytearray)):
					break
				decoded = line.decode("utf-8", errors="replace").rstrip()
				if decoded:
					logger.debug(f"[MPV stderr] {decoded}")
		except Exception as exc:
			logger.debug(f"Lectura de MPV stderr finalizada: {exc}")

	async def _read_ipc_events_windows(self) -> None:
		main_loop = asyncio.get_running_loop()

		def read_pipe() -> None:
			try:
				if not self.socket_path:
					return
				with open(self.socket_path, "r+b") as pipe:
					for idx, prop in enumerate(
						("volume", "pause", "time-pos", "duration", "mute", "current-vo"), start=1
					):
						payload = json.dumps({"command": ["observe_property", idx, prop]}) + "\n"
						pipe.write(payload.encode("utf-8"))
					pipe.flush()

					while True:
						line = pipe.readline()
						if not line:
							break
						asyncio.run_coroutine_threadsafe(self._process_event_line(line), main_loop)
			except Exception as e:
				logger.debug(f"Pifió algo leyendo la pipa en Windows: {e}")

		try:
			await asyncio.to_thread(read_pipe)
		finally:
			self.reader = None
			if self.writer:
				try:
					res = self.writer.close()
					if asyncio.iscoroutine(res):
						res.close()
				except Exception:
					pass
				self.writer = None

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

		self.reader = None
		if self.writer:
			try:
				res = self.writer.close()
				if asyncio.iscoroutine(res):
					res.close()
			except Exception:
				pass
			self.writer = None

	async def _process_event_line(self, line: bytes) -> None:
		try:
			event_data = json.loads(line.decode("utf-8").strip())
			event_name = event_data.get("event")
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
				elif prop_name == "current-vo":
					is_visible = bool(prop_val and prop_val != "null")
					if self.state_ref and hasattr(self.state_ref, "mpv_visible"):
						self.state_ref.mpv_visible = is_visible
					if "visibility_update" in self.callbacks:
						asyncio.create_task(self.callbacks["visibility_update"](is_visible))
		except json.JSONDecodeError:
			pass

	async def _send(self, cmd_payload: str) -> None:
		"""Envía un comando JSON crudo por el socket IPC de MPV."""
		if not self.is_running:
			return
		cmd_bytes = (cmd_payload + "\n").encode("utf-8")

		try:
			if self.is_windows:

				def write_pipe() -> None:
					if not self.socket_path:
						return
					with open(self.socket_path, "r+b") as pipe:
						pipe.write(cmd_bytes)
						pipe.flush()

				await asyncio.to_thread(write_pipe)
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

					def write_pipe_retry() -> None:
						if not self.socket_path:
							return
						with open(self.socket_path, "r+b") as pipe:
							pipe.write(cmd_bytes)
							pipe.flush()

					await asyncio.to_thread(write_pipe_retry)
				elif self.writer:
					self.writer.write(cmd_bytes)
					await self.writer.drain()
			except Exception as retry_e:
				logger.error(f"Reintento fallido: {retry_e}")

	async def command(self, *args: Any) -> None:
		"""Envía una lista de argumentos como comando JSON IPC a MPV."""
		await self._send(json.dumps({"command": list(args)}, ensure_ascii=False))

	async def set_property(self, name: str, value: Any) -> None:
		"""Establece una propiedad de MPV."""
		await self.command("set_property", name, value)

	async def load_file(self, path: str | Path) -> None:
		"""Carga y reproduce un archivo o URL en MPV."""
		await self.command("loadfile", str(path))

	async def set_pause(self, paused: bool) -> None:
		"""Pausa o reanuda la reproducción en MPV."""
		await self.set_property("pause", bool(paused))

	async def set_volume(self, volume: float) -> None:
		"""Ajusta el volumen de MPV (0 a 110)."""
		clamped = max(0, min(110, int(volume)))
		await self.set_property("volume", clamped)

	async def set_mute(self, muted: bool) -> None:
		"""Silencia o reactiva el audio en MPV."""
		await self.set_property("mute", bool(muted))

	async def seek_relative(self, amount: float) -> None:
		"""Desplaza la posición de reproducción relativamente en segundos."""
		await self.command("seek", amount)

	async def seek_absolute(self, position: float) -> None:
		"""Salta a una posición absoluta en segundos."""
		await self.command("seek", position, "absolute")

	async def toggle_fullscreen(self) -> None:
		"""Alterna pantalla completa en la ventana de MPV."""
		await self.command("cycle", "fullscreen")

	async def set_force_window(self, visible: bool) -> None:
		"""Muestra u oculta la ventana gráfica de MPV."""
		await self.set_property("force-window", "yes" if visible else "no")

	async def add_subtitle(self, sub_path: str | Path) -> None:
		"""Carga y selecciona un archivo de subtítulos externo (.srt o .lrc) en MPV."""
		await self.command("sub-add", str(sub_path), "select")

	async def stop_playback(self) -> None:
		"""Detiene la reproducción activa en MPV."""
		await self.command("stop")


def ensure_mpv_methods(mpv_obj: Any) -> Any:
	"""
	Garantiza que cualquier objeto dummy o SimpleNamespace con `_send` asignado a `state.mpv`
	exponga los métodos de alto nivel de AsyncMpvController delegando en `_send`.
	"""
	if mpv_obj is None or isinstance(mpv_obj, AsyncMpvController):
		return mpv_obj
	send_fn = getattr(mpv_obj, "_send", None)
	if not callable(send_fn):
		return mpv_obj

	async def _cmd(*args: Any) -> None:
		await mpv_obj._send(json.dumps({"command": list(args)}, ensure_ascii=False))

	async def _load_file(path: str | Path) -> None:
		await _cmd("loadfile", str(path))

	async def _set_pause(paused: bool) -> None:
		await _cmd("set_property", "pause", bool(paused))

	async def _set_volume(volume: float) -> None:
		await _cmd("set_property", "volume", max(0, min(110, int(volume))))

	async def _set_mute(muted: bool) -> None:
		await _cmd("set_property", "mute", bool(muted))

	async def _seek_relative(amount: float) -> None:
		await _cmd("seek", amount)

	async def _seek_absolute(position: float) -> None:
		await _cmd("seek", position, "absolute")

	async def _toggle_fullscreen() -> None:
		await _cmd("cycle", "fullscreen")

	async def _set_force_window(visible: bool) -> None:
		await _cmd("set_property", "force-window", "yes" if visible else "no")

	async def _add_subtitle(sub_path: str | Path) -> None:
		await _cmd("sub-add", str(sub_path), "select")

	async def _stop_playback() -> None:
		await _cmd("stop")

	fallbacks = {
		"command": _cmd,
		"load_file": _load_file,
		"set_pause": _set_pause,
		"set_volume": _set_volume,
		"set_mute": _set_mute,
		"seek_relative": _seek_relative,
		"seek_absolute": _seek_absolute,
		"toggle_fullscreen": _toggle_fullscreen,
		"set_force_window": _set_force_window,
		"add_subtitle": _add_subtitle,
		"stop_playback": _stop_playback,
	}
	for name, fn in fallbacks.items():
		if not hasattr(mpv_obj, name):
			try:
				setattr(mpv_obj, name, fn)
			except Exception:
				pass
	return mpv_obj
