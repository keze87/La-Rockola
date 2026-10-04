"""
Abstracción de acceso a datos para La Rockola del Carpincho (patrón Repository).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.db.database import execute_query, execute_write, get_db_connection


class TrackRepository:
	"""Acceso y manipulación de pistas musicales en la base de datos."""

	def __init__(self, db_path: Path | str | None = None) -> None:
		self.db_path = db_path

	def save(self, track: dict[str, Any]) -> None:
		"""Inserta o actualiza una pista identificada por su track_id."""
		sql = """
			INSERT OR REPLACE INTO tracks
			(track_id, path, title, album, artist, duration_str, mtime, file_size, bpm, energy, spectral_centroid, fingerprint)
			VALUES (:track_id, :path, :title, :album, :artist, :duration_str, :mtime, :file_size, :bpm, :energy, :spectral_centroid, :fingerprint)
		"""
		params = {
			"track_id": track.get("track_id"),
			"path": track.get("path"),
			"title": track.get("title"),
			"album": track.get("album"),
			"artist": track.get("artist"),
			"duration_str": track.get("duration_str"),
			"mtime": track.get("mtime"),
			"file_size": track.get("file_size"),
			"bpm": track.get("bpm"),
			"energy": track.get("energy"),
			"spectral_centroid": track.get("spectral_centroid"),
			"fingerprint": track.get("fingerprint"),
		}
		execute_write(sql, params, self.db_path)

	def get_by_id(self, track_id: str) -> dict[str, Any] | None:
		"""Busca una pista por su identificador único (smart hash)."""
		sql = "SELECT * FROM tracks WHERE track_id = ?"
		rows = execute_query(sql, (track_id,), self.db_path)
		return rows[0] if rows else None

	def get_by_path(self, path: str) -> dict[str, Any] | None:
		"""Busca una pista por su ruta de archivo en el disco."""
		sql = "SELECT * FROM tracks WHERE path = ?"
		rows = execute_query(sql, (path,), self.db_path)
		return rows[0] if rows else None

	def update_mood(
		self,
		track_id: str,
		bpm: float | None = None,
		energy: float | None = None,
		spectral_centroid: float | None = None,
	) -> None:
		"""Actualiza las métricas acústicas de una canción."""
		sql = "UPDATE tracks SET bpm = ?, energy = ?, spectral_centroid = ? WHERE track_id = ?"
		execute_write(sql, (bpm, energy, spectral_centroid, track_id), self.db_path)

	def update_fingerprint(self, track_id: str, fingerprint: str) -> None:
		"""Guarda la huella digital Chromaprint de la pista."""
		sql = "UPDATE tracks SET fingerprint = ? WHERE track_id = ?"
		execute_write(sql, (fingerprint, track_id), self.db_path)

	def delete_by_path(self, path: str) -> int:
		"""Elimina el registro de una pista cuando el archivo ya no existe en disco."""
		sql = "DELETE FROM tracks WHERE path = ?"
		return execute_write(sql, (path,), self.db_path)

	def count(self) -> int:
		"""Retorna la cantidad total de canciones registradas en la biblioteca."""
		sql = "SELECT COUNT(*) as total FROM tracks"
		rows = execute_query(sql, (), self.db_path)
		return rows[0]["total"] if rows else 0

	def list_all(self) -> list[dict[str, Any]]:
		"""Obtiene todas las pistas ordenadas por artista y título."""
		sql = "SELECT * FROM tracks ORDER BY artist ASC, title ASC"
		return execute_query(sql, (), self.db_path)

	def list_for_scan_cache(self) -> list[dict[str, Any]]:
		"""Obtiene los campos necesarios para verificar la caché de escaneo."""
		sql = "SELECT path, mtime, file_size, track_id, title, album, artist, duration_str, bpm, energy, spectral_centroid, fingerprint FROM tracks"
		return execute_query(sql, (), self.db_path)

	def save_many(self, tracks: list[tuple[Any, ...]]) -> int:
		"""Inserta o actualiza un lote de pistas en una sola transacción."""
		sql = """
			INSERT OR REPLACE INTO tracks
			(track_id, path, title, album, artist, duration_str, mtime, file_size, bpm, energy, spectral_centroid, fingerprint)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		"""
		with get_db_connection(self.db_path) as conn:
			cursor = conn.cursor()
			cursor.execute("BEGIN IMMEDIATE;")
			try:
				cursor.executemany(sql, tracks)
				conn.execute("COMMIT;")
				return cursor.rowcount
			except Exception:
				conn.execute("ROLLBACK;")
				raise

	def update_mood_batch(self, batch: list[tuple[Any, ...]]) -> int:
		"""Actualiza bpm, energy, spectral_centroid y fingerprint para un lote de pistas."""
		sql = "UPDATE tracks SET bpm=?, energy=?, spectral_centroid=?, fingerprint=? WHERE track_id=?"
		with get_db_connection(self.db_path) as conn:
			cursor = conn.cursor()
			cursor.execute("BEGIN IMMEDIATE;")
			try:
				cursor.executemany(sql, batch)
				conn.execute("COMMIT;")
				return cursor.rowcount
			except Exception:
				conn.execute("ROLLBACK;")
				raise


class FavoritesRepository:
	"""Gestión de temas favoritos."""

	def __init__(self, db_path: Path | str | None = None) -> None:
		self.db_path = db_path

	def add(self, track_id: str) -> None:
		"""Agrega un track_id a la lista de favoritos."""
		sql = "INSERT OR IGNORE INTO favorites (track_id) VALUES (?)"
		execute_write(sql, (track_id,), self.db_path)

	def remove(self, track_id: str) -> None:
		"""Quita un track_id de la lista de favoritos."""
		sql = "DELETE FROM favorites WHERE track_id = ?"
		execute_write(sql, (track_id,), self.db_path)

	def is_favorite(self, track_id: str) -> bool:
		"""Verifica si un track_id está marcado como favorito."""
		sql = "SELECT 1 FROM favorites WHERE track_id = ?"
		rows = execute_query(sql, (track_id,), self.db_path)
		return len(rows) > 0

	def list_all(self) -> list[str]:
		"""Retorna la lista de todos los track_ids favoritos."""
		sql = "SELECT track_id FROM favorites"
		rows = execute_query(sql, (), self.db_path)
		return [r["track_id"] for r in rows]


class HistoryRepository:
	"""Gestión del historial de reproducción."""

	def __init__(self, db_path: Path | str | None = None) -> None:
		self.db_path = db_path

	def add_play(self, track_id: str, played_at: float | None = None) -> None:
		"""Registra una reproducción."""
		timestamp = played_at or time.time()
		sql = "INSERT INTO play_history (track_id, played_at) VALUES (?, ?)"
		execute_write(sql, (track_id, timestamp), self.db_path)

	def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
		"""Retorna los registros de reproducción más recientes."""
		sql = "SELECT * FROM play_history ORDER BY id DESC LIMIT ?"
		return execute_query(sql, (limit,), self.db_path)

	def get_top_played(self, limit: int = 20, since: float | None = None) -> list[dict[str, Any]]:
		"""Calcula los temas más reproducidos agrupados por track_id."""
		if since is not None:
			sql = """
				SELECT track_id, COUNT(*) as count
				FROM play_history
				WHERE played_at >= ?
				  AND (track_id NOT LIKE '%radio_announcement.mp3%' OR track_id IN (SELECT track_id FROM tracks))
				GROUP BY track_id
				ORDER BY count DESC
				LIMIT ?
			"""
			return execute_query(sql, (since, limit), self.db_path)
		else:
			sql = """
				SELECT track_id, COUNT(*) as count
				FROM play_history
				WHERE (track_id NOT LIKE '%radio_announcement.mp3%' OR track_id IN (SELECT track_id FROM tracks))
				GROUP BY track_id
				ORDER BY count DESC
				LIMIT ?
			"""
			return execute_query(sql, (limit,), self.db_path)

	def purge_radio_announcements(self) -> int:
		"""Limpia entradas espurias de locución radial en el historial."""
		sql = """
			DELETE FROM play_history
			WHERE track_id LIKE '%radio_announcement.mp3%'
			  AND track_id NOT IN (SELECT track_id FROM tracks)
		"""
		return execute_write(sql, (), self.db_path)


class UrlLogsRepository:
	"""Historial y caché de URLs remotas (YouTube y streaming)."""

	def __init__(self, db_path: Path | str | None = None) -> None:
		self.db_path = db_path

	def add_url(
		self,
		url: str,
		title: str | None = None,
		artist: str | None = None,
		played_at: str | None = None,
	) -> None:
		"""Registra una URL remota reproducida, limpiando registros previos duplicados."""
		ts = played_at or time.strftime("%Y-%m-%d %H:%M:%S")
		execute_write("DELETE FROM url_logs WHERE url = ?", (url,), self.db_path)
		sql = "INSERT INTO url_logs (url, title, artist, played_at) VALUES (?, ?, ?, ?)"
		execute_write(sql, (url, title, artist, ts), self.db_path)

	def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
		"""Retorna el historial de URLs remotas reproducidas."""
		sql = "SELECT * FROM url_logs ORDER BY id DESC LIMIT ?"
		return execute_query(sql, (limit,), self.db_path)
