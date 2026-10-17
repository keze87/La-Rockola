"""
Conexiones SQLite thread-safe con WAL mode, transacciones explícitas y backups atómicos.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.core.config import get_carpincho_data_dir
from app.core.container import get_container
from app.infrastructure.db.migrations import apply_migrations

logger = logging.getLogger("RockolaCarpincho")

DB_PATH = get_carpincho_data_dir() / "rockola.db"


def get_default_db_path() -> Path:
	"""Obtiene la ruta activa de base de datos desde el contenedor de dependencias."""
	return Path(get_container().db_path)


def init_db(db_path: Path | str | None = None) -> None:
	"""Inicializa la base de datos y aplica migraciones pendientes."""
	path = Path(db_path) if db_path else get_default_db_path()
	apply_migrations(path)

	with get_db_connection(path) as conn:
		conn.execute("PRAGMA journal_mode=WAL;")
		conn.execute("PRAGMA synchronous=NORMAL;")

	try:
		execute_write(
			"""
			DELETE FROM play_history
			WHERE track_id LIKE '%radio_announcement.mp3%'
			  AND track_id NOT IN (SELECT track_id FROM tracks)
			""",
			db_path=path,
		)
	except Exception as e:
		logger.debug(f"No se pudo purgar la locución radial de play_history: {e}")


@contextmanager
def get_db_connection(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
	"""Context manager que abre una conexión a SQLite optimizada para concurrencia."""
	path = Path(db_path) if db_path else get_default_db_path()
	path.parent.mkdir(parents=True, exist_ok=True)

	conn = sqlite3.connect(
		str(path),
		timeout=30.0,
		check_same_thread=False,
		isolation_level=None,
	)
	conn.row_factory = sqlite3.Row
	try:
		conn.execute("PRAGMA busy_timeout=30000;")
		yield conn
	finally:
		conn.close()


def execute_query(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
	"""Ejecuta un SELECT y devuelve una lista de diccionarios."""
	with get_db_connection(db_path) as conn:
		cursor = conn.cursor()
		cursor.execute(sql, params)
		rows = cursor.fetchall()
		return [dict(row) for row in rows]


def execute_write(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> int:
	"""Ejecuta un INSERT, UPDATE o DELETE en una transacción atómica."""
	with get_db_connection(db_path) as conn:
		cursor = conn.cursor()
		cursor.execute("BEGIN IMMEDIATE;")
		try:
			cursor.execute(sql, params)
			conn.execute("COMMIT;")
			return cursor.rowcount
		except Exception:
			conn.execute("ROLLBACK;")
			raise


async def async_execute_query(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
	"""Ejecuta una consulta en el threadpool de asyncio."""
	return await asyncio.to_thread(execute_query, sql, params, db_path)


async def async_execute_write(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> int:
	"""Ejecuta una escritura en el threadpool de asyncio."""
	return await asyncio.to_thread(execute_write, sql, params, db_path)


def backup_db(db_path: Path | str | None = None, data_dir: Path | str | None = None) -> Path | None:
	"""Genera un backup atómico de la base de datos conservando las últimas 8 semanas."""
	source_path = Path(db_path) if db_path else get_default_db_path()
	base_dir = Path(data_dir) if data_dir else source_path.parent

	if not source_path.exists():
		return None

	backup_dir = base_dir / "backups"
	backup_dir.mkdir(parents=True, exist_ok=True)

	now = time.time()
	backups = sorted(backup_dir.glob("rockola_backup_*.db"), key=lambda p: p.name, reverse=True)
	if backups and (now - os.path.getmtime(backups[0])) < 7 * 24 * 3600:
		return backups[0]

	backup_name = f"rockola_backup_{time.strftime('%Y-%m-%d')}.db"
	backup_path = backup_dir / backup_name
	temp_backup = backup_dir / f".tmp_{backup_name}"

	src_uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
	src_conn = sqlite3.connect(src_uri, uri=True, timeout=10.0)
	dst_conn = sqlite3.connect(temp_backup)
	try:
		with dst_conn:
			src_conn.backup(dst_conn, pages=100)
	finally:
		dst_conn.close()
		src_conn.close()

	temp_backup.replace(backup_path)
	logger.info(f"Copia de seguridad atómica de la DB armada joya: {backup_name}")

	all_backups = sorted(backup_dir.glob("rockola_backup_*.db"), key=lambda p: p.name, reverse=True)
	for old in all_backups[8:]:
		try:
			old.unlink(missing_ok=True)
		except Exception as e:
			logger.debug(f"No se pudo limpiar backup viejo {old}: {e}")

	return backup_path


db_query = execute_query
