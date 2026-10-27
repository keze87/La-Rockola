"""
Servicio de locución radial para La Rockola del Carpincho.
Coordina el diálogo de cabina, pronóstico meteorológico, síntesis TTS y mezcla acústica.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.radio.banks import (
	DEFAULT_BG_VOLUME,
	DEFAULT_COHOST_DISPLAY_NAME,
	DEFAULT_HOST_NAME,
	DEFAULT_RADIO_ARTIST,
	DEFAULT_RADIO_TITLE,
	DEFAULT_TTS_RETRIES,
	DEFAULT_TTS_TIMEOUT,
	DEFAULT_WEATHER_LOCATION,
	RADIO_INTROS,
	VOICE_NAMES,
	VOICE_TOMAS,
	VOICES,
	build_radio_context,
	filter_by_context,
	get_outros_for_category,
	get_outros_for_mode,
	resolve_segment_category,
)
from app.domain.radio.dialogue import (
	apply_rioplatense_tts_phonetics,
	build_radio_dialogue_plan,
	clean_subtitle_text,
	get_modular_time_segments,
	group_plan_into_speech_turns,
	select_radio_hosts,
)
from app.domain.radio.nlp import (
	get_radio_state,
	record_phrase_played,
	render_tracked_phrase,
	select_radio_phrase,
	set_radio_state,
	weighted_choice_by_recency,
)
from app.infrastructure.binaries.manager import (
	check_internet_async,  # noqa: F401
	find_binary,
	get_clean_env,
)
from app.infrastructure.media.mixer import (
	build_lrc_content,
	build_srt_content,
	embed_cover_art_in_mp3,
	get_audio_duration,
	mix_announcement_with_bg_track,
)
from app.infrastructure.media.tts_cache import (
	HAS_EDGE_TTS,
	edge_tts,
	estimate_mp3_duration,
	synthesize_segment,
)
from app.infrastructure.weather.client import (
	extract_current_temp_c,
	fetch_weather_json,
	get_weather_info,
)

logger = logging.getLogger("rockola.radio")


@dataclass(slots=True)
class RadioAnnouncementResult:
	"""Resultado estructurado de la síntesis de un anuncio radial."""

	ok: bool
	display_title: str = ""
	script: str = ""
	error: str | None = None
	outro_mode: str = "continue"
	host_voice: str = ""
	stem_segments: list[Any] | None = None
	display_artist: str = "Transmisión de Cabina 🎙️"

	def __iter__(self):
		yield self.ok
		yield self.display_title
		yield self.script if self.ok else (self.error or "")
		yield self.display_artist

	def __getitem__(self, index: int):
		return tuple(self)[index]

	def __len__(self) -> int:
		return 4


def _recent_temp_c(now_ts: float, db_path: Path | str | None = None, max_age: float = 3 * 3600.0) -> int | None:
	"""Última temperatura conocida (guardada al consultar wttr.in) si tiene menos de 3 horas."""
	temp = get_radio_state("last_temp_c", db_path=db_path)
	ts = get_radio_state("last_temp_ts", db_path=db_path)
	if temp is None or ts is None:
		return None
	try:
		if now_ts - float(ts) > max_age:
			return None
		return round(float(temp))
	except (ValueError, TypeError):
		return None


def assemble_announcement_audio(
	segments: list[Any],
	output_path: Path | str,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	cover_image_path: Path | str | None = None,
	title: str | None = DEFAULT_RADIO_TITLE,
	artist: str | None = DEFAULT_RADIO_ARTIST,
	timeout: float = 10.0,
	cues_text: list[str] | None = None,
) -> bool:
	"""
	Concatena los segmentos de audio MP3 intercalando ruido de sala sutil (~100-350ms),
	aplicando crossfade suave (~50ms) entre la hora y los minutos de un mismo locutor,
	solapando reacciones cortas (~200ms) sobre la línea anterior,
	igualando volumen entre voces con dynaudnorm y pasando el master final por filtro highpass + compresión.
	Opcionalmente superpone cortina musical de fondo utilizando ffmpeg e incrusta cover art.
	Genera simultáneamente archivos de subtítulos sincronizados (.lrc y .srt) junto al audio.
	Todas las operaciones intermedias se ejecutan en RAM (tmpfs /tmp).
	"""
	out_p = Path(output_path)
	out_p.parent.mkdir(parents=True, exist_ok=True)
	work_dir = Path(tempfile.mkdtemp(prefix="rockola_announcement_"))
	tmp_dest = out_p.parent / f".tmp_{out_p.name}"

	try:
		ffmpeg_bin = find_binary("ffmpeg")
		clean_env = get_clean_env()
		tmp_voice_combined = work_dir / "voice_combined.mp3"
		ffmpeg_timeout = max(5.0, timeout)

		# Normalizar segmentos a tuplas (bytes, categoria, voz, texto, cues)
		parsed_segments: list[tuple[bytes, str, str, str, list[tuple[float, float, str]] | None]] = []
		for idx, s in enumerate(segments):
			txt = cues_text[idx] if cues_text and idx < len(cues_text) else ""
			if len(s) >= 5:
				parsed_segments.append((s[0], str(s[1]), str(s[2]), str(s[3]), s[4]))
			elif len(s) == 4:
				parsed_segments.append((s[0], str(s[1]), str(s[2]), str(s[3]), None))
			elif len(s) == 3:
				parsed_segments.append((s[0], str(s[1]), str(s[2]), txt, None))
			elif len(s) == 2:
				parsed_segments.append((s[0], str(s[1]), "", txt, None))
			else:
				parsed_segments.append((s[0], "", "", txt, None))

		cues: list[tuple[float, float, str]] = []

		if ffmpeg_bin:
			# Atajo directo cuando hay un único parlamento/segmento (discurso completo continuo)
			if len(parsed_segments) == 1:
				tmp_voice_combined.write_bytes(parsed_segments[0][0])
				concat_ok = tmp_voice_combined.is_file() and tmp_voice_combined.stat().st_size > 0
				t_single = parsed_segments[0][3]
				cues_single = parsed_segments[0][4]
				if cues_single:
					for cs, ce, ct in cues_single:
						cues.append((cs, ce, ct))
				elif t_single:
					dur_single = (
						get_audio_duration(tmp_voice_combined) or estimate_mp3_duration(parsed_segments[0][0]) or 1.0
					)
					cues.append((0.0, dur_single, t_single))
			else:
				# Generar archivos MP3 temporales con normalización dynaudnorm para nivelar volumen entre voces
				temp_seg_files: list[Path] = []
				for i, (seg_bytes, _cat, _v, _txt, *_rest) in enumerate(parsed_segments):
					raw_file = work_dir / f"raw_seg_{i}.mp3"
					raw_file.write_bytes(seg_bytes)
					norm_file = work_dir / f"norm_seg_{i}.mp3"
					norm_cmd = [
						ffmpeg_bin,
						"-y",
						"-i",
						str(raw_file),
						"-af",
						"dynaudnorm=p=0.9:s=5",
						"-c:a",
						"libmp3lame",
						"-b:a",
						"192k",
						str(norm_file),
					]
					try:
						proc_norm = subprocess.run(
							norm_cmd,
							capture_output=True,
							timeout=min(ffmpeg_timeout, 3.0),
							check=False,
							env=clean_env,
						)
						if proc_norm.returncode == 0 and norm_file.is_file() and norm_file.stat().st_size > 0:
							temp_seg_files.append(norm_file)
						else:
							err_norm = proc_norm.stderr.decode("utf-8", errors="ignore").strip()
							logger.warning(f"ffmpeg falló al normalizar segmento {i}: {err_norm[:200]}")
							temp_seg_files.append(raw_file)
					except Exception as e:
						logger.warning(f"Error al normalizar segmento {i} con ffmpeg: {e}")
						temp_seg_files.append(raw_file)

				blocks: list[tuple[Path, str, str, str, list[tuple[float, float, str]] | None]] = []
				skip_next = False
				for i in range(len(parsed_segments)):
					if skip_next:
						skip_next = False
						continue

					_bytes_i, cat_i, voice_i, text_i, cues_i = parsed_segments[i]
					file_i = temp_seg_files[i]

					# Caso 1: fusión continua (sin gap de silencio) entre 'hora' y 'minuto' consecutivos de la misma voz
					if cat_i == "hora" and i + 1 < len(parsed_segments):
						_bytes_next, cat_next, voice_next, text_next, cues_next = parsed_segments[i + 1]
						if cat_next == "minuto" and (voice_i == voice_next or not voice_i or not voice_next):
							file_next = temp_seg_files[i + 1]
							time_combined = work_dir / f"time_combined_{i}.mp3"
							filter_fade = (
								"[0:a]areverse,silenceremove=start_periods=1:start_threshold=-35dB:start_duration=0.02,areverse[h];"
								"[1:a]silenceremove=start_periods=1:start_threshold=-35dB:start_duration=0.02[m];"
								"[h][m]acrossfade=d=0.05:c1=tri:c2=tri[a]"
							)
							fade_cmd = [
								ffmpeg_bin,
								"-y",
								"-i",
								str(file_i),
								"-i",
								str(file_next),
								"-filter_complex",
								filter_fade,
								"-map",
								"[a]",
								"-c:a",
								"libmp3lame",
								"-b:a",
								"192k",
								str(time_combined),
							]
							try:
								proc_fade = subprocess.run(
									fade_cmd,
									capture_output=True,
									timeout=ffmpeg_timeout,
									check=False,
									env=clean_env,
								)
								if (
									proc_fade.returncode == 0
									and time_combined.is_file()
									and time_combined.stat().st_size > 0
								):
									combined_time_text = f"{text_i} {text_next}".strip()
									combined_cues: list[tuple[float, float, str]] | None = None
									if cues_i or cues_next:
										dur_i = get_audio_duration(file_i) or estimate_mp3_duration(_bytes_i) or 1.0
										combined_cues = []
										if cues_i:
											combined_cues.extend(cues_i)
										elif text_i:
											combined_cues.append((0.0, dur_i, text_i))
										shift_next = max(0.0, dur_i - 0.05)
										if cues_next:
											for cs, ce, ct in cues_next:
												combined_cues.append((cs + shift_next, ce + shift_next, ct))
										elif text_next:
											dur_next = (
												get_audio_duration(file_next)
												or estimate_mp3_duration(_bytes_next)
												or 1.0
											)
											combined_cues.append((shift_next, shift_next + dur_next, text_next))
									blocks.append(
										(time_combined, "hora_minuto", voice_i, combined_time_text, combined_cues)
									)
									skip_next = True
									continue
								err_fade = proc_fade.stderr.decode("utf-8", errors="ignore").strip()
								logger.warning(f"ffmpeg falló en acrossfade hora/minuto: {err_fade[:200]}")
							except Exception as e:
								logger.warning(f"Error en acrossfade hora/minuto con ffmpeg: {e}")

					# Caso 2: reacción corta que solapa 150-250 ms sobre el final de la línea anterior (adelay + amix)
					if i + 1 < len(parsed_segments):
						_bytes_next, cat_next, voice_next, text_next, cues_next = parsed_segments[i + 1]
						if cat_next == "reaccion" or cat_next.startswith("reaccion"):
							file_next = temp_seg_files[i + 1]
							dur_i = get_audio_duration(file_i)
							if dur_i > 0.25:
								overlap_sec = 0.20
								delay_ms = int(max(0.0, (dur_i - overlap_sec)) * 1000)
								react_combined = work_dir / f"react_combined_{i}.mp3"
								filter_overlap = (
									f"[0:a]volume=1.0[prev];"
									f"[1:a]volume=0.85,adelay={delay_ms}|{delay_ms}[react];"
									f"[prev][react]amix=inputs=2:duration=longest:dropout_transition=0[out]"
								)
								overlap_cmd = [
									ffmpeg_bin,
									"-y",
									"-i",
									str(file_i),
									"-i",
									str(file_next),
									"-filter_complex",
									filter_overlap,
									"-map",
									"[out]",
									"-c:a",
									"libmp3lame",
									"-b:a",
									"192k",
									str(react_combined),
								]
								try:
									proc_react = subprocess.run(
										overlap_cmd,
										capture_output=True,
										timeout=ffmpeg_timeout,
										check=False,
										env=clean_env,
									)
									if (
										proc_react.returncode == 0
										and react_combined.is_file()
										and react_combined.stat().st_size > 0
									):
										combined_react_text = f"{text_i} {text_next}".strip()
										combined_cues = None
										if cues_i or cues_next:
											combined_cues = []
											if cues_i:
												combined_cues.extend(cues_i)
											elif text_i:
												combined_cues.append((0.0, dur_i, text_i))
											shift_next = max(0.0, dur_i - overlap_sec)
											if cues_next:
												for cs, ce, ct in cues_next:
													combined_cues.append((cs + shift_next, ce + shift_next, ct))
											elif text_next:
												dur_next = (
													get_audio_duration(temp_seg_files[i + 1])
													or estimate_mp3_duration(_bytes_next)
													or 1.0
												)
												combined_cues.append((shift_next, shift_next + dur_next, text_next))
										blocks.append(
											(
												react_combined,
												f"{cat_i}_reaccion",
												voice_i,
												combined_react_text,
												combined_cues,
											)
										)
										skip_next = True
										continue
									err_react = proc_react.stderr.decode("utf-8", errors="ignore").strip()
									logger.warning(f"ffmpeg falló al solapar reacción: {err_react[:200]}")
								except Exception as e:
									logger.warning(f"Error solapando reacción con ffmpeg: {e}")

					blocks.append((file_i, cat_i, voice_i, text_i, cues_i))

				def make_room_tone(duration_sec: float, filename: str) -> Path | None:
					tone_path = work_dir / filename
					cmd = [
						ffmpeg_bin,
						"-y",
						"-f",
						"lavfi",
						"-i",
						"anoisesrc=c=pink:a=0.002:r=44100",
						"-t",
						f"{duration_sec:.3f}",
						"-c:a",
						"libmp3lame",
						"-b:a",
						"192k",
						str(tone_path),
					]
					try:
						res = subprocess.run(
							cmd, capture_output=True, timeout=ffmpeg_timeout, check=False, env=clean_env
						)
						if res.returncode == 0 and tone_path.is_file() and tone_path.stat().st_size > 0:
							return tone_path
						err_tone = res.stderr.decode("utf-8", errors="ignore").strip()
						logger.warning(f"ffmpeg falló generando room tone (anoisesrc): {err_tone[:200]}")
					except Exception as e:
						logger.warning(f"Error ejecutando ffmpeg para room tone (anoisesrc): {e}")

					fallback_cmd = [
						ffmpeg_bin,
						"-y",
						"-f",
						"lavfi",
						"-i",
						"anullsrc=r=44100:cl=mono",
						"-t",
						f"{duration_sec:.3f}",
						"-c:a",
						"libmp3lame",
						"-b:a",
						"192k",
						str(tone_path),
					]
					try:
						res = subprocess.run(
							fallback_cmd, capture_output=True, timeout=ffmpeg_timeout, check=False, env=clean_env
						)
						if res.returncode == 0 and tone_path.is_file() and tone_path.stat().st_size > 0:
							return tone_path
						err_null = res.stderr.decode("utf-8", errors="ignore").strip()
						logger.warning(f"ffmpeg falló generando anullsrc fallback: {err_null[:200]}")
					except Exception as e:
						logger.warning(f"Fallo generando anullsrc fallback con ffmpeg: {e}")

					return None

				# Construir cadena de archivos intercalando pausas de sala y ritmo de locución
				chain_files: list[Path] = []
				current_time = 0.0

				tone_start = make_room_tone(0.15, "tone_start.mp3")
				if tone_start:
					chain_files.append(tone_start)
					current_time = 0.15

				for i, (block_file, block_cat, block_voice, block_text, block_cues) in enumerate(blocks):
					chain_files.append(block_file)
					dur = get_audio_duration(block_file)
					if dur <= 0.0:
						try:
							dur = estimate_mp3_duration(block_file.read_bytes()) or 1.0
						except Exception as e:
							logger.warning(f"Error al estimar duración MP3 para {block_file}: {e}")
							dur = 1.0

					if block_cues:
						for cs, ce, ct in block_cues:
							cues.append((current_time + cs, current_time + ce, clean_subtitle_text(ct)))
					elif block_text:
						cues.append((current_time, current_time + dur, clean_subtitle_text(block_text)))
					current_time += dur

					if i == len(blocks) - 1:
						continue

					next_cat = blocks[i + 1][1]
					next_voice = blocks[i + 1][2]
					is_speaker_change = bool(block_voice and next_voice and block_voice != next_voice)
					if is_speaker_change:
						gap_sec = 0.10
					elif block_cat == "hora" and next_cat == "minuto":
						gap_sec = 0.0
					elif block_cat == "intro":
						gap_sec = 0.30
					elif block_cat in ("hora", "hora_minuto", "minuto"):
						gap_sec = 0.25
					elif block_cat == "clima":
						gap_sec = 0.30
					elif block_cat == "lead_in":
						gap_sec = 0.35
					elif block_cat == "fortuna":
						gap_sec = 0.25
					else:
						gap_sec = 0.25

					if gap_sec > 0.0:
						tone = make_room_tone(gap_sec, f"tone_gap_{i}.mp3")
						if tone:
							chain_files.append(tone)
						current_time += gap_sec

				concat_inputs: list[str] = []
				for f in chain_files:
					concat_inputs.extend(["-i", str(f)])

				filter_concat = (
					"".join(f"[{k}:a]" for k in range(len(chain_files))) + f"concat=n={len(chain_files)}:v=0:a=1[v]"
				)

				concat_cmd = [
					ffmpeg_bin,
					"-y",
					*concat_inputs,
					"-filter_complex",
					filter_concat,
					"-map",
					"[v]",
					"-c:a",
					"libmp3lame",
					"-b:a",
					"192k",
					str(tmp_voice_combined),
				]

				proc = subprocess.run(
					concat_cmd, capture_output=True, timeout=ffmpeg_timeout, check=False, env=clean_env
				)
				concat_ok = (
					proc.returncode == 0 and tmp_voice_combined.is_file() and tmp_voice_combined.stat().st_size > 0
				)

				if not concat_ok:
					logger.warning(
						f"ffmpeg filter_complex falló ({proc.stderr.decode('utf-8', errors='ignore')[:150]}). Probando concat demuxer..."
					)
					concat_list = work_dir / "concat_list.txt"
					concat_list.write_text("\n".join(f"file '{f.name}'" for f in chain_files), encoding="utf-8")
					demux_cmd = [
						ffmpeg_bin,
						"-y",
						"-f",
						"concat",
						"-safe",
						"0",
						"-i",
						str(concat_list),
						"-c:a",
						"copy",
						str(tmp_voice_combined),
					]
					proc_demux = subprocess.run(
						demux_cmd,
						cwd=str(work_dir),
						capture_output=True,
						timeout=ffmpeg_timeout,
						check=False,
						env=clean_env,
					)
					concat_ok = (
						proc_demux.returncode == 0
						and tmp_voice_combined.is_file()
						and tmp_voice_combined.stat().st_size > 0
					)
					if not concat_ok and proc_demux.returncode != 0:
						logger.warning(
							f"ffmpeg concat demuxer falló con código {proc_demux.returncode}: {proc_demux.stderr.decode('utf-8', errors='ignore')[:150]}"
						)

			# Mastering final de voz: filtro paso-alto ~80 Hz, compresión y normalización broadcast (-14 LUFS)
			if concat_ok:
				tmp_voice_mastered = work_dir / "voice_mastered.mp3"
				master_cmd = [
					ffmpeg_bin,
					"-y",
					"-i",
					str(tmp_voice_combined),
					"-af",
					"highpass=f=80,acompressor=threshold=-18dB:ratio=2.5:attack=20:release=250:makeup=2,loudnorm=I=-14:TP=-1.5:LRA=7",
					"-c:a",
					"libmp3lame",
					"-b:a",
					"192k",
					str(tmp_voice_mastered),
				]
				try:
					proc_master = subprocess.run(
						master_cmd,
						capture_output=True,
						timeout=ffmpeg_timeout,
						check=False,
						env=clean_env,
					)
					if (
						proc_master.returncode == 0
						and tmp_voice_mastered.is_file()
						and tmp_voice_mastered.stat().st_size > 0
					):
						shutil.copyfile(tmp_voice_mastered, tmp_voice_combined)
					elif proc_master.returncode != 0:
						logger.warning(
							f"ffmpeg falló en masterización de voz: {proc_master.stderr.decode('utf-8', errors='ignore')[:200]}"
						)
				except Exception as e:
					logger.warning(f"Error aplicando filtro de estudio/compresión con ffmpeg: {e}")

			if not concat_ok:
				logger.warning("ffmpeg concat demuxer también falló. Recurriendo a concatenación directa de bytes.")
				combined = b"".join(seg[0] for seg in parsed_segments)
				tmp_voice_combined.write_bytes(combined)
		else:
			combined = b"".join(seg[0] for seg in parsed_segments)
			tmp_voice_combined.write_bytes(combined)
			curr_offset = 0.0
			for seg in parsed_segments:
				dur_fb = estimate_mp3_duration(seg[0]) or 1.0
				seg_cues = seg[4]
				if seg_cues:
					for cs, ce, ct in seg_cues:
						cues.append((curr_offset + cs, curr_offset + ce, clean_subtitle_text(ct)))
				elif seg[3]:
					cues.append((curr_offset, curr_offset + dur_fb, clean_subtitle_text(seg[3])))
				curr_offset += dur_fb

		def _save_subtitles() -> None:
			if cues:
				lrc_content = build_lrc_content(cues)
				srt_content = build_srt_content(cues)
				try:
					out_p.with_suffix(".lrc").write_text(lrc_content, encoding="utf-8")
					out_p.with_suffix(".srt").write_text(srt_content, encoding="utf-8")
				except Exception as sub_e:
					logger.debug(f"Error escribiendo subtítulos en {out_p}: {sub_e}")

		has_bg = bg_track_path is not None and Path(bg_track_path).is_file()
		if has_bg and ffmpeg_bin:
			mixed = mix_announcement_with_bg_track(
				voice_path=tmp_voice_combined,
				output_path=out_p,
				bg_track_path=bg_track_path,
				bg_offset=bg_offset,
				bg_volume=bg_volume,
				timeout=timeout,
			)
			if mixed:
				embed_cover_art_in_mp3(
					out_p,
					cover_image_path=cover_image_path,
					title=title,
					artist=artist,
					timeout=timeout,
				)
				_save_subtitles()
				return True

		shutil.copyfile(tmp_voice_combined, tmp_dest)
		embed_cover_art_in_mp3(
			tmp_dest,
			cover_image_path=cover_image_path,
			title=title,
			artist=artist,
			timeout=timeout,
		)
		tmp_dest.replace(out_p)
		_save_subtitles()
		return True
	except Exception as e:
		logger.warning(f"Error ensamblando locución radial: {e}")
		if tmp_dest.exists():
			tmp_dest.unlink(missing_ok=True)
		return False
	finally:
		shutil.rmtree(work_dir, ignore_errors=True)


async def create_radio_announcement(
	output_path: Path | str,
	voice: str | None = None,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	db_path: Path | str | None = None,
	dt: datetime | None = None,
	force_system_fortune: bool | None = None,
	cover_image_path: Path | str | None = None,
	weather_location: str | None = None,
	dialogue_mode: bool | None = None,
	outro_mode: str = "continue",
) -> RadioAnnouncementResult:
	"""Sintetiza la locución radial con dinámica de charla de cabina entre locutores carpinchos."""
	if not HAS_EDGE_TTS or edge_tts is None:
		err_msg = "El paquete 'edge-tts' no está instalado en el entorno de Python o falló su importación."
		logger.warning(f"📻 El Carpincho no puede locutar: {err_msg}")
		return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg, outro_mode=outro_mode)

	out_p = Path(output_path)
	try:
		out_p.parent.mkdir(parents=True, exist_ok=True)
	except Exception as e:
		err_msg = f"No se pudo crear el directorio de destino '{out_p.parent}': {type(e).__name__}: {e}"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg, outro_mode=outro_mode)

	effective_dt = dt if dt is not None else datetime.now(UTC).astimezone()
	now_ts = effective_dt.timestamp()

	weather_text: str | None = None
	weather_condition: str | None = None
	current_weather_slot = effective_dt.strftime("%Y-%m-%d %H")
	last_weather_hour = get_radio_state("last_weather_hour", db_path=db_path)
	last_weather_ts = get_radio_state("last_weather_timestamp", db_path=db_path)

	enough_time_passed = last_weather_ts is None or (now_ts - float(last_weather_ts)) >= (30 * 60)

	pending_weather_slot: str | None = None
	pending_weather_ts: float | None = None
	loc_to_query = weather_location or DEFAULT_WEATHER_LOCATION
	weather_data: dict[str, Any] | None = None

	if last_weather_hour != current_weather_slot and enough_time_passed:
		try:
			weather_timeout = min(timeout, 5.0)
			weather_data = await asyncio.to_thread(fetch_weather_json, loc_to_query, "es", weather_timeout)
			if weather_data:
				fresh_temp = extract_current_temp_c(weather_data)
				if fresh_temp is not None:
					set_radio_state("last_temp_c", fresh_temp, db_path=db_path)
					set_radio_state("last_temp_ts", now_ts, db_path=db_path)
		except Exception as e:
			logger.debug(f"Fallo no crítico consultando el clima: {e}")
			weather_data = None

	ctx = build_radio_context(effective_dt, temp_c=_recent_temp_c(now_ts, db_path=db_path))

	if weather_data:
		try:
			weather_info = get_weather_info(
				weather_data,
				current_hour=effective_dt.hour,
				location=loc_to_query,
				ctx=ctx,
			)
			if weather_info:
				weather_text, weather_condition = weather_info
				pending_weather_slot = current_weather_slot
				pending_weather_ts = now_ts
				logger.debug(f"🌤️ Reporte del clima incorporado a la locución: '{weather_text}'")
		except Exception as e:
			logger.debug(f"Fallo no crítico procesando reporte del clima: {e}")

	fortuna, is_sys = select_radio_phrase(force_system_fortune, db_path=db_path, ctx=ctx)
	host_voice, cohost_voice = select_radio_hosts(host_voice=voice, is_system_fortune=is_sys)
	locutor_nombre = VOICE_NAMES.get(host_voice, DEFAULT_HOST_NAME)
	cohost_nombre = VOICE_NAMES.get(cohost_voice, DEFAULT_COHOST_DISPLAY_NAME)

	intro_candidates = filter_by_context(RADIO_INTROS, ctx) or list(RADIO_INTROS)
	intro = weighted_choice_by_recency(intro_candidates, category="intro", db_path=db_path)
	hora_seg, minuto_seg, _ = get_modular_time_segments(effective_dt)
	seg_cat = resolve_segment_category(fortuna)
	outro_pool = get_outros_for_category(seg_cat, outro_mode)
	outro_candidates = filter_by_context(outro_pool, ctx) or list(outro_pool)
	outro = weighted_choice_by_recency(outro_candidates, category="salida", db_path=db_path)

	is_dialogue = dialogue_mode if dialogue_mode is not None else (random.random() < 0.85)
	last_reaction = get_radio_state("last_reaction", db_path=db_path)

	plan = build_radio_dialogue_plan(
		intro=intro,
		hora_seg=hora_seg,
		minuto_seg=minuto_seg,
		fortuna=fortuna,
		outro=outro,
		host_voice=host_voice,
		cohost_voice=cohost_voice,
		is_system_fortune=is_sys,
		weather_text=weather_text,
		weather_condition=weather_condition,
		dialogue_mode=is_dialogue,
		last_reaction=last_reaction,
		db_path=db_path,
		ctx=ctx,
	)

	full_script = " ".join(t[0].strip() for t in plan if t[0].strip())
	display_title = DEFAULT_RADIO_TITLE
	if is_dialogue and cohost_nombre:
		display_artist = f"{locutor_nombre} y {cohost_nombre} 🎙️"
	else:
		display_artist = f"{locutor_nombre} 🎙️"
	speech_turns = group_plan_into_speech_turns(plan)
	try:
		# El timeout total debe considerar la cantidad de turnos de habla
		turn_count = max(1, len(speech_turns))
		margin = 10.0 if timeout >= 1.0 else max(0.05, timeout)
		total_timeout = (timeout * max(1, max_retries) * turn_count) + margin

		tasks = [
			synthesize_segment(
				text=apply_rioplatense_tts_phonetics(text),
				voice=v,
				category=category,
				allow_cache=allow_cache,
				timeout=timeout,
				max_retries=max_retries,
				db_path=db_path,
				return_cues=True,
			)
			for text, v, category, allow_cache in speech_turns
		]
		raw_segments = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=total_timeout)
		segment_results: list[tuple[bytes, str, str, str, list[tuple[float, float, str]] | None]] = []
		for i, res in enumerate(raw_segments):
			if isinstance(res, Exception):
				logger.warning(
					f"📻 El Carpincho: no se pudo sintetizar el segmento '{speech_turns[i][2]}': {res}. Omitiendo para no frenar la locución..."
				)
				continue
			if isinstance(res, tuple) and len(res) == 2:
				seg_bytes, seg_cues = res
			else:
				seg_bytes, seg_cues = res, None  # type: ignore[assignment]
			segment_results.append((seg_bytes, speech_turns[i][2], speech_turns[i][1], speech_turns[i][0], seg_cues))

		if not segment_results:
			exc_list = [r for r in raw_segments if isinstance(r, Exception)]
			if exc_list:
				nested_msgs = "; ".join(
					f"{type(sub).__name__}: {sub}" if str(sub) else type(sub).__name__ for sub in exc_list
				)
				err_msg = f"Error de síntesis ({nested_msgs})"
			else:
				err_msg = "Ningún segmento de locución pudo ser sintetizado."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg, outro_mode=outro_mode)

		if is_dialogue:
			logger.info(f"🎙️ Locución radial en cabina ({locutor_nombre} y {cohost_nombre}): '{full_script}'")
		else:
			logger.info(f"🎙️ Locución radial generada exitosamente con {locutor_nombre} ({host_voice}): '{full_script}'")

		loop = asyncio.get_running_loop()
		ok = await loop.run_in_executor(
			None,
			assemble_announcement_audio,
			segment_results,
			out_p,
			bg_track_path,
			bg_offset,
			bg_volume,
			cover_image_path,
			display_title,
			display_artist,
			timeout,
		)
		if not ok:
			err_msg = "Falló el ensamblado del audio del anuncio radial."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg, outro_mode=outro_mode)

		if pending_weather_slot:
			set_radio_state("last_weather_hour", pending_weather_slot, db_path=db_path)
		if pending_weather_ts is not None:
			set_radio_state("last_weather_timestamp", pending_weather_ts, db_path=db_path)

		reactions_in_plan = [text for text, _v, cat, _c in plan if cat == "reaccion" or "reaccion" in cat]
		if reactions_in_plan:
			set_radio_state("last_reaction", reactions_in_plan[-1], db_path=db_path)

		for seg_text, _v, cat, _c in plan:
			clean_s = seg_text.strip()
			if clean_s:
				record_phrase_played(clean_s, category=cat, timestamp=now_ts, db_path=db_path)

		stem_segs = segment_results[:-1] if len(segment_results) > 1 else []
		return RadioAnnouncementResult(
			ok=True,
			display_title=display_title,
			script=full_script,
			error=None,
			outro_mode=outro_mode,
			host_voice=host_voice,
			stem_segments=stem_segs,
			display_artist=display_artist,
		)

	except Exception as e:
		is_timeout = isinstance(e, (asyncio.TimeoutError, TimeoutError)) or (
			hasattr(e, "exceptions")
			and any(isinstance(sub, (asyncio.TimeoutError, TimeoutError)) for sub in getattr(e, "exceptions", []))
		)
		if is_timeout:
			err_msg = f"Se agotó el tiempo de espera ({timeout}s) contactando al servicio de síntesis de voz (edge-tts). Verificá la conexión a internet."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg, outro_mode=outro_mode)

		if hasattr(e, "exceptions"):
			nested_msgs = "; ".join(
				f"{type(sub).__name__}: {sub}" if str(sub) else type(sub).__name__
				for sub in getattr(e, "exceptions", [])
			)
			err_msg = f"Error de síntesis ({nested_msgs})"
		else:
			err_msg = f"Error de síntesis ({type(e).__name__}: {e})"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return RadioAnnouncementResult(ok=False, display_title="", script="", error=err_msg, outro_mode=outro_mode)


async def replace_announcement_outro(
	stem_segments: list[tuple[bytes, str, str, str, list[tuple[float, float, str]] | None]],
	host_voice: str,
	outro_mode: str,
	output_path: Path | str,
	bg_track_path: Path | str | None = None,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	db_path: Path | str | None = None,
	dt: datetime | None = None,
	cover_image_path: Path | str | None = None,
	timeout: float = DEFAULT_TTS_TIMEOUT,
	max_retries: int = DEFAULT_TTS_RETRIES,
) -> RadioAnnouncementResult:
	"""Reemplaza únicamente el segmento final ('salida') sobre los segmentos troncales pregenerados."""
	out_p = Path(output_path)
	effective_dt = dt if dt is not None else datetime.now(UTC).astimezone()
	now_ts = effective_dt.timestamp()
	ctx = build_radio_context(effective_dt, temp_c=_recent_temp_c(now_ts, db_path=db_path))

	outro_pool = get_outros_for_mode(outro_mode)
	outro_candidates = filter_by_context(outro_pool, ctx) or list(outro_pool)
	raw_outro = weighted_choice_by_recency(outro_candidates, category="salida", db_path=db_path)
	outro_text = render_tracked_phrase(raw_outro, ctx)
	effective_voice = host_voice if host_voice in VOICES else VOICE_TOMAS
	locutor_nombre = VOICE_NAMES.get(effective_voice, DEFAULT_HOST_NAME)

	try:
		res = await synthesize_segment(
			text=apply_rioplatense_tts_phonetics(outro_text),
			voice=effective_voice,
			category="salida",
			allow_cache=True,
			timeout=timeout,
			max_retries=max_retries,
			db_path=db_path,
			return_cues=True,
		)
		if isinstance(res, tuple) and len(res) == 2:
			outro_bytes, outro_cues = res
		else:
			outro_bytes, outro_cues = res, None  # type: ignore[assignment]

		combined_segments = [*stem_segments, (outro_bytes, "salida", effective_voice, outro_text, outro_cues)]
		full_script = " ".join(s[3].strip() for s in combined_segments if len(s) >= 4 and s[3].strip())
		display_title = DEFAULT_RADIO_TITLE

		voices_in_segs = {s[2] for s in combined_segments if len(s) >= 3 and s[2] in VOICE_NAMES}
		if len(voices_in_segs) > 1:
			locutores = [VOICE_NAMES[v] for v in VOICES if v in voices_in_segs]
			display_artist = f"{' y '.join(locutores)} 🎙️"
		elif voices_in_segs:
			display_artist = f"{VOICE_NAMES.get(next(iter(voices_in_segs)), locutor_nombre)} 🎙️"
		else:
			display_artist = f"{locutor_nombre} 🎙️"

		loop = asyncio.get_running_loop()
		ok = await loop.run_in_executor(
			None,
			assemble_announcement_audio,
			combined_segments,
			out_p,
			bg_track_path,
			bg_offset,
			bg_volume,
			cover_image_path,
			display_title,
			display_artist,
			timeout,
		)
		if not ok:
			err_msg = "Falló el re-ensamblado del cierre radial."
			logger.warning(f"📻 El Carpincho: {err_msg}")
			return RadioAnnouncementResult(
				ok=False,
				display_title="",
				script="",
				error=err_msg,
				outro_mode=outro_mode,
			)

		record_phrase_played(outro_text, category="salida", timestamp=now_ts, db_path=db_path)
		return RadioAnnouncementResult(
			ok=True,
			display_title=display_title,
			script=full_script,
			error=None,
			outro_mode=outro_mode,
			host_voice=effective_voice,
			stem_segments=list(stem_segments),
			display_artist=display_artist,
		)
	except Exception as e:
		err_msg = f"Error cambiando el cierre radial ({type(e).__name__}: {e})"
		logger.warning(f"📻 El Carpincho: {err_msg}")
		return RadioAnnouncementResult(
			ok=False,
			display_title="",
			script="",
			error=err_msg,
			outro_mode=outro_mode,
		)


RADIO_PREGENERATION_MAX_AGE_SECONDS: float = 15.0 * 60.0


class RadioService:
	"""Servicio de dominio para gestionar la locución, pregeneración y archivo del Modo Radio."""

	def __init__(self, db_path: Path | str | None = None, weather_location: str = DEFAULT_WEATHER_LOCATION) -> None:
		self.db_path = db_path
		self.weather_location = weather_location or DEFAULT_WEATHER_LOCATION
		self.enabled: bool = True
		self.is_playing_announcement: bool = False
		self.is_synthesizing: bool = False
		self.announcement_path = Path(tempfile.gettempdir()) / "radio_announcement.mp3"
		self.pregenerated_path = Path(tempfile.gettempdir()) / "radio_pregenerated.mp3"
		self.archive_dir = Path(tempfile.gettempdir()) / "la_rockola_radio_archive"
		self.archive_max_files = 60
		self.pregeneration_task: asyncio.Task[None] | None = None
		self.pregenerated_announcement: dict[str, Any] | None = None

	@property
	def is_available(self) -> bool:
		"""Indica si Edge-TTS está instalado y disponible."""
		return bool(HAS_EDGE_TTS)

	def cancel_pregeneration(self) -> None:
		"""Cancela cualquier pregeneración en curso y limpia archivos parciales."""
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
				logger.debug(f"No se pudo limpiar archivo de pregeneración parcial: {e}")

	def start_pregeneration(
		self,
		track_duration: float = 0.0,
		location: str | None = None,
		pregenerated_path: Path | str | None = None,
		outro_mode: str = "continue",
	) -> None:
		"""Dispara la pregeneración anticipada de la locución radial en segundo plano."""
		if not self.is_available:
			return
		self.cancel_pregeneration()
		target_path = Path(pregenerated_path) if pregenerated_path else self.pregenerated_path
		target_loc = location or self.weather_location

		async def _do_pregeneration() -> None:
			import time as _time
			from datetime import timedelta

			now = datetime.now(UTC).astimezone()
			finish_dt = now + timedelta(seconds=max(0.0, track_duration)) if track_duration > 0 else now
			try:
				res = await create_radio_announcement(
					str(target_path),
					dt=finish_dt,
					bg_track_path=None,
					weather_location=target_loc,
					db_path=self.db_path,
					outro_mode=outro_mode,
				)
				if res.ok:
					self.pregenerated_announcement = {
						"path": str(target_path),
						"display_title": res.display_title,
						"display_artist": res.display_artist,
						"script": res.script,
						"created_at": _time.time(),
						"outro_mode": res.outro_mode,
						"host_voice": res.host_voice,
						"stem_segments": res.stem_segments,
					}
			except asyncio.CancelledError:
				pass
			except Exception as e:
				logger.debug(f"Excepción en pregeneración radial: {e}")

		self.pregeneration_task = asyncio.create_task(_do_pregeneration())

	async def apply_hot_mix_to_announcement(
		self,
		voice_file: Path,
		out_file: Path,
		title: str,
		next_track_path: str | None = None,
		bg_offset: float = 0.0,
		display_artist: str = DEFAULT_RADIO_ARTIST,
	) -> bool:
		"""Superpone la cortina musical en caliente sobre la voz pregenerada."""
		from app.infrastructure.media.mixer import get_carpincho_cover_path

		mixed_ok = False
		if next_track_path and Path(next_track_path).is_file():
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
					cover_p = get_carpincho_cover_path()
					await asyncio.to_thread(
						embed_cover_art_in_mp3,
						out_file,
						cover_p,
						title,
						display_artist,
						"La Rockola del Carpincho",
					)
					mixed_ok = True
			except Exception as mix_err:
				logger.debug(f"Fallo en mezcla en caliente con '{next_track_path}': {mix_err}")

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

	async def _consume_pregenerated(
		self,
		pre: dict[str, Any],
		target_ann_path: Path,
		next_track_path: str | None,
		bg_offset: float,
		outro_mode: str,
	) -> tuple[bool, str, str]:
		import time as _time

		from app.infrastructure.media.mixer import is_valid_mp3_file

		pre_created_at = pre.get("created_at")
		pre_age = (_time.time() - pre_created_at) if pre_created_at is not None else 0.0
		if pre_age > RADIO_PREGENERATION_MAX_AGE_SECONDS:
			logger.warning(
				f"📻 Transmisión de Cabina: Anuncio pregenerado descartado por antigüedad ({pre_age:.1f}s > {RADIO_PREGENERATION_MAX_AGE_SECONDS}s)."
			)
			return False, "", ""

		pre_p = Path(pre["path"])
		if not is_valid_mp3_file(pre_p):
			logger.warning(f"📻 Transmisión de Cabina: Anuncio pregenerado corrupto o inválido en '{pre_p}'.")
			return False, "", ""

		pre_mode = pre.get("outro_mode")
		stem_segments = pre.get("stem_segments")
		pre_artist = pre.get("display_artist", DEFAULT_RADIO_ARTIST)
		if pre_mode is not None and pre_mode != outro_mode and stem_segments:
			swapped_res = await replace_announcement_outro(
				stem_segments=stem_segments,
				host_voice=pre.get("host_voice") or "",
				outro_mode=outro_mode,
				output_path=target_ann_path,
				bg_track_path=next_track_path,
				bg_offset=bg_offset,
				bg_volume=0.1,
				db_path=self.db_path,
			)
			if swapped_res.ok:
				pre["display_artist"] = swapped_res.display_artist
				return True, swapped_res.display_title, swapped_res.script

		if await self.apply_hot_mix_to_announcement(
			pre_p,
			target_ann_path,
			pre["display_title"],
			next_track_path=next_track_path,
			bg_offset=bg_offset,
			display_artist=pre_artist,
		):
			return True, pre["display_title"], pre.get("script", "")
		return False, "", ""

	async def get_or_synthesize(
		self,
		next_track_path: str | None = None,
		bg_offset: float = 0.0,
		on_synthesis_status: Any | None = None,
		location: str | None = None,
		announcement_path: Path | str | None = None,
		outro_mode: str = "continue",
	) -> tuple[bool, str, str, str | None, str]:
		"""Obtiene la locución pregenerada o sintetiza una fresca en caliente."""
		if not self.is_available:
			return False, "", "", "Servicio de radio no disponible", DEFAULT_RADIO_ARTIST

		target_ann_path = Path(announcement_path) if announcement_path else self.announcement_path
		target_loc = location or self.weather_location
		ok = False
		display_title = ""
		display_artist = DEFAULT_RADIO_ARTIST
		script = ""
		radio_err: str | None = None

		if self.pregenerated_announcement:
			pre = self.pregenerated_announcement
			self.pregenerated_announcement = None
			if on_synthesis_status:
				res_notify = on_synthesis_status(True)
				if asyncio.iscoroutine(res_notify):
					await res_notify
			ok, display_title, script = await self._consume_pregenerated(
				pre, target_ann_path, next_track_path, bg_offset, outro_mode
			)
			display_artist = pre.get("display_artist", DEFAULT_RADIO_ARTIST)
			if not ok and on_synthesis_status:
				res_notify = on_synthesis_status(False)
				if asyncio.iscoroutine(res_notify):
					await res_notify

		if not ok and self.pregeneration_task and not self.pregeneration_task.done():
			try:
				logger.info("📻 Transmisión de Cabina: Esperando finalización de pregeneración en curso...")
				if on_synthesis_status:
					res_notify = on_synthesis_status(True)
					if asyncio.iscoroutine(res_notify):
						await res_notify
				await asyncio.wait_for(asyncio.shield(self.pregeneration_task), timeout=3.0)
				if self.pregenerated_announcement:
					pre = self.pregenerated_announcement
					self.pregenerated_announcement = None
					ok, display_title, script = await self._consume_pregenerated(
						pre, target_ann_path, next_track_path, bg_offset, outro_mode
					)
					display_artist = pre.get("display_artist", DEFAULT_RADIO_ARTIST)
			except Exception as wait_e:
				logger.debug(f"Espera de pregeneración agotada o falló: {wait_e}")
			finally:
				if not ok and on_synthesis_status:
					res_notify = on_synthesis_status(False)
					if asyncio.iscoroutine(res_notify):
						await res_notify

		if not ok:
			logger.info("🎙️ Transmisión de Cabina: Sintetizando locución fresca...")
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
					db_path=self.db_path,
					outro_mode=outro_mode,
				)
				ok = res.ok
				display_title = res.display_title
				display_artist = res.display_artist
				script = res.script
				radio_err = res.error
			except Exception as e:
				ok = False
				radio_err = f"{type(e).__name__}: {e}"
			finally:
				if not ok and on_synthesis_status:
					res_notify = on_synthesis_status(False)
					if asyncio.iscoroutine(res_notify):
						await res_notify

		return ok, display_title, script, radio_err, display_artist

	def prune_radio_archive(self, archive_dir: Path | None = None, max_files: int = 50) -> int:
		"""Elimina guiones históricos viejos del directorio de archivo."""
		target_dir = archive_dir or self.archive_dir
		if max_files <= 0 or not target_dir.is_dir():
			return 0
		try:
			for mp3 in target_dir.glob("radio_*.mp3"):
				mp3.unlink(missing_ok=True)
			txt_files = sorted(target_dir.glob("radio_*.txt"), key=lambda p: (p.stat().st_mtime, p.name))
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
		src_mp3_path: str | Path | None = None,
		archive_dir: Path | None = None,
		script_text: str = "",
		display_title: str = "",
		max_files: int = 50,
	) -> Path | None:
		"""Guarda el guion .txt en el archivo histórico con marca temporal."""
		if isinstance(src_mp3_path, Path) and src_mp3_path.is_dir() and archive_dir is None:
			target_dir = src_mp3_path
		else:
			target_dir = archive_dir or self.archive_dir
		try:
			target_dir.mkdir(parents=True, exist_ok=True)
			now = datetime.now(UTC).astimezone()
			ts_str = now.strftime("%Y-%m-%d_%H-%M-%S")
			dest_txt = target_dir / f"radio_{ts_str}.txt"
			if dest_txt.exists():
				dest_txt = target_dir / f"radio_{ts_str}_{now.microsecond:06d}.txt"
			header = f"Título: {display_title}\nFecha: {now.isoformat()}\n\n" if display_title else ""
			dest_txt.write_text(f"{header}{script_text.strip()}\n", encoding="utf-8")
			logger.debug(f"📻 Guion radial archivado en: {dest_txt.name}")
			self.prune_radio_archive(target_dir, max_files=max_files)
			return dest_txt
		except Exception as e:
			logger.debug(f"No se pudo archivar el guion radial: {e}")
			return None
