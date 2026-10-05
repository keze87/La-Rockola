"""
Migraciones versionadas de esquema para La Rockola del Carpincho.
Reemplaza bloques try/except frágiles con revisiones ordenadas e idempotentes.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("RockolaCarpincho")


def get_current_schema_version(db_path: Path | str) -> int:
	"""Obtiene el número de revisión de esquema actual de la base de datos."""
	conn = sqlite3.connect(str(db_path))
	try:
		cursor = conn.cursor()
		cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
		if not cursor.fetchone():
			return 0
		cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
		row = cursor.fetchone()
		return row[0] if row else 0
	finally:
		conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
	"""Verifica si una columna ya existe en la tabla dada."""
	cursor = conn.cursor()
	cursor.execute(f"PRAGMA table_info({table})")
	cols = {row[1] for row in cursor.fetchall()}
	return column in cols


def _migration_rev_1(conn: sqlite3.Connection) -> None:
	"""Rev 1: Tablas base de canciones, historial, favoritos y URLs."""
	c = conn.cursor()
	c.execute("""
		CREATE TABLE IF NOT EXISTS tracks (
			track_id TEXT PRIMARY KEY,
			path TEXT,
			title TEXT,
			album TEXT,
			artist TEXT,
			duration_str TEXT
		)
	""")
	c.execute("""
		CREATE TABLE IF NOT EXISTS play_history (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			track_id TEXT,
			played_at REAL
		)
	""")
	c.execute("""
		CREATE TABLE IF NOT EXISTS favorites (
			track_id TEXT PRIMARY KEY
		)
	""")
	c.execute("""
		CREATE TABLE IF NOT EXISTS url_logs (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			url TEXT,
			title TEXT,
			artist TEXT,
			played_at TEXT
		)
	""")


def _migration_rev_2(conn: sqlite3.Connection) -> None:
	"""Rev 2: Metadatos de modificación y tamaño de archivo."""
	c = conn.cursor()
	if not _column_exists(conn, "tracks", "mtime"):
		c.execute("ALTER TABLE tracks ADD COLUMN mtime REAL")
	if not _column_exists(conn, "tracks", "file_size"):
		c.execute("ALTER TABLE tracks ADD COLUMN file_size INTEGER")


def _migration_rev_3(conn: sqlite3.Connection) -> None:
	"""Rev 3: Campos de análisis acústico y mood (BPM, energía RMS, centroide espectral)."""
	c = conn.cursor()
	if not _column_exists(conn, "tracks", "bpm"):
		c.execute("ALTER TABLE tracks ADD COLUMN bpm REAL")
	if not _column_exists(conn, "tracks", "energy"):
		c.execute("ALTER TABLE tracks ADD COLUMN energy REAL")
	if not _column_exists(conn, "tracks", "spectral_centroid"):
		c.execute("ALTER TABLE tracks ADD COLUMN spectral_centroid REAL")


def _migration_rev_4(conn: sqlite3.Connection) -> None:
	"""Rev 4: Huella acústica digital Chromaprint (fpcalc)."""
	c = conn.cursor()
	if not _column_exists(conn, "tracks", "fingerprint"):
		c.execute("ALTER TABLE tracks ADD COLUMN fingerprint TEXT")


def _migration_rev_5(conn: sqlite3.Connection) -> None:
	"""Rev 5: Saneamiento y purga de pistas auxiliares de locución radial en play_history."""
	c = conn.cursor()
	c.execute("""
		DELETE FROM play_history
		WHERE track_id LIKE '%radio_announcement.mp3%'
		  AND track_id NOT IN (SELECT track_id FROM tracks)
	""")


# Registro ordenado de migraciones
MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None], str]] = [
	(1, _migration_rev_1, "Tablas iniciales de rockola"),
	(2, _migration_rev_2, "Columnas mtime y file_size"),
	(3, _migration_rev_3, "Columnas de análisis acústico y mood"),
	(4, _migration_rev_4, "Columna de huella acústica fingerprint"),
	(5, _migration_rev_5, "Purga de locuciones radiales en historial"),
]


def apply_migrations(db_path: Path | str) -> int:
	"""Aplica todas las migraciones pendientes en orden transaccional."""
	path = Path(db_path)
	path.parent.mkdir(parents=True, exist_ok=True)

	conn = sqlite3.connect(str(path), timeout=30.0)
	try:
		conn.execute("PRAGMA journal_mode=WAL;")
		conn.execute("PRAGMA synchronous=NORMAL;")
		conn.execute("PRAGMA busy_timeout=30000;")
		c = conn.cursor()
		c.execute("""
			CREATE TABLE IF NOT EXISTS schema_version (
				version INTEGER PRIMARY KEY,
				applied_at REAL,
				description TEXT
			)
		""")
		conn.commit()

		c.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
		current_version = c.fetchone()[0]

		for version, migration_fn, description in MIGRATIONS:
			if version > current_version:
				logger.info(f"Aplicando migración {version}: {description}...")
				migration_fn(conn)
				c.execute(
					"INSERT OR REPLACE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
					(version, time.time(), description),
				)
				conn.commit()
				current_version = version

		return current_version
	finally:
		conn.close()
