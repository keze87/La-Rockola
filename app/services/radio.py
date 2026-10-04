"""
Servicio de locución automática DJ Carpincho.
Integra Edge-TTS, mezcla con cortina en caliente, pronóstico meteorológico y archivado de guiones.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
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
try:
	from scripts.binary_utils import check_internet_async
except ImportError:
	try:
		from binary_utils import check_internet_async
	except ImportError:

		async def check_internet_async(timeout: float = 0.8) -> bool:
			return True


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

	async def apply_hot_mix_to_announcement(
		self,
		voice_file: Path,
		out_file: Path,
		title: str,
		next_track_path: str | None = None,
		bg_offset: float = 0.0,
	) -> bool:
		"""Superpone la cortina musical en caliente sobre la voz usando la pista que efectivamente suena después."""
		mixed_ok = False
		mixer = globals().get("mix_announcement_with_bg_track")
		embedder = globals().get("embed_cover_art_in_mp3")
		if next_track_path and Path(next_track_path).is_file() and mixer is not None:
			try:
				mixed = await asyncio.to_thread(
					mixer,
					voice_file,
					out_file,
					next_track_path,
					bg_offset,
					0.1,
					10.0,
				)
				if mixed:
					if embedder is not None:
						cover_getter = globals().get("get_carpincho_cover_path")
						cover_p = cover_getter() if cover_getter else None
						await asyncio.to_thread(
							embedder,
							out_file,
							cover_p,
							title,
							"Carpincho Locutor 🎙️",
							"La Rockola del Carpincho",
						)
					mixed_ok = True
			except Exception as mix_err:
				logger.debug(f"Fallo en mezcla en caliente con '{next_track_path}': {mix_err}")

		# Copiar subtítulos si existen
		for ext in (".lrc", ".srt"):
			sub_src = voice_file.with_suffix(ext)
			sub_dst = out_file.with_suffix(ext)
			if sub_src.is_file():
				try:
					shutil.copyfile(sub_src, sub_dst)
				except Exception as copy_sub_err:
					logger.debug(f"Error copiando subtítulo {sub_src} a {sub_dst}: {copy_sub_err}")

		if not mixed_ok:
			try:
				shutil.copyfile(voice_file, out_file)
			except Exception as copy_err:
				logger.error(f"Error copiando archivo de locución {voice_file} a {out_file}: {copy_err}")
				return False
		return True

	def prune_radio_archive(self, archive_dir: Path, max_files: int = 50) -> int:
		"""Elimina guiones históricos viejos y residuales en el directorio de archivo."""
		if max_files <= 0 or not archive_dir.is_dir():
			return 0
		try:
			for mp3 in archive_dir.glob("radio_*.mp3"):
				try:
					mp3.unlink(missing_ok=True)
				except Exception:
					pass

			txt_files = sorted(
				archive_dir.glob("radio_*.txt"),
				key=lambda p: (p.stat().st_mtime, p.name),
			)
			pruned = 0
			if len(txt_files) > max_files:
				for txt in txt_files[: len(txt_files) - max_files]:
					txt.unlink(missing_ok=True)
					pruned += 1
			return pruned
		except Exception as e:
			logger.debug(f"Error podando archivo histórico de locuciones: {e}")
			return 0

	def archive_radio_announcement(
		self,
		archive_dir: Path,
		script_text: str = "",
		display_title: str = "",
		max_files: int = 50,
	) -> Path | None:
		"""Guarda el guion .txt en el archivo histórico con marca temporal."""
		try:
			archive_dir.mkdir(parents=True, exist_ok=True)
			from datetime import UTC, datetime

			now = datetime.now(UTC).astimezone()
			ts_str = now.strftime("%Y-%m-%d_%H-%M-%S")
			dest_txt = archive_dir / f"radio_{ts_str}.txt"
			if dest_txt.exists():
				dest_txt = archive_dir / f"radio_{ts_str}_{now.microsecond:06d}.txt"

			header = f"Título: {display_title}\nFecha: {now.isoformat()}\n\n" if display_title else ""
			dest_txt.write_text(f"{header}{script_text.strip()}\n", encoding="utf-8")
			logger.debug(f"📻 Guion radial archivado en: {dest_txt.name}")
			self.prune_radio_archive(archive_dir, max_files=max_files)
			return dest_txt
		except Exception as e:
			logger.debug(f"No se pudo archivar el guion radial: {e}")
			return None
