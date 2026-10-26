"""
Pruebas unitarias para la portada radio.jpg y los locutores dinámicos en cabina.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from app.core.container import AppContainer, set_container
from app.domain.playback.orchestrator import PlaybackOrchestrator
from app.domain.radio.banks import VOICE_TOMAS
from app.domain.radio.service import RadioAnnouncementResult
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
