"""
Pruebas de fonética rioplatense automática y ortografía limpia en bancos de radio.
Verifica la separación de texto visual (subtítulos) y fonética para Edge-TTS.
"""

from __future__ import annotations

import re

import pytest

from app.domain.radio.banks import (
	CARPINCHO_FORTUNES,
	CARPINCHO_PHRASES,
	RADIO_INTROS,
	RADIO_OUTROS,
)
from app.domain.radio.dialogue import (
	apply_rioplatense_tts_phonetics,
	format_fortune_for_speech,
)


def test_rioplatense_voseo_enclitic_phonetics() -> None:
	"""Verifica la acentuación prosódica en verbos de voseo con pronombres enclíticos."""
	cases = {
		"fijate si conseguís hielo": "fijáte si conseguís hielo",
		"Fijate bien": "Fijáte bien",
		"mandale play": "mandále play",
		"Mandale play": "Mandále play",
		"ponete otro temazo": "ponéte otro temazo",
		"dejate llevar": "dejáte llevar",
		"subile al volumen": "subíle al volumen",
		"tocale el hombro": "tocále el hombro",
		"decile que afloje": "decíle que afloje",
		"decime qué onda": "decíme qué onda",
		"hacete amigo": "hacéte amigo",
		"cebate otro mate": "cebáte otro mate",
		"metele ritmo": "metéle ritmo",
		"apurate Beto": "apuráte Beto",
		"pedite una pinta": "pedíte una pinta",
		"pegale un trago": "pegále un trago",
		"prendete a La Rockola": "prendéte a La Rockola",
		"tirate un rocanrol": "tiráte un rocanrol",
		"tirame la data": "tiráme la data",
		"acomodate en el barro": "acomodáte en el barro",
		"agarrate fuerte": "agarráte fuerte",
		"escuchate este chisme": "escucháte este chisme",
		"anotate esta máxima": "anotáte esta máxima",
		"prestale atención": "prestále atención",
		"cambiame la música": "cambiáme la música",
		"cambiamela por favor": "cambiámela por favor",
		"ajustate los cinturones": "ajustáte los cinturones",
		"asomate al bañado": "asomáte al bañado",
		"olvidate del paraguas": "olvidáte del paraguas",
		"preparate para el agua": "preparáte para el agua",
		"cantame los números": "cantáme los números",
		"contame qué dice": "contáme qué dice",
		"echale agua": "echále agua",
		"guardame el secreto": "guardáme el secreto",
		"sentate a la sombra": "sentáte a la sombra",
		"tomate un mate": "tomáte un mate",
		"largate a bailar": "largáte a bailar",
	}

	for original, expected in cases.items():
		res = apply_rioplatense_tts_phonetics(original)
		assert res == expected, f"Fallo en fonética de voseo para '{original}': obtenido '{res}', esperado '{expected}'"


def test_rioplatense_abbreviations_and_no_false_positives() -> None:
	"""Verifica transformación de DJ a DiYei y ausencia de falsos positivos en sustantivos."""
	# 1. DJ -> DiYei
	assert apply_rioplatense_tts_phonetics("el DJ Bara toma las bandejas") == "el DiYei Bara toma las bandejas"
	assert apply_rioplatense_tts_phonetics("suena el dj en vivo") == "suena el DiYei en vivo"

	# 2. No debe tocar palabras graves comunes o sustantivos que no están en la lista blanca
	non_targets = "chocolate calle baile mensaje cable"
	assert apply_rioplatense_tts_phonetics(non_targets) == non_targets


def test_format_fortune_for_speech_applies_phonetics() -> None:
	"""Verifica que format_fortune_for_speech limpie comillas y aplique fonética rioplatense."""
	raw = '"Fijate de no quemar la pava y mandale play al DJ"'
	res = format_fortune_for_speech(raw)
	assert "Fijáte" in res
	assert "mandále" in res
	assert "DiYei" in res
	assert res.endswith(".")


def test_banks_orthography_clean_without_forced_enclitic_accents() -> None:
	"""Verifica que banks.py tenga ortografía estándar limpia sin tildes forzadas ni DiYei hardcodeado."""
	# 1. escrachádo -> escrachado en CARPINCHO_FORTUNES
	fortunes_text = " ".join(CARPINCHO_FORTUNES)
	assert "escrachádo" not in fortunes_text
	assert "escrachado" in fortunes_text

	# 2. No debe existir 'DiYei' en los bancos de frases, debe decir 'DJ'
	all_phrases = [
		*CARPINCHO_FORTUNES,
		*[p.text for p in CARPINCHO_PHRASES],
		*RADIO_INTROS,
		*RADIO_OUTROS,
	]
	full_corpus = " ".join(all_phrases)

	assert "DiYei" not in full_corpus, "Se encontró 'DiYei' en los bancos de frases; debe ser 'DJ'"

	# 3. No debe haber tildes prosódicas forzadas en verbos de voseo en los textos visuales
	forced_accents = [
		"fijáte",
		"acordáte",
		"mandále",
		"ponéte",
		"dejáte",
		"subíle",
		"tocále",
		"decíle",
		"hacéte",
		"cebáte",
		"metéle",
		"apuráte",
		"pedíte",
		"pegále",
		"prendéte",
		"tiráte",
		"acomodáte",
		"agarráte",
		"escucháte",
		"anotáte",
		"prestále",
		"cambiáme",
		"ajustáte",
		"asomáte",
		"olvidáte",
		"preparáte",
		"cantáme",
		"contáme",
		"echále",
		"guardáme",
		"decíme",
		"tiráme",
	]
	for word in forced_accents:
		assert not re.search(
			rf"\b{word}\b", full_corpus, re.IGNORECASE
		), f"Se encontró tilde forzada '{word}' en los bancos de frases"


def test_clean_subtitle_text_reverts_phonetics() -> None:
	"""Verifica que clean_subtitle_text devuelva la ortografía estándar limpia para subtítulos."""
	from app.domain.radio.dialogue import clean_subtitle_text

	assert clean_subtitle_text("fijáte en el DiYei") == "fijate en el DJ"
	assert clean_subtitle_text("¡Mandále play y subíle dos rayitas!") == "¡Mandale play y subile dos rayitas!"
	assert clean_subtitle_text("cambiámela") == "cambiamela"

