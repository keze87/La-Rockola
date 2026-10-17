"""
Selector inteligente y modo seguro para DJ Carpincho.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

logger = logging.getLogger("RockolaCarpincho")


class DjCarpinchoSelector:
	"""Gestiona la selección automática de canciones, el modo seguro y el countdown de 10s."""

	def __init__(self) -> None:
		self.enabled: bool = False
		self.safe_mode: bool = False
		self.next_track: dict[str, Any] | None = None
		self.countdown_task: asyncio.Task[Any] | None = None

	def cancel_countdown(self) -> bool:
		"""Cancela el countdown activo si no fue invocado desde la propia tarea."""
		if self.countdown_task and not self.countdown_task.done():
			try:
				curr = asyncio.current_task()
			except RuntimeError:
				curr = None
			if curr is not self.countdown_task:
				self.countdown_task.cancel()
				self.countdown_task = None
				logger.info("Countdown del DJ Carpincho cancelado por nueva acción del usuario.")
				return True
		return False

	def select_candidate(
		self,
		unplayed: list[dict[str, Any]],
		favorites: list[str],
		path_to_id: dict[str, str],
	) -> dict[str, Any] | None:
		"""Elige un tema entre los pendientes aplicando la ponderación del modo seguro (90% favoritos)."""
		if not unplayed:
			return None
		if self.safe_mode:
			favs = [t for t in unplayed if path_to_id.get(t["path"]) in favorites]
			normals = [t for t in unplayed if path_to_id.get(t["path"]) not in favorites]

			if favs and normals:
				return random.choice(favs) if random.random() < 0.90 else random.choice(normals)
			if favs:
				return random.choice(favs)
			return random.choice(normals)
		return random.choice(unplayed)

	def refresh_preview(
		self,
		queue: list[str],
		history: list[str],
		current_track: str | None,
		tracks_cache: list[dict[str, Any]],
		favorites: list[str],
		path_to_id: dict[str, str],
	) -> dict[str, Any] | None:
		"""Actualiza o limpia la preselección del DJ según el estado actual de la fila."""
		if self.enabled and not queue and tracks_cache:
			played_paths = set(history)
			if current_track:
				played_paths.add(current_track)

			unplayed = [t for t in tracks_cache if t["path"] not in played_paths]
			chosen = self.select_candidate(unplayed, favorites, path_to_id)
			if chosen:
				self.next_track = chosen
				is_fav = path_to_id.get(chosen["path"]) in favorites
				logger.info(
					f"🦦 DJ Carpincho pre-eligió: {chosen['display_title']} (Favorito: {'Sí' if is_fav else 'No'})"
				)
				return chosen
		self.next_track = None
		return None
