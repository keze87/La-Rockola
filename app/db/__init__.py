"""
Capa de persistencia y base de datos de La Rockola del Carpincho.
Manejo seguro de SQLite con migraciones versionadas y patrón Repository.
"""

from app.db.database import (
	backup_db,
	execute_query,
	execute_write,
	get_db_connection,
)
from app.db.migrations import apply_migrations, get_current_schema_version
from app.db.repositories import (
	FavoritesRepository,
	HistoryRepository,
	TrackRepository,
	UrlLogsRepository,
)

__all__ = [
	"FavoritesRepository",
	"HistoryRepository",
	"TrackRepository",
	"UrlLogsRepository",
	"apply_migrations",
	"backup_db",
	"execute_query",
	"execute_write",
	"get_current_schema_version",
	"get_db_connection",
]
