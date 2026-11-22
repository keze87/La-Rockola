"""
Backends de almacenamiento unificados para rutas POSIX estándar y árboles Android SAF (content://).
Evita copiar la biblioteca completa al sandbox privado mediante acceso directo por ContentResolver / fd.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol, Self

from mutagen import File as MutagenFile

logger = logging.getLogger("RockolaCarpincho")

_SAF_NAME_CACHE: dict[str, str] = {}


def is_saf_uri(raw: str | Path | None) -> bool:
	"""Indica si una referencia corresponde a una URI SAF de Android (`content://`)."""
	if raw is None or isinstance(raw, Path):
		return False
	return str(raw).strip().startswith("content://")


def get_authorized_media_roots() -> list[str]:
	"""Obtiene las raíces de biblioteca autorizadas (music_dir / music_dir2) del contenedor activo."""
	from app.core.config import get_settings
	from app.core.container import get_container

	container = get_container()
	state = getattr(container, "orchestrator", None)
	settings = get_settings()
	candidates = [
		getattr(state, "initial_dir", None) if state else None,
		getattr(state, "secondary_dir", None) if state else None,
		getattr(settings, "music_dir", None) if settings else None,
		getattr(settings, "music_dir2", None) if settings else None,
	]
	roots: list[str] = []
	for raw in candidates:
		val = str(raw or "").strip()
		if val and val not in roots:
			roots.append(val)
	return roots


def is_authorized_media_path(
	raw_path: str,
	*,
	require_known_track: bool = False,
	require_audio_extension: bool = False,
) -> bool:
	"""
	Valida de forma centralizada que una ruta POSIX o URI SAF pertenezca a la biblioteca autorizada.
	En SAF exige pertenencia a un árbol autorizado (y validación nativa por DocumentsContract cuando está disponible).
	"""
	cleaned = (raw_path or "").strip()
	if not cleaned or cleaned.startswith(("http://", "https://")):
		return False

	from app.core.container import get_container

	container = get_container()
	state = getattr(container, "orchestrator", None)
	tracks_cache = getattr(state, "tracks_cache", None) or []
	path_to_id = getattr(state, "path_to_id", None) or {}
	queue = getattr(state, "queue", None) or []
	current_track = getattr(state, "current_track", None)
	roots = get_authorized_media_roots()

	if is_saf_uri(cleaned):
		in_inventory = (
			cleaned == current_track
			or cleaned in queue
			or cleaned in path_to_id
			or any(t.get("path") == cleaned for t in tracks_cache)
		)
		if require_known_track and not in_inventory:
			return False
		if (tracks_cache or path_to_id) and not in_inventory:
			return False

		saf_roots = [r for r in roots if is_saf_uri(r)]
		if not saf_roots:
			return False

		bridge = get_android_storage_bridge()
		if bridge is not None and hasattr(bridge, "isAuthorizedDocumentUri"):
			try:
				return bool(bridge.isAuthorizedDocumentUri(cleaned, json.dumps(saf_roots), require_audio_extension))
			except Exception:
				return False

		return any(cleaned.startswith(f"{r}/document/") for r in saf_roots)

	resolved = Path(cleaned).expanduser().resolve()
	for root in roots:
		if not is_saf_uri(root) and resolved.is_relative_to(Path(root).expanduser().resolve()):
			return True

	for track in tracks_cache:
		track_path = track.get("path")
		is_local = (
			bool(track_path) and not str(track_path).startswith(("http://", "https://")) and not is_saf_uri(track_path)
		)
		if is_local and Path(track_path).expanduser().resolve() == resolved:
			return True
	return bool(
		current_track
		and not is_saf_uri(current_track)
		and not str(current_track).startswith(("http://", "https://"))
		and Path(current_track).expanduser().resolve() == resolved
	)


def _remember_saf_name(uri: str, name: str | None) -> None:
	if uri and name:
		if len(_SAF_NAME_CACHE) > 20000:
			_SAF_NAME_CACHE.clear()
		_SAF_NAME_CACHE[uri] = name


def get_saf_name(uri_or_path: str | Path) -> str:
	"""Obtiene el nombre de archivo sin dañar URIs SAF."""
	raw = str(uri_or_path).strip()
	if not is_saf_uri(raw):
		return Path(uri_or_path).name
	cached = _SAF_NAME_CACHE.get(raw)
	if cached:
		return cached
	tail = urllib.parse.unquote(raw.rstrip("/").rsplit("/", 1)[-1])
	if ":" in tail:
		tail = tail.rsplit(":", 1)[-1]
	return tail or "pista"


def get_saf_stem(uri_or_path: str | Path) -> str:
	"""Devuelve el nombre base sin extensión tanto para POSIX como para URIs SAF."""
	if not is_saf_uri(uri_or_path):
		return Path(uri_or_path).stem
	return os.path.splitext(get_saf_name(uri_or_path))[0]


def normalize_music_root(raw: str | Path | None) -> str:
	"""Normaliza rutas POSIX preservando intactas las URIs `content://`."""
	if not raw:
		return ""
	cleaned = str(raw).strip()
	if not cleaned:
		return ""
	if is_saf_uri(cleaned):
		return cleaned
	if cleaned == "~/Music":
		return "~/Music"
	return str(Path(cleaned).expanduser().resolve())


def get_android_storage_bridge() -> Any | None:
	"""Resuelve la clase Kotlin `AndroidStorageBridge` dentro del runtime Chaquopy."""
	from app.infrastructure.binaries.manager import is_android

	if not is_android():
		return None
	try:
		import java

		return java.jclass("ar.carpincho.rockola.AndroidStorageBridge")
	except Exception as exc:
		logger.debug("No se pudo obtener AndroidStorageBridge vía Chaquopy: %s", exc)
		return None


@dataclass(slots=True)
class FolderValidationResult:
	"""Resultado estructurado de validación de una carpeta raíz de música."""

	status: str  # ok | unconfigured | missing | permission_denied | storage_unavailable | unsupported_provider
	path: str
	display_name: str | None = None
	error: str | None = None


@dataclass(slots=True)
class ScannedAudioFile:
	"""Representación mínima de una pista descubierta durante un escaneo."""

	path: str
	name: str
	mtime: float | None
	size: int | None


@dataclass(slots=True)
class SafScanOutcome:
	"""Resultado estructurado de un escaneo SAF diferenciando vacío de errores de acceso."""

	status: str
	files: list[ScannedAudioFile]
	failed_dirs: list[str]
	error: str | None = None


class _NamedBinaryStream:
	"""Envoltorio sobre BufferedReader con `.name` en string para compatibilidad con Mutagen."""

	def __init__(self, stream: BinaryIO, name: str) -> None:
		self._stream = stream
		self.name = name

	def read(self, size: int = -1) -> bytes:
		return self._stream.read(size)

	def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
		return self._stream.seek(offset, whence)

	def tell(self) -> int:
		return self._stream.tell()

	def readable(self) -> bool:
		return True

	def seekable(self) -> bool:
		try:
			return bool(self._stream.seekable())
		except Exception:
			return False

	def close(self) -> None:
		self._stream.close()

	def __getattr__(self, item: str) -> Any:
		return getattr(self._stream, item)

	def __enter__(self) -> Self:
		return self

	def __exit__(self, *args: object) -> None:
		self.close()


class StorageBackend(Protocol):
	"""Contrato mínimo de acceso a archivos para POSIX y Android SAF."""

	def validate_root(self, root: str | None) -> FolderValidationResult: ...
	def iter_audio_files(self, root: str, audio_extensions: set[str]) -> list[ScannedAudioFile]: ...
	def stat_file(self, track_ref: str | Path) -> tuple[float, int] | None: ...
	def exists(self, track_ref: str | Path) -> bool: ...
	def open_binary(self, track_ref: str | Path) -> BinaryIO: ...
	def read_sibling_lyrics(
		self,
		track_ref: str | Path,
		extensions: tuple[str, ...] = (".ass", ".lrc"),
	) -> tuple[str, str, str] | None: ...


class PosixStorageBackend:
	"""Backend de sistema de archivos tradicional para escritorio y rutas locales legibles."""

	def validate_root(self, root: str | None) -> FolderValidationResult:
		cleaned = (root or "").strip()
		if not cleaned:
			return FolderValidationResult(status="unconfigured", path="", display_name=None, error=None)
		if is_saf_uri(cleaned):
			return FolderValidationResult(
				status="unsupported_provider",
				path=cleaned,
				display_name=None,
				error="URI SAF no soportada en entorno POSIX",
			)
		try:
			resolved = Path(cleaned).expanduser().resolve()
			if not resolved.is_dir():
				return FolderValidationResult(
					status="missing",
					path=str(resolved),
					display_name=resolved.name,
					error=f"La carpeta no existe o no es accesible: {cleaned}",
				)
			if not os.access(resolved, os.R_OK):
				return FolderValidationResult(
					status="permission_denied",
					path=str(resolved),
					display_name=resolved.name,
					error=f"Sin permisos de lectura sobre la carpeta: {cleaned}",
				)
			return FolderValidationResult(status="ok", path=str(resolved), display_name=resolved.name, error=None)
		except Exception as exc:
			return FolderValidationResult(
				status="storage_unavailable",
				path=cleaned,
				display_name=None,
				error=str(exc),
			)

	def iter_audio_files(self, root: str, audio_extensions: set[str]) -> list[ScannedAudioFile]:
		music_dir = Path(root).expanduser()
		if not music_dir.exists():
			return []
		found: list[ScannedAudioFile] = []
		for root_str, _dirs, files in os.walk(music_dir):
			for fname in files:
				if os.path.splitext(fname)[1].lower() in audio_extensions:
					fp = Path(root_str) / fname
					try:
						st = fp.stat()
						found.append(
							ScannedAudioFile(
								path=str(fp),
								name=fname,
								mtime=float(st.st_mtime),
								size=int(st.st_size),
							)
						)
					except OSError:
						continue
		return found

	def stat_file(self, track_ref: str | Path) -> tuple[float, int] | None:
		try:
			st = os.stat(track_ref)
			return float(st.st_mtime), int(st.st_size)
		except OSError:
			return None

	def exists(self, track_ref: str | Path) -> bool:
		return os.path.exists(track_ref)

	def open_binary(self, track_ref: str | Path) -> BinaryIO:
		return open(Path(track_ref), "rb")

	def read_sibling_lyrics(
		self,
		track_ref: str | Path,
		extensions: tuple[str, ...] = (".ass", ".lrc"),
	) -> tuple[str, str, str] | None:
		base = Path(track_ref)
		for ext in extensions:
			cand = base.with_suffix(ext)
			if cand.is_file():
				try:
					return ext, cand.read_text(encoding="utf-8"), str(cand)
				except Exception:
					return None
		return None


class AndroidSafStorageBackend:
	"""Backend respaldado por ContentResolver/DocumentsContract vía AndroidStorageBridge."""

	@staticmethod
	def _norm_mtime(raw_mtime: Any) -> float | None:
		if raw_mtime is None:
			return None
		val = float(raw_mtime)
		if val < 0:
			return None
		return val / 1000.0 if val > 1e11 else val

	@staticmethod
	def _norm_size(raw_size: Any) -> int | None:
		if raw_size is None:
			return None
		val = int(raw_size)
		return val if val >= 0 else None

	def validate_root(self, root: str | None) -> FolderValidationResult:
		cleaned = (root or "").strip()
		if not cleaned:
			return FolderValidationResult(status="unconfigured", path="", display_name=None, error=None)
		bridge = get_android_storage_bridge()
		if bridge is None:
			return FolderValidationResult(
				status="storage_unavailable",
				path=cleaned,
				display_name=None,
				error="El puente nativo SAF de Android no está disponible.",
			)
		try:
			payload = json.loads(str(bridge.validateTreeUriJson(cleaned)))
			return FolderValidationResult(
				status=str(payload.get("status") or "storage_unavailable"),
				path=str(payload.get("uri") or cleaned),
				display_name=payload.get("display_name"),
				error=payload.get("error"),
			)
		except Exception as exc:
			return FolderValidationResult(
				status="storage_unavailable",
				path=cleaned,
				display_name=None,
				error=str(exc),
			)

	def scan_audio_files(self, root: str, audio_extensions: set[str]) -> SafScanOutcome:
		bridge = get_android_storage_bridge()
		if bridge is None:
			return SafScanOutcome(
				status="storage_unavailable",
				files=[],
				failed_dirs=[],
				error="El puente nativo SAF de Android no está disponible.",
			)
		status = "success_empty"
		failed_dirs: list[str] = []
		error: str | None = None
		try:
			if hasattr(bridge, "startSafScanJson") and hasattr(bridge, "nextSafScanBatchJson"):
				session_id = str(bridge.startSafScanJson(str(root)) or "")
				if not session_id:
					return SafScanOutcome(
						status="storage_unavailable",
						files=[],
						failed_dirs=[],
						error="No se pudo iniciar sesión de escaneo SAF.",
					)
				items = []
				try:
					while True:
						payload = json.loads(str(bridge.nextSafScanBatchJson(session_id, 250)))
						status = str(payload.get("status") or "provider_error")
						items.extend(payload.get("files") or [])
						failed_dirs = [str(d) for d in (payload.get("failed_dirs") or [])]
						error = payload.get("error")
						if not payload.get("has_more"):
							break
				except Exception:
					if hasattr(bridge, "cancelSafScan"):
						bridge.cancelSafScan(session_id)
					raise
			elif hasattr(bridge, "scanAudioFilesJson"):
				payload = json.loads(str(bridge.scanAudioFilesJson(str(root))))
				status = str(payload.get("status") or "provider_error")
				items = payload.get("files") or []
				failed_dirs = [str(d) for d in (payload.get("failed_dirs") or [])]
				error = payload.get("error")
			else:
				items = json.loads(str(bridge.listAudioFilesJson(str(root))))
				status = "success_with_files" if items else "success_empty"
		except Exception as exc:
			logger.warning("Error enumerando carpeta SAF %s: %s", root, exc)
			return SafScanOutcome(status="provider_error", files=[], failed_dirs=[], error=str(exc))

		found: list[ScannedAudioFile] = []
		for item in items:
			uri = str(item.get("uri") or "")
			name = str(item.get("name") or get_saf_name(uri))
			if not uri or os.path.splitext(name)[1].lower() not in audio_extensions:
				continue
			_remember_saf_name(uri, name)
			found.append(
				ScannedAudioFile(
					path=uri,
					name=name,
					mtime=self._norm_mtime(item.get("mtime")),
					size=self._norm_size(item.get("size")),
				)
			)
		if status == "success_empty" and found:
			status = "success_with_files"
		return SafScanOutcome(status=status, files=found, failed_dirs=failed_dirs, error=error)

	def iter_audio_files(self, root: str, audio_extensions: set[str]) -> list[ScannedAudioFile]:
		return self.scan_audio_files(root, audio_extensions).files

	def _is_saf_ref_authorized(self, track_ref: str | Path) -> bool:
		uri = str(track_ref)
		if not is_saf_uri(uri):
			return False
		saf_roots = [r for r in get_authorized_media_roots() if is_saf_uri(r)]
		if not saf_roots:
			return True
		bridge = get_android_storage_bridge()
		if bridge is not None and hasattr(bridge, "isAuthorizedDocumentUri"):
			try:
				return bool(bridge.isAuthorizedDocumentUri(uri, json.dumps(saf_roots), False))
			except Exception:
				return False
		return any(uri.startswith(f"{r}/document/") for r in saf_roots)

	def stat_file(self, track_ref: str | Path) -> tuple[float | None, int | None] | None:
		bridge = get_android_storage_bridge()
		if bridge is None or not self._is_saf_ref_authorized(track_ref):
			return None
		try:
			raw = bridge.statDocumentJson(str(track_ref))
			if not raw:
				return None
			payload = json.loads(str(raw))
			_remember_saf_name(str(track_ref), payload.get("name"))
			return self._norm_mtime(payload.get("mtime")), self._norm_size(payload.get("size"))
		except Exception:
			return None

	def exists(self, track_ref: str | Path) -> bool:
		return self.stat_file(track_ref) is not None

	def open_binary(self, track_ref: str | Path) -> BinaryIO:
		bridge = get_android_storage_bridge()
		if bridge is None:
			raise FileNotFoundError(f"Puente Android SAF no disponible para {track_ref}")
		if not self._is_saf_ref_authorized(track_ref):
			raise PermissionError(f"URI SAF fuera de la biblioteca autorizada: {track_ref}")
		fd = int(bridge.openFileDescriptorForRead(str(track_ref)))
		if fd < 0:
			raise FileNotFoundError(f"No se pudo abrir descriptor SAF para {track_ref}")
		stream = os.fdopen(fd, "rb")
		return _NamedBinaryStream(stream, get_saf_name(track_ref))  # type: ignore[return-value]

	def read_sibling_lyrics(
		self,
		track_ref: str | Path,
		extensions: tuple[str, ...] = (".ass", ".lrc"),
	) -> tuple[str, str, str] | None:
		bridge = get_android_storage_bridge()
		if bridge is None:
			return None
		try:
			raw = bridge.findSiblingTextJson(str(track_ref), ",".join(extensions))
			if not raw:
				return None
			payload = json.loads(str(raw))
			ext = str(payload.get("ext") or "")
			content = str(payload.get("content") or "")
			if not ext or not content:
				return None
			return ext, content, f"{track_ref}{ext}"
		except Exception:
			return None


def get_storage_backend(path_or_root: str | Path | None = None) -> StorageBackend:
	"""Devuelve el backend apropiado según si el recurso es una URI SAF o ruta POSIX."""
	if is_saf_uri(path_or_root):
		return AndroidSafStorageBackend()
	return PosixStorageBackend()


@contextmanager
def open_mutagen_file(path_or_uri: str | Path, easy: bool = False) -> Generator[Any, None, None]:
	"""Abre metadatos con Mutagen de forma transparente tanto en POSIX como sobre un fd SAF."""
	if not is_saf_uri(path_or_uri):
		yield MutagenFile(path_or_uri, easy=easy)
		return
	backend = AndroidSafStorageBackend()
	with backend.open_binary(path_or_uri) as f:
		audio = MutagenFile(f, easy=easy)
		if audio is None and easy:
			f.seek(0)
			audio = MutagenFile(f, easy=False)
		yield audio
