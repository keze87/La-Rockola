"""
Paquete de procesamiento de medios, caché TTS y mezcla con FFmpeg.
"""

from app.infrastructure.media.mixer import (
	build_lrc_content,
	build_srt_content,
	embed_cover_art_in_mp3,
	estimate_mp3_duration,
	format_lrc_timestamp,
	format_srt_timestamp,
	get_audio_duration,
	get_carpincho_cover_path,
	is_valid_mp3_file,
	is_valid_mp3_stream,
	mix_announcement_with_bg_track,
)
from app.infrastructure.media.tts_cache import (
	get_cache_key,
	get_cached_audio,
	get_cached_audio_by_category,
	init_tts_cache_db,
	prune_tts_cache_db,
	save_cached_audio,
	synthesize_segment,
)

__all__ = [
	"HAS_EDGE_TTS",
	"build_lrc_content",
	"build_srt_content",
	"embed_cover_art_in_mp3",
	"estimate_mp3_duration",
	"format_lrc_timestamp",
	"format_srt_timestamp",
	"get_audio_duration",
	"get_cache_key",
	"get_cached_audio",
	"get_cached_audio_by_category",
	"get_carpincho_cover_path",
	"init_tts_cache_db",
	"is_valid_mp3_file",
	"is_valid_mp3_stream",
	"mix_announcement_with_bg_track",
	"prune_tts_cache_db",
	"save_cached_audio",
	"synthesize_segment",
]
