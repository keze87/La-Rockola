#!/usr/bin/env python3
"""
Pruebas E2E reales para la app Android de La Rockola del Carpincho sobre dispositivos ADB.

Cubre:
- Modo servidor (host embebido en el dispositivo, ForegroundService, endpoints SAF, botones nativos).
- Modo cliente (envío de comandos HTTP de reproducción, cola, volumen, seek, skip y pausa).
- Escenarios con pantalla prendida y pantalla apagada (KEYCODE_SLEEP / KEYCODE_WAKEUP),
  verificando MediaSession, estabilidad del servicio y ausencia de crashes en logcat.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

try:
	import websockets
except ImportError:  # pragma: no cover - fallback si no está instalado websockets
	websockets = None

PACKAGE_NAME = "ar.carpincho.rockola"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"
SERVICE_NAME = f"{PACKAGE_NAME}/.RockolaForegroundService"
DEFAULT_DEVICE_PORT = 1729
DEFAULT_LOCAL_FORWARD_PORT = 11729


@dataclass(slots=True)
class E2EResult:
	"""Resultado de un paso o suite E2E."""

	name: str
	ok: bool
	detail: str


def _run_adb(serial: str | None, args: list[str], check: bool = True, timeout: float = 20.0) -> str:
	cmd = ["adb"]
	if serial:
		cmd.extend(["-s", serial])
	cmd.extend(args)
	proc = subprocess.run(
		cmd,
		capture_output=True,
		text=True,
		encoding="utf-8",
		errors="replace",
		check=False,
		timeout=timeout,
	)
	if check and proc.returncode != 0:
		raise RuntimeError(
			f"Falló `{' '.join(cmd)}` (exit={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
		)
	return proc.stdout.strip()


def detect_adb_devices() -> list[str]:
	"""Devuelve los seriales de dispositivos ADB listos en estado 'device'."""
	try:
		out = _run_adb(None, ["devices"], check=True, timeout=10.0)
	except Exception:
		return []
	serials: list[str] = []
	for line in out.splitlines()[1:]:
		parts = line.strip().split()
		if len(parts) >= 2 and parts[1] == "device":
			serials.append(parts[0])
	return serials


def _http_json(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 10.0) -> tuple[int, dict]:
	data = json.dumps(payload).encode("utf-8") if payload is not None else None
	headers = {"Content-Type": "application/json"} if payload is not None else {}
	req = urllib.request.Request(url, data=data, headers=headers, method=method)
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		raw = resp.read().decode("utf-8")
		return int(resp.status), json.loads(raw) if raw else {}


def _http_bytes(url: str, headers: dict[str, str] | None = None, timeout: float = 15.0) -> tuple[int, bytes]:
	req = urllib.request.Request(url, headers=headers or {}, method="GET")
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		return int(resp.status), resp.read()


def _wait_health(base_url: str, timeout_sec: float = 15.0) -> None:
	deadline = time.monotonic() + timeout_sec
	last_err: Exception | None = None
	while time.monotonic() < deadline:
		try:
			st, data = _http_json(f"{base_url}/health", timeout=3.0)
			if st == 200 and data.get("status") == "ok":
				return
		except Exception as exc:
			last_err = exc
		time.sleep(0.4)
	raise RuntimeError(f"El servidor embebido no respondió /health en {timeout_sec:.0f}s: {last_err}")


def _is_screen_awake(serial: str) -> bool:
	power_dump = _run_adb(serial, ["shell", "dumpsys", "power"], check=False)
	for line in power_dump.splitlines():
		if "mWakefulness=" in line:
			return "mWakefulness=Awake" in line
	return "Display Power: state=ON" in power_dump


def _set_screen_state(serial: str, awake: bool) -> None:
	if _is_screen_awake(serial) == awake:
		return
	keycode = "KEYCODE_WAKEUP" if awake else "KEYCODE_SLEEP"
	_run_adb(serial, ["shell", "input", "keyevent", keycode], check=False)
	deadline = time.monotonic() + 5.0
	while time.monotonic() < deadline:
		if _is_screen_awake(serial) == awake:
			return
		time.sleep(0.3)
	if awake and not _is_screen_awake(serial):
		_run_adb(serial, ["shell", "input", "keyevent", "KEYCODE_WAKEUP"], check=False)
		time.sleep(0.8)
		if not _is_screen_awake(serial):
			raise RuntimeError("No se pudo encender la pantalla del dispositivo antes de la prueba")


def _assert_process_alive(serial: str) -> str:
	pid = _run_adb(serial, ["shell", "pidof", PACKAGE_NAME], check=False)
	if not pid:
		raise RuntimeError(f"El proceso {PACKAGE_NAME} murió o no está ejecutándose")
	return pid.strip()


def _assert_process_and_foreground(serial: str) -> str:
	pid = _assert_process_alive(serial)
	svc_dump = _run_adb(serial, ["shell", "dumpsys", "activity", "services", PACKAGE_NAME], check=False)
	if "isForeground=true" not in svc_dump:
		raise RuntimeError("RockolaForegroundService no figura con isForeground=true")
	return pid


def _assert_foreground_released(serial: str, timeout_sec: float = 35.0) -> str:
	deadline = time.monotonic() + timeout_sec
	while True:
		pid = _assert_process_alive(serial)
		svc_dump = _run_adb(serial, ["shell", "dumpsys", "activity", "services", PACKAGE_NAME], check=False)
		if "isForeground=true" not in svc_dump:
			return pid
		if time.monotonic() >= deadline:
			raise RuntimeError("RockolaForegroundService sigue con isForeground=true tras pausar sin clientes remotos")
		time.sleep(1.0)


def _assert_no_fatal_logcat(serial: str) -> None:
	logs = _run_adb(serial, ["logcat", "-d", "-t", "500"], check=False)
	bad_markers = (
		"FATAL EXCEPTION",
		"ForegroundServiceStartNotAllowedException",
		"Stopping service due to app idle",
		"Scheduling restart of crashed service",
		"ANR in ",
		"has died",
	)
	for line in logs.splitlines():
		if any(marker in line for marker in bad_markers) and (
			PACKAGE_NAME in line or "Rockola" in line or "AndroidRuntime" in line
		):
			raise RuntimeError(f"Error crítico detectado en logcat: {line}")


def _get_media_session_state(serial: str) -> str:
	return _run_adb(serial, ["shell", "dumpsys", "media_session"], check=False)


def _run_server_mode_checks(serial: str, base_url: str, screen_awake: bool) -> list[E2EResult]:
	results: list[E2EResult] = []
	label = "pantalla_prendida" if screen_awake else "pantalla_apagada"
	_set_screen_state(serial, awake=screen_awake)
	if not screen_awake:
		# Aguantamos 2.5s con pantalla apagada para validar que no muere ni cae el foreground
		time.sleep(2.5)

	pid = _assert_process_alive(serial)
	results.append(E2EResult(f"server_{label}_alive", True, f"pid={pid}, alive=True"))

	st_h, health = _http_json(f"{base_url}/health")
	assert st_h == 200 and health.get("status") == "ok"
	st_c, caps = _http_json(f"{base_url}/api/system/capabilities")
	assert st_c == 200 and "has_edge_tts" in caps
	st_tts, tts_info = _http_json(f"{base_url}/api/system/tts-preload?limit=5")
	if st_tts != 200 or not isinstance(tts_info.get("total"), int) or not isinstance(tts_info.get("recent"), list):
		raise RuntimeError(f"/api/system/tts-preload devolvió respuesta inválida (status={st_tts}): {tts_info}")
	results.append(
		E2EResult(
			f"server_{label}_tts_preload",
			True,
			f"total={tts_info['total']}, bytes={tts_info.get('total_bytes', 0)}, recent={len(tts_info['recent'])}",
		)
	)
	t0 = time.perf_counter()
	st_lib, lib = _http_json(f"{base_url}/library")
	lib_ms = (time.perf_counter() - t0) * 1000.0
	tracks = lib.get("data") or []
	assert st_lib == 200
	results.append(E2EResult(f"server_{label}_http", True, f"tracks={len(tracks)} en {lib_ms:.1f}ms"))

	if tracks:
		track_path = random.choice(tracks)["path"]
		st_rng, body = _http_bytes(
			f"{base_url}/stream?path={quote(track_path, safe='')}", headers={"Range": "bytes=0-1023"}
		)
		if st_rng not in (200, 206) or not body:
			raise RuntimeError(f"/stream devolvió status={st_rng} bytes={len(body)}")
		results.append(E2EResult(f"server_{label}_stream", True, f"status={st_rng}, bytes={len(body)}"))

		try:
			st_lrc, lrc_body = _http_bytes(f"{base_url}/lrc?path={quote(track_path, safe='')}", timeout=30.0)
			results.append(E2EResult(f"server_{label}_lrc", True, f"status={st_lrc}, bytes={len(lrc_body)}"))
		except urllib.error.HTTPError as exc:
			if exc.code != 404:
				raise
			results.append(E2EResult(f"server_{label}_lrc", True, "status=404 (sin letra hermana)"))
		except TimeoutError:
			results.append(
				E2EResult(f"server_{label}_lrc", True, "timeout (>30s) durante escaneo inicial SAF en ContentProvider")
			)

	_assert_no_fatal_logcat(serial)
	return results


def _run_client_mode_checks(serial: str, base_url: str, screen_awake: bool) -> list[E2EResult]:
	results: list[E2EResult] = []
	label = "pantalla_prendida" if screen_awake else "pantalla_apagada"
	_set_screen_state(serial, awake=True)

	_, lib = _http_json(f"{base_url}/library")
	tracks = lib.get("data") or []
	if len(tracks) < 2:
		raise RuntimeError(
			f"Se necesitan al menos 2 pistas en biblioteca para probar reproducción/skip (hay {len(tracks)})"
		)

	t1, t2 = random.sample(tracks, 2)
	_http_json(f"{base_url}/command", "POST", {"cmd": "play", "path": t1["path"]})
	time.sleep(1.5)
	if not screen_awake:
		# Apagamos la pantalla con reproducción activa (en Android 12+ una app ya detenida no puede promover FGS vía HTTP puro)
		_set_screen_state(serial, awake=False)
	_http_json(f"{base_url}/command", "POST", {"cmd": "toggle_queue", "path": t2["path"]})
	_http_json(f"{base_url}/command", "POST", {"cmd": "set_volume", "value": 65})
	_http_json(f"{base_url}/command", "POST", {"cmd": "seek_absolute", "value": 10})
	time.sleep(1.0)
	_http_json(f"{base_url}/command", "POST", {"cmd": "skip"})
	time.sleep(1.8)

	_assert_process_and_foreground(serial)
	session_play = _get_media_session_state(serial)
	if "RockolaMediaSession" not in session_play:
		raise RuntimeError("RockolaMediaSession no registrada tras comandos de reproducción")

	_http_json(f"{base_url}/command", "POST", {"cmd": "pause", "state": True})
	time.sleep(0.8)
	session_pause = _get_media_session_state(serial)
	if "PAUSED(2)" not in session_pause and "PLAYING(3)" not in session_pause:
		raise RuntimeError("Estado de MediaSession inesperado tras pause")

	if not screen_awake:
		_assert_foreground_released(serial)
	_assert_no_fatal_logcat(serial)
	results.append(
		E2EResult(
			f"client_{label}_playback",
			True,
			f"play->queue->volume->seek->skip->pause OK ({t1.get('display_title')} -> {t2.get('display_title')})",
		)
	)
	return results


def _ws_url_from_http(base_url: str) -> str:
	if base_url.startswith("https://"):
		return "wss://" + base_url[len("https://") :] + "/ws"
	if base_url.startswith("http://"):
		return "ws://" + base_url[len("http://") :] + "/ws"
	return base_url.rstrip("/") + "/ws"


async def _active_client_soak_async(
	serial: str,
	base_url: str,
	initial_pid: str,
	soak_seconds: int,
	poll_interval: float = 10.0,
) -> tuple[int, int]:
	ws_url = _ws_url_from_http(base_url)
	deadline = time.monotonic() + soak_seconds
	checks = 0
	ws_msgs = 0

	async def _loop(ws_conn: object | None) -> None:
		nonlocal checks, ws_msgs
		while True:
			remaining = deadline - time.monotonic()
			if remaining <= 0:
				break
			step = min(poll_interval, remaining)
			if ws_conn is not None:
				step_end = time.monotonic() + step
				while time.monotonic() < step_end:
					wait_left = max(0.05, step_end - time.monotonic())
					try:
						await asyncio.wait_for(ws_conn.recv(), timeout=wait_left)
						ws_msgs += 1
					except TimeoutError:
						break
			else:
				await asyncio.sleep(step)

			checks += 1
			current_pid = _assert_process_and_foreground(serial)
			if current_pid != initial_pid:
				raise RuntimeError(
					f"El proceso cambió de PID durante soak con cliente activo ({initial_pid} -> {current_pid})"
				)
			st_h, health = _http_json(f"{base_url}/health", timeout=5.0)
			if st_h != 200 or health.get("status") != "ok":
				raise RuntimeError(f"/health falló durante soak: status={st_h}, body={health}")
			# Simulamos tráfico de cliente activo (consulta de estado + comando liviano)
			_http_json(f"{base_url}/api/system/info", timeout=5.0)
			_http_json(f"{base_url}/command", "POST", {"cmd": "set_volume", "value": 65}, timeout=5.0)
			session_dump = _get_media_session_state(serial)
			if "RockolaMediaSession" not in session_dump:
				raise RuntimeError("RockolaMediaSession desapareció durante soak con cliente activo")
			_assert_no_fatal_logcat(serial)

	if websockets is not None:
		async with websockets.connect(ws_url, open_timeout=10, ping_interval=20, ping_timeout=10) as ws_conn:
			await _loop(ws_conn)
	else:
		await _loop(None)

	return checks, ws_msgs


def _run_screen_off_soak_check(serial: str, base_url: str, soak_seconds: int) -> list[E2EResult]:
	"""Simula un cliente activo conectado (WS + polling/comandos) con pantalla apagada y verifica que no muera."""
	if soak_seconds <= 0:
		return []

	_, lib = _http_json(f"{base_url}/library")
	tracks = lib.get("data") or []
	if not tracks:
		raise RuntimeError("No hay pistas en biblioteca para ejecutar la prueba prolongada con pantalla apagada")

	_set_screen_state(serial, awake=True)
	_run_adb(serial, ["shell", "wm", "dismiss-keyguard"], check=False)
	_run_adb(serial, ["shell", "am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"], check=False)
	time.sleep(0.8)
	initial_pid = _assert_process_alive(serial)
	_http_json(f"{base_url}/command", "POST", {"cmd": "play", "path": random.choice(tracks)["path"]})
	time.sleep(1.5)
	_assert_process_and_foreground(serial)
	_set_screen_state(serial, awake=False)

	print(f"⏳ Iniciando soak con cliente activo y pantalla apagada ({soak_seconds}s, pid={initial_pid})...")
	checks, ws_msgs = asyncio.run(_active_client_soak_async(serial, base_url, initial_pid, soak_seconds))

	_http_json(f"{base_url}/command", "POST", {"cmd": "pause", "state": True})
	ws_label = f"ws_msgs={ws_msgs}" if websockets is not None else "sin_ws(http_polling)"
	return [
		E2EResult(
			"soak_cliente_activo_pantalla_apagada",
			True,
			f"{soak_seconds}s vivo sin reinicios (pid={initial_pid}, {ws_label}, checks={checks})",
		)
	]


def _run_shortcut_checks(serial: str) -> list[E2EResult]:
	"""Dispara todos los shortcuts de Android con pantalla encendida y verifica estabilidad."""
	_set_screen_state(serial, awake=True)
	shortcuts = (
		("library", f"{PACKAGE_NAME}.ACTION_OPEN_LIBRARY"),
		("queue", f"{PACKAGE_NAME}.ACTION_OPEN_QUEUE"),
		("tops", f"{PACKAGE_NAME}.ACTION_OPEN_TOPS"),
		("fogon", f"{PACKAGE_NAME}.ACTION_OPEN_FOGON"),
	)
	for _, action in shortcuts:
		_run_adb(serial, ["shell", "am", "start", "-W", "-a", action, "-n", MAIN_ACTIVITY], timeout=20.0)
		time.sleep(0.5)
	pid = _assert_process_alive(serial)
	_assert_no_fatal_logcat(serial)
	return [E2EResult("shortcuts_pantalla_prendida", True, f"4/4 shortcuts OK (pid={pid})")]


def _run_radio_test_checks(serial: str, base_url: str) -> list[E2EResult]:
	"""Prueba generación y reproducción radial con fundido en distintas variantes."""
	variants = (
		("continue_play", {"play": True, "outro_mode": "continue"}),
		("dj_play", {"play": True, "outro_mode": "dj"}),
		("pause_dry", {"play": False, "outro_mode": "pause"}),
	)
	results: list[E2EResult] = []
	for label, payload in variants:
		st, data = _http_json(f"{base_url}/api/radio/test", "POST", payload, timeout=30.0)
		if st != 200 or not data.get("ok") or not data.get("script"):
			raise RuntimeError(f"POST /api/radio/test ({label}) falló: status={st}, data={data}")
		if payload["play"] and not data.get("played"):
			raise RuntimeError(f"POST /api/radio/test ({label}) no inició reproducción: {data}")
		if payload["play"]:
			time.sleep(1.5)
			_assert_process_and_foreground(serial)
			session_dump = _get_media_session_state(serial)
			if "RockolaMediaSession" not in session_dump:
				raise RuntimeError(f"RockolaMediaSession ausente tras radio test ({label})")
		results.append(
			E2EResult(
				f"radio_{label}",
				True,
				f"ok=True, played={data.get('played')}, script={len(data.get('script', ''))}ch",
			)
		)

	_http_json(f"{base_url}/command", "POST", {"cmd": "pause", "state": True})
	_assert_process_alive(serial)
	_assert_no_fatal_logcat(serial)
	return results


def _parse_duration_sec(track: dict[str, object]) -> float:
	raw_dur = track.get("duration")
	if isinstance(raw_dur, (int, float)) and raw_dur > 0:
		return float(raw_dur)
	dur_str = str(track.get("duration_str") or "").strip()
	if not dur_str or ":" not in dur_str:
		return 0.0
	parts = dur_str.split(":")
	try:
		nums = [int(p) for p in parts]
		if len(nums) == 2:
			return float(nums[0] * 60 + nums[1])
		if len(nums) == 3:
			return float(nums[0] * 3600 + nums[1] * 60 + nums[2])
	except ValueError:
		return 0.0
	return 0.0


async def _wait_ws_track(
	ws_url: str,
	predicate: object,
	timeout_sec: float = 35.0,
) -> dict[str, object]:
	deadline = time.monotonic() + timeout_sec
	state_snapshot: dict[str, object] = {}
	async with websockets.connect(ws_url, open_timeout=10, ping_interval=20, ping_timeout=10) as ws_conn:
		while True:
			left = deadline - time.monotonic()
			if left <= 0:
				raise RuntimeError(
					f"Timeout ({timeout_sec:.0f}s) esperando estado WebSocket (último track={state_snapshot.get('current_track')})"
				)
			try:
				raw = await asyncio.wait_for(ws_conn.recv(), timeout=left)
			except TimeoutError as exc:
				raise RuntimeError(
					f"Timeout ({timeout_sec:.0f}s) esperando estado WebSocket "
					f"(track={state_snapshot.get('current_track')}, pos={state_snapshot.get('time_pos')}, dur={state_snapshot.get('duration')})"
				) from exc
			msg = json.loads(raw)
			if isinstance(msg, dict):
				state_snapshot.update(msg)
				if predicate(state_snapshot):  # type: ignore[operator]
					return dict(state_snapshot)


def _run_screen_off_eof_and_radio_checks(serial: str, base_url: str) -> list[E2EResult]:
	"""Verifica transición natural por EOF entre canciones y reproducción de radio con pantalla apagada."""
	if websockets is None:
		return [E2EResult("pantalla_apagada_eof_y_radio", True, "omitido (falta paquete Python websockets)")]

	_, lib = _http_json(f"{base_url}/library")
	tracks = lib.get("data") or []
	long_tracks = [t for t in tracks if _parse_duration_sec(t) >= 20.0]
	pool = long_tracks if len(long_tracks) >= 2 else tracks
	if len(pool) < 2:
		raise RuntimeError("Se necesitan al menos 2 pistas para probar transición por EOF con pantalla apagada")

	t1, t2 = random.sample(pool, 2)
	_set_screen_state(serial, awake=True)
	_run_adb(serial, ["shell", "wm", "dismiss-keyguard"], check=False)
	_run_adb(serial, ["shell", "am", "start", "-n", MAIN_ACTIVITY], check=False)
	time.sleep(0.8)
	initial_pid = _assert_process_alive(serial)

	ws_url = _ws_url_from_http(base_url)
	_http_json(f"{base_url}/command", "POST", {"cmd": "clear_round"})
	_http_json(f"{base_url}/command", "POST", {"cmd": "play", "path": t1["path"]})
	_http_json(f"{base_url}/command", "POST", {"cmd": "toggle_queue", "path": t2["path"]})

	started_state = asyncio.run(
		_wait_ws_track(
			ws_url,
			lambda s: s.get("current_track") == t1["path"] and float(s.get("duration") or 0.0) > 10.0,
			timeout_sec=25.0,
		)
	)
	dur1 = float(started_state.get("duration") or _parse_duration_sec(t1) or 60.0)
	_assert_process_and_foreground(serial)

	# Apagamos pantalla ANTES del final natural (EOF) y hacemos seek al cierre del tema
	_set_screen_state(serial, awake=False)
	time.sleep(1.5)
	seek_pos = max(0.0, dur1 - 5.0)
	_http_json(f"{base_url}/command", "POST", {"cmd": "seek_absolute", "amount": seek_pos})

	saw_radio_on_eof = False

	def _reached_next_track(s: dict[str, object]) -> bool:
		nonlocal saw_radio_on_eof
		cur = str(s.get("current_track") or "")
		if "radio_announcement" in cur or bool(s.get("is_playing_radio_announcement")):
			saw_radio_on_eof = True
		return cur == t2["path"]

	asyncio.run(
		_wait_ws_track(
			ws_url,
			_reached_next_track,
			timeout_sec=75.0,
		)
	)
	time.sleep(1.5)
	eof_pid = _assert_process_and_foreground(serial)
	if eof_pid != initial_pid:
		raise RuntimeError(f"El proceso cambió de PID durante transición EOF ({initial_pid} -> {eof_pid})")
	st_h, health = _http_json(f"{base_url}/health", timeout=5.0)
	if st_h != 200 or health.get("status") != "ok":
		raise RuntimeError(f"/health falló tras EOF con pantalla apagada: {st_h}")
	_assert_no_fatal_logcat(serial)

	radio_note = " (con locución radial intermedia)" if saw_radio_on_eof else ""
	results: list[E2EResult] = [
		E2EResult(
			"pantalla_apagada_eof_transicion",
			True,
			f"EOF {t1.get('display_title')} -> {t2.get('display_title')}{radio_note} OK (pid={initial_pid})",
		)
	]

	# Con pantalla aún apagada, disparamos reproducción real de radio y verificamos estabilidad
	st_r, radio_data = _http_json(
		f"{base_url}/api/radio/test",
		"POST",
		{"play": True, "outro_mode": "continue"},
		timeout=30.0,
	)
	if st_r != 200 or not radio_data.get("ok") or not radio_data.get("played"):
		raise RuntimeError(f"POST /api/radio/test falló con pantalla apagada: status={st_r}, data={radio_data}")

	time.sleep(5.0)
	radio_pid = _assert_process_and_foreground(serial)
	if radio_pid != initial_pid:
		raise RuntimeError(
			f"El proceso cambió de PID durante radio con pantalla apagada ({initial_pid} -> {radio_pid})"
		)
	session_dump = _get_media_session_state(serial)
	if "RockolaMediaSession" not in session_dump:
		raise RuntimeError("RockolaMediaSession ausente durante radio con pantalla apagada")
	st_h2, health2 = _http_json(f"{base_url}/health", timeout=5.0)
	if st_h2 != 200 or health2.get("status") != "ok":
		raise RuntimeError(f"/health falló durante radio con pantalla apagada: {st_h2}")
	_assert_no_fatal_logcat(serial)

	results.append(
		E2EResult(
			"pantalla_apagada_radio_reproduccion",
			True,
			f"radio play OK 5s con pantalla apagada (pid={initial_pid}, script={len(radio_data.get('script', ''))}ch)",
		)
	)
	_http_json(f"{base_url}/command", "POST", {"cmd": "pause", "state": True})
	return results


def _run_idle_paused_soak_check(serial: str, base_url: str, idle_seconds: int) -> list[E2EResult]:
	"""Observa qué ocurre sin clientes conectados y el servidor en pausa (informativo: no falla si Android lo mata)."""
	if idle_seconds <= 0:
		return []

	initial_pid = _assert_process_alive(serial)
	_http_json(f"{base_url}/command", "POST", {"cmd": "pause", "state": True})
	_set_screen_state(serial, awake=False)

	print(f"⏳ Observando servidor en pausa sin clientes ({idle_seconds}s, pid={initial_pid})...")
	time.sleep(idle_seconds)

	end_pid = _run_adb(serial, ["shell", "pidof", PACKAGE_NAME], check=False).strip()
	svc_dump = _run_adb(serial, ["shell", "dumpsys", "activity", "services", PACKAGE_NAME], check=False)
	is_fg = "isForeground=true" in svc_dump
	health_ok = False
	try:
		st_h, health = _http_json(f"{base_url}/health", timeout=4.0)
		health_ok = st_h == 200 and health.get("status") == "ok"
	except Exception:
		health_ok = False

	if end_pid == initial_pid and is_fg and health_ok:
		detail = f"{idle_seconds}s en pausa sin cliente: SIGUE VIVO (pid={end_pid}, isForeground=true, health=200)"
	elif not end_pid:
		detail = (
			f"{idle_seconds}s en pausa sin cliente: Android mató el proceso (pid inicial={initial_pid}) [informativo]"
		)
	else:
		detail = (
			f"{idle_seconds}s en pausa sin cliente: estado cambiado "
			f"(pid={initial_pid}->{end_pid}, isForeground={is_fg}, health={health_ok}) [informativo]"
		)

	return [E2EResult("soak_pausa_sin_cliente_observacion", True, detail)]


def run_e2e(
	serial: str | None,
	mode: str = "all",
	apk_path: Path | None = None,
	local_port: int = DEFAULT_LOCAL_FORWARD_PORT,
	device_port: int = DEFAULT_DEVICE_PORT,
	server_url: str | None = None,
	if_available: bool = False,
	soak_seconds: int = 90,
	idle_soak_seconds: int = 30,
) -> int:
	"""Orquesta la batería E2E sobre el dispositivo Android conectado por ADB."""
	devices = detect_adb_devices()
	if not serial:
		if not devices:
			msg = "No hay dispositivos Android conectados por ADB."
			if if_available:
				print(f"ℹ️ {msg} Se omite E2E (--if-available).")
				return 0
			print(f"❌ {msg}", file=sys.stderr)
			return 2
		serial = devices[0]
	elif serial not in devices:
		print(f"❌ Dispositivo {serial} no conectado o no autorizado en `adb devices`.", file=sys.stderr)
		return 2

	print(f"📱 Ejecutando E2E Android sobre dispositivo: {serial} (modo={mode})")
	if apk_path is not None:
		if not apk_path.is_file():
			print(f"❌ APK no encontrada: {apk_path}", file=sys.stderr)
			return 1
		print(f"📦 Instalando {apk_path.name}...")
		_run_adb(serial, ["install", "-r", str(apk_path)], timeout=60.0)

	_run_adb(serial, ["logcat", "-c"], check=False)
	_run_adb(serial, ["shell", "am", "force-stop", PACKAGE_NAME], check=False)
	# Primero verificamos que la pantalla esté efectivamente encendida antes de arrancar
	_set_screen_state(serial, awake=True)
	if not _is_screen_awake(serial):
		raise RuntimeError("La pantalla del dispositivo no quedó encendida al iniciar la prueba")
	all_results: list[E2EResult] = [E2EResult("pantalla_inicial_encendida", True, "mWakefulness=Awake")]
	_run_adb(serial, ["shell", "am", "start", "-W", "-n", MAIN_ACTIVITY], timeout=30.0)

	forwarded = False
	if server_url:
		base_url = server_url.rstrip("/")
	else:
		_run_adb(serial, ["forward", f"tcp:{local_port}", f"tcp:{device_port}"])
		forwarded = True
		base_url = f"http://127.0.0.1:{local_port}"

	try:
		_wait_health(base_url, timeout_sec=20.0)
		all_results.extend(_run_shortcut_checks(serial))
		all_results.extend(_run_radio_test_checks(serial, base_url))
		if mode in ("server", "all"):
			all_results.extend(_run_server_mode_checks(serial, base_url, screen_awake=True))
			all_results.extend(_run_server_mode_checks(serial, base_url, screen_awake=False))
		if mode in ("client", "all"):
			all_results.extend(_run_client_mode_checks(serial, base_url, screen_awake=True))
			all_results.extend(_run_client_mode_checks(serial, base_url, screen_awake=False))
			all_results.extend(_run_screen_off_eof_and_radio_checks(serial, base_url))
		all_results.extend(_run_screen_off_soak_check(serial, base_url, soak_seconds=soak_seconds))
		all_results.extend(_run_idle_paused_soak_check(serial, base_url, idle_seconds=idle_soak_seconds))
	finally:
		_set_screen_state(serial, awake=True)
		if forwarded:
			_run_adb(serial, ["forward", "--remove", f"tcp:{local_port}"], check=False)

	print("\n📋 Resumen E2E Android:")
	for item in all_results:
		icon = "✅" if item.ok else "❌"
		print(f"  {icon} {item.name}: {item.detail}")
	return 0 if all(item.ok for item in all_results) else 1


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Pruebas E2E Android sobre dispositivo ADB real.")
	parser.add_argument("--device", default=None, help="Serial ADB del dispositivo objetivo.")
	parser.add_argument(
		"--mode",
		choices=("server", "client", "all"),
		default="all",
		help="Modo a probar: server (host embebido), client (comandos remotos) o all.",
	)
	parser.add_argument("--install", type=Path, default=None, help="Ruta a APK para instalar antes de probar.")
	parser.add_argument("--server-url", default=None, help="URL HTTP remota opcional (omite adb forward).")
	parser.add_argument("--if-available", action="store_true", help="Sale con 0 si no hay dispositivo ADB conectado.")
	parser.add_argument(
		"--soak-seconds",
		type=int,
		default=90,
		help="Segundos sostenidos con pantalla apagada reproduciendo y cliente activo (default: 90, 0 desactiva).",
	)
	parser.add_argument(
		"--idle-soak-seconds",
		type=int,
		default=30,
		help="Segundos en pausa sin cliente para observar comportamiento de Android (default: 30, 0 desactiva).",
	)
	args = parser.parse_args(argv)

	try:
		return run_e2e(
			serial=args.device,
			mode=args.mode,
			apk_path=args.install,
			server_url=args.server_url,
			if_available=args.if_available,
			soak_seconds=args.soak_seconds,
			idle_soak_seconds=args.idle_soak_seconds,
		)
	except Exception as exc:
		print(f"❌ Falló E2E Android: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
