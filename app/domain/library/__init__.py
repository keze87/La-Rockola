"""
Dominio de biblioteca musical: hash inteligente, mood acústico, entidad Track y escáner.
"""

from app.domain.library.hasher import compare_fps, generate_smart_hash, parse_fp
from app.domain.library.models import Track, get_track_duration_seconds, parse_duration_str
from app.domain.library.mood import calculate_mood_scores, extract_audio_features_ffmpeg, is_mood_available
from app.domain.library.service import LibraryService

__all__ = [
	"LibraryService",
	"Track",
	"calculate_mood_scores",
	"compare_fps",
	"extract_audio_features_ffmpeg",
	"generate_smart_hash",
	"get_track_duration_seconds",
	"is_mood_available",
	"parse_duration_str",
	"parse_fp",
]
