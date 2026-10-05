"""
Servicio de locución automática DJ Carpincho.
Integra Edge-TTS, pregeneración anticipada, mezcla con cortina en caliente,
control de caducidad (15 min tras pausa prolongada), pronóstico meteorológico y archivado de guiones.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
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
		DEFAULT_WEATHER_LOCATION = "San Miguel de Tucumán"
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


RADIO_PREGENERATION_MAX_AGE_SECONDS: float = 15.0 * 60.0  # 15 minutos de caducidad tras pausa prolongada


def _is_valid_radio_mp3_file(path: Path | str) -> bool:
	"""Valida que el archivo de locución exista y su cabecera corresponda a un MP3 válido."""
	if is_valid_mp3_file is not None:
		return is_valid_mp3_file(path)
	try:
		p = Path(path)
		if not p.is_file() or p.stat().st_size < 4:
			return False
		with p.open("rb") as f:
			head = f.read(10)
		return bool(head.startswith(b"ID3") or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0))
	except Exception:
		return False


def _unpack_radio_result(res: Any) -> tuple[bool, str, str, str]:
	"""Normaliza el resultado devuelto por create_radio_announcement."""
	ok = res.ok if hasattr(res, "ok") else bool(res[0])
	title = res.display_title if hasattr(res, "display_title") else str(res[1])
	script = res.script if hasattr(res, "script") else str(res[2])
	err = res.error if hasattr(res, "error") else (script if not ok else "")
	return ok, title, script, err or ""


class RadioService:
	"""Orquesta la locución y producción radial de DJ Carpincho."""

	def __init__(self, weather_location: str | None = None) -> None:
		self.weather_location = weather_location or DEFAULT_WEATHER_LOCATION
		self.announcement_path = Path(tempfile.gettempdir()) / "radio_announcement.mp3"
		self.pregenerated_path = Path(tempfile.gettempdir()) / "radio_pregenerated.mp3"
		self.archive_dir = Path(tempfile.gettempdir()) / "la_rockola_radio_archive"
		self.archive_max_files = 60
		self.pregeneration_task: asyncio.Task | None = None
		self.pregenerated_announcement: dict[str, Any] | None = None

	@property
	def is_available(self) -> bool:
		"""Indica si el sistema de síntesis TTS está operativo evaluando el estado del módulo."""
		return bool(HAS_EDGE_TTS and create_radio_announcement is not None)

	def cancel_pregeneration(self) -> None:
		"""Cancela cualquier pregeneración en curso de la locución radial y limpia archivos parciales."""
		if self.pregeneration_task and not self.pregeneration_task.done():
			self.pregeneration_task.cancel()
		self.pregeneration_task = None
		self.pregenerated_announcement = None
		if self.pregenerated_path:
			try:
				p = Path(self.pregenerated_path)
				if p.exists():
					p.unlink(missing_ok=True)
			except Exception as e:
				logger.debug(f"Error borrando archivo parcial de pregeneración: {e}")

	def start_pregeneration(
		self,
		track_duration: float = 0.0,
		location: str | None = None,
		pregenerated_path: Path | str | None = None,
	) -> None:
		"""
		Dispara la síntesis y procesamiento de la locución radial en segundo plano
		al comienzo de la canción, calculando el cuarto horario estimado en el que terminará el tema.
		"""
		if not self.is_available or create_radio_announcement is None:
			return

		self.cancel_pregeneration()
		target_path = Path(pregenerated_path) if pregenerated_path else self.pregenerated_path
		target_loc = location or self.weather_location

		async def _do_pregeneration():
			now = datetime.now(UTC).astimezone()
			finish_dt = now + timedelta(seconds=max(0.0, track_duration)) if track_duration > 0 else now

			try:
				logger.info("📻 Carpincho Locutor: Iniciando pregeneración anticipada al comienzo de la canción...")
				res = await create_radio_announcement(
					str(target_path),
					dt=finish_dt,
					bg_track_path=None,
					weather_location=target_loc,
				)
				res_ok, res_title, res_script, res_err = _unpack_radio_result(res)

				if res_ok:
					self.pregenerated_announcement = {
						"path": str(target_path),
						"display_title": res_title,
						"script": res_script,
						"created_at": time.time(),
					}
					logger.info(
						"📻 Carpincho Locutor: Pregeneración de voz lista con anticipación para el final del tema."
					)
				else:
					logger.debug(f"Pregeneración radial no completada: {res_err}")
			except asyncio.CancelledError:
				logger.debug("Pregeneración radial cancelada.")
			except Exception as e:
				logger.debug(f"Excepción en pregeneración radial: {e}")

		self.pregeneration_task = asyncio.create_task(_do_pregeneration())

	async def get_or_synthesize(
		self,
		next_track_path: str | None = None,
		bg_offset: float = 0.0,
		on_synthesis_status: Callable[[bool], Any] | None = None,
		location: str | None = None,
		announcement_path: Path | str | None = None,
	) -> tuple[bool, str, str, str | None]:
		"""
		Obtiene la locución pregenerada o realiza síntesis en caliente, aplicando
		control de caducidad (15 min tras pausa prolongada) y mezcla con cortina.
		"""
		if not self.is_available or create_radio_announcement is None:
			return False, "", "", "Servicio de radio no disponible"

		target_ann_path = Path(announcement_path) if announcement_path else self.announcement_path
		target_loc = location or self.weather_location
		ok = False
		display_title = ""
		script = ""
		radio_err = None

		# 1. Comprobar si ya está lista la pregeneración de fondo (0 ms de latencia)
		if self.pregenerated_announcement:
			pre = self.pregenerated_announcement
			pre_created_at = pre.get("created_at")
			pre_age = (time.time() - pre_created_at) if pre_created_at is not None else 0.0
			if pre_age > RADIO_PREGENERATION_MAX_AGE_SECONDS:
				logger.info(
					f"📻 Carpincho Locutor: La locución pregenerada expiró ({pre_age / 60:.1f} min > 15 min tras pausa). Descartando para sintetizar locución fresca..."
				)
			else:
				pre_p = Path(pre["path"])
				if _is_valid_radio_mp3_file(pre_p):
					if await self.apply_hot_mix_to_announcement(
						pre_p,
						target_ann_path,
						pre["display_title"],
						next_track_path=next_track_path,
						bg_offset=bg_offset,
					):
						ok = True
						display_title = pre["display_title"]
						script = pre.get("script", "")
						logger.info(
							"⚡ Carpincho Locutor: Transición con locución pregenerada y mezcla de cortina en caliente."
						)
				else:
					logger.warning(
						"📻 Carpincho Locutor: El archivo pregenerado está incompleto o no es un MP3 válido. Descartando..."
					)
			self.pregenerated_announcement = None

		# 2. Si la tarea de pregeneración sigue corriendo, esperarla brevemente
		if not ok and self.pregeneration_task and not self.pregeneration_task.done():
			try:
				logger.info("📻 Carpincho Locutor: Esperando finalización de pregeneración en curso...")
				if on_synthesis_status:
					res_notify = on_synthesis_status(True)
					if asyncio.iscoroutine(res_notify):
						await res_notify
				await asyncio.wait_for(asyncio.shield(self.pregeneration_task), timeout=3.0)
				if self.pregenerated_announcement:
					pre = self.pregenerated_announcement
					pre_created_at = pre.get("created_at")
					pre_age = (time.time() - pre_created_at) if pre_created_at is not None else 0.0
					if pre_age > RADIO_PREGENERATION_MAX_AGE_SECONDS:
						logger.info(
							f"📻 Carpincho Locutor: La locución pregenerada expiró ({pre_age / 60:.1f} min > 15 min tras pausa). Descartando..."
						)
					else:
						pre_p = Path(pre["path"])
						if _is_valid_radio_mp3_file(pre_p):
							if await self.apply_hot_mix_to_announcement(
								pre_p,
								target_ann_path,
								pre["display_title"],
								next_track_path=next_track_path,
								bg_offset=bg_offset,
							):
								ok = True
								display_title = pre["display_title"]
								script = pre.get("script", "")
						else:
							logger.warning(
								"📻 Carpincho Locutor: El archivo pregenerado esperado está incompleto o no es un MP3 válido. Descartando..."
							)
					self.pregenerated_announcement = None
			except Exception as wait_e:
				logger.debug(f"Espera de pregeneración agotada o falló: {wait_e}")
			finally:
				if on_synthesis_status:
					res_notify = on_synthesis_status(False)
					if asyncio.iscoroutine(res_notify):
						await res_notify

		# 3. Fallback: síntesis en caliente si no hubo pregeneración
		if not ok:
			logger.info("🎙️ Carpincho Locutor: Sintetizando locución fresca...")
			if on_synthesis_status:
				res_notify = on_synthesis_status(True)
				if asyncio.iscoroutine(res_notify):
					await res_notify

			try:
				res = await create_radio_announcement(
					str(target_ann_path),
					bg_track_path=next_track_path,
					bg_offset=bg_offset,
					bg_volume=0.1,
					weather_location=target_loc,
				)
				ok, display_title, script, radio_err = _unpack_radio_result(res)
			except Exception as e:
				ok = False
				display_title = ""
				script = ""
				radio_err = f"{type(e).__name__}: {e}"
			finally:
				if on_synthesis_status:
					res_notify = on_synthesis_status(False)
					if asyncio.iscoroutine(res_notify):
						await res_notify

		return ok, display_title, script, radio_err

	async def synthesize_announcement(
		self,
		current_track: dict[str, Any] | None,
		next_track: dict[str, Any] | None,
		location: str | None = None,
	) -> Any:
		"""Genera una locución radial mezclada con cortina."""
		if not self.is_available or create_radio_announcement is None:
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

		if next_track_path and Path(next_track_path).is_file() and mix_announcement_with_bg_track is not None:
			try:
				mixed = await asyncio.to_thread(
					mix_announcement_with_bg_track,
					voice_file,
					out_file,
					next_track_path,
					bg_offset,
					0.1,
					10.0,
				)
				if mixed:
					if embed_cover_art_in_mp3 is not None:
						cover_p = get_carpincho_cover_path() if get_carpincho_cover_path is not None else None
						await asyncio.to_thread(
							embed_cover_art_in_mp3,
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
