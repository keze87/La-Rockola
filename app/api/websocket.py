"""
ConnectionManager: gestión tipada de conexiones WebSocket, soporte de reproductor local y sincronización.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from starlette.websockets import WebSocket

logger = logging.getLogger("RockolaCarpincho")


class ConnectionManager:
	"""Mantiene la lista de conexiones activas y gestiona el cliente reproductor local."""

	def __init__(self) -> None:
		self.active_connections: list[WebSocket] = []
		self.local_player_ws: WebSocket | None = None
		self._lock = asyncio.Lock()

	async def connect(self, websocket: WebSocket) -> None:
		"""Acepta y registra una nueva conexión WebSocket."""
		try:
			await websocket.accept()
		except Exception:
			# En tests o si ya fue aceptado
			pass
		async with self._lock:
			if websocket not in self.active_connections:
				self.active_connections.append(websocket)
		logger.debug(f"Nueva conexión WebSocket registrada. Total: {len(self.active_connections)}")

	def disconnect(self, websocket: WebSocket) -> bool:
		"""Desregistra una conexión y libera el rol de reproductor local si le pertenecía."""
		if websocket in self.active_connections:
			self.active_connections.remove(websocket)
		was_local = self.local_player_ws is websocket
		if was_local:
			self.local_player_ws = None
			logger.info("El reproductor local se desconectó; rol liberado.")
		logger.debug(f"Conexión WebSocket cerrada. Restantes: {len(self.active_connections)}")
		return was_local

	def claim_local_player(self, websocket: WebSocket) -> bool:
		"""Intenta asignar el rol de reproductor local exclusivo a este cliente."""
		if self.local_player_ws is not None and self.local_player_ws is not websocket:
			return False
		self.local_player_ws = websocket
		return True

	def release_local_player(self, websocket: WebSocket) -> bool:
		"""Libera el rol de reproductor local si el solicitante es el dueño actual."""
		if self.local_player_ws is websocket:
			self.local_player_ws = None
			return True
		return False

	async def broadcast(self, message: dict[str, Any] | str) -> None:
		"""Emite un mensaje a todos los clientes conectados de manera concurrente y segura."""

		if isinstance(message, dict):
			log_msg = message.copy()
			if "library" in log_msg:
				count = len(log_msg["library"]) if isinstance(log_msg["library"], (list, dict)) else ""
				log_msg["library"] = (
					f"<Librería omitida del log ({count} temas)>" if count != "" else "<Librería omitida del log>"
				)

			if "top_played" in log_msg:
				count = len(log_msg["top_played"]) if isinstance(log_msg["top_played"], (list, dict)) else ""
				log_msg["top_played"] = (
					f"<Top temas omitido del log ({count} temas)>" if count != "" else "<Top temas omitido del log>"
				)

			if "fingerprint" in log_msg:
				log_msg["fingerprint"] = "<Fingerprint omitido del log>"

			if "dj_next_track" in log_msg and isinstance(log_msg["dj_next_track"], dict):
				dj_copy = log_msg["dj_next_track"].copy()
				if "fingerprint" in dj_copy:
					dj_copy["fingerprint"] = "<Fingerprint omitido del log>"
				log_msg["dj_next_track"] = dj_copy

			# Evitamos spamear la consola si el broadcast es solo el pulso periódico de posición
			is_routine_tick = set(message.keys()) <= {"type", "time_pos"}
			if not is_routine_tick:
				try:
					from app.core.logging import highlight_json

					formatted_log = highlight_json(log_msg)
				except Exception:
					formatted_log = json.dumps(log_msg)
				logger.debug(f"AVISANDO A LA MUCHACHADA:\n{formatted_log}")

		for connection in self.active_connections.copy():
			try:
				if isinstance(message, dict):
					await connection.send_json(message)
				else:
					await connection.send_text(message)
			except Exception:
				self.disconnect(connection)

	broadcast_json = broadcast

	@staticmethod
	def arbitrate_seek_drift(
		state_pos: float, new_pos: float, last_seek_drift: float | None
	) -> tuple[bool, float | None]:
		"""
		Arbitra derivas de tiempo entre el reproductor del navegador y MPV.
		Previene bucles de rebote y llamadas redundantes a seek.
		Retorna (debe_enviar_seek, nuevo_last_seek_drift).
		"""
		diff = abs(state_pos - new_pos)
		if diff > 5.0:
			current_drift = new_pos - state_pos
			if last_seek_drift is None or abs(current_drift - last_seek_drift) > 1.0:
				return True, current_drift
			return False, last_seek_drift
		# Si la diferencia es menor o igual a 5.0s, consideramos sincronizado
		return False, None
