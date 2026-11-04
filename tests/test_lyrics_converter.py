"""
Pruebas unitarias y de integración real para el conversor de letras ASS y cliente BetterLyrics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.lyrics.converter import LyricsAssConverter
from app.domain.lyrics.service import BetterLyricsService

SAMPLE_JWT = (
	"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
	"eyJpYXQiOjE3MDAwMDAwMDAsImV4cCI6MjAwMDAwMDAwMCwianRpIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwiaXAiOiIxMjcuMC4wLjEifQ."
	"c2lnbmF0dXJlX2V4YW1wbGVfdmFsdWU"
)

SAMPLE_CURL_COMMAND = f"""curl 'https://lyrics.api.dacubeking.com/v2/lyrics' \\
  -X POST \\
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:159.0) Gecko/20100101 Firefox/159.0' \\
  -H 'Content-Type: application/x-www-form-urlencoded;charset=UTF-8' \\
  --data-raw 'videoId=9vWNauaZAgg&song=Back+In+Black&artist=AC%2FDC&duration=255&album=Back+In+Black&alwaysFetchMetadata=false&token={SAMPLE_JWT}'"""


def test_extract_token_from_user_curl():
	"""Verifica que se extraiga el JWT exactamente del comando cURL o cabeceras."""
	extracted = BetterLyricsService.extract_token(SAMPLE_CURL_COMMAND)
	assert extracted == SAMPLE_JWT

	# También debe extraerlo si se pasa el JWT directo o con Bearer
	assert BetterLyricsService.extract_token(SAMPLE_JWT) == SAMPLE_JWT
	assert BetterLyricsService.extract_token(f"Authorization: Bearer {SAMPLE_JWT}") == SAMPLE_JWT


def test_jwt_expiry_parsing():
	"""Verifica la decodificación del payload JWT para obtener el timestamp exp."""
	exp = BetterLyricsService.parse_jwt_expiry(SAMPLE_JWT)
	assert exp == 2000000000


def test_convert_ttml_word_by_word_to_ass():
	"""Verifica que el TTML palabra por palabra de binimum genere etiquetas \\kf válidas sin pegar palabras."""
	ttml = (
		'<tt xmlns="http://www.w3.org/ns/ttml" xmlns:lrc="http://lrc.red/lyric-ttml-internal" lrc:timing="Word">'
		"<body><div>"
		'<p begin="1:12.952" end="1:17.802">'
		'<span begin="1:12.952" end="1:13.515">You</span> '
		'<span begin="1:13.515" end="1:13.731">could</span>'
		'<span begin="1:13.731" end="1:13.981">n\'t</span> '
		'<span begin="1:13.981" end="1:14.248">wait</span>'
		"</p></div></body></tt>"
	)
	ass, has_syllables = LyricsAssConverter.convert_source_to_ass(
		ttml, source_key="binimum_lyrics", title="DANCE...", artist="Slayyyter"
	)
	assert has_syllables is True
	assert "[Script Info]" in ass
	assert "[Events]" in ass
	assert "Dialogue: 0,0:01:12.95,0:01:17.80,Default" in ass
	assert "{\\kf56}You {\\kf21}could{\\kf25}n't {\\kf382}wait" in ass


def test_convert_qrc_to_ass():
	"""Verifica que el formato QRC de QQ Music se convierta a ASS con tiempos palabra por palabra."""
	qrc_xml = (
		'<?xml version="1.0" encoding="utf-8"?>\n'
		"<QrcInfos><LyricInfo><Lyric_1 LyricContent="
		'"[ti:Back In Black]\n[offset:0]\n'
		'[26792,2776]Back (26792,168)in (26960,327)black (27287,396)I (28275,168)hit (28443,176)the (28619,168)sack(28787,327)"'
		"/></LyricInfo></QrcInfos>"
	)
	ass, has_syllables = LyricsAssConverter.convert_source_to_ass(
		qrc_xml, source_key="qq_lyrics", title="Back In Black", artist="AC/DC"
	)
	assert has_syllables is True
	assert "Dialogue: 0,0:00:26.79,0:00:29.57,Default" in ass
	assert "{\\kf" in ass
	assert "Back " in ass
	assert "sack" in ass


def test_convert_musixmatch_word_by_word_to_ass():
	"""Verifica que el formato eLRC de Musixmatch wordByWord se convierta a ASS con \\kf."""
	elrc = (
		"[offset:-0.1788173076923077]\n"
		"[00:26.60] <00:26.60> Back <00:27.03>   <00:27.18> in <00:27.26>   <00:27.31> black, <00:27.66>"
	)
	ass, has_syllables = LyricsAssConverter.convert_source_to_ass(
		elrc, source_key="musixmatch_wordByWord", title="Back In Black", artist="AC/DC"
	)
	assert has_syllables is True
	assert "{\\kf" in ass
	assert "Back " in ass
	assert "in " in ass
	assert "black," in ass


@pytest.mark.anyio
async def test_live_betterlyrics_back_in_black(tmp_path, monkeypatch):
	"""
	Prueba contra la respuesta real de BetterLyrics para 'Back In Black' de AC/DC
	verificando la conversión de todos los proveedores reales devueltos.
	"""
	service = BetterLyricsService(cache_dir=tmp_path)
	service.set_token(SAMPLE_CURL_COMMAND)

	fixture_file = Path(__file__).parent / "fixtures" / "betterlyrics_back_in_black.txt"
	fixture_text = fixture_file.read_text(encoding="utf-8")

	class MockResponse:
		status_code = 200
		text = fixture_text

		def raise_for_status(self):
			pass

	async def mock_post(*args, **kwargs):
		return MockResponse()

	monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

	result = await service.search_lyrics(
		title="Back In Black",
		artist="AC/DC",
		album="Back In Black",
		duration=255,
	)

	assert result["title"] == "Back In Black"
	assert result["artist"] == "AC/DC"
	providers = result["providers"]
	assert len(providers) >= 4

	provider_keys = [p["provider"] for p in providers]
	# Deben estar presentes los proveedores reales devueltos por BetterLyrics
	assert "binimum" in provider_keys
	assert "lrclib" in provider_keys
	assert "qq" in provider_keys
	assert "kugou" in provider_keys

	# Verificar que qq o golyrics tengan sílabas (\kf) y las líneas de Back In Black
	qq_prov = next(p for p in providers if p["provider"] == "qq")
	assert qq_prov["has_syllables"] is True
	assert "[Script Info]" in qq_prov["ass"]
	assert "[Events]" in qq_prov["ass"]
	assert "{\\kf" in qq_prov["ass"]
	assert "black" in qq_prov["ass"].lower()

	# Verificar que lrclib esté convertido a ASS
	lrclib_prov = next(p for p in providers if p["provider"] == "lrclib")
	assert "Dialogue:" in lrclib_prov["ass"]
	assert "Back in black" in lrclib_prov["ass"]
