"""
Planificador de diálogo de cabina entre locutores carpinchos, segmentación horaria
y agrupación de turnos de habla para síntesis con prosodia natural.
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from pathlib import Path

from app.domain.radio.banks import (
	DEFAULT_COHOST_NAME,
	HOUR_NAMES,
	MINUTE_SEGMENTS,
	OUTROS_CHISMES,
	PASES_A_CLIMA,
	RADIO_HANDOFFS,
	RADIO_INTROS,
	RADIO_OUTROS,
	RADIO_OUTROS_BREAK,
	RADIO_OUTROS_DJ,
	RADIO_OUTROS_PAUSE,
	RADIO_REACTIONS,
	REACCIONES_CLIMA,
	REACCIONES_FORTUNA,
	SPECIAL_HOURS,
	VOICE_ELENA,
	VOICE_NAMES,
	VOICES,
	RadioContext,
	RadioPhrase,
	build_radio_context,
	expand_phrase_variants,
	filter_by_context,
	get_lead_ins_for_category,
	get_outros_for_category,
	get_reactions_for_category,
	render_phrase,
	resolve_segment_category,
)
from app.domain.radio.nlp import (
	_normalize_phrase_key,
	render_tracked_phrase,
	select_fortune,
	weighted_choice_by_recency,
)
from app.infrastructure.weather.client import format_temperature

NO_MERGE_CATEGORIES: set[str] = {"intro", "hora", "minuto", "clima", "salida"}


def select_radio_hosts(
	host_voice: str | None = None,
	is_system_fortune: bool = False,
) -> tuple[str, str]:
	"""Selecciona el locutor principal (host) y el co-conductor (cohost), garantizando host != cohost."""
	if not host_voice or host_voice not in VOICES:
		host = random.choice(VOICES)
	else:
		host = host_voice

	other_voices = [v for v in VOICES if v != host]

	if is_system_fortune:
		cohost = random.choice(other_voices) if host == VOICE_ELENA else VOICE_ELENA
	else:
		cohost = random.choice(other_voices)

	return host, cohost


_ACCENT_MAP = {
	"a": "á",
	"e": "é",
	"i": "í",
	"o": "ó",
	"u": "ú",
	"A": "Á",
	"E": "É",
	"I": "Í",
	"O": "Ó",
	"U": "Ú",
}

_VOSEO_ROOTS = (
	"acomoda",
	"acorda",
	"agarra",
	"ajusta",
	"anota",
	"apura",
	"asoma",
	"cambia",
	"canta",
	"ceba",
	"conta",
	"deci",
	"deja",
	"echa",
	"escucha",
	"fija",
	"guarda",
	"hace",
	"larga",
	"manda",
	"mete",
	"olvida",
	"pedi",
	"pega",
	"pone",
	"prepara",
	"presta",
	"prende",
	"senta",
	"subi",
	"tira",
	"toca",
	"toma",
)

_VOSEO_PATTERN = re.compile(
	r"\b(?P<root>"
	+ "|".join(sorted(_VOSEO_ROOTS, key=len, reverse=True))
	+ r")(?P<pron>mela|melo|tela|telo|sela|selo|me|te|se|le|lo|la|nos|les|los|las)\b",
	re.IGNORECASE,
)

_REVERSE_ACCENT_MAP = {
	"á": "a",
	"é": "e",
	"í": "i",
	"ó": "o",
	"ú": "u",
	"Á": "A",
	"É": "E",
	"I": "I",
	"O": "O",
	"U": "Ú",
}

_VOSEO_ACCENTED_ROOTS = tuple(root[:-1] + _ACCENT_MAP.get(root[-1], root[-1]) for root in _VOSEO_ROOTS)

_VOSEO_CLEAN_PATTERN = re.compile(
	r"\b(?P<root>"
	+ "|".join(sorted(_VOSEO_ACCENTED_ROOTS, key=len, reverse=True))
	+ r")(?P<pron>mela|melo|tela|telo|sela|selo|me|te|se|le|lo|la|nos|les|los|las)\b",
	re.IGNORECASE,
)


def _replace_voseo_accent(match: re.Match) -> str:
	root = match.group("root")
	pron = match.group("pron")
	last_char = root[-1]
	accented = _ACCENT_MAP.get(last_char, last_char)
	return f"{root[:-1]}{accented}{pron}"


def _restore_voseo_accent(match: re.Match) -> str:
	root = match.group("root")
	pron = match.group("pron")
	last_char = root[-1]
	unaccented = _REVERSE_ACCENT_MAP.get(last_char, last_char)
	return f"{root[:-1]}{unaccented}{pron}"


def apply_rioplatense_tts_phonetics(text: str) -> str:
	"""
	Transforma el texto para Edge-TTS aplicando fonética rioplatense:
	1. Acentúa prosódicamente verbos imperativos de voseo con pronombres enclíticos.
	2. Convierte 'DJ' en 'DiYei' para locución criolla natural.
	"""
	if not text:
		return ""
	result = _VOSEO_PATTERN.sub(_replace_voseo_accent, text)
	return re.sub(r"\bDJ\b", "DiYei", result, flags=re.IGNORECASE)


def clean_subtitle_text(text: str) -> str:
	"""
	Limpia las tildes prosódicas de Edge-TTS y abreviaturas fonéticas para que los
	subtítulos en pantalla mantengan su ortografía correcta y natural.
	"""
	if not text:
		return ""
	result = _VOSEO_CLEAN_PATTERN.sub(_restore_voseo_accent, text)
	return re.sub(r"\bDiYei\b", "DJ", result, flags=re.IGNORECASE)


def format_fortune_for_speech(fortuna: str | tuple[str, str] | RadioPhrase) -> str:
	"""Prepara el texto de una fortuna para locución quitando comillas duras, asegurando puntuación terminal y fonética."""
	raw = fortuna[0] if isinstance(fortuna, (tuple, list)) else str(fortuna)
	cleaned = raw.strip().strip("\"'«»")
	if not cleaned.endswith((".", "!", "?", "…")):
		cleaned = f"{cleaned}."
	return apply_rioplatense_tts_phonetics(cleaned)


def get_modular_hour_segments() -> list[str]:
	"""Genera la lista con los 24 segmentos modulares de hora."""
	return [HOUR_NAMES[h % 12] for h in range(24)]


def get_modular_minute_segments() -> list[str]:
	"""Genera la lista con los segmentos modulares de minutos (1 a 59 minutos más expresiones cada 5 min)."""
	mins = ["un minuto." if m == 1 else f"{m} minutos." for m in range(1, 60)]
	for seg in MINUTE_SEGMENTS:
		if seg not in mins:
			mins.append(seg)
	return mins


def get_all_time_segments() -> list[str]:
	"""Genera todas las combinaciones posibles de locución horaria para precarga en caché."""
	segments: list[str] = []
	for special in SPECIAL_HOURS.values():
		if special not in segments:
			segments.append(special)
	for hora in HOUR_NAMES:
		for minuto in MINUTE_SEGMENTS:
			combo = f"{hora} {minuto}"
			if combo not in segments:
				segments.append(combo)
	return segments


def get_all_degree_segments(min_deg: int = -10, max_deg: int = 45) -> list[str]:
	"""Devuelve las frases de temperaturas en grados para locución modular del clima."""
	segs: list[str] = []
	for d in range(min_deg, max_deg + 1):
		formatted = format_temperature(d)
		if formatted not in segs:
			segs.append(formatted)
		direct = f"{d} grados"
		if direct not in segs:
			segs.append(direct)
	return segs


def get_all_weather_handoff_segments() -> list[str]:
	res: list[str] = []
	for tpl in PASES_A_CLIMA:
		for variant in expand_phrase_variants(tpl):
			if variant not in res:
				res.append(variant)
	return res


def get_all_weather_reaction_segments() -> list[str]:
	res: list[str] = []
	for reactions in REACCIONES_CLIMA.values():
		for r in reactions:
			for variant in expand_phrase_variants(r):
				if variant not in res:
					res.append(variant)
	return res


def get_all_fortune_reaction_segments() -> list[str]:
	res: list[str] = []
	for r in REACCIONES_FORTUNA:
		for variant in expand_phrase_variants(r):
			if variant not in res:
				res.append(variant)
	return res


def get_all_intro_segments() -> list[str]:
	res: list[str] = []
	for intro in RADIO_INTROS:
		for variant in expand_phrase_variants(intro):
			if variant not in res:
				res.append(variant)
	return res


def get_all_outro_segments() -> list[str]:
	res: list[str] = []
	for outro in (*RADIO_OUTROS, *RADIO_OUTROS_PAUSE, *RADIO_OUTROS_BREAK, *OUTROS_CHISMES, *RADIO_OUTROS_DJ):
		for variant in expand_phrase_variants(outro):
			if variant not in res:
				res.append(variant)
	return res


def get_all_handoff_segments() -> list[str]:
	res: list[str] = []
	for h in RADIO_HANDOFFS:
		for variant in expand_phrase_variants(h):
			if variant not in res:
				res.append(variant)
	return res


def get_all_reaction_segments() -> list[str]:
	res: list[str] = []
	for r in RADIO_REACTIONS:
		for variant in expand_phrase_variants(r):
			if variant not in res:
				res.append(variant)
	return res


def get_modular_time_segments(dt: datetime | None = None) -> tuple[str, str | None, str]:
	"""Divide el anuncio de la hora en segmentos modulares redondeados cada 5 minutos."""
	if dt is None:
		dt = datetime.now(UTC).astimezone()

	hour = dt.hour
	minute = dt.minute

	if minute in range(3, 8):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[1]
	elif minute in range(8, 13):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[2]
	elif minute in range(13, 18):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[3]
	elif minute in range(18, 23):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[4]
	elif minute in range(23, 28):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[5]
	elif minute in range(28, 33):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[6]
	elif minute in range(33, 38):
		hora_seg = HOUR_NAMES[hour % 12]
		minuto_seg = MINUTE_SEGMENTS[7]
	elif minute in range(38, 43):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[8]
	elif minute in range(43, 48):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[9]
	elif minute in range(48, 53):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[10]
	elif minute in range(53, 58):
		next_hour = (hour + 1) % 24
		hora_seg = HOUR_NAMES[next_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[11]
	else:
		target_hour = (hour + 1) % 24 if minute >= 58 else hour
		if target_hour in SPECIAL_HOURS:
			special = SPECIAL_HOURS[target_hour]
			return special, None, special
		hora_seg = HOUR_NAMES[target_hour % 12]
		minuto_seg = MINUTE_SEGMENTS[0]

	full_time_str = f"{hora_seg} {minuto_seg}"
	return hora_seg, minuto_seg, full_time_str


def get_fortune_voice(is_system_fortune: bool, host_voice: str) -> str:
	"""Determina la voz para sintetizar la fortuna radial."""
	if is_system_fortune:
		return VOICE_ELENA
	return host_voice


def build_radio_dialogue_plan(
	intro: str | None = None,
	hora_seg: str | None = None,
	minuto_seg: str | None = None,
	fortuna: str | tuple[str, str] | RadioPhrase | None = None,
	outro: str | None = None,
	host_voice: str | None = None,
	cohost_voice: str | None = None,
	lead_in: str | None = None,
	is_system_fortune: bool = False,
	weather_text: str | None = None,
	weather_condition: str | None = None,
	dialogue_mode: bool = True,
	last_reaction: str | None = None,
	db_path: Path | str | None = None,
	ctx: RadioContext | None = None,
	*,
	dt: datetime | None = None,
	fortune: str | tuple[str, str] | RadioPhrase | None = None,
	weather_phrase: str | None = None,
	outro_mode: str = "continue",
) -> list[tuple[str, str, str, bool]]:
	"""
	Construye el plan estructurado de segmentos para la locución radial (texto, voz, categoría, allow_cache).
	Acepta tanto componentes individuales explícitos como argumentos de alto nivel (dt, fortune, weather_phrase, outro_mode).
	"""
	effective_dt = dt if dt is not None else datetime.now(UTC).astimezone()
	if ctx is None:
		ctx = build_radio_context(effective_dt)

	effective_fortuna = (
		fortuna if fortuna is not None else (fortune if fortune is not None else "Siempre que llovió, paró.")
	)
	effective_weather = weather_text if weather_text is not None else weather_phrase

	if host_voice is None or cohost_voice is None:
		auto_host, auto_cohost = select_radio_hosts(host_voice=host_voice, is_system_fortune=is_system_fortune)
		host_voice = host_voice or auto_host
		cohost_voice = cohost_voice or auto_cohost

	if hora_seg is None:
		hora_seg, minuto_seg, _ = get_modular_time_segments(effective_dt)

	if intro is None:
		intro = weighted_choice_by_recency(filter_by_context(RADIO_INTROS, ctx), category="intro", db_path=db_path)

	time_phrase = f"{hora_seg} {minuto_seg}".strip() if minuto_seg else hora_seg.strip()
	fortune_text = format_fortune_for_speech(effective_fortuna)
	seg_cat = resolve_segment_category(effective_fortuna)
	cohost_name = VOICE_NAMES.get(cohost_voice, DEFAULT_COHOST_NAME)

	if outro is None:
		outro_pool = get_outros_for_category(seg_cat, outro_mode)
		outro = weighted_choice_by_recency(filter_by_context(outro_pool, ctx), category="salida", db_path=db_path)

	rendered_intro = render_tracked_phrase(intro, ctx)
	rendered_outro = render_tracked_phrase(outro, ctx)

	if lead_in is not None:
		effective_lead_in = render_tracked_phrase(lead_in, ctx)
	else:
		cat_lead_ins = filter_by_context(get_lead_ins_for_category(seg_cat), ctx)
		effective_lead_in = render_tracked_phrase(
			weighted_choice_by_recency(cat_lead_ins, category=f"lead_in_{seg_cat}", db_path=db_path), ctx
		)

	if not dialogue_mode:
		fortune_voice = VOICE_ELENA if is_system_fortune else host_voice
		solo_plan: list[tuple[str, str, str, bool]] = [
			(rendered_intro, host_voice, "intro", True),
			(time_phrase, host_voice, "hora", True),
		]
		if effective_weather:
			solo_plan.append((effective_weather, host_voice, "clima", False))
		solo_plan.extend(
			[
				(effective_lead_in, host_voice, "lead_in", True),
				(fortune_text, fortune_voice, "fortuna", True),
				(rendered_outro, host_voice, "salida", True),
			]
		)
		return solo_plan

	plan: list[tuple[str, str, str, bool]] = [
		(rendered_intro, host_voice, "intro", True),
		(time_phrase, host_voice, "hora", True),
	]

	prev_reaction = last_reaction
	prev_key = _normalize_phrase_key(prev_reaction) if prev_reaction else None

	if effective_weather:
		pase_pool = filter_by_context(PASES_A_CLIMA, ctx)
		pase_template = weighted_choice_by_recency(pase_pool, category="pase", db_path=db_path)
		pase_text = render_tracked_phrase(pase_template, ctx, addressee_voice=cohost_voice, cohost_name=cohost_name)
		plan.append((pase_text, host_voice, "pase", True))

		plan.append((effective_weather, cohost_voice, "clima", False))

		cond = weather_condition or "agradable"
		candidates = filter_by_context(REACCIONES_CLIMA.get(cond, REACCIONES_CLIMA["agradable"]), ctx)
		valid_reactions = [r for r in candidates if _normalize_phrase_key(r) != prev_key]
		pool_clima = valid_reactions if valid_reactions else candidates
		reaccion_clima = render_tracked_phrase(
			weighted_choice_by_recency(pool_clima, category="reaccion_clima", db_path=db_path),
			ctx,
			addressee_voice=cohost_voice,
		)
		plan.append((reaccion_clima, host_voice, "reaccion", True))
		prev_key = _normalize_phrase_key(reaccion_clima)

	plan.append((effective_lead_in, host_voice, "lead_in", True))

	fortune_voice = VOICE_ELENA if is_system_fortune else cohost_voice
	plan.append((fortune_text, fortune_voice, "fortuna", True))

	react_voice = host_voice if fortune_voice == cohost_voice else cohost_voice
	addressee_voice = cohost_voice if react_voice == host_voice else host_voice

	cat_reactions = filter_by_context(get_reactions_for_category(seg_cat), ctx)
	valid_fortune_reactions = [r for r in cat_reactions if _normalize_phrase_key(r) != prev_key]
	pool_fortuna = valid_fortune_reactions if valid_fortune_reactions else cat_reactions
	reaccion_fortuna = render_tracked_phrase(
		weighted_choice_by_recency(pool_fortuna, category=f"reaccion_{seg_cat}", db_path=db_path),
		ctx,
		addressee_voice=addressee_voice,
	)
	plan.append((reaccion_fortuna, react_voice, "reaccion", True))
	plan.append((rendered_outro, host_voice, "salida", True))

	return plan


def group_plan_into_speech_turns(
	plan: list[tuple[str, str, str, bool]],
) -> list[tuple[str, str, str, bool]]:
	"""Agrupa turnos consecutivos del mismo locutor para mejorar la prosodia de edge-tts."""
	if not plan:
		return []

	turns: list[tuple[str, str, str, bool]] = []
	current_texts: list[str] = [plan[0][0].strip()]
	current_voice = plan[0][1]
	current_category = plan[0][2]
	current_allow_cache = plan[0][3]

	for text, v, category, allow_cache in plan[1:]:
		clean_txt = text.strip()
		if not clean_txt:
			continue

		can_merge = (
			v == current_voice and current_category not in NO_MERGE_CATEGORIES and category not in NO_MERGE_CATEGORIES
		)

		if can_merge:
			current_texts.append(clean_txt)
			if not allow_cache:
				current_allow_cache = False
		else:
			turns.append((" ".join(current_texts), current_voice, current_category, current_allow_cache))
			current_texts = [clean_txt]
			current_voice = v
			current_category = category
			current_allow_cache = allow_cache

	if current_texts:
		turns.append((" ".join(current_texts), current_voice, current_category, current_allow_cache))

	return turns


def generate_modular_radio_script(
	dt: datetime | None = None,
	voice: str | None = None,
	force_system_fortune: bool | None = None,
	outro_mode: str = "continue",
) -> tuple[str, str, str | None, str, str, bool, str, str, str]:
	"""Genera los componentes del guión radial de forma modular."""
	if not voice or voice not in VOICES:
		voice = random.choice(VOICES)

	ctx = build_radio_context(dt)
	intro = render_phrase(random.choice(filter_by_context(RADIO_INTROS, ctx)), ctx)
	hora_seg, minuto_seg, _ = get_modular_time_segments(dt)
	fortuna, is_system_fortune = select_fortune(force_system_fortune, ctx=ctx)
	seg_cat = resolve_segment_category(fortuna)
	cat_lead_ins = get_lead_ins_for_category(seg_cat)
	lead_in = random.choice(filter_by_context(cat_lead_ins, ctx))
	outro_pool = get_outros_for_category(seg_cat, outro_mode)
	outro = render_phrase(random.choice(filter_by_context(outro_pool, ctx)), ctx)
	hora_full = f"{hora_seg} {minuto_seg}" if minuto_seg else hora_seg
	fort_speech = format_fortune_for_speech(fortuna)
	full_script = f"{intro} {hora_full} {lead_in} {fort_speech} {outro}"
	return intro, hora_seg, minuto_seg, lead_in, fortuna, is_system_fortune, outro, voice, full_script
