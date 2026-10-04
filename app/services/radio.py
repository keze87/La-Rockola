"""
Servicio de locución automática DJ Carpincho.
Integra Edge-TTS, mezcla con cortina en caliente, pronóstico meteorológico y archivado de guiones.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("RockolaCarpincho")

try:
	from scripts.radio_announcer import (
		DEFAULT_WEATHER_LOCATION,
		HAS_EDGE_TTS,
		RadioAnnouncementResult,
		create_radio_announcement,
		embed_cover_art_in_mp3,
		get_carpincho_cover_path,
		is_valid_mp3_file,
		is_valid_mp3_stream,
		mix_announcement_with_bg_track,
	)
except ImportError:
	try:
		from radio_announcer import (
			DEFAULT_WEATHER_LOCATION,
			HAS_EDGE_TTS,
			RadioAnnouncementResult,
			create_radio_announcement,
			embed_cover_art_in_mp3,
			get_carpincho_cover_path,
			is_valid_mp3_file,
			is_valid_mp3_stream,
			mix_announcement_with_bg_track,
		)
	except ImportError:
		HAS_EDGE_TTS = False
		RadioAnnouncementResult = None
		create_radio_announcement = None
		get_carpincho_cover_path = None
		mix_announcement_with_bg_track = None
		embed_cover_art_in_mp3 = None
		is_valid_mp3_file = None
		is_valid_mp3_stream = None
		DEFAULT_WEATHER_LOCATION = "San Miguel de Tucumán"


class RadioService:
	"""Orquesta la locución y producción radial de DJ Carpincho."""

	def __init__(self, weather_location: str | None = None) -> None:
		self.weather_location = weather_location or DEFAULT_WEATHER_LOCATION
		self.has_edge_tts = HAS_EDGE_TTS

	@property
	def is_available(self) -> bool:
		"""Indica si el sistema de síntesis TTS está operativo."""
		return bool(self.has_edge_tts and create_radio_announcement is not None)

	async def synthesize_announcement(
		self,
		current_track: dict[str, Any] | None,
		next_track: dict[str, Any] | None,
		location: str | None = None,
	) -> Any:
		"""Genera una locución radial mezclada con cortina."""
		if not self.is_available:
			return None
		target_loc = location or self.weather_location
		return await create_radio_announcement(
			current_track=current_track,
			next_track=next_track,
			location=target_loc,
		)
