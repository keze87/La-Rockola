"""
Enrutador de la API para gestión y edición de subtítulos ASS (/api/lyrics).
Provee endpoints de búsqueda, configuración de token y guardado con conversión previa.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/lyrics", tags=["lyrics"])

# Memoria simulada para el token durante la etapa de maquetas
_mock_token_store = {
	"token": "mock_jwt_token_configured",
	"hours_remaining": 72,
	"status_text": "Token de BetterLyrics listo y al día (Simulado)",
}


class TokenRequest(BaseModel):
	token: str


class SaveLyricsRequest(BaseModel):
	path: str
	content: str
	format: str = "ass"


def _generate_mock_ass(title: str, artist: str, provider: str) -> str:
	"""Genera un archivo ASS simulado con estilos y líneas de diálogo para pruebas."""
	return (
		"[Script Info]\n"
		f"; Letra adaptada por La Rockola del Carpincho ({provider})\n"
		f"Title: {title}\n"
		f"Original Artist: {artist}\n"
		"ScriptType: v4.00+\n"
		"WrapStyle: 0\n"
		"ScaledBorderAndShadow: yes\n"
		"YCbCr Matrix: None\n"
		"PlayResX: 1920\n"
		"PlayResY: 1080\n"
		"\n"
		"[V4+ Styles]\n"
		"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
		"Style: Default,Rubik,48,&H00FFFFFF,&H0050C878,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,50,1\n"
		"\n"
		"[Events]\n"
		"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
		"Dialogue: 0,0:00:59.97,0:01:02.50,Default,,0,0,0,,{\\kf40}Wan{\\kf50}na {\\kf60}play {\\kf70}ya\n"
		"Dialogue: 0,0:01:02.50,0:01:07.92,Default,,0,0,0,,{\\kf50}Wan{\\kf50}na {\\kf60}play {\\kf70}ya\n"
		"Dialogue: 0,0:01:07.92,0:01:12.60,Default,,0,0,0,,{\\kf80}Ooh-{\\kf90}oh\n"
		"Dialogue: 0,0:01:12.95,0:01:17.80,Default,,0,0,0,,{\\kf35}You {\\kf40}could{\\kf30}n't {\\kf45}wait {\\kf30}to {\\kf35}see {\\kf35}me {\\kf60}out\n"
		"Dialogue: 0,0:01:21.17,0:01:26.43,Default,,0,0,0,,{\\kf30}I'm {\\kf40}real {\\kf50}qui{\\kf30}et {\\kf30}when {\\kf40}you {\\kf40}run {\\kf30}your {\\kf60}mouth\n"
		"Dialogue: 0,0:01:28.55,0:01:30.67,Default,,0,0,0,,{\\kf50}Lock {\\kf60}eyes\n"
		"Dialogue: 0,0:01:30.67,0:01:32.56,Default,,0,0,0,,{\\kf50}Walk {\\kf60}by\n"
		"Dialogue: 0,0:01:32.58,0:01:35.32,Default,,0,0,0,,{\\kf30}Can't {\\kf40}help {\\kf30}but {\\kf50}feel\n"
		"Dialogue: 0,0:01:37.01,0:01:43.95,Default,,0,0,0,,{\\kf50}Un{\\kf60}u{\\kf40}su{\\kf50}al, {\\kf30}are {\\kf30}you {\\kf40}for {\\kf80}real?\n"
		"Dialogue: 0,0:01:46.60,0:01:48.61,Default,,0,0,0,,{\\kf30}I {\\kf30}kin{\\kf30}da {\\kf40}hate {\\kf30}you, {\\kf40}but\n"
		"Dialogue: 0,0:01:48.73,0:01:53.93,Default,,0,0,0,,{\\kf30}It {\\kf30}does{\\kf30}n't {\\kf40}mat{\\kf30}ter, {\\kf30}let {\\kf30}me {\\kf80}dance\n"
		"Dialogue: 0,0:01:55.10,0:02:02.58,Default,,0,0,0,,{\\kf30}You {\\kf30}seem {\\kf30}so {\\kf40}mis{\\kf30}er{\\kf30}able, {\\kf30}it {\\kf30}does{\\kf30}n't {\\kf40}mat{\\kf30}ter, {\\kf30}let {\\kf30}me {\\kf80}dance\n"
		"Dialogue: 0,0:02:03.00,0:02:08.68,Default,,0,0,0,,{\\kf40}Feel {\\kf40}it {\\kf40}in {\\kf40}my {\\kf50}bones, {\\kf50}writ{\\kf40}ten {\\kf40}in {\\kf60}blood\n"
		"Dialogue: 0,0:02:11.03,0:02:17.20,Default,,0,0,0,,{\\kf40}I {\\kf40}don't {\\kf40}need {\\kf40}you, {\\kf40}I {\\kf40}don't {\\kf40}need {\\kf30}a{\\kf30}ny{\\kf60}one\n"
	)


@router.get("/token")
async def get_token_status() -> dict:
	"""Devuelve el estado del token de BetterLyrics."""
	has_token = bool(_mock_token_store.get("token"))
	return {
		"is_configured": has_token,
		"status_text": _mock_token_store.get("status_text", "Sin token configurado"),
		"hours_remaining": _mock_token_store.get("hours_remaining", 0),
	}


@router.post("/token")
async def save_token(payload: TokenRequest) -> dict:
	"""Almacena un nuevo token de BetterLyrics validando la entrada."""
	tok = payload.token.strip()
	if not tok:
		raise HTTPException(status_code=400, detail="El token no puede estar vacío")

	_mock_token_store["token"] = tok
	_mock_token_store["hours_remaining"] = 72
	_mock_token_store["status_text"] = "Token configurado de primera"
	return {
		"success": True,
		"status_text": _mock_token_store["status_text"],
		"hours_remaining": _mock_token_store["hours_remaining"],
	}


@router.get("/search")
async def search_lyrics(
	title: str = Query(..., description="Título de la canción"),
	artist: str = Query(..., description="Artista de la canción"),
	album: str | None = Query(None, description="Álbum opcional"),
	duration: int | None = Query(None, description="Duración en segundos"),
) -> dict:
	"""
	Simula la búsqueda en BetterLyrics devolviendo los proveedores ya convertidos a ASS.
	El frontend nunca realiza conversiones de formato.
	"""
	# Generamos variantes simuladas para cada proveedor de la carga de BetterLyrics
	providers = [
		{
			"provider": "binimum",
			"name": "Apple Music (binimum) - Sincronizado palabra por palabra",
			"has_syllables": True,
			"ass": _generate_mock_ass(title, artist, "Apple Music / binimum"),
		},
		{
			"provider": "lrclib",
			"name": "LRCLib - Sincronizado por línea",
			"has_syllables": False,
			"ass": _generate_mock_ass(title, artist, "LRCLib"),
		},
		{
			"provider": "musixmatch",
			"name": "Musixmatch",
			"has_syllables": False,
			"ass": _generate_mock_ass(title, artist, "Musixmatch"),
		},
		{
			"provider": "qq",
			"name": "QQ Music - Letras sincronizadas",
			"has_syllables": True,
			"ass": _generate_mock_ass(title, artist, "QQ Music"),
		},
		{
			"provider": "kugou",
			"name": "KuGou",
			"has_syllables": False,
			"ass": _generate_mock_ass(title, artist, "KuGou"),
		},
	]

	return {
		"title": title,
		"artist": artist,
		"providers": providers,
	}


@router.get("/content")
async def get_lyrics_content(
	path: str = Query(..., description="Ruta de la pista de audio"),
) -> dict:
	"""
	Obtiene el contenido actual del archivo .ass o .lrc asociado a la pista.
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
			content = lrc_path.read_text(encoding="utf-8")
			return {"exists": True, "content": content, "format": "lrc", "path": str(lrc_path)}
		except Exception as e:
			raise HTTPException(status_code=500, detail=f"Error al leer .lrc: {e}")

	# Si no existe en disco, al ser endpoint simulado devolvemos un archivo .ass simulado
	track_title = p.stem or "Canción"
	mock_content = _generate_mock_ass(track_title, "Artista", "Mock Local")
	return {"exists": True, "content": mock_content, "format": "ass", "path": str(ass_path)}


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
