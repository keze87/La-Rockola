"""
Manejo seguro de SQLite para La Rockola del Carpincho.
Operaciones thread-safe con WAL mode, transacciones atómicas y delegación asíncrona.
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

logger = logging.getLogger("RockolaCarpincho")


def get_default_db_path() -> Path:
	"""Determina la ruta por defecto a rockola.db."""
	from app.core.dependencies import get_db_path

	return Path(get_db_path())


DB_PATH = get_carpincho_data_dir() / "rockola.db"


def init_db(db_path: Path | str | None = None) -> None:
	"""Inicializa la base de datos y aplica migraciones pendientes."""
	from app.db.migrations import apply_migrations

	path = Path(db_path) if db_path else get_default_db_path()
	apply_migrations(path)

	# Saneamiento de locuciones radiales en historial (evitando borrar pistas legítimas de la biblioteca)
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


def db_query(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
	"""Alias de compatibilidad para execute_query."""
	return execute_query(sql, params, db_path)


@contextmanager
def get_db_connection(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
	"""Context manager que abre una conexión a SQLite optimizada para concurrencia."""
	path = Path(db_path) if db_path else get_default_db_path()
	path.parent.mkdir(parents=True, exist_ok=True)

	conn = sqlite3.connect(
		str(path),
		timeout=30.0,
		check_same_thread=False,
		isolation_level=None,  # Manejamos transacciones explícitas con BEGIN/COMMIT
	)
	conn.row_factory = sqlite3.Row
	try:
		# Activamos WAL (Write-Ahead Logging) y synchronous=NORMAL para máximo rendimiento y seguridad
		conn.execute("PRAGMA journal_mode=WAL;")
		conn.execute("PRAGMA synchronous=NORMAL;")
		conn.execute("PRAGMA busy_timeout=30000;")
		yield conn
	finally:
		conn.close()


def execute_query(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
	"""Ejecuta una consulta SELECT y retorna una lista de diccionarios con los resultados."""
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
	"""Ejecuta un INSERT, UPDATE o DELETE dentro de una transacción atómica y retorna rowcount."""
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
	"""Delega la consulta en el threadpool de asyncio para no bloquear el event loop."""
	return await asyncio.to_thread(execute_query, sql, params, db_path)


async def async_execute_write(
	sql: str,
	params: tuple[Any, ...] | dict[str, Any] = (),
	db_path: Path | str | None = None,
) -> int:
	"""Delega la escritura en el threadpool de asyncio para no frenar la reproducción."""
	return await asyncio.to_thread(execute_write, sql, params, db_path)


def backup_db(db_path: Path | str | None = None, data_dir: Path | str | None = None) -> Path | None:
	"""Genera un backup atómico de la base de datos manteniendo las últimas 8 semanas."""
	source_path = Path(db_path) if db_path else get_default_db_path()
	base_dir = Path(data_dir) if data_dir else source_path.parent

	if not source_path.exists():
		return None

	backup_dir = base_dir / "backups"
	backup_dir.mkdir(parents=True, exist_ok=True)

	now = time.time()
	backups = sorted(backup_dir.glob("rockola_backup_*.db"), key=lambda p: p.name, reverse=True)
	if backups and (now - os.path.getmtime(backups[0])) < 7 * 24 * 3600:
		return backups[0]  # Ya existe un backup reciente

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

	# Rotación de backups antiguos (conservar 8)
	all_backups = sorted(backup_dir.glob("rockola_backup_*.db"), key=lambda p: p.name, reverse=True)
	for old in all_backups[8:]:
		try:
			old.unlink(missing_ok=True)
		except Exception as e:
			logger.debug(f"No se pudo limpiar backup viejo {old}: {e}")

	return backup_path
