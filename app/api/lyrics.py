"""
Enrutador de la API para gestión y edición de subtítulos ASS (/api/lyrics).
Provee endpoints de búsqueda en BetterLyrics, configuración de token y guardado con conversión previa.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.domain.lyrics.converter import LyricsAssConverter
from app.domain.lyrics.service import get_lyrics_service

router = APIRouter(prefix="/lyrics", tags=["lyrics"])


class TokenRequest(BaseModel):
	token: str


class SaveLyricsRequest(BaseModel):
	path: str
	content: str
	format: str = "ass"


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
	Si solo existe un .lrc en disco, lo convierte a .ass antes de devolverlo.
	"""
	p = Path(path)
	base_path = p.with_suffix("")

	ass_path = base_path.with_suffix(".ass")
	lrc_path = base_path.with_suffix(".lrc")

	if ass_path.exists():
		try:
			content = ass_path.read_text(encoding="utf-8")
			return {"exists": True, "content": content, "format": "ass", "path": str(ass_path)}
		except Exception as e:
			raise HTTPException(status_code=500, detail=f"Error al leer .ass: {e}")

	if lrc_path.exists():
		try:
			lrc_raw = lrc_path.read_text(encoding="utf-8")
			ass_converted, _ = LyricsAssConverter.convert_source_to_ass(
				lrc_raw,
				source_key="local_lrc",
				title=p.stem or "Canción",
				artist="Artista",
			)
			if ass_converted:
				return {"exists": True, "content": ass_converted, "format": "ass", "path": str(ass_path)}
		except Exception as e:
			raise HTTPException(status_code=500, detail=f"Error al convertir .lrc a .ass: {e}")

	return {"exists": False, "content": "", "format": "", "path": str(ass_path)}


@router.post("/save")
async def save_lyrics_content(payload: SaveLyricsRequest) -> dict:
	"""
	Guarda el archivo de letras personalizado directamente en el disco.
	"""
	p = Path(payload.path)
	target_ext = f".{payload.format.lstrip('.')}"
	target_path = p.with_suffix(target_ext)

	try:
		# Creamos carpetas contenedor si no existiesen
		target_path.parent.mkdir(parents=True, exist_ok=True)
		target_path.write_text(payload.content, encoding="utf-8")
		return {
			"success": True,
			"path": str(target_path),
			"message": "Letra guardada con éxito en la pulpería",
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"No se pudo guardar la letra: {e}")
