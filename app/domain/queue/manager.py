"""
Gestor de estado de fila, historial y transiciones de reproducción (QueueManager).
"""

from __future__ import annotations


class QueueManager:
	"""Encapsula de forma cohesiva la fila de espera, el historial y la pista activa."""

	def __init__(self) -> None:
		self.current_track: str | None = None
		self.queue: list[str] = []
		self.history: list[str] = []
		self.pause_after_path: str | None = None

	def clear(self) -> None:
		"""Vacía la fila y el historial por completo."""
		self.queue.clear()
		self.history.clear()

	def toggle(self, path: str) -> bool:
		"""Agrega o quita un tema de la fila. Retorna True si fue agregado."""
		if path in self.queue:
			self.queue.remove(path)
			return False
		self.queue.append(path)
		return True

	def insert(self, path: str, index: int | None = None) -> int:
		"""Inserta un tema en una posición acotada de la fila."""
		idx = max(0, min(len(self.queue), index if index is not None else len(self.queue)))
		self.queue.insert(idx, path)
		return idx

	def remove_queue_item(self, index: int) -> str | None:
		"""Quita y retorna un ítem de la fila por su índice."""
		if 0 <= index < len(self.queue):
			return self.queue.pop(index)
		return None

	def move_queue_item(self, old_index: int, new_index: int) -> bool:
		"""Reordena un ítem dentro de la fila."""
		if 0 <= old_index < len(self.queue) and 0 <= new_index < len(self.queue):
			item = self.queue.pop(old_index)
			self.queue.insert(new_index, item)
			return True
		return False

	def remove_history_item(self, index: int) -> str | None:
		"""Quita y retorna un ítem del historial por su índice."""
		if 0 <= index < len(self.history):
			return self.history.pop(index)
		return None

	def move_history_item(self, old_index: int, new_index: int) -> bool:
		"""Reordena un ítem dentro del historial."""
		if 0 <= old_index < len(self.history) and 0 <= new_index < len(self.history):
			item = self.history.pop(old_index)
			self.history.insert(new_index, item)
			return True
		return False

	def toggle_pause_after(self, path: str | None) -> str | None:
		"""Activa o desactiva la pausa programada tras terminar un tema determinado."""
		if path is None or self.pause_after_path == path:
			self.pause_after_path = None
		else:
			self.pause_after_path = path
		return self.pause_after_path

	def advance_current(self, exclude_from_history: bool = False) -> tuple[str | None, bool]:
		"""
		Finaliza el tema actual moviéndolo al historial (salvo locuciones radiales)
		y evalúa si correspondía pausar al finalizar.
		"""
		just_finished = self.current_track
		if self.current_track:
			if not exclude_from_history:
				self.history.append(self.current_track)
			self.current_track = None

		should_pause = (self.pause_after_path is not None) and (just_finished == self.pause_after_path)
		if should_pause:
			self.pause_after_path = None

		return just_finished, should_pause

	def pop_next(self) -> str | None:
		"""Extrae y retorna el primer tema de la fila si existe."""
		if self.queue:
			return self.queue.pop(0)
		return None

	def pop_previous(self) -> str | None:
		"""Recupera el último tema del historial devolviendo el tema actual al inicio de la fila."""
		if self.history:
			prev_path = self.history.pop()
			if self.current_track:
				self.queue.insert(0, self.current_track)
				self.current_track = None
			return prev_path
		return self.current_track

	rewind_previous = pop_previous

	def jump_to_queue(self, index: int) -> None:
		"""Salta hacia un índice de la fila pasando los temas salteados al historial."""
		skipped = self.queue[:index]
		if self.current_track:
			self.history.append(self.current_track)
			self.current_track = None
		self.history.extend(skipped)
		self.queue = self.queue[index:]

	def jump_to_history(self, index: int) -> str | None:
		"""Rebobina hasta un índice del historial devolviendo los temas posteriores a la fila."""
		if not (0 <= index < len(self.history)):
			return None
		rewound = self.history[index + 1 :]
		if self.current_track:
			rewound.append(self.current_track)
			self.current_track = None
		self.queue = rewound + self.queue
		target = self.history[index]
		self.history = self.history[:index]
		return target
