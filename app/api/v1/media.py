"""
Enrutador de medios: streaming de audio (/stream), portadas (/cover) y subtítulos (/lrc).
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from mutagen import File as MutagenFile

from app.core.config import get_dist_dirs
from app.core.dependencies import get_state

logger = logging.getLogger("RockolaCarpincho")
router = APIRouter(tags=["Media"])


HAS_PIL = False
try:
	from PIL import Image

	HAS_PIL = True
except ImportError:
	pass

# Caché en memoria para portadas redimensionadas y originales
_COVER_MEM_CACHE: dict[str, tuple[int, int, bytes | None, str, str]] = {}
_MAX_COVER_MEM_CACHE = 1000


def _set_cover_cache(key: str, value: tuple[int, int, bytes | None, str, str]) -> None:
	"""Inserta en el caché de portadas aplicando desalojo FIFO/LRU si se supera el límite."""
	if key in _COVER_MEM_CACHE:
		_COVER_MEM_CACHE.pop(key)
	elif len(_COVER_MEM_CACHE) >= _MAX_COVER_MEM_CACHE:
		_COVER_MEM_CACHE.pop(next(iter(_COVER_MEM_CACHE)))
	_COVER_MEM_CACHE[key] = value


def _resize_cover(cover_bytes: bytes, max_size: int) -> tuple[bytes, str]:
	"""Redimensiona la imagen conservando aspect ratio si PIL está disponible."""
	if not HAS_PIL or not cover_bytes or max_size <= 0:
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


@router.get("/cover", response_model=None)
async def serve_cover(
	path: str = Query(..., description="Ruta absoluta o relativa del archivo de audio"),
	size: int | None = Query(default=None, description="Tamaño máximo de carátula en píxeles"),
	request: Request = None,
) -> Response:
	"""Extrae la portada incrustada del archivo de audio o devuelve la predeterminada."""
	state = get_state()
	if not isinstance(size, int) or size <= 0:
		size = None

	try:
		if state and hasattr(state, "is_radio_announcement") and state.is_radio_announcement(path):
			try:
				from scripts.radio_announcer import get_carpincho_cover_path

				carpincho_img = get_carpincho_cover_path()
				if carpincho_img and carpincho_img.is_file():
					if size and size > 0 and HAS_PIL:
						c_data, c_mime = _resize_cover(carpincho_img.read_bytes(), size)
						return Response(content=c_data, media_type=c_mime)
					mime = "image/png" if carpincho_img.suffix.lower() == ".png" else "image/jpeg"
					return FileResponse(carpincho_img, media_type=mime)
			except Exception:
				pass

			# Si falló la carátula de radio_announcer, intentamos con el favicon/arte por defecto
			frontend_dir, dist_dir, _ = get_dist_dirs()
			candidates = [
				dist_dir / "favicon.png",
				frontend_dir / "public" / "favicon.png",
			]
			if hasattr(sys, "_MEIPASS"):
				candidates.append(Path(sys._MEIPASS) / "public" / "favicon.png")

			for cand in candidates:
				if cand.is_file():
					if size and size > 0 and HAS_PIL:
						c_data, c_mime = _resize_cover(cand.read_bytes(), size)
						return Response(content=c_data, media_type=c_mime)
					return FileResponse(cand, media_type="image/png")

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

		if request:
			if_none_match = request.headers.get("if-none-match")
			if if_none_match and etag in if_none_match:
				return Response(status_code=304, headers=cache_headers)

		cache_key = f"{path}:s={size}" if (size and size > 0) else path
		if cache_key in _COVER_MEM_CACHE:
			c_mtime, c_size, c_data, c_mime, _ = _COVER_MEM_CACHE[cache_key]
			if c_mtime == mtime and c_size == file_size:
				# Reubicamos la clave al final para actualizar el orden de acceso LRU
				_COVER_MEM_CACHE[cache_key] = _COVER_MEM_CACHE.pop(cache_key)
				if c_data is None:
					return Response(status_code=404, headers=cache_headers)
				return Response(content=c_data, media_type=c_mime, headers=cache_headers)

		cover_data = None
		mime_type = "image/jpeg"
		if size and size > 0 and path in _COVER_MEM_CACHE:
			c_mtime, c_size, c_data, c_mime, _ = _COVER_MEM_CACHE[path]
			if c_mtime == mtime and c_size == file_size and c_data:
				_COVER_MEM_CACHE[path] = _COVER_MEM_CACHE.pop(path)
				cover_data = c_data
				mime_type = c_mime

		if not cover_data:
			audio = MutagenFile(path)
			if not audio:
				_set_cover_cache(cache_key, (mtime, file_size, None, "image/jpeg", etag))
				return Response(status_code=404, headers=cache_headers)

			if hasattr(audio, "pictures") and audio.pictures:
				cover_data = audio.pictures[0].data
				mime_type = getattr(audio.pictures[0], "mime", "image/jpeg")
			elif hasattr(audio, "tags") and audio.tags:
				for key, tag in audio.tags.items():
					if key.startswith("APIC"):
						cover_data = tag.data
						mime_type = getattr(tag, "mime", "image/jpeg")
						break
				if not cover_data and "covr" in audio.tags:
					covr_item = audio.tags["covr"][0]
					cover_data = bytes(covr_item)
					mime_type = "image/jpeg" if cover_data.startswith(b"\xff\xd8") else "image/png"

			if not cover_data:
				_set_cover_cache(cache_key, (mtime, file_size, None, "image/jpeg", etag))
				return Response(status_code=404, headers=cache_headers)

			# Cache original
			_set_cover_cache(path, (mtime, file_size, cover_data, mime_type, etag))

		if size and size > 0:
			resized_data, r_mime = _resize_cover(cover_data, size)
			_set_cover_cache(cache_key, (mtime, file_size, resized_data, r_mime, etag))
			return Response(content=resized_data, media_type=r_mime, headers=cache_headers)

		return Response(content=cover_data, media_type=mime_type, headers=cache_headers)

	except Exception as e:
		logger.debug(f"Error procesando cover para {path}: {e}")
		return Response(status_code=404)


@router.get("/stream")
async def stream_audio(path: str = Query(..., description="Ruta de la canción a transmitir")) -> Response:
	"""Transmite el archivo de audio para reproducción local en el navegador del cliente."""
	state = get_state()
	is_radio = state.is_radio_announcement(path) if (state and hasattr(state, "is_radio_announcement")) else False
	path_to_id = getattr(state, "path_to_id", {}) if state else {}
	tracks_cache = getattr(state, "tracks_cache", []) if state else []
	if not is_radio and path not in path_to_id and not any(t.get("path") == path for t in tracks_cache):
		return Response(status_code=404)

	if not os.path.exists(path):
		return Response(status_code=404)

	return FileResponse(
		path,
		headers={
			"Accept-Ranges": "bytes",
			"Cache-Control": "public, max-age=86400, stale-while-revalidate=172800",
		},
	)


@router.get("/lrc")
async def serve_lrc(path: str = Query(..., description="Ruta de la canción para buscar subtítulos .lrc")) -> Response:
	"""Sirve la letra sincronizada .lrc si existe junto al archivo original."""
	state = get_state()
	is_radio = state.is_radio_announcement(path) if (state and hasattr(state, "is_radio_announcement")) else False
	path_to_id = getattr(state, "path_to_id", {}) if state else {}
	tracks_cache = getattr(state, "tracks_cache", []) if state else []

	# Validación de seguridad: solo servimos letras de temas en biblioteca o locuciones oficiales
	if not is_radio and path not in path_to_id and not any(t.get("path") == path for t in tracks_cache):
		return Response(status_code=404)

	lrc_path = Path(path).with_suffix(".lrc")
	if not lrc_path.exists():
		if is_radio:
			pre_path = getattr(state, "radio_pregenerated_path", None) if state else None
			if pre_path:
				pre_lrc = Path(pre_path).with_suffix(".lrc")
				if pre_lrc.exists():
					lrc_path = pre_lrc
		if not lrc_path.exists():
			return Response(status_code=404)

	headers = {"Cache-Control": "no-cache"} if is_radio else {"Cache-Control": "public, max-age=600, must-revalidate"}
	return FileResponse(
		lrc_path,
		media_type="text/plain",
		headers=headers,
	)
