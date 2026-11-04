"""
Conversor de letras desde formatos de BetterLyrics (TTML, QRC, eLRC, LRC) hacia subtítulos ASS.
Adaptado e inspirado en el motor de conversión de elrc.py con tipado fuerte y sin dependencias gráficas.
"""

from __future__ import annotations

import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger("RockolaCarpincho")

# Etiquetas legibles para la interfaz del selector de proveedores
PROVIDER_LABELS: dict[str, tuple[str, str]] = {
	"binimum_lyrics": ("binimum", "Apple Music (binimum) - Palabra por palabra"),
	"binimumTtml": ("binimum", "Apple Music (binimum) - Palabra por palabra"),
	"golyrics_lyrics": ("golyrics", "Apple Music (golyrics) - Palabra por palabra"),
	"goLyricsApiTtml": ("golyrics", "Apple Music (golyrics) - Palabra por palabra"),
	"musixmatch_wordByWord": ("musixmatch_wbw", "Musixmatch - Palabra por palabra"),
	"musixmatchWordByWordLyrics": ("musixmatch_wbw", "Musixmatch - Palabra por palabra"),
	"qq_lyrics": ("qq", "QQ Music - Palabra por palabra"),
	"qqLyricsApiLyrics": ("qq", "QQ Music - Palabra por palabra"),
	"lrclib_synced": ("lrclib", "LRCLib - Sincronizado por línea"),
	"lrclibSyncedLyrics": ("lrclib", "LRCLib - Sincronizado por línea"),
	"musixmatch_synced": ("musixmatch", "Musixmatch - Sincronizado por línea"),
	"musixmatchSyncedLyrics": ("musixmatch", "Musixmatch - Sincronizado por línea"),
	"kugou_lyrics": ("kugou", "KuGou - Sincronizado por línea"),
	"kugouLyricsApiLyrics": ("kugou", "KuGou - Sincronizado por línea"),
}

PROVIDER_PRIORITY: tuple[str, ...] = (
	"binimum_lyrics",
	"binimumTtml",
	"golyrics_lyrics",
	"goLyricsApiTtml",
	"musixmatch_wordByWord",
	"musixmatchWordByWordLyrics",
	"qq_lyrics",
	"qqLyricsApiLyrics",
	"lrclib_synced",
	"lrclibSyncedLyrics",
	"musixmatch_synced",
	"musixmatchSyncedLyrics",
	"kugou_lyrics",
	"kugouLyricsApiLyrics",
)


class LyricsAssConverter:
	"""Motor de conversión de payloads SSE/JSON/TTML/QRC/LRC a formato Advanced SubStation Alpha (.ass)."""

	@staticmethod
	def fix_mojibake(text: str) -> str:
		"""Repara cadenas UTF-8 que fueron mal decodificadas como Windows-1252 o Latin-1 en origen."""
		if not text or not isinstance(text, str):
			return text

		if "Ã" not in text and "Â" not in text and "ï¼" not in text and "â€" not in text and "Ã©" not in text:
			return text

		for bad, good in (
			("ï¼š", "："),
			("ï¼ˆ", "（"),
			("ï¼‰", "）"),
			("ï¼Œ", "，"),
			("ï¼Ž", "。"),
			("ï¼ ", "！"),
			("ï¼Ÿ", "？"),
			("ï¼", "："),
			("â€™", "’"),
			("â€˜", "‘"),
			("â€œ", "“"),
			("â€”", "—"),
			("â€“", "–"),
			("â€¦", "…"),
		):
			if bad in text:
				text = text.replace(bad, good)

		for enc in ("cp1252", "latin1"):
			try:
				return text.encode(enc).decode("utf-8")
			except (UnicodeEncodeError, UnicodeDecodeError):
				pass

		if "\n" in text:
			return "\n".join(LyricsAssConverter.fix_mojibake(line) for line in text.split("\n"))

		def _repl_mojibake_bytes(m: re.Match[str]) -> str:
			tok = m.group(0)
			for enc in ("cp1252", "latin1"):
				try:
					return tok.encode(enc).decode("utf-8")
				except (UnicodeEncodeError, UnicodeDecodeError):
					pass
			return tok

		return re.sub(r"[\xc2\xc3][\x80-\xbf]", _repl_mojibake_bytes, text)

	@staticmethod
	def parse_time(time_str: str | float | None) -> float:
		"""Convierte una cadena de tiempo TTML o LRC a segundos flotantes."""
		if not time_str:
			return 0.0

		raw = str(time_str).strip().strip("[]")

		clock_regex = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d+))?$")
		match = clock_regex.match(raw)
		if match:
			h = float(match.group(1)) if match.group(1) else 0.0
			m = float(match.group(2))
			s = float(match.group(3))
			ms = float(f"0.{match.group(4)}") if match.group(4) else 0.0
			return (h * 3600.0) + (m * 60.0) + s + ms

		try:
			parts = [float(p) for p in raw.split(":")]
			if len(parts) == 3:
				return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
			if len(parts) == 2:
				return parts[0] * 60.0 + parts[1]
			if len(parts) == 1:
				return parts[0]
		except ValueError:
			pass

		try:
			if raw.endswith("s") and not raw.endswith("ms"):
				return float(raw[:-1])
			if raw.endswith("ms"):
				return float(raw[:-2]) / 1000.0
			if raw.endswith("m"):
				return float(raw[:-1]) * 60.0
			if raw.endswith("h"):
				return float(raw[:-1]) * 3600.0
		except ValueError:
			pass

		return 0.0

	@staticmethod
	def format_ass_timestamp(seconds: float) -> str:
		"""Formatea segundos flotantes al formato ASS h:mm:ss.cc."""
		seconds = max(seconds, 0.0)
		h = int(seconds // 3600)
		m = int((seconds % 3600) // 60)
		s = seconds % 60
		return f"{h}:{m:02d}:{s:05.2f}"

	@staticmethod
	def format_lrc_timestamp(seconds: float) -> str:
		"""Convierte segundos a formato estándar LRC [mm:ss.xx]."""
		seconds = max(seconds, 0.0)
		m = int(seconds // 60)
		s = seconds % 60
		return f"{m:02d}:{s:05.2f}"

	@classmethod
	def ass_to_lrc(cls, ass_content: str) -> str:
		"""
		Convierte el contenido de un archivo .ass a formato .lrc estándar por línea.
		Extrae los tiempos de inicio de las líneas 'Dialogue:' y elimina etiquetas {...} de karaoke o formato.
		"""
		if not ass_content:
			return ""

		lrc_lines: list[str] = []
		dialogue_re = re.compile(r"^Dialogue:\s*[^,]+,([^,]+),([^,]+),[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,(.*)$")
		tag_re = re.compile(r"\{[^}]*\}")

		for line in ass_content.splitlines():
			line_str = line.strip()
			m = dialogue_re.match(line_str)
			if not m:
				continue
			start_time_str = m.group(1).strip()
			text_part = m.group(3).strip()

			# Limpiar tags de estilo y karaoke ASS (\kf, etc.)
			clean_text = tag_re.sub("", text_part)
			clean_text = clean_text.replace(r"\N", " ").replace(r"\n", " ").replace(r"\h", " ").strip()

			if not clean_text:
				continue

			start_sec = cls.parse_time(start_time_str)
			ts_lrc = cls.format_lrc_timestamp(start_sec)
			lrc_lines.append(f"[{ts_lrc}]{clean_text}")

		return "\n".join(lrc_lines) + ("\n" if lrc_lines else "")

	@staticmethod
	def _parse_offset_from_header(content_str: str) -> float:
		"""Extrae el tag [offset:...] y lo convierte a segundos aplicando heurística decimal."""
		offset_regex = re.compile(r"\[offset:\s*([+-]?\d+(?:\.\d+)?)\]", re.IGNORECASE)
		match = offset_regex.search(content_str)
		if not match:
			return 0.0

		raw_str = match.group(1)
		raw_val = float(raw_str)
		# Heurística de elrc.py: valor pequeño con punto decimal indica segundos (ej. Musixmatch)
		if abs(raw_val) < 1000.0 and "." in raw_str:
			return raw_val
		return raw_val / 1000.0

	@staticmethod
	def _unwrap_and_clean_ttml(ttml_content: str) -> str:
		"""Desenvuelve posibles capas JSON alrededor de un documento TTML."""
		content = ttml_content
		for _ in range(3):
			if content.strip().startswith("<"):
				break
			try:
				parsed = json.loads(content)
				if isinstance(parsed, dict) and "ttml" in parsed:
					content = str(parsed["ttml"])
				elif isinstance(parsed, str):
					content = parsed
				else:
					break
			except (json.JSONDecodeError, ValueError, TypeError):
				break
		return content

	@staticmethod
	def _strip_namespaces(elem: ET.Element) -> ET.Element:
		"""Elimina prefijos de espacio de nombres XML para facilitar la búsqueda de nodos."""
		for node in elem.iter():
			if "}" in node.tag:
				node.tag = node.tag.split("}", 1)[1]
			for key in list(node.attrib.keys()):
				if "}" in key:
					new_key = key.split("}", 1)[1]
					node.attrib[new_key] = node.attrib.pop(key)
		return elem

	@classmethod
	def parse_ttml(cls, ttml_content: str) -> list[dict[str, Any]]:
		"""Parsea un documento XML TTML extrayendo líneas y sílabas/palabras con tiempos."""
		content = cls._unwrap_and_clean_ttml(ttml_content)
		try:
			root = ET.fromstring(content)
			root = cls._strip_namespaces(root)
		except ET.ParseError as exc:
			logger.warning(f"Error al parsear XML TTML: {exc}")
			return []

		global_offset = 0.0
		itunes_meta = root.find(".//iTunesMetadata")
		if itunes_meta is not None:
			audio_tag = itunes_meta.find("audio")
			if audio_tag is not None and audio_tag.get("lyricOffset"):
				try:
					global_offset = float(audio_tag.get("lyricOffset", "0")) / 1000.0
				except ValueError:
					pass

		parsed_lines: list[dict[str, Any]] = []
		for p in root.findall(".//p"):
			line_begin = p.get("begin")
			line_end = p.get("end")
			if not line_begin:
				continue

			line_start_sec = max(0.0, cls.parse_time(line_begin) + global_offset)
			line_end_sec = max(0.0, cls.parse_time(line_end) + global_offset) if line_end else 0.0

			words_list: list[dict[str, Any]] = []
			line_text_parts: list[str] = []
			spans = list(p.iter("span"))

			if spans:
				for span in spans:
					word_begin = span.get("begin")
					word_end = span.get("end")
					word_text = span.text or ""
					tail = span.tail or ""
					trailing_space = bool(tail) and tail.strip() == ""

					if word_text:
						line_text_parts.append(word_text)
						if trailing_space:
							line_text_parts.append(" ")

						clean_word = word_text.strip()
						if clean_word and word_begin:
							w_start = max(0.0, cls.parse_time(word_begin) + global_offset)
							w_end = max(0.0, cls.parse_time(word_end) + global_offset) if word_end else 0.0
							words_list.append(
								{
									"text": clean_word,
									"startTime": w_start,
									"endTime": w_end,
									"trailing_space": trailing_space,
								}
							)
				full_line_text = "".join(line_text_parts)
			else:
				full_line_text = "".join(p.itertext()).strip()

			full_line_text = re.sub(r"\s+", " ", full_line_text).strip()
			if full_line_text:
				parsed_lines.append(
					{
						"text": full_line_text,
						"startTime": line_start_sec,
						"endTime": line_end_sec,
						"words": words_list,
					}
				)

		return cls._fix_durations(parsed_lines)

	@classmethod
	def parse_qrc(cls, content: str, offset: float = 0.0) -> list[dict[str, Any]]:
		"""Parsea el formato QRC de QQ Music (embebido o crudo)."""
		qrc_text = content
		match = re.search(r'LyricContent\s*=\s*(["\'])(.*?)\1\s*(?:/>|>)', content, re.DOTALL)
		if not match:
			match = re.search(r'LyricContent\s*=\s*(["\'])(.*)\1', content, re.DOTALL)

		if match:
			qrc_text = html.unescape(match.group(2))
			qrc_text = qrc_text.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")

		parsed_lines: list[dict[str, Any]] = []
		line_regex = re.compile(r"^\[\s*(\d+)\s*,\s*(\d+)\s*\](.*)")
		word_regex = re.compile(r"(.*?)\(\s*(\d+)\s*,\s*(\d+)\s*\)")

		for raw_line in qrc_text.splitlines():
			line = raw_line.strip()
			if not line:
				continue

			m_line = line_regex.match(line)
			if not m_line:
				continue

			line_start = max(0.0, float(m_line.group(1)) / 1000.0 - offset)
			line_dur = float(m_line.group(2)) / 1000.0
			remainder = m_line.group(3)
			words: list[dict[str, Any]] = []
			full_text = ""

			for m_word in word_regex.finditer(remainder):
				w_text = cls.fix_mojibake(html.unescape(m_word.group(1)))
				w_start = max(0.0, float(m_word.group(2)) / 1000.0 - offset)
				w_dur = float(m_word.group(3)) / 1000.0
				full_text += w_text

				if not w_text.strip():
					if words:
						words[-1]["text"] += w_text
						words[-1]["endTime"] = max(words[-1]["endTime"], w_start + w_dur)
					continue

				words.append(
					{
						"text": w_text,
						"startTime": w_start,
						"endTime": w_start + w_dur,
						"trailing_space": False,
					}
				)

			if not words and remainder:
				full_text = remainder

			if full_text.strip():
				parsed_lines.append(
					{
						"text": cls.fix_mojibake(full_text.strip()),
						"startTime": line_start,
						"endTime": line_start + line_dur,
						"words": words,
					}
				)

		parsed_lines.sort(key=lambda x: x["startTime"])
		return cls._fix_durations(parsed_lines)

	@classmethod
	def parse_elrc_line(cls, line: str, offset: float = 0.0) -> dict[str, Any] | None:
		"""Parsea una línea en formato A2 eLRC (ej. Musixmatch wordByWord)."""
		line_match = re.match(r"^\[(\d+):(\d{2}\.\d{2,3})\](.*)", line)
		if not line_match:
			return None

		m = float(line_match.group(1))
		s = float(line_match.group(2))
		start_time = max(0.0, (m * 60.0 + s) - offset)
		remainder = line_match.group(3)

		tag_regex = re.compile(r"<(\d{2}:\d{2}\.\d{2,3})>([^<]*)")
		matches = list(tag_regex.finditer(remainder))

		words: list[dict[str, Any]] = []
		full_text_parts: list[str] = []

		for i, match in enumerate(matches):
			t_str = match.group(1)
			word_text = cls.fix_mojibake(match.group(2).strip())
			word_start = max(0.0, cls.parse_time(t_str) - offset)

			word_end = word_start + 0.5
			if i < len(matches) - 1:
				next_start_str = matches[i + 1].group(1)
				word_end = max(0.0, cls.parse_time(next_start_str) - offset)

			if word_text:
				words.append(
					{
						"text": word_text,
						"startTime": word_start,
						"endTime": word_end,
						"trailing_space": True,
					}
				)
				full_text_parts.append(word_text)

		if words:
			words[-1]["trailing_space"] = False

		full_text = " ".join(full_text_parts).strip()
		if not words and remainder.strip():
			full_text = cls.fix_mojibake(remainder.strip())

		if not full_text:
			return None

		end_time = words[-1]["endTime"] if words else 0.0
		return {
			"startTime": start_time,
			"endTime": end_time,
			"text": full_text,
			"words": words,
		}

	@classmethod
	def parse_lrc_lines(cls, content: str, offset: float = 0.0) -> list[dict[str, Any]]:
		"""Parsea líneas LRC estándar sincronizadas por línea."""
		parsed: list[dict[str, Any]] = []
		time_regex = re.compile(r"\[(\d+):(\d{2})(?:[.:](\d{1,3}))?\]")

		for raw_line in content.split("\n"):
			line = raw_line.strip()
			if not line:
				continue
			if line.lower().startswith(("[offset:", "[ti:", "[ar:", "[al:", "[by:", "[length:")):
				continue

			timestamps = list(time_regex.finditer(line))
			if not timestamps:
				continue

			text_content = cls.fix_mojibake(time_regex.sub("", line).strip())
			if not text_content:
				continue

			for match in timestamps:
				m = float(match.group(1))
				s = float(match.group(2))
				ms_part = match.group(3)
				if ms_part:
					s += float(f"0.{ms_part}")

				start_time = max(0.0, (m * 60.0 + s) - offset)
				parsed.append(
					{
						"startTime": start_time,
						"endTime": 0.0,
						"text": text_content,
						"words": [],
					}
				)

		parsed.sort(key=lambda x: x["startTime"])
		return parsed

	@staticmethod
	def _fix_durations(parsed_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
		"""Fusiona espacios cortos entre palabras para evitar parpadeos en el karaoke."""
		for line in parsed_lines:
			words = line.get("words", [])
			if not words or len(words) < 2:
				continue
			for i in range(len(words) - 1, 0, -1):
				curr = words[i]
				prev = words[i - 1]
				curr_duration = curr["endTime"] - curr["startTime"]
				if not curr["text"].strip() and prev["text"].strip() and curr_duration < 0.15:
					prev["endTime"] = curr["endTime"]
					words.pop(i)
		return parsed_lines

	@classmethod
	def generate_ass(
		cls,
		parsed_data: list[dict[str, Any]],
		title: str = "Canción",
		artist: str = "Artista",
		provider_label: str = "BetterLyrics",
		force_spaces: bool = False,
	) -> str:
		"""Genera el documento ASS completo con estilos y etiquetas \\kf a partir de líneas parseadas."""
		clean_title = cls.fix_mojibake(title or "Canción")
		clean_artist = cls.fix_mojibake(artist or "Artista")

		header = (
			"[Script Info]\n"
			f"; Letra generada por La Rockola del Carpincho ({provider_label})\n"
			f"Title: {clean_title}\n"
			f"Original Artist: {clean_artist}\n"
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
			"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
		)
		lines = [header]

		for i, line in enumerate(parsed_data):
			start_time_seconds = float(line["startTime"])
			raw_end = float(line.get("endTime", 0.0))
			words = line.get("words") or []

			if raw_end <= start_time_seconds:
				if words:
					raw_end = float(words[-1]["endTime"]) + 0.1
				elif i < len(parsed_data) - 1:
					next_start = float(parsed_data[i + 1]["startTime"])
					raw_end = min(next_start, start_time_seconds + 6.0)
				else:
					raw_end = start_time_seconds + 4.0

			if i < len(parsed_data) - 1:
				next_start = float(parsed_data[i + 1]["startTime"])
				if raw_end > next_start:
					overlap = raw_end - next_start
					if overlap < 0.3 or not words:
						raw_end = max(next_start, start_time_seconds)

			start_time_ass = cls.format_ass_timestamp(start_time_seconds)
			end_time_ass = cls.format_ass_timestamp(raw_end)

			ass_text = ""
			if words:
				for j, word in enumerate(words):
					word_text = cls.fix_mojibake(word["text"])
					w_start = float(word["startTime"])
					if j < len(words) - 1:
						w_end = float(words[j + 1]["startTime"])
					else:
						w_end = raw_end

					duration_cs = max(int((w_end - w_start) * 100), 1)
					ass_text += f"{{\\kf{duration_cs}}}{word_text}"

					if word.get("trailing_space", False) or force_spaces:
						ass_text += " "
			else:
				ass_text = cls.fix_mojibake(line.get("text", ""))

			event_line = f"Dialogue: 0,{start_time_ass},{end_time_ass},Default,,0,0,0,,{ass_text}"
			lines.append(event_line)

		return "\n".join(lines) + "\n"

	@classmethod
	def _extract_from_json_obj(
		cls,
		json_obj: Any,
		lyrics_data: dict[str, Any],
		metadata: dict[str, Any],
	) -> None:
		"""Extrae campos de letras y metadatos desde un bloque JSON de BetterLyrics."""
		if not isinstance(json_obj, dict):
			return

		if "song" in json_obj:
			metadata["title"] = json_obj.get("song")
		if "artist" in json_obj:
			metadata["artist"] = json_obj.get("artist")
		if "album" in json_obj:
			metadata["album"] = json_obj.get("album")
		if "duration" in json_obj:
			metadata["duration"] = json_obj.get("duration")

		if json_obj.get("musixmatchWordByWordLyrics"):
			lyrics_data["musixmatchWordByWordLyrics"] = json_obj["musixmatchWordByWordLyrics"]
		if json_obj.get("musixmatchSyncedLyrics"):
			lyrics_data["musixmatchSyncedLyrics"] = json_obj["musixmatchSyncedLyrics"]
		if json_obj.get("lrclibSyncedLyrics"):
			lyrics_data["lrclibSyncedLyrics"] = json_obj["lrclibSyncedLyrics"]

		if json_obj.get("goLyricsApiTtml"):
			g_wrapper = json_obj["goLyricsApiTtml"]
			try:
				g_data = json.loads(g_wrapper)
				lyrics_data["goLyricsApiTtml"] = g_data.get("ttml", g_wrapper)
			except (json.JSONDecodeError, ValueError, TypeError):
				lyrics_data["goLyricsApiTtml"] = g_wrapper

		if json_obj.get("binimumTtml"):
			lyrics_data["binimumTtml"] = json_obj["binimumTtml"]

		if json_obj.get("qqLyricsApiLyrics"):
			qq_wrapper = json_obj["qqLyricsApiLyrics"]
			try:
				qq_data = json.loads(qq_wrapper)
				lyrics_data["qqLyricsApiLyrics"] = qq_data.get("lyrics", qq_wrapper)
			except (json.JSONDecodeError, ValueError, TypeError):
				lyrics_data["qqLyricsApiLyrics"] = qq_wrapper

		if json_obj.get("kugouLyricsApiLyrics"):
			kg_wrapper = json_obj["kugouLyricsApiLyrics"]
			try:
				kg_data = json.loads(kg_wrapper)
				lyrics_data["kugouLyricsApiLyrics"] = kg_data.get("lyrics", kg_wrapper)
			except (json.JSONDecodeError, ValueError, TypeError):
				lyrics_data["kugouLyricsApiLyrics"] = kg_wrapper

		if "results" in json_obj and isinstance(json_obj["results"], dict):
			res = json_obj["results"]
			provider = json_obj.get("provider", "unknown_provider")

			if res.get("wordByWord"):
				lyrics_data[f"{provider}_wordByWord"] = res["wordByWord"]
			if res.get("synced"):
				lyrics_data[f"{provider}_synced"] = res["synced"]
			if res.get("lyrics"):
				val = res["lyrics"]
				try:
					inner = json.loads(val)
					if isinstance(inner, dict):
						if "ttml" in inner:
							val = inner["ttml"]
						elif "lyrics" in inner:
							val = inner["lyrics"]
				except (json.JSONDecodeError, ValueError, TypeError):
					pass
				lyrics_data[f"{provider}_lyrics"] = val

	@classmethod
	def parse_payload(cls, content: str) -> tuple[dict[str, Any], dict[str, Any]]:
		"""Parsea un stream SSE (Server-Sent Events) o JSON de BetterLyrics."""
		lyrics_data: dict[str, Any] = {}
		metadata: dict[str, Any] = {}

		raw = content.strip()
		if not raw:
			return lyrics_data, metadata

		if "event:" in raw and "data:" in raw:
			current_data_blocks: list[str] = []
			for line in raw.splitlines():
				if line.startswith("data:"):
					current_data_blocks.append(line[len("data:") :])
				elif not line.strip() and current_data_blocks:
					try:
						data_obj = json.loads("".join(current_data_blocks))
						cls._extract_from_json_obj(data_obj, lyrics_data, metadata)
					except json.JSONDecodeError:
						pass
					current_data_blocks = []

			if current_data_blocks:
				try:
					data_obj = json.loads("".join(current_data_blocks))
					cls._extract_from_json_obj(data_obj, lyrics_data, metadata)
				except json.JSONDecodeError:
					pass
		else:
			try:
				data_obj = json.loads(raw)
				cls._extract_from_json_obj(data_obj, lyrics_data, metadata)
			except json.JSONDecodeError:
				pass

		for key, value in list(lyrics_data.items()):
			if isinstance(value, str):
				lyrics_data[key] = cls.fix_mojibake(value)
		for key, value in list(metadata.items()):
			if isinstance(value, str):
				metadata[key] = cls.fix_mojibake(value)

		return lyrics_data, metadata

	@classmethod
	def convert_source_to_ass(
		cls,
		raw_source: str | list[str],
		source_key: str = "raw",
		title: str = "Canción",
		artist: str = "Artista",
	) -> tuple[str, bool]:
		"""
		Convierte el contenido de una fuente individual a formato ASS.
		Devuelve (ass_content, has_syllables). Si no contiene líneas sincronizadas válidas, devuelve ("", False).
		"""
		content_str = "\n".join(raw_source) if isinstance(raw_source, list) else str(raw_source).strip()
		if not content_str:
			return "", False

		parsed_lines: list[dict[str, Any]] = []

		if source_key in ("binimum_lyrics", "binimumTtml", "golyrics_lyrics", "goLyricsApiTtml"):
			parsed_lines = cls.parse_ttml(content_str)
		elif source_key in ("qq_lyrics", "qqLyricsApiLyrics"):
			offset = cls._parse_offset_from_header(content_str)
			parsed_lines = cls.parse_qrc(content_str, offset=offset)
		elif source_key in ("musixmatch_wordByWord", "musixmatchWordByWordLyrics"):
			offset = cls._parse_offset_from_header(content_str)
			for line in content_str.splitlines():
				p = cls.parse_elrc_line(line.strip(), offset=offset)
				if p:
					parsed_lines.append(p)
			parsed_lines = cls._fix_durations(parsed_lines)
		elif source_key in (
			"lrclib_synced",
			"lrclibSyncedLyrics",
			"musixmatch_synced",
			"musixmatchSyncedLyrics",
			"kugou_lyrics",
			"kugouLyricsApiLyrics",
		):
			offset = cls._parse_offset_from_header(content_str)
			parsed_lines = cls.parse_lrc_lines(content_str, offset=offset)
		else:
			# Detección automática para archivos locales (.lrc / .elrc / .ttml)
			if content_str.startswith("<") or "<tt" in content_str:
				parsed_lines = cls.parse_ttml(content_str)
			elif re.search(r"<\d{2}:\d{2}", content_str):
				offset = cls._parse_offset_from_header(content_str)
				for line in content_str.splitlines():
					p = cls.parse_elrc_line(line.strip(), offset=offset)
					if p:
						parsed_lines.append(p)
				parsed_lines = cls._fix_durations(parsed_lines)
			else:
				offset = cls._parse_offset_from_header(content_str)
				parsed_lines = cls.parse_lrc_lines(content_str, offset=offset)

		if not parsed_lines:
			return "", False

		has_syllables = any(bool(line.get("words")) for line in parsed_lines)
		_, provider_label = PROVIDER_LABELS.get(source_key, (source_key, source_key))
		ass_text = cls.generate_ass(
			parsed_lines,
			title=title,
			artist=artist,
			provider_label=provider_label,
		)
		return ass_text, has_syllables

	@classmethod
	def convert_payload_to_providers(
		cls,
		raw_payload: str,
		default_title: str = "Canción",
		default_artist: str = "Artista",
	) -> list[dict[str, Any]]:
		"""
		Procesa el stream SSE/JSON completo de BetterLyrics y devuelve la lista ordenada
		de proveedores cuyos resultados tienen sincronización válida convertidos a ASS.
		"""
		lyrics_data, extracted_meta = cls.parse_payload(raw_payload)
		title = str(extracted_meta.get("title") or default_title)
		artist = str(extracted_meta.get("artist") or default_artist)

		ordered_keys: list[str] = [k for k in PROVIDER_PRIORITY if k in lyrics_data]
		for k in lyrics_data:
			if k not in ordered_keys:
				ordered_keys.append(k)

		providers_out: list[dict[str, Any]] = []
		seen_provider_ids: set[str] = set()

		for key in ordered_keys:
			raw_val = lyrics_data.get(key)
			if not raw_val:
				continue

			ass_content, has_syllables = cls.convert_source_to_ass(
				raw_val,
				source_key=key,
				title=title,
				artist=artist,
			)
			if not ass_content:
				continue

			prov_id, prov_name = PROVIDER_LABELS.get(key, (key, f"{key}"))
			if prov_id in seen_provider_ids:
				continue
			seen_provider_ids.add(prov_id)

			providers_out.append(
				{
					"provider": prov_id,
					"name": prov_name,
					"has_syllables": has_syllables,
					"ass": ass_content,
				}
			)

		return providers_out
