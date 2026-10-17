"""
Mezclador de audio con FFmpeg, incrustación de carátulas ID3 y generación de subtítulos LRC/SRT.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from app.domain.radio.banks import (
	DEFAULT_BG_VOLUME,
	DEFAULT_RADIO_ALBUM,
	DEFAULT_RADIO_ARTIST,
	DEFAULT_RADIO_TITLE,
)
from app.infrastructure.binaries.manager import find_binary, get_clean_env
from app.infrastructure.media.tts_cache import estimate_mp3_duration, is_valid_mp3_stream

logger = logging.getLogger("rockola.radio")


def is_valid_mp3_file(path: Path | str) -> bool:
	"""Verifica que el archivo exista y comience con un encabezado MP3 válido."""
	try:
		p = Path(path)
		if not p.is_file() or p.stat().st_size < 4:
			return False
		with p.open("rb") as f:
			head = f.read(10)
		return is_valid_mp3_stream(head)
	except Exception as e:
		logger.warning(f"Error comprobando validez de archivo MP3 '{path}': {e}")
		return False


def get_audio_duration(file_path: Path | str, timeout: float = 2.0) -> float:
	"""Obtiene la duración en segundos de un archivo de audio usando mutagen o ffprobe."""
	p = Path(file_path)
	if p.is_file():
		try:
			from mutagen import File as MutagenFile

			audio = MutagenFile(p)
			if audio and audio.info and getattr(audio.info, "length", None) is not None:
				dur = float(audio.info.length)
				if dur > 0.0:
					return dur
		except ImportError as e:
			logger.info(f"Librería opcional mutagen no disponible para calcular duración de {p}: {e}")
		except Exception as e:
			logger.warning(f"Error al calcular duración con mutagen para {p}: {e}")

	ffprobe_bin = find_binary("ffprobe")
	if not ffprobe_bin:
		return 0.0
	try:
		res = subprocess.run(
			[
				ffprobe_bin,
				"-v",
				"error",
				"-show_entries",
				"format=duration",
				"-of",
				"default=noprint_wrappers=1:nokey=1",
				str(file_path),
			],
			capture_output=True,
			text=True,
			timeout=timeout,
			check=False,
			env=get_clean_env(),
		)
		if res.returncode == 0 and res.stdout.strip():
			return float(res.stdout.strip())
		if res.returncode != 0:
			logger.warning(f"ffprobe falló al obtener duración de {file_path}: {res.stderr.strip()[:200]}")
	except Exception as e:
		logger.warning(f"Error ejecutando ffprobe para {file_path}: {e}")
	return 0.0


def format_lrc_timestamp(seconds: float) -> str:
	"""Formatea segundos como marca de tiempo LRC mm:ss.xx."""
	total_sec = max(0.0, seconds)
	mins = int(total_sec // 60)
	secs = total_sec % 60
	return f"{mins:02d}:{secs:05.2f}"


def format_srt_timestamp(seconds: float) -> str:
	"""Formatea segundos como marca de tiempo SRT hh:mm:ss,mmm."""
	total_sec = max(0.0, seconds)
	hours = int(total_sec // 3600)
	mins = int((total_sec % 3600) // 60)
	secs = int(total_sec % 60)
	millis = round((total_sec - int(total_sec)) * 1000)
	if millis >= 1000:
		secs += 1
		millis -= 1000
	return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def build_lrc_content(cues: list[tuple[float, float, str]]) -> str:
	"""Construye el contenido de letras sincronizadas en formato .lrc."""
	lines: list[str] = []
	for start, _end, text in cues:
		clean = text.strip()
		if clean:
			lines.append(f"[{format_lrc_timestamp(start)}] {clean}")
	return "\n".join(lines) + "\n" if lines else ""


def build_srt_content(cues: list[tuple[float, float, str]]) -> str:
	"""Construye el contenido de subtítulos en formato SubRip (.srt)."""
	blocks: list[str] = []
	idx = 1
	for start, end, text in cues:
		clean = text.strip()
		if clean:
			start_str = format_srt_timestamp(start)
			end_str = format_srt_timestamp(max(end, start + 0.1))
			blocks.append(f"{idx}\n{start_str} --> {end_str}\n{clean}\n")
			idx += 1
	return "\n".join(blocks)


def get_carpincho_cover_path() -> Path | None:
	"""Localiza la imagen del carpincho (public/favicon.png o dist/favicon.png)."""
	root = Path(__file__).resolve().parents[3]
	candidates = [
		root / "public" / "favicon.png",
		root / "dist" / "favicon.png",
	]
	if hasattr(sys, "_MEIPASS"):
		candidates.insert(0, Path(sys._MEIPASS) / "public" / "favicon.png")
		candidates.insert(1, Path(sys._MEIPASS) / "dist" / "favicon.png")

	for c in candidates:
		if c.is_file():
			return c
	return None


def embed_cover_art_in_mp3(
	mp3_path: Path | str,
	cover_image_path: Path | str | None = None,
	title: str | None = DEFAULT_RADIO_TITLE,
	artist: str | None = DEFAULT_RADIO_ARTIST,
	album: str = DEFAULT_RADIO_ALBUM,
	timeout: float = 10.0,
) -> bool:
	"""Incrusta la carátula del carpincho y metadatos ID3 en el archivo MP3."""
	mp3_p = Path(mp3_path)
	if not mp3_p.is_file():
		return False

	data_head = mp3_p.read_bytes()[:10]
	if not is_valid_mp3_stream(data_head):
		return False

	cover_p = Path(cover_image_path) if cover_image_path else get_carpincho_cover_path()
	if not cover_p or not cover_p.is_file():
		return False

	try:
		from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError

		try:
			tags = ID3(str(mp3_p))
		except ID3NoHeaderError:
			tags = ID3()

		cover_bytes = cover_p.read_bytes()
		mime = "image/png" if cover_p.suffix.lower() == ".png" else "image/jpeg"

		tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_bytes))
		if title:
			tags.add(TIT2(encoding=3, text=[title]))
		if artist:
			tags.add(TPE1(encoding=3, text=[artist]))
		if album:
			tags.add(TALB(encoding=3, text=[album]))

		tags.save(str(mp3_p))
		logger.debug(f"🖼️ Carátula del carpincho incrustada con mutagen en '{mp3_p.name}'")
		return True
	except ImportError as e:
		logger.info(f"Librería opcional mutagen no está disponible para ID3: {e}. Probando fallback con ffmpeg...")
	except Exception as e:
		logger.warning(f"Mutagen falló al incrustar carátula en {mp3_p}: {e}. Probando fallback con ffmpeg...")

	ffmpeg_bin = find_binary("ffmpeg")
	if ffmpeg_bin:
		tmp_tagged = mp3_p.parent / f".tmp_tag_{uuid.uuid4().hex[:8]}.mp3"
		cmd = [
			ffmpeg_bin,
			"-y",
			"-i",
			str(mp3_p),
			"-i",
			str(cover_p),
			"-map",
			"0:a",
			"-map",
			"1:v",
			"-c",
			"copy",
			"-id3v2_version",
			"3",
			"-metadata:s:v",
			"title=Cover",
			"-metadata:s:v",
			"comment=Cover (front)",
		]
		if title:
			cmd.extend(["-metadata", f"title={title}"])
		if artist:
			cmd.extend(["-metadata", f"artist={artist}"])
		if album:
			cmd.extend(["-metadata", f"album={album}"])
		cmd.append(str(tmp_tagged))

		try:
			proc = subprocess.run(
				cmd,
				capture_output=True,
				timeout=max(3.0, timeout * 0.5),
				check=False,
				env=get_clean_env(),
			)
			if proc.returncode == 0 and tmp_tagged.is_file() and tmp_tagged.stat().st_size > 0:
				tmp_tagged.replace(mp3_p)
				logger.debug(f"🖼️ Carátula del carpincho incrustada con ffmpeg en '{mp3_p.name}'")
				return True
			logger.warning(f"ffmpeg falló al incrustar carátula: {proc.stderr.decode('utf-8', errors='ignore')[:150]}")
		except Exception as e:
			logger.warning(f"Excepción usando ffmpeg para carátula: {e}")
		finally:
			if tmp_tagged.exists():
				try:
					tmp_tagged.unlink()
				except Exception as e:
					logger.warning(f"No se pudo eliminar archivo temporal {tmp_tagged}: {e}")

	return False


def mix_announcement_with_bg_track(
	voice_path: Path | str,
	output_path: Path | str,
	bg_track_path: Path | str,
	bg_offset: float = 0.0,
	bg_volume: float = DEFAULT_BG_VOLUME,
	timeout: float = 10.0,
) -> bool:
	"""Superpone la canción de fondo como cortina musical con la voz del locutor usando FFmpeg."""
	ffmpeg_bin = find_binary("ffmpeg")
	if not ffmpeg_bin:
		return False

	voice_p = Path(voice_path)
	bg_p = Path(bg_track_path)
	out_p = Path(output_path)

	if not voice_p.is_file() or not bg_p.is_file():
		return False

	voice_dur = get_audio_duration(voice_p, timeout=max(2.0, timeout * 0.3))
	if voice_dur > 2.0:
		fade_in = 1.0
		fade_out = 1.5
		fade_out_start = max(0.0, voice_dur - fade_out)
		filter_complex = (
			f"[0:a]volume=1.0[v];"
			f"[1:a]volume={bg_volume},afade=t=in:ss=0:d={fade_in},afade=t=out:st={fade_out_start:.2f}:d={fade_out}[bg];"
			f"[v][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0"
		)
	else:
		filter_complex = (
			f"[0:a]volume=1.0[v];[1:a]volume={bg_volume}[bg];"
			f"[v][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0"
		)

	tmp_out = Path(tempfile.gettempdir()) / f"rockola_mix_{uuid.uuid4().hex[:8]}.mp3"
	cmd = [
		ffmpeg_bin,
		"-y",
		"-i",
		str(voice_p),
		"-ss",
		str(max(0.0, bg_offset)),
		"-i",
		str(bg_p),
		"-filter_complex",
		filter_complex,
		"-c:a",
		"libmp3lame",
		"-b:a",
		"192k",
		str(tmp_out),
	]

	try:
		proc = subprocess.run(cmd, capture_output=True, timeout=max(5.0, timeout), check=False, env=get_clean_env())
		if proc.returncode == 0 and tmp_out.is_file() and tmp_out.stat().st_size > 0:
			tmp_dest = out_p.parent / f".tmp_{out_p.name}"
			shutil.copyfile(tmp_out, tmp_dest)
			tmp_dest.replace(out_p)
			logger.info(
				f"🎵 Cortina musical superpuesta con éxito desde el segundo {bg_offset:.1f} de '{bg_p.name}' (volumen {bg_volume * 100:.0f}%)"
			)
			return True
		logger.warning(f"ffmpeg falló al mezclar cortina musical: {proc.stderr.decode('utf-8', errors='ignore')[:200]}")
	except Exception as e:
		logger.warning(f"Error mezclando cortina musical con ffmpeg: {e}")
	finally:
		if tmp_out.exists():
			try:
				tmp_out.unlink()
			except Exception as e:
				logger.warning(f"No se pudo eliminar archivo temporal {tmp_out}: {e}")

	return False


__all__ = [
	"build_lrc_content",
	"build_srt_content",
	"embed_cover_art_in_mp3",
	"estimate_mp3_duration",
	"format_lrc_timestamp",
	"format_srt_timestamp",
	"get_audio_duration",
	"get_carpincho_cover_path",
	"is_valid_mp3_file",
	"is_valid_mp3_stream",
	"mix_announcement_with_bg_track",
]
