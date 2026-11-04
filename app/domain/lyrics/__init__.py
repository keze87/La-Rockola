"""
Dominio de letras sincronizadas y subtítulos ASS.
"""

from app.domain.lyrics.converter import LyricsAssConverter
from app.domain.lyrics.service import BetterLyricsService, get_lyrics_service

__all__ = [
	"BetterLyricsService",
	"LyricsAssConverter",
	"get_lyrics_service",
]
