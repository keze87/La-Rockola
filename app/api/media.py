"""
Enrutador de medios: streaming de audio (/stream), portadas (/cover) y subtítulos (/lrc).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import mimetypes
import os
import re
import threading
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from mutagen import File as MutagenFile

from app.core.container import get_container
from app.infrastructure.db.repositories import CoverThumbRepository
from app.infrastructure.media.mixer import get_carpincho_cover_path
from app.infrastructure.storage import get_saf_name, get_storage_backend, is_saf_uri, open_mutagen_file

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["Media"])


def _extract_mutagen_cover(audio: object) -> tuple[bytes | None, str]:
	if not audio:
		return None, "image/jpeg"
	pics = getattr(audio, "pictures", None)
	if pics:
		return bytes(pics[0].data), str(getattr(pics[0], "mime", "image/jpeg"))
	tags = getattr(audio, "tags", None)
	if tags:
		for key, tag in tags.items():
			if str(key).startswith("APIC"):
				return bytes(tag.data), str(getattr(tag, "mime", "image/jpeg"))
		if "covr" in tags:
			covr_item = tags["covr"][0]
			raw = bytes(covr_item)
			mime = "image/jpeg" if raw.startswith(b"\xff\xd8") else "image/png"
			return raw, mime
	return None, "image/jpeg"


HAS_PIL = False
try:
	from PIL import Image

	HAS_PIL = True
except ImportError:
	pass

_COVER_MEM_CACHE: dict[str, tuple[int, int, bytes | None, str, str]] = {}
_MAX_COVER_MEM_CACHE = 1000
_COVER_CACHE_LOCK = threading.Lock()
_COVER_PATH_LOCKS: dict[str, threading.Lock] = {}


def _get_cover_cache(key: str) -> tuple[int, int, bytes | None, str, str] | None:
	with _COVER_CACHE_LOCK:
		if key not in _COVER_MEM_CACHE:
			return None
		val = _COVER_MEM_CACHE.pop(key)
		_COVER_MEM_CACHE[key] = val
		return val


def _set_cover_cache(key: str, value: tuple[int, int, bytes | None, str, str]) -> None:
	with _COVER_CACHE_LOCK:
		if key in _COVER_MEM_CACHE:
			_COVER_MEM_CACHE.pop(key)
		elif len(_COVER_MEM_CACHE) >= _MAX_COVER_MEM_CACHE:
			_COVER_MEM_CACHE.pop(next(iter(_COVER_MEM_CACHE)))
		_COVER_MEM_CACHE[key] = value


def _get_cover_path_lock(path: str) -> threading.Lock:
	with _COVER_CACHE_LOCK:
		lock = _COVER_PATH_LOCKS.get(path)
		if lock is None:
			if len(_COVER_PATH_LOCKS) >= 512:
				_COVER_PATH_LOCKS.clear()
			lock = threading.Lock()
			_COVER_PATH_LOCKS[path] = lock
		return lock


def _get_android_image_resizer():
	try:
		import java

		return java.jclass("ar.carpincho.rockola.AndroidImageResizer")
	except Exception:
		return None


def _resize_cover(cover_bytes: bytes, max_size: int) -> tuple[bytes, str]:
	if not cover_bytes or max_size <= 0:
		return cover_bytes, "image/jpeg"
	if not HAS_PIL:
		from app.infrastructure.binaries.manager import is_android

		if is_android():
			resizer = _get_android_image_resizer()
			if resizer is not None:
				try:
					resized = resizer.resizeJpeg(cover_bytes, int(max_size))
					if resized:
						return bytes(resized), "image/jpeg"
				except Exception:
					pass
		return cover_bytes, "image/jpeg"
	try:
		with Image.open(io.BytesIO(cover_bytes)) as img:
			if img.width <= max_size and img.height <= max_size:
				format_mime = Image.MIME.get(img.format, "image/jpeg") if img.format else "image/jpeg"
				return cover_bytes, format_mime

			img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
			if img.mode in ("RGBA", "LA", "P"):
				bg = Image.new("RGB", img.size, (30, 26, 23))
				if img.mode == "P":
					img = img.convert("RGBA")
				bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
				img = bg
			elif img.mode != "RGB":
				img = img.convert("RGB")

			out = io.BytesIO()
			img.save(out, format="JPEG", quality=85, optimize=True)
			return out.getvalue(), "image/jpeg"
	except Exception:
		return cover_bytes, "image/jpeg"


def _serve_cover_sync(
	path: str,
	size: int | None,
	if_none_match: str | None,
	is_announcement: bool,
	db_path: Any,
) -> Response:
	"""Resuelve la portada en hilo trabajador para no bloquear el event loop durante I/O SAF/Mutagen."""
	try:
		if is_announcement:
			carpincho_img = get_carpincho_cover_path()
			if carpincho_img and carpincho_img.is_file():
				img_stat = carpincho_img.stat()
				etag = f'"{carpincho_img.name}:{int(img_stat.st_mtime)}:{img_stat.st_size}:s={size}"'
				cache_headers = {
					"ETag": etag,
					"Cache-Control": "public, max-age=86400, stale-while-revalidate=3600",
				}
				if if_none_match and etag in if_none_match:
					return Response(status_code=304, headers=cache_headers)

				if size and size > 0:
					c_data, c_mime = _resize_cover(carpincho_img.read_bytes(), size)
					return Response(content=c_data, media_type=c_mime, headers=cache_headers)
				mime = "image/png" if carpincho_img.suffix.lower() == ".png" else "image/jpeg"
				return FileResponse(carpincho_img, media_type=mime, headers=cache_headers)

		saf = is_saf_uri(path)
		if saf:
			st_info = get_storage_backend(path).stat_file(path)
			if st_info is None:
				return Response(status_code=404)
			mtime = int(st_info[0])
			file_size = st_info[1]
		else:
			if not os.path.exists(path):
				return Response(status_code=404)
			st = os.stat(path)
			mtime = int(st.st_mtime)
			file_size = st.st_size
		etag_raw = f"{path}:{mtime}:{file_size}:s={size}" if (size and size > 0) else f"{path}:{mtime}:{file_size}"
		etag = f'"{hashlib.md5(etag_raw.encode()).hexdigest()}"'
		cache_headers = {
			"ETag": etag,
			"Cache-Control": "public, max-age=2592000, stale-while-revalidate=86400",
		}

		if if_none_match and etag in if_none_match:
			return Response(status_code=304, headers=cache_headers)

		cache_key = f"{path}:s={size}" if (size and size > 0) else path
		cached = _get_cover_cache(cache_key)
		if cached is not None:
			c_mtime, c_size, c_data, c_mime, _ = cached
			if c_mtime == mtime and c_size == file_size:
				if c_data is None:
					return Response(status_code=404, headers=cache_headers)
				return Response(content=c_data, media_type=c_mime, headers=cache_headers)

		# Serializamos por archivo para que pedidos simultáneos (HeadBar + Notificación) no lean SAF dos veces
		with _get_cover_path_lock(path):
			cached_after_wait = _get_cover_cache(cache_key)
			if cached_after_wait is not None:
				c_mtime, c_size, c_data, c_mime, _ = cached_after_wait
				if c_mtime == mtime and c_size == file_size:
					if c_data is None:
						return Response(status_code=404, headers=cache_headers)
					return Response(content=c_data, media_type=c_mime, headers=cache_headers)

			thumb_repo = CoverThumbRepository(db_path) if db_path else None
			if size == 128 and thumb_repo is not None:
				try:
					cached_thumb = thumb_repo.get(path, mtime, file_size)
					if cached_thumb is not None:
						t_blob, t_mime = cached_thumb
						_set_cover_cache(cache_key, (mtime, file_size, t_blob or None, t_mime, etag))
						if not t_blob:
							return Response(status_code=404, headers=cache_headers)
						return Response(content=t_blob, media_type=t_mime, headers=cache_headers)
				except Exception as e:
					logger.debug(f"No pude consultar miniatura 128px en SQLite para {path}: {e}")

			cover_data = None
			mime_type = "image/jpeg"
			if size and size > 0:
				raw_cached = _get_cover_cache(path)
				if raw_cached is not None:
					c_mtime, c_size, c_data, c_mime, _ = raw_cached
					if c_mtime == mtime and c_size == file_size and c_data:
						cover_data = c_data
						mime_type = c_mime

			if not cover_data:
				if saf:
					with open_mutagen_file(path, easy=False) as audio:
						cover_data, mime_type = _extract_mutagen_cover(audio)
				else:
					audio = MutagenFile(path)
					cover_data, mime_type = _extract_mutagen_cover(audio)
				if not cover_data:
					_set_cover_cache(cache_key, (mtime, file_size, None, "image/jpeg", etag))
					if size == 128 and thumb_repo is not None:
						try:
							thumb_repo.upsert(path, mtime, file_size, b"", "image/jpeg")
						except Exception:
							pass
					return Response(status_code=404, headers=cache_headers)

				_set_cover_cache(path, (mtime, file_size, cover_data, mime_type, etag))

			if size and size > 0:
				resized_data, r_mime = _resize_cover(cover_data, size)
				_set_cover_cache(cache_key, (mtime, file_size, resized_data, r_mime, etag))
				if thumb_repo is not None:
					try:
						if size == 128:
							thumb_repo.upsert(path, mtime, file_size, resized_data, r_mime)
						elif thumb_repo.get(path, mtime, file_size) is None:
							thumb_128, thumb_mime = _resize_cover(cover_data, 128)
							thumb_repo.upsert(path, mtime, file_size, thumb_128, thumb_mime)
					except Exception as e:
						logger.debug(f"No pude guardar miniatura 128px en SQLite para {path}: {e}")
				return Response(content=resized_data, media_type=r_mime, headers=cache_headers)

			return Response(content=cover_data, media_type=mime_type, headers=cache_headers)

	except Exception as e:
		logger.debug(f"Error procesando cover para {path}: {e}")
		return Response(status_code=404)


@router.get("/cover", response_model=None)
async def serve_cover(
	path: str = Query(..., description="Ruta absoluta o relativa del archivo de audio"),
	size: int | None = Query(default=None, description="Tamaño máximo de carátula en píxeles"),
	request: Request = None,  # type: ignore[assignment]
) -> Response:
	"""Extrae la portada incrustada del archivo de audio o devuelve la predeterminada."""
	container = get_container()
	state = container.ensure_orchestrator()
	if not isinstance(size, int) or size <= 0:
		size = None

	is_announcement = False
	if state and hasattr(state, "is_radio_announcement"):
		is_announcement = state.is_radio_announcement(path)
	elif path and get_saf_name(path) in ("radio_announcement.mp3", "radio_pregenerated.mp3"):
		is_announcement = True

	if_none_match = request.headers.get("if-none-match") if request else None
	db_path = getattr(container, "db_path", None)
	return await asyncio.to_thread(_serve_cover_sync, path, size, if_none_match, is_announcement, db_path)


def _build_saf_stream_response(
	path: str,
	file_size: int,
	media_type: str,
	cache_control: str,
	range_header: str | None,
) -> Response:
	backend = get_storage_backend(path)
	base_headers = {
		"Accept-Ranges": "bytes",
		"Cache-Control": cache_control,
	}
	if file_size <= 0 and not range_header:
		return Response(
			content=b"", status_code=200, media_type=media_type, headers={**base_headers, "Content-Length": "0"}
		)

	start = 0
	end = max(0, file_size - 1)
	status_code = 200
	if range_header:
		match = re.match(r"^\s*bytes=(\d*)-(\d*)\s*$", range_header.split(",", 1)[0])
		if not match or file_size <= 0:
			return Response(status_code=416, headers={**base_headers, "Content-Range": f"bytes */{file_size}"})
		raw_start, raw_end = match.group(1), match.group(2)
		if raw_start == "" and raw_end == "":
			return Response(status_code=416, headers={**base_headers, "Content-Range": f"bytes */{file_size}"})
		if raw_start == "":
			suffix_len = int(raw_end)
			if suffix_len <= 0:
				return Response(status_code=416, headers={**base_headers, "Content-Range": f"bytes */{file_size}"})
			start = max(0, file_size - suffix_len)
			end = file_size - 1
		else:
			start = int(raw_start)
			end = int(raw_end) if raw_end else file_size - 1
			if start >= file_size or end < start:
				return Response(status_code=416, headers={**base_headers, "Content-Range": f"bytes */{file_size}"})
			end = min(end, file_size - 1)
		status_code = 206

	content_length = end - start + 1
	headers = {
		**base_headers,
		"Content-Length": str(content_length),
	}
	if status_code == 206:
		headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

	def _iter_chunks():
		with backend.open_binary(path) as f:
			if start > 0:
				f.seek(start)
			remaining = content_length
			while remaining > 0:
				chunk = f.read(min(65536, remaining))
				if not chunk:
					break
				remaining -= len(chunk)
				yield chunk

	return StreamingResponse(
		_iter_chunks(),
		status_code=status_code,
		media_type=media_type,
		headers=headers,
	)


@router.get("/stream")
async def stream_audio(
	path: str = Query(..., description="Ruta de la canción a transmitir"),
	request: Request = None,  # type: ignore[assignment]
) -> Response:
	"""Transmite el archivo de audio para reproducción local en el navegador del cliente."""
	state = get_container().ensure_orchestrator()
	is_radio = state.is_radio_announcement(path) if (state and hasattr(state, "is_radio_announcement")) else False
	path_to_id = getattr(state, "path_to_id", {}) if state else {}
	tracks_cache = getattr(state, "tracks_cache", []) if state else []
	queue = getattr(state, "queue", []) if state else []
	current_track = getattr(state, "current_track", None) if state else None

	is_known = (
		is_radio
		or path in path_to_id
		or any(t.get("path") == path for t in tracks_cache)
		or path == current_track
		or path in queue
	)
	if not is_known:
		return Response(status_code=404)

	# Si es una URL externa (YouTube / web), resolvemos el flujo de audio con yt-dlp y redirigimos
	if path.startswith(("http://", "https://")):
		ytdlp_srv = getattr(state, "ytdlp_service", None)
		if ytdlp_srv and hasattr(ytdlp_srv, "get_stream_url"):
			direct_url = await ytdlp_srv.get_stream_url(path)
			if direct_url:
				return RedirectResponse(url=direct_url, status_code=307)
		return Response(status_code=502)

	cache_control = (
		"no-store, no-cache, must-revalidate" if is_radio else "public, max-age=86400, stale-while-revalidate=172800"
	)

	if is_saf_uri(path):
		st_info = await asyncio.to_thread(get_storage_backend(path).stat_file, path)
		if st_info is None:
			return Response(status_code=404)
		media_type = mimetypes.guess_type(get_saf_name(path))[0] or "application/octet-stream"
		range_header = request.headers.get("range") if request else None
		return await asyncio.to_thread(
			_build_saf_stream_response, path, st_info[1], media_type, cache_control, range_header
		)

	if not os.path.exists(path):
		return Response(status_code=404)

	return FileResponse(
		path,
		headers={
			"Accept-Ranges": "bytes",
			"Cache-Control": cache_control,
		},
	)


@router.get("/lrc")
async def serve_lrc(
	path: str = Query(..., description="Ruta de la canción para buscar subtítulos (.ass o .lrc)"),
) -> Response:
	"""Sirve la letra sincronizada (.ass prioritario para word-by-word o .lrc de respaldo)."""
	state = get_container().ensure_orchestrator()
	is_radio = state.is_radio_announcement(path) if (state and hasattr(state, "is_radio_announcement")) else False
	path_to_id = getattr(state, "path_to_id", {}) if state else {}
	tracks_cache = getattr(state, "tracks_cache", []) if state else []

	if not is_radio and path not in path_to_id and not any(t.get("path") == path for t in tracks_cache):
		return Response(status_code=404)

	headers = (
		{"Cache-Control": "no-store, no-cache, must-revalidate"}
		if is_radio
		else {"Cache-Control": "public, max-age=600, must-revalidate"}
	)

	if is_saf_uri(path):
		sibling = await asyncio.to_thread(
			get_storage_backend(path).read_sibling_lyrics, path, extensions=(".ass", ".lrc")
		)
		if sibling is None:
			return Response(status_code=404)
		return Response(content=sibling[1], media_type="text/plain; charset=utf-8", headers=headers)

	# Buscamos subtítulos (.ass prioritario para karaoke palabra por palabra, o .lrc de respaldo)
	from app.infrastructure.media.mixer import resolve_subtitle_path

	pre_path = getattr(state, "radio_pregenerated_path", None) if (state and is_radio) else None
	target_path = await asyncio.to_thread(
		resolve_subtitle_path, path, fallback_path=pre_path, extensions=(".ass", ".lrc")
	)

	if not target_path or not target_path.exists():
		return Response(status_code=404)

	return FileResponse(
		target_path,
		media_type="text/plain; charset=utf-8",
		headers=headers,
	)
