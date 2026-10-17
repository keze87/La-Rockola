"""
Dominio de Modo Radio: bancos de frases, procesamiento lingüístico, diálogo de cabina y síntesis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from app.domain.radio.dialogue import (
		build_radio_dialogue_plan,
		generate_modular_radio_script,
		get_modular_time_segments,
		group_plan_into_speech_turns,
		select_radio_hosts,
	)
	from app.domain.radio.nlp import (
		clean_fortune_text,
		contains_blacklisted_content,
		get_radio_fortune,
		get_radio_state,
		is_spanish_text,
		is_tts_friendly_fortune,
		is_valid_spoken_sentence,
		record_phrase_played,
		reset_radio_memory_state,
		select_fortune,
		select_radio_phrase,
		set_radio_state,
		weighted_choice_by_recency,
	)
	from app.domain.radio.service import (
		RadioAnnouncementResult,
		RadioService,
		assemble_announcement_audio,
		create_radio_announcement,
		replace_announcement_outro,
	)

__all__ = [
	"RadioAnnouncementResult",
	"RadioService",
	"assemble_announcement_audio",
	"build_radio_dialogue_plan",
	"clean_fortune_text",
	"contains_blacklisted_content",
	"create_radio_announcement",
	"generate_modular_radio_script",
	"get_modular_time_segments",
	"get_radio_fortune",
	"get_radio_state",
	"group_plan_into_speech_turns",
	"is_spanish_text",
	"is_tts_friendly_fortune",
	"is_valid_spoken_sentence",
	"record_phrase_played",
	"replace_announcement_outro",
	"reset_radio_memory_state",
	"select_fortune",
	"select_radio_hosts",
	"select_radio_phrase",
	"set_radio_state",
	"weighted_choice_by_recency",
]


def __getattr__(name: str) -> Any:
	if name in {
		"build_radio_dialogue_plan",
		"generate_modular_radio_script",
		"get_modular_time_segments",
		"group_plan_into_speech_turns",
		"select_radio_hosts",
	}:
		from app.domain.radio import dialogue

		return getattr(dialogue, name)
	if name in {
		"clean_fortune_text",
		"contains_blacklisted_content",
		"get_radio_fortune",
		"get_radio_state",
		"is_spanish_text",
		"is_tts_friendly_fortune",
		"is_valid_spoken_sentence",
		"record_phrase_played",
		"reset_radio_memory_state",
		"select_fortune",
		"select_radio_phrase",
		"set_radio_state",
		"weighted_choice_by_recency",
	}:
		from app.domain.radio import nlp

		return getattr(nlp, name)
	if name in {
		"RadioAnnouncementResult",
		"RadioService",
		"assemble_announcement_audio",
		"create_radio_announcement",
		"replace_announcement_outro",
	}:
		from app.domain.radio import service

		return getattr(service, name)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
