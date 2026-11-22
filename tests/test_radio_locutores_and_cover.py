"""
Pruebas unitarias para la portada radio.jpg y los locutores dinámicos en cabina.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.container import AppContainer, set_container
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.domain.radio.service import RadioAnnouncementResult
from app.domain.radio.voices import VOICE_TOMAS
from app.infrastructure.db.connection import init_db
from app.infrastructure.media.mixer import get_carpincho_cover_path


class TestRadioLocutoresAndCover:
	def test_01_cover_path_prioritizes_radio_jpg(self) -> None:
		"""Verifica que get_carpincho_cover_path priorice radio.jpg sobre favicon.png."""
		cover_p = get_carpincho_cover_path()
		assert cover_p is not None
		assert cover_p.name == "radio.jpg"
		assert cover_p.is_file()

	def test_02_radio_announcement_result_has_display_artist(self) -> None:
		"""Verifica que RadioAnnouncementResult soporte display_artist con los locutores."""
		res = RadioAnnouncementResult(
			ok=True,
			display_title="Locución de prueba",
			script="Hola a todos",
			display_artist="Tomás y Elena 🎙️",
			host_voice=VOICE_TOMAS,
		)
		assert res.display_artist == "Tomás y Elena 🎙️"
		# Verificamos compatibilidad con desempaquetado de 3 o 4 elementos
		ok, title, _script, *_rest = res
		assert ok is True
		assert title == "Locución de prueba"

	async def test_03_orchestrator_uses_dynamic_display_artist(self, tmp_path: Path, monkeypatch) -> None:
		"""El orquestador debe guardar el display_artist dinámico retornado por el servicio de radio."""
		import app.domain.radio.service as radio_service_mod

		db_path = tmp_path / "orch_artist.db"
		init_db(db_path)
		orch = PlaybackOrchestrator(db_path=db_path)
		orch.mpv.start = AsyncMock()
		orch.mpv.load_file = AsyncMock()
		orch.mpv.set_force_window = AsyncMock()
		orch.current_track = "/musica/tema1.mp3"
		orch.queue = ["/musica/tema2.mp3"]
		orch.radio_mode_enabled = True
		orch.last_radio_time = 0.0
		orch.radio_time_until_next = 1.0
		set_container(AppContainer(db_path=db_path, orchestrator=orch))

		monkeypatch.setattr(radio_service_mod, "check_internet_async", AsyncMock(return_value=True))

		async def mock_get_or_synthesize(*args, **kwargs):
			res = RadioAnnouncementResult(
				ok=True,
				display_title="Charla radial",
				script="Guión de prueba",
				display_artist="Elena y Tomás 🎙️",
			)
			return res

		monkeypatch.setattr(orch.radio_service, "get_or_synthesize", mock_get_or_synthesize)

		await orch.play_next(skipped_by_user=False)

		meta = orch.url_metadata.get(orch.radio_announcement_path, {})
		assert meta.get("display_artist") == "Elena y Tomás 🎙️"

	def test_04_cover_endpoint_serves_radio_image_with_cache_headers(self) -> None:
		"""Verifica que /cover sirva radio.jpg con cabeceras ETag y Cache-Control para anuncios radiales."""
		from starlette.testclient import TestClient

		from app.main import app

		client = TestClient(app)
		# Ruta absoluta típica en /tmp
		res = client.get("/cover?path=/tmp/radio_announcement.mp3&size=512")
		assert res.status_code == 200
		assert res.headers["content-type"].startswith("image/jpeg")
		assert "etag" in res.headers
		assert "cache-control" in res.headers
		assert len(res.content) > 1000

		# Ruta relativa enviada por el front como fallback ('radio_announcement.mp3')
		res_rel = client.get("/cover?path=radio_announcement.mp3&size=512")
		assert res_rel.status_code == 200
		assert res_rel.headers["content-type"].startswith("image/jpeg")
		assert "etag" in res_rel.headers
		assert "cache-control" in res_rel.headers
		assert len(res_rel.content) > 1000

	def test_05_default_radio_title_is_transmision_de_cabina(self) -> None:
		"""Verifica que el título oficial de la radio sea 'Transmisión de Cabina'."""
		from app.domain.radio.voices import DEFAULT_RADIO_TITLE

		assert DEFAULT_RADIO_TITLE == "Transmisión de Cabina"

	def test_06_direct_radio_jpg_endpoint(self) -> None:
		"""Verifica que /radio.jpg sirva la imagen directamente con cabeceras de caché."""
		from starlette.testclient import TestClient

		from app.main import app

		client = TestClient(app)
		res = client.get("/radio.jpg")
		assert res.status_code == 200
		assert res.headers["content-type"] == "image/jpeg"
		assert "etag" in res.headers
		assert "cache-control" in res.headers

	def test_07_serve_index_has_no_cache_headers(self, tmp_path, monkeypatch) -> None:
		"""Verifica que / (index.html) tenga cabeceras para prevenir que el browser cachee un bundle obsoleto."""
		from starlette.testclient import TestClient

		import app.main as main_mod

		# 1. Caso con index.html presente (FileResponse)
		fake_dist = tmp_path / "dist"
		fake_dist.mkdir()
		fake_html = fake_dist / "index.html"
		fake_html.write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
		monkeypatch.setattr(main_mod, "get_dist_dirs", lambda: (tmp_path, fake_dist, fake_dist / "assets"))

		client = TestClient(main_mod.app)
		res = client.get("/")
		assert res.status_code == 200
		assert "no-cache" in res.headers.get("cache-control", "")
		assert res.headers.get("content-type", "").startswith("text/html")

		# 2. Caso sin index.html (JSONResponse fallback cuando no se compiló el front)
		fake_empty_dist = tmp_path / "empty_dist"
		fake_empty_dist.mkdir()
		monkeypatch.setattr(main_mod, "get_dist_dirs", lambda: (tmp_path, fake_empty_dist, fake_empty_dist / "assets"))

		res_empty = client.get("/")
		assert res_empty.status_code == 200
		assert "no-cache" in res_empty.headers.get("cache-control", "")
		assert res_empty.headers.get("content-type", "").startswith("application/json")

	def test_08_cover_path_honors_rockola_dist_dir_for_android(self, tmp_path: Path, monkeypatch) -> None:
		"""Verifica que get_carpincho_cover_path resuelva radio.jpg desde ROCKOLA_DIST_DIR (Android/Chaquopy)."""
		custom_dist = tmp_path / "android_dist"
		custom_dist.mkdir()
		radio_img = custom_dist / "radio.jpg"
		radio_img.write_bytes(b"\xff\xd8\xff\xe0dummy")
		monkeypatch.setenv("ROCKOLA_DIST_DIR", str(custom_dist))

		cover_p = get_carpincho_cover_path()
		assert cover_p == radio_img.resolve()

	def test_09_stream_disables_http_cache_for_radio_announcements(self, tmp_path: Path) -> None:
		"""Verifica que /stream devuelva no-store/no-cache para locuciones radiales y conserve caché para canciones."""
		from starlette.testclient import TestClient

		from app.main import app

		db_path = tmp_path / "stream_cache.db"
		init_db(db_path)
		orch = PlaybackOrchestrator(db_path=db_path)
		radio_file = tmp_path / "radio_announcement.mp3"
		radio_file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")
		song_file = tmp_path / "tema.mp3"
		song_file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")
		orch.radio_announcement_path = str(radio_file)
		orch.tracks_cache = [{"path": str(song_file)}]
		orch.path_to_id = {str(song_file): 1}
		set_container(AppContainer(db_path=db_path, orchestrator=orch))

		client = TestClient(app)
		radio_res = client.get(f"/stream?path={radio_file}")
		assert radio_res.status_code == 200
		radio_cc = radio_res.headers.get("cache-control", "")
		assert "no-store" in radio_cc
		assert "no-cache" in radio_cc

		song_res = client.get(f"/stream?path={song_file}")
		assert song_res.status_code == 200
		assert "max-age=86400" in song_res.headers.get("cache-control", "")

	async def test_10_tts_cache_does_not_reuse_stale_category_for_time_or_weather(self, tmp_path: Path) -> None:
		"""No debe reciclar audios de caché por categoría para hora, minuto o clima cuando falla Edge-TTS."""
		from unittest.mock import patch

		import pytest

		from app.infrastructure.media import tts_cache

		db_path = tmp_path / "tts_stale.db"
		tts_cache.init_tts_cache_db(db_path)
		# Guardamos entradas previas para otra hora/minuto/temperatura
		tts_cache.save_cached_audio("hora", "es-AR-TomasNeural", "Son las nueve", b"ID3hour_old", db_path=db_path)
		tts_cache.save_cached_audio("minuto", "es-AR-TomasNeural", "y cinco", b"ID3min_old", db_path=db_path)
		tts_cache.save_cached_audio(
			"clima", "es-AR-TomasNeural", "Hacen quince grados", b"ID3temp_old", db_path=db_path
		)
		# Una categoría estática sí debe seguir pudiendo usar salvavidas
		tts_cache.save_cached_audio("fortuna", "es-AR-TomasNeural", "Vieja fortuna", b"ID3fortuna", db_path=db_path)

		with (
			patch.object(tts_cache, "HAS_EDGE_TTS", False),
			patch.object(tts_cache, "edge_tts", None),
		):
			for cat, fresh_text in [
				("hora", "Son las diez"),
				("minuto", "menos veinte"),
				("clima", "Hacen veintidós grados"),
			]:
				with pytest.raises(RuntimeError):
					await tts_cache.synthesize_segment(
						text=fresh_text,
						voice="es-AR-TomasNeural",
						category=cat,
						allow_cache=True,
						db_path=db_path,
					)

			fortuna_bytes = await tts_cache.synthesize_segment(
				text="Nueva fortuna no cacheada",
				voice="es-AR-TomasNeural",
				category="fortuna",
				allow_cache=True,
				db_path=db_path,
			)
			assert fortuna_bytes == b"ID3fortuna"


def test_cancel_pregeneration_cleans_sidecar_subtitles(tmp_path: Path) -> None:
	"""cancel_pregeneration debe borrar .lrc/.srt/.ass viejos para no mezclar letras entre segmentos."""
	from app.domain.radio.service import RadioService

	svc = RadioService()
	pre_mp3 = tmp_path / "radio_pregenerated.mp3"
	svc.pregenerated_path = pre_mp3
	for ext in (".mp3", ".lrc", ".srt", ".ass"):
		pre_mp3.with_suffix(ext).write_text("viejo", encoding="utf-8")

	svc.cancel_pregeneration()

	for ext in (".mp3", ".lrc", ".srt", ".ass"):
		assert not pre_mp3.with_suffix(ext).exists()


def test_assemble_announcement_audio_removes_stale_ass_and_subtitles(tmp_path: Path) -> None:
	"""assemble_announcement_audio debe limpiar .ass/.lrc/.srt previos antes de guardar los actuales."""
	from app.domain.radio.service import assemble_announcement_audio

	out_mp3 = tmp_path / "radio_announcement.mp3"
	stale_ass = out_mp3.with_suffix(".ass")
	stale_ass.write_text("[Events]\nViejo ASS", encoding="utf-8")

	fake_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 20
	with patch("app.domain.radio.service.find_binary", return_value=None):
		ok = assemble_announcement_audio(
			segments=[(fake_mp3, "intro", "es-AR-TomasNeural", "Hola gente", [(0.0, 1.0, "Hola gente")])],
			output_path=out_mp3,
		)

	assert ok is True
	assert not stale_ass.exists()
	assert out_mp3.with_suffix(".lrc").exists()


@pytest.mark.asyncio
async def test_toggle_dj_carpincho_cancels_stale_radio_pregeneration() -> None:
	"""Cambiar DJ Bara debe invalidar cualquier locución pregenerada para no confundir el cierre."""
	from app.api.commands import _cmd_toggle_dj_carpincho
	from app.api.schemas import CommandRequest

	state = MagicMock()
	state.dj_carpincho_enabled = False
	state.current_track = "/music/tema.mp3"
	state.dj_next_track = {"path": "/music/otro.mp3"}

	req = CommandRequest(cmd="toggle_dj_carpincho", state=True)
	await _cmd_toggle_dj_carpincho(state, req, MagicMock())
	state._cancel_radio_pregeneration.assert_called_once()

	state._cancel_radio_pregeneration.reset_mock()
	req_off = CommandRequest(cmd="toggle_dj_carpincho", state=False)
	await _cmd_toggle_dj_carpincho(state, req_off, MagicMock())
	state._cancel_radio_pregeneration.assert_called_once()
	assert state.dj_next_track is None


@pytest.mark.asyncio
async def test_serve_lrc_for_radio_sets_no_store_cache_control(tmp_path: Path) -> None:
	"""El endpoint /lrc para locuciones radiales debe usar no-store para que WebView no cachee letras viejas."""
	from types import SimpleNamespace

	from app.api.media import serve_lrc

	ann_mp3 = tmp_path / "radio_announcement.mp3"
	ann_lrc = tmp_path / "radio_announcement.lrc"
	ann_mp3.write_bytes(b"mp3")
	ann_lrc.write_text("[00:00.00] Segmento fresco\n", encoding="utf-8")

	fake_state = SimpleNamespace(
		is_radio_announcement=lambda p: str(p) == str(ann_mp3),
		path_to_id={},
		tracks_cache=[],
		radio_pregenerated_path=str(tmp_path / "radio_pregenerated.mp3"),
	)
	fake_container = MagicMock()
	fake_container.ensure_orchestrator.return_value = fake_state

	with patch("app.api.media.get_container", return_value=fake_container):
		resp = await serve_lrc(path=str(ann_mp3))

	assert "no-store" in resp.headers.get("cache-control", "")
