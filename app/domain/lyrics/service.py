"""
Servicio y cliente HTTP para BetterLyrics (DacubeKing API).
Maneja autenticación JWT, caché en disco y conversión de respuestas a ASS.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_config_path, get_settings, load_config, save_config
from app.domain.lyrics.converter import LyricsAssConverter

logger = logging.getLogger("RockolaCarpincho")

DEFAULT_BETTERLYRICS_TOKEN = ""


class BetterLyricsService:
	"""Gestiona el token de BetterLyrics, la caché en disco y las consultas a la API."""

	BASE_URL = "https://lyrics.api.dacubeking.com/v2/lyrics"

	def __init__(self, cache_dir: Path | None = None) -> None:
		self._cache_dir = cache_dir or (Path(tempfile.gettempdir()) / "carpincho_betterlyrics_cache")
		self._cache_dir.mkdir(parents=True, exist_ok=True)
		self._memory_token: str | None = None

	@staticmethod
	def extract_token(text: str) -> str:
		"""
		Extrae el token JWT desde texto plano, comandos cURL o cabeceras Authorization.
		"""
		if not text:
			return ""
		raw = text.strip()

		# 1. Parámetro token= en query string o --data-raw de cURL
		m = re.search(r"token=([a-zA-Z0-9_\-\.]+)", raw)
		if m:
			cand = m.group(1).strip()
			if cand.startswith("eyJ"):
				return cand

		# 2. Cabecera Authorization: Bearer
		m = re.search(r"Bearer\s+([a-zA-Z0-9_\-\.]+)", raw, re.IGNORECASE)
		if m:
			cand = m.group(1).strip()
			if cand.startswith("eyJ"):
				return cand

		# 3. JWT estándar de 3 segmentos (eyJ...)
		m = re.search(r"\b(eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+)\b", raw)
		if m:
			return m.group(1).strip()

		# 4. Token directo que empieza por eyJ
		if raw.startswith("eyJ") and len(raw) > 20:
			return raw.split()[0]

		return ""

	@staticmethod
	def parse_jwt_expiry(token_str: str) -> int | None:
		"""Decodifica el payload del JWT para extraer la fecha de expiración (exp en segundos epoch)."""
		if not token_str:
			return None
		try:
			parts = token_str.strip().split(".")
			if len(parts) >= 2:
				payload_b64 = parts[1]
				padded = payload_b64 + "=" * (-len(payload_b64) % 4)
				data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
				exp = data.get("exp")
				return int(exp) if exp is not None else None
		except Exception:
			pass
		return None

	def get_token(self) -> str:
		"""Resuelve el token activo desde memoria, variable de entorno, rockola_config.json o el default."""
		if self._memory_token:
			return self._memory_token

		env_token = os.environ.get("BETTER_LYRICS_TOKEN")
		if env_token and env_token.strip():
			return env_token.strip()

		try:
			settings = get_settings()
			if settings.better_lyrics_token and settings.better_lyrics_token.strip():
				return settings.better_lyrics_token.strip()
		except Exception:
			pass

		try:
			cfg = load_config()
			tok = cfg.get("better_lyrics_token")
			if isinstance(tok, str) and tok.strip():
				return tok.strip()
		except Exception:
			pass

		return DEFAULT_BETTERLYRICS_TOKEN

	def set_token(self, raw_input: str) -> dict[str, Any]:
		"""Extrae y persiste el token JWT en memoria y en rockola_config.json."""
		extracted = self.extract_token(raw_input)
		if not extracted:
			return {
				"success": False,
				"is_configured": False,
				"status_text": "No se encontró un token JWT válido",
				"hours_remaining": 0,
			}

		self._memory_token = extracted
		try:
			config_path = get_config_path()
			cfg = load_config(config_path)
			cfg["better_lyrics_token"] = extracted
			save_config(config_path, cfg)
			settings = get_settings()
			settings.better_lyrics_token = extracted
		except Exception as exc:
			logger.warning(f"No se pudo persistir el token en disco: {exc}")

		status = self.get_token_status(extracted)
		return {
			"success": True,
			**status,
		}

	def get_token_status(self, token: str | None = None) -> dict[str, Any]:
		"""Evalúa la validez y el tiempo restante del token configurado."""
		tok = (token.strip() if token else "") if token is not None else self.get_token()
		if not tok:
			return {
				"is_configured": False,
				"status_text": "Sin token configurado",
				"hours_remaining": 0,
			}

		exp = self.parse_jwt_expiry(tok)
		if not exp:
			return {
				"is_configured": True,
				"status_text": "Token configurado (sin fecha de expiración)",
				"hours_remaining": 24,
			}

		now = int(time.time())
		diff = exp - now
		if diff <= 0:
			exp_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
			return {
				"is_configured": False,
				"status_text": f"Token vencido el {exp_date}",
				"hours_remaining": 0,
			}

		hours = diff // 3600
		minutes = (diff % 3600) // 60
		if hours > 0:
			return {
				"is_configured": True,
				"status_text": f"Token activo ({hours}h {minutes}m restantes)",
				"hours_remaining": hours,
			}
		return {
			"is_configured": True,
			"status_text": f"Token activo ({minutes}m restantes)",
			"hours_remaining": 0,
		}

	@staticmethod
	def generate_video_id(title: str, artist: str) -> str:
		"""Genera un identificador determinístico de 11 caracteres compatible con BetterLyrics."""
		digest = hashlib.md5(f"{artist}_{title}".encode()).digest()
		return base64.urlsafe_b64encode(digest)[:11].decode("ascii")

	def _cache_key(self, artist: str, title: str, duration: int | None = None) -> str:
		raw = f"{artist.strip().lower()}|{title.strip().lower()}|{int(duration) if duration and duration > 0 else 0}"
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()

	def read_disk_cache(self, artist: str, title: str, duration: int | None = None) -> str | None:
		"""Lee la respuesta cruda de BetterLyrics desde la caché en disco si existe."""
		try:
			key = self._cache_key(artist, title, duration)
			cache_file = self._cache_dir / f"{key}.json"
			if cache_file.exists():
				data = json.loads(cache_file.read_text(encoding="utf-8"))
				content = data.get("content")
				if isinstance(content, str) and content.strip():
					return content
		except Exception as exc:
			logger.debug(f"Error leyendo caché de BetterLyrics: {exc}")
		return None

	def write_disk_cache(self, artist: str, title: str, duration: int | None, content: str) -> None:
		"""Guarda la respuesta cruda de BetterLyrics en la caché en disco."""
		try:
			key = self._cache_key(artist, title, duration)
			cache_file = self._cache_dir / f"{key}.json"
			payload = {
				"artist": artist,
				"title": title,
				"duration": duration,
				"content": content,
				"timestamp": int(time.time()),
			}
			cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
		except Exception as exc:
			logger.debug(f"Error escribiendo caché de BetterLyrics: {exc}")

	async def fetch_raw_sse(
		self,
		title: str,
		artist: str,
		album: str | None = None,
		duration: int | None = None,
		force: bool = False,
	) -> str | None:
		"""Realiza la petición HTTP POST a BetterLyrics o recupera desde caché en disco."""
		if not force:
			cached = self.read_disk_cache(artist, title, duration)
			if cached:
				return cached

		tok = self.get_token()
		if not tok:
			logger.warning("Búsqueda en BetterLyrics omitida: no hay token configurado.")
			return None

		vid = self.generate_video_id(title, artist)
		headers = {
			"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:159.0) Gecko/20100101 Firefox/159.0",
			"Referer": "https://music.youtube.com/",
			"Origin": "https://music.youtube.com",
			"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
		}

		payload_dict: dict[str, str] = {
			"videoId": vid,
			"song": title or "",
			"artist": artist or "",
			"token": tok,
			"alwaysFetchMetadata": "true" if force else "false",
		}
		if album:
			payload_dict["album"] = album
		if duration and duration > 0:
			payload_dict["duration"] = str(int(duration))

		try:
			async with httpx.AsyncClient(timeout=15.0) as client:
				resp = await client.post(
					self.BASE_URL,
					headers=headers,
					data=payload_dict,
				)
				if resp.status_code in (401, 403):
					logger.warning(f"Autenticación en BetterLyrics rechazada ({resp.status_code}).")
					return None
				if resp.status_code == 429:
					logger.warning("Límite de peticiones alcanzado en BetterLyrics (HTTP 429).")
					return None
				resp.raise_for_status()
				raw_body = resp.text

			if (
				raw_body
				and "event: provider" in raw_body
				and any(marker in raw_body for marker in ('"lyrics"', '"synced"', '"wordByWord"'))
			):
				self.write_disk_cache(artist, title, duration, raw_body)
				return raw_body
		except Exception as exc:
			logger.error(f"Fallo en la petición a BetterLyrics: {exc}")

		return None

	async def search_lyrics(
		self,
		title: str,
		artist: str,
		album: str | None = None,
		duration: int | None = None,
		force: bool = False,
	) -> dict[str, Any]:
		"""Busca letras en BetterLyrics y devuelve todos los proveedores convertidos a ASS."""
		raw_sse = await self.fetch_raw_sse(
			title=title,
			artist=artist,
			album=album,
			duration=duration,
			force=force,
		)
		if not raw_sse:
			return {
				"title": title,
				"artist": artist,
				"providers": [],
			}

		providers = LyricsAssConverter.convert_payload_to_providers(
			raw_sse,
			default_title=title,
			default_artist=artist,
		)
		return {
			"title": title,
			"artist": artist,
			"providers": providers,
		}


_global_lyrics_service: BetterLyricsService | None = None


def get_lyrics_service() -> BetterLyricsService:
	"""Devuelve la instancia singleton del servicio de letras."""
	global _global_lyrics_service
	if _global_lyrics_service is None:
		_global_lyrics_service = BetterLyricsService()
	return _global_lyrics_service
