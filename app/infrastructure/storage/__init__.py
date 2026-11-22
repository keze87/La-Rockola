"""
Abstracción de almacenamiento para bibliotecas musicales en POSIX y Android SAF.
"""

from app.infrastructure.storage.backend import (
	AndroidSafStorageBackend,
	FolderValidationResult,
	PosixStorageBackend,
	ScannedAudioFile,
	get_android_storage_bridge,
	get_authorized_media_roots,
	get_saf_name,
	get_saf_stem,
	get_storage_backend,
	is_authorized_media_path,
	is_saf_uri,
	normalize_music_root,
	open_mutagen_file,
)

__all__ = [
	"AndroidSafStorageBackend",
	"FolderValidationResult",
	"PosixStorageBackend",
	"ScannedAudioFile",
	"get_android_storage_bridge",
	"get_authorized_media_roots",
	"get_saf_name",
	"get_saf_stem",
	"get_storage_backend",
	"is_authorized_media_path",
	"is_saf_uri",
	"normalize_music_root",
	"open_mutagen_file",
]
