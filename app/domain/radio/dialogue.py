"""
Planificador de diálogo de cabina entre locutores carpinchos, segmentación horaria
y agrupación de turnos de habla para síntesis con prosodia natural.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.domain.radio.classification import (
	RadioPhrase,
	resolve_segment_category,
	resolve_segment_subcategory,
)
from app.domain.radio.context import (
	RadioContext,
	build_radio_context,
	filter_by_context,
)
from app.domain.radio.linguistics import (
	apply_rioplatense_tts_phonetics,
	clean_subtitle_text,
	format_fortune_for_speech,
)
from app.domain.radio.nlp import (
	_normalize_phrase_key,
	render_tracked_phrase,
	select_radio_phrase,
	weighted_choice_by_recency,
)
from app.domain.radio.segments import (
	HOUR_NAMES,
	LEAD_INS_UNKNOWN,
	MINUTE_SEGMENTS,
	OUTROS_BY_CATEGORY,
	PASES_A_CLIMA,
	PASES_A_CLIMA_NEUTROS,
	RADIO_HANDOFFS,
	RADIO_INTROS,
	RADIO_OUTROS,
	RADIO_OUTROS_BREAK,
	RADIO_OUTROS_DJ,
	RADIO_OUTROS_NIGHT,
	RADIO_OUTROS_PAUSE,
	RADIO_OUTROS_PREVIA,
	RADIO_OUTROS_ROMANCE,
	RADIO_REACTIONS,
	REACCIONES_BY_CATEGORY,
	REACCIONES_CLIMA,
	REACCIONES_FORTUNA,
	REACCIONES_UNKNOWN,
	SPECIAL_HOURS,
	get_intros_for_first_block,
	get_lead_ins_for_category,
	get_outros_for_category,
	get_pases_for_weather_condition,
	get_reactions_for_category,
)
from app.domain.radio.templates import (
	expand_phrase_variants,
	render_phrase,
	resolve_bank_for_gender,
)
from app.domain.radio.voices import (
	DEFAULT_COHOST_NAME,
	HOST_PROFILES,
	VOICE_ELENA,
	VOICE_NAMES,
	VOICE_TOMAS,
	VOICE_VALENTINA,
	VOICES,
	resolve_voice_gender,
)
from app.infrastructure.weather.client import format_temperature

__all__ = [
	"NO_MERGE_CATEGORIES",
	"apply_rioplatense_tts_phonetics",
	"build_radio_dialogue_plan",
	"clean_subtitle_text",
	"format_fortune_for_speech",
	"get_modular_hour_segments",
	"get_modular_minute_segments",
	"get_modular_time_segments",
	"group_plan_into_speech_turns",
	"select_radio_hosts",
]

NO_MERGE_CATEGORIES: set[str] = {"intro", "hora", "minuto", "clima", "salida", "lead_in", "reaccion", "pase"}


def select_radio_hosts(
	host_voice: str | None = None,
	is_system_fortune: bool = False,
	category: str | None = None,
	cohost_voice: str | None = None,
) -> tuple[str, str]:
	"""Selecciona el locutor principal (host) y el co-conductor (cohost), garantizando siempre host != cohost."""
	valid_cohost = cohost_voice if cohost_voice in VOICES else None

	if not host_voice or host_voice not in VOICES or host_voice == valid_cohost:
		candidates = [v for v in VOICES if v != valid_cohost]
		if category:
			preferred = [v for v in candidates if category in HOST_PROFILES.get(v, {}).get("preferred_categories", ())]
			host = random.choice(preferred) if preferred else random.choice(candidates)
		else:
			host = random.choice(candidates)
	else:
		host = host_voice

	other_voices = [v for v in VOICES if v != host]

	if valid_cohost and valid_cohost in other_voices:
		cohost = valid_cohost
	elif is_system_fortune:
		cohost = random.choice(other_voices) if host == VOICE_ELENA else VOICE_ELENA
	elif category in ("chismes", "novela") and VOICE_VALENTINA in other_voices:
		cohost = VOICE_VALENTINA
	elif category in ("aviso", "oyentes") and VOICE_ELENA in other_voices:
		cohost = VOICE_ELENA
	elif category in ("alerta_criolla",) and VOICE_TOMAS in other_voices:
		cohost = VOICE_TOMAS
	else:
		cohost = random.choice(other_voices)

	return host, cohost


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
	all_outros: list[str] = [
		*RADIO_OUTROS,
		*RADIO_OUTROS_ROMANCE,
		*RADIO_OUTROS_PREVIA,
		*RADIO_OUTROS_NIGHT,
		*RADIO_OUTROS_PAUSE,
		*RADIO_OUTROS_BREAK,
		*RADIO_OUTROS_DJ,
	]
	for cat_outros in OUTROS_BY_CATEGORY.values():
		for outro in cat_outros:
			if outro not in all_outros:
				all_outros.append(outro)
	for outro in all_outros:
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
	all_reactions: list[str] = list(RADIO_REACTIONS)
	for cat_reactions in REACCIONES_BY_CATEGORY.values():
		for r in cat_reactions:
			if r not in all_reactions:
				all_reactions.append(r)
	for r in all_reactions:
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


logger = logging.getLogger("RockolaCarpincho")

BLOCK_ALIASES: dict[str, str] = {
	"hora": "hora",
	"time": "hora",
	"clima": "clima",
	"weather": "clima",
	"contenido": "contenido",
	"content": "contenido",
	"frase": "contenido",
	"fortuna": "contenido",
	"phrase": "contenido",
}


def _resolve_block_order(block_order: Sequence[str] | None, valid_keys: list[str]) -> list[str]:
	"""Resuelve el orden de bloques intermedios: respeta `block_order` (avisando claves desconocidas) o mezcla al azar."""
	if block_order:
		for raw_key in block_order:
			if raw_key not in BLOCK_ALIASES:
				logger.warning(f"Bloque de locución desconocido en block_order ignorado: {raw_key!r}")
		return [BLOCK_ALIASES[k] for k in block_order if k in BLOCK_ALIASES and BLOCK_ALIASES[k] in valid_keys]
	ordered = list(valid_keys)
	random.shuffle(ordered)
	return ordered


_SAFE_NEUTRAL_FALLBACKS: dict[str, str] = {
	"intro": "Transmite La Rockola del Carpincho.",
	"salida": "¡Seguimos con más música!",
	"lead_in": "Atenti a lo que compartimos en el aire de La Rockola.",
	"pase": "¿Cómo viene la mano afuera, {cohost}?",
	"reaccion": "¡Clarito como el agua de la orilla!",
}


def _filter_with_safe_fallback(
	candidates: Sequence[str],
	ctx: RadioContext | None,
	category: str,
	fallback_pool: Sequence[str] | None = None,
) -> list[str]:
	"""
	Filtra candidatos por contexto y, si todos son descartados, busca en un banco neutral filtrado por el mismo contexto.
	Nunca reintroduce frases que violen la coherencia temporal o climática.
	"""
	filtered = filter_by_context(candidates, ctx, category)
	if filtered:
		return filtered
	if fallback_pool:
		fallback_filtered = filter_by_context(fallback_pool, ctx, category)
		if fallback_filtered:
			return fallback_filtered
	return [_SAFE_NEUTRAL_FALLBACKS.get(category, "Transmite La Rockola del Carpincho.")]


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
	outro_mode: str = "continue",
	block_order: Sequence[str] | None = None,
) -> list[tuple[str, str, str, bool]]:
	"""
	Construye el plan estructurado de segmentos para la locución radial (texto, voz, categoría, allow_cache).
	Permuta modularmente los bloques intermedios (hora, clima, contenido) para mayor naturalidad radiofónica.
	"""
	effective_dt = dt if dt is not None else datetime.now(UTC).astimezone()
	if ctx is None:
		ctx = build_radio_context(effective_dt, outro_mode=outro_mode)
	elif outro_mode != "continue" and ctx.outro_mode != outro_mode:
		ctx = ctx._replace(outro_mode=outro_mode)
	effective_outro_mode = ctx.outro_mode if outro_mode == "continue" else outro_mode

	effective_fortuna = fortuna if fortuna is not None else "Siempre que llovió, paró."
	effective_weather = weather_text

	seg_cat = resolve_segment_category(effective_fortuna)
	seg_subcat = resolve_segment_subcategory(effective_fortuna, category=seg_cat)

	if host_voice is None or cohost_voice is None or host_voice == cohost_voice:
		host_voice, cohost_voice = select_radio_hosts(
			host_voice=host_voice,
			cohost_voice=cohost_voice,
			is_system_fortune=is_system_fortune,
			category=seg_cat,
		)

	host_gender = resolve_voice_gender(host_voice)
	cohost_gender = resolve_voice_gender(cohost_voice)

	if hora_seg is None:
		hora_seg, minuto_seg, _ = get_modular_time_segments(effective_dt)

	# El orden de bloques se resuelve ANTES de elegir la intro y las reacciones,
	# para filtrar intros incompatibles con el primer bloque y mantener la anti-repetición de reacciones.
	valid_block_keys = ["hora", "contenido"] + (["clima"] if effective_weather else [])
	ordered_keys = _resolve_block_order(block_order, valid_block_keys)
	first_block = ordered_keys[0] if ordered_keys else "hora"

	if intro is None:
		raw_intros = get_intros_for_first_block(first_block, gender=host_gender)
		neutral_intros = resolve_bank_for_gender(RADIO_INTROS, host_gender)
		intro_candidates = _filter_with_safe_fallback(raw_intros, ctx, "intro", fallback_pool=neutral_intros)
		intro = weighted_choice_by_recency(intro_candidates, category="intro", db_path=db_path)

	time_phrase = f"{hora_seg} {minuto_seg}".strip() if minuto_seg else hora_seg.strip()
	fortune_text = format_fortune_for_speech(effective_fortuna)
	cohost_name = VOICE_NAMES.get(cohost_voice, DEFAULT_COHOST_NAME)

	if outro is None:
		outro_pool = get_outros_for_category(seg_cat, effective_outro_mode, gender=host_gender, ctx=ctx)
		neutral_outros = resolve_bank_for_gender(
			RADIO_OUTROS_PAUSE
			if effective_outro_mode == "pause"
			else RADIO_OUTROS_BREAK
			if effective_outro_mode == "break"
			else RADIO_OUTROS,
			host_gender,
		)
		outro_candidates = _filter_with_safe_fallback(outro_pool, ctx, "salida", fallback_pool=neutral_outros)
		outro = weighted_choice_by_recency(outro_candidates, category="salida", db_path=db_path)

	host_name = VOICE_NAMES.get(host_voice, "Tomás")
	rendered_intro = render_tracked_phrase(intro, ctx, host_name=host_name, host_voice=host_voice)
	rendered_outro = render_tracked_phrase(outro, ctx, host_name=host_name, host_voice=host_voice)

	if lead_in is not None:
		effective_lead_in = render_tracked_phrase(lead_in, ctx)
	else:
		raw_lead_ins = get_lead_ins_for_category(seg_cat, subcategory=seg_subcat)
		cat_lead_ins = _filter_with_safe_fallback(raw_lead_ins, ctx, "lead_in", fallback_pool=LEAD_INS_UNKNOWN)
		effective_lead_in = render_tracked_phrase(
			weighted_choice_by_recency(cat_lead_ins, category=f"lead_in_{seg_subcat}", db_path=db_path), ctx
		)

	fortune_category = (
		seg_cat if seg_cat in ("fortuna", "aviso", "alerta_criolla", "oyentes", "chismes", "novela") else "fortuna"
	)

	if not dialogue_mode:
		fortune_voice = VOICE_ELENA if is_system_fortune else host_voice
		time_block = [(time_phrase, host_voice, "hora", True)]
		content_block = [
			(effective_lead_in, host_voice, "lead_in", True),
			(fortune_text, fortune_voice, fortune_category, True),
		]
		available_blocks: dict[str, list[tuple[str, str, str, bool]]] = {
			"hora": time_block,
			"contenido": content_block,
		}
		if effective_weather:
			available_blocks["clima"] = [(effective_weather, host_voice, "clima", False)]

		solo_plan: list[tuple[str, str, str, bool]] = [
			(rendered_intro, host_voice, "intro", True),
		]
		for k in ordered_keys:
			solo_plan.extend(available_blocks[k])
		solo_plan.append((rendered_outro, host_voice, "salida", True))
		return solo_plan

	time_block = [(time_phrase, host_voice, "hora", True)]

	prev_key = _normalize_phrase_key(last_reaction) if last_reaction else None

	def _build_weather_block() -> list[tuple[str, str, str, bool]]:
		cond = weather_condition or "agradable"
		raw_pases = get_pases_for_weather_condition(cond, gender=cohost_gender)
		neutral_pases = resolve_bank_for_gender(PASES_A_CLIMA_NEUTROS, cohost_gender)
		pase_pool = _filter_with_safe_fallback(raw_pases, ctx, "pase", fallback_pool=neutral_pases)
		pase_template = weighted_choice_by_recency(pase_pool, category="pase", db_path=db_path)
		pase_text = render_tracked_phrase(pase_template, ctx, addressee_voice=cohost_voice, cohost_name=cohost_name)

		cond_options = resolve_bank_for_gender(
			REACCIONES_CLIMA.get(cond, REACCIONES_CLIMA["agradable"]),
			cohost_gender,
		)
		neutral_clima_react = resolve_bank_for_gender(REACCIONES_CLIMA["agradable"], cohost_gender)
		candidates = _filter_with_safe_fallback(cond_options, ctx, "reaccion", fallback_pool=neutral_clima_react)
		valid_reactions = [r for r in candidates if _normalize_phrase_key(r) != prev_key]
		pool_clima = valid_reactions if valid_reactions else candidates
		reaccion_clima = render_tracked_phrase(
			weighted_choice_by_recency(pool_clima, category="reaccion_clima", db_path=db_path),
			ctx,
			addressee_voice=cohost_voice,
		)
		return [
			(pase_text, host_voice, "pase", True),
			(effective_weather or "", cohost_voice, "clima", False),
			(reaccion_clima, host_voice, "reaccion", True),
		]

	fortune_voice = VOICE_ELENA if is_system_fortune else cohost_voice
	react_voice = host_voice if fortune_voice == cohost_voice else cohost_voice
	addressee_voice = cohost_voice if react_voice == host_voice else host_voice
	addressee_gender = resolve_voice_gender(addressee_voice)

	def _build_content_block() -> list[tuple[str, str, str, bool]]:
		raw_reactions = get_reactions_for_category(seg_cat, subcategory=seg_subcat, gender=addressee_gender)
		neutral_reactions = resolve_bank_for_gender(REACCIONES_UNKNOWN, addressee_gender)
		cat_reactions = _filter_with_safe_fallback(raw_reactions, ctx, "reaccion", fallback_pool=neutral_reactions)
		valid_fortune_reactions = [r for r in cat_reactions if _normalize_phrase_key(r) != prev_key]
		pool_fortuna = valid_fortune_reactions if valid_fortune_reactions else cat_reactions
		reaccion_fortuna = render_tracked_phrase(
			weighted_choice_by_recency(pool_fortuna, category=f"reaccion_{seg_subcat}", db_path=db_path),
			ctx,
			addressee_voice=addressee_voice,
		)
		return [
			(effective_lead_in, host_voice, "lead_in", True),
			(fortune_text, fortune_voice, fortune_category, True),
			(reaccion_fortuna, react_voice, "reaccion", True),
		]

	available_dialogue_blocks: dict[str, list[tuple[str, str, str, bool]]] = {}
	for k in ordered_keys:
		if k == "hora":
			available_dialogue_blocks[k] = time_block
		elif k == "clima":
			available_dialogue_blocks[k] = _build_weather_block()
			prev_key = _normalize_phrase_key(available_dialogue_blocks[k][-1][0])
		else:
			available_dialogue_blocks[k] = _build_content_block()
			prev_key = _normalize_phrase_key(available_dialogue_blocks[k][-1][0])

	plan: list[tuple[str, str, str, bool]] = [
		(rendered_intro, host_voice, "intro", True),
	]
	for k in ordered_keys:
		plan.extend(available_dialogue_blocks[k])
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

	ctx = build_radio_context(dt, outro_mode=outro_mode)
	voice_gender = resolve_voice_gender(voice)
	raw_intros = get_intros_for_first_block("hora", gender=voice_gender)
	neutral_intros = resolve_bank_for_gender(RADIO_INTROS, voice_gender)
	intro_candidates = _filter_with_safe_fallback(raw_intros, ctx, "intro", fallback_pool=neutral_intros)
	host_name = VOICE_NAMES.get(voice, "Tomás")
	intro = render_phrase(random.choice(intro_candidates), ctx, host_name=host_name, host_voice=voice)
	hora_seg, minuto_seg, _ = get_modular_time_segments(dt)
	phrase, is_system_fortune = select_radio_phrase(force_system_fortune, ctx=ctx)
	fortuna = phrase.text
	seg_cat = phrase.category
	seg_subcat = resolve_segment_subcategory(fortuna, category=seg_cat)
	cat_lead_ins = get_lead_ins_for_category(seg_cat, subcategory=seg_subcat)
	filtered_lead_ins = _filter_with_safe_fallback(cat_lead_ins, ctx, "lead_in", fallback_pool=LEAD_INS_UNKNOWN)
	lead_in = random.choice(filtered_lead_ins)
	outro_pool = get_outros_for_category(seg_cat, outro_mode, gender=voice_gender, ctx=ctx)
	neutral_outros = resolve_bank_for_gender(
		RADIO_OUTROS_PAUSE if outro_mode == "pause" else RADIO_OUTROS_BREAK if outro_mode == "break" else RADIO_OUTROS,
		voice_gender,
	)
	filtered_outros = _filter_with_safe_fallback(outro_pool, ctx, "salida", fallback_pool=neutral_outros)
	outro = render_phrase(random.choice(filtered_outros), ctx, host_name=host_name, host_voice=voice)

	hora_full = f"{hora_seg} {minuto_seg}" if minuto_seg else hora_seg
	fort_speech = format_fortune_for_speech(fortuna)
	full_script = f"{intro} {hora_full} {lead_in} {fort_speech} {outro}"
	return intro, hora_seg, minuto_seg, lead_in, fortuna, is_system_fortune, outro, voice, full_script
