"""
Selector inteligente, modos de reproducción (shuffle, favorites, library) y countdown para DJ Bara.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Literal

logger = logging.getLogger("RockolaCarpincho")

type DjMode = Literal["shuffle", "favorites", "library"]


class DjBaraSelector:
	"""Gestiona la selección automática de canciones, modos de DJ y el countdown de 10s."""

	def __init__(self) -> None:
		self.enabled: bool = False
		self._mode: DjMode = "shuffle"
		self.library_order: list[str] = []
		self.last_library_track: str | None = None
		self.next_track: dict[str, Any] | None = None
		self.countdown_task: asyncio.Task[Any] | None = None

	@property
	def mode(self) -> DjMode:
		return self._mode

	@mode.setter
	def mode(self, val: str) -> None:
		if val in ("shuffle", "favorites", "library"):
			self._mode = val  # type: ignore[assignment]
		elif val == "shuffle_favorites":
			self._mode = "favorites"
		else:
			self._mode = "shuffle"

	@property
	def safe_mode(self) -> bool:
		"""Compatibilidad retroactiva: indica si el modo activo es favoritos."""
		return self._mode == "favorites"

	@safe_mode.setter
	def safe_mode(self, val: bool) -> None:
		self.mode = "favorites" if val else "shuffle"

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
				logger.info("Countdown del DJ Bara cancelado por nueva acción del usuario.")
				return True
		return False

	def select_candidate(
		self,
		unplayed: list[dict[str, Any]],
		favorites: list[str],
		path_to_id: dict[str, str],
		current_track: str | None = None,
		tracks_cache: list[dict[str, Any]] | None = None,
	) -> dict[str, Any] | None:
		"""Elige un tema según el modo activo: shuffle, favorites (ponderado) o library (siguiente en lista)."""
		if self.mode == "library":
			candidates = tracks_cache if tracks_cache else unplayed
			if not candidates:
				return None

			path_to_track = {t["path"]: t for t in candidates}
			effective_order = (
				[p for p in self.library_order if p in path_to_track]
				if self.library_order
				else [t["path"] for t in candidates]
			)
			if not effective_order:
				return None

			if current_track and current_track in effective_order:
				ref_track = current_track
				self.last_library_track = current_track
			elif self.last_library_track and self.last_library_track in effective_order:
				ref_track = self.last_library_track
			else:
				ref_track = None

			if ref_track is not None:
				curr_idx = effective_order.index(ref_track)
				next_idx = (curr_idx + 1) % len(effective_order)
			else:
				next_idx = 0

			next_path = effective_order[next_idx]
			return path_to_track.get(next_path)

		if not unplayed:
			return None

		if self.mode == "favorites":
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
		"""Actualiza o limpia la preselección del DJ según el estado actual de la fila y modo."""
		if self.enabled and not queue and tracks_cache:
			if self.mode == "library":
				chosen = self.select_candidate(
					unplayed=tracks_cache,
					favorites=favorites,
					path_to_id=path_to_id,
					current_track=current_track,
					tracks_cache=tracks_cache,
				)
			else:
				played_paths = set(history)
				if current_track:
					played_paths.add(current_track)

				unplayed = [t for t in tracks_cache if t["path"] not in played_paths]
				chosen = self.select_candidate(
					unplayed=unplayed,
					favorites=favorites,
					path_to_id=path_to_id,
					current_track=current_track,
					tracks_cache=tracks_cache,
				)

			if chosen:
				self.next_track = chosen
				is_fav = path_to_id.get(chosen["path"]) in favorites
				logger.info(
					f"🦦 DJ Bara ({self.mode}) pre-eligió: {chosen['display_title']} (Favorito: {'Sí' if is_fav else 'No'})"
				)
				return chosen
		self.next_track = None
		return None
