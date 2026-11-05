"""
Enrutador de la API para gestión y edición de subtítulos ASS (/api/lyrics).
Provee endpoints de búsqueda en BetterLyrics, configuración de token y guardado con conversión previa.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.container import get_container
from app.domain.lyrics.converter import LyricsAssConverter
from app.domain.lyrics.service import get_lyrics_service

logger = logging.getLogger("RockolaCarpincho")

router = APIRouter(prefix="/lyrics", tags=["lyrics"])


class TokenRequest(BaseModel):
	token: str


class SaveLyricsRequest(BaseModel):
	path: str
	content: str
	format: Literal["ass", "lrc"] = "ass"


def _is_allowed_track_path(raw_path: str) -> bool:
	"""
	Un path es válido si, ya resuelto (symlinks y '..' incluidos), cae dentro de alguna carpeta
	de música configurada o coincide con una pista conocida de la biblioteca.
	"""
	if not raw_path or raw_path.startswith(("http://", "https://")):
		return False
	container = get_container()
	resolved = Path(raw_path).expanduser().resolve()

	roots = [container.settings.music_dir, container.settings.music_dir2]
	for root in roots:
		if root and resolved.is_relative_to(Path(root).expanduser().resolve()):
			return True

	state = container.orchestrator
	for track in getattr(state, "tracks_cache", None) or []:
		track_path = track.get("path")
		is_local = bool(track_path) and not str(track_path).startswith(("http://", "https://"))
		if is_local and Path(track_path).expanduser().resolve() == resolved:
			return True
	return False


def _require_track_path(raw_path: str) -> Path:
	if not _is_allowed_track_path(raw_path):
		raise HTTPException(status_code=403, detail="Ruta fuera de las carpetas de música")
	return Path(raw_path).expanduser().resolve()


@router.get("/token")
async def get_lyrics_token_status() -> dict:
	"""Devuelve el estado actual del token de BetterLyrics."""
	service = get_lyrics_service()
	return service.get_token_status()


@router.post("/token")
async def set_lyrics_token(payload: TokenRequest) -> dict:
	"""Configura y persiste el token de BetterLyrics (soporta JWT directo o comando cURL)."""
	raw = payload.token.strip()
	if not raw:
		raise HTTPException(status_code=400, detail="Token vacío")

	service = get_lyrics_service()
	result = service.set_token(raw)
	if not result.get("success"):
		raise HTTPException(status_code=400, detail=result.get("status_text", "Token inválido"))

	return {
		"success": True,
		"status_text": result["status_text"],
		"hours_remaining": result["hours_remaining"],
	}


@router.get("/search")
async def search_lyrics(
	title: str = Query(..., description="Título de la canción"),
	artist: str = Query(..., description="Artista de la canción"),
	album: str | None = Query(None, description="Álbum opcional"),
	duration: int | None = Query(None, description="Duración en segundos"),
	force: bool = Query(False, description="Forzar recarga omitiendo caché"),
) -> dict:
	"""
	Consulta BetterLyrics y devuelve todos los proveedores con letras ya convertidas a ASS.
	El frontend nunca realiza conversiones de formato.
	"""
	service = get_lyrics_service()
	return await service.search_lyrics(
		title=title,
		artist=artist,
		album=album,
		duration=duration,
		force=force,
	)


@router.get("/content")
async def get_lyrics_content(
	path: str = Query(..., description="Ruta de la pista de audio"),
) -> dict:
	"""
	Obtiene el contenido actual del archivo .ass asociado a la pista.
	Solo se consideran letras existentes si existe un archivo .ass (con soporte palabra por palabra).
	"""
	p = _require_track_path(path)
	base_path = p.with_suffix("")
	ass_path = base_path.with_suffix(".ass")

	if ass_path.exists():
		try:
			content = ass_path.read_text(encoding="utf-8")
			return {"exists": True, "content": content, "format": "ass", "path": str(ass_path)}
		except Exception as e:
			raise HTTPException(status_code=500, detail=f"Error al leer .ass: {e}")

	return {"exists": False, "content": "", "format": "", "path": str(ass_path)}


@router.post("/save")
async def save_lyrics_content(payload: SaveLyricsRequest) -> dict:
	"""
	Guarda el archivo de letras personalizado directamente en el disco.
	Si se guarda un .ass y la pista no tiene un .lrc preexistente,
	genera automáticamente un .lrc complementario para otros reproductores.
	"""
	p = _require_track_path(payload.path)
	target_ext = f".{payload.format}"
	target_path = p.with_suffix(target_ext)

	try:
		# Creamos carpetas contenedor si no existiesen
		target_path.parent.mkdir(parents=True, exist_ok=True)
		target_path.write_text(payload.content, encoding="utf-8")

		# Si guardamos un ASS y no existe un .lrc previo, generamos uno complementario
		if target_ext.lower() == ".ass":
			lrc_path = p.with_suffix(".lrc")
			if not lrc_path.exists():
				try:
					lrc_content = LyricsAssConverter.ass_to_lrc(payload.content)
					if lrc_content.strip():
						lrc_path.write_text(lrc_content, encoding="utf-8")
						logger.info(f"Generado .lrc complementario para otros reproductores: {lrc_path}")
				except Exception as lrc_err:
					logger.warning(f"No se pudo generar el .lrc complementario: {lrc_err}")

		return {
			"success": True,
			"path": str(target_path),
			"message": "Letra guardada con éxito en la pulpería",
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"No se pudo guardar la letra: {e}")
