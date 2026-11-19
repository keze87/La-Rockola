"""
Pruebas de aislamiento para el entorno E2E de La Rockola del Carpincho.
Verifica que ROCKOLA_DATA_DIR aísle DB/config, que /api/health responda ok
y que POST /api/test/reset esté protegido por ROCKOLA_ENABLE_TEST_ROUTES=1.
Uso: pytest tests/test_rockola_e2e_isolation.py
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_carpincho_data_dir
from app.core.container import get_container
from app.infrastructure.db.connection import execute_query, execute_write
from app.main import app


def test_get_carpincho_data_dir_respects_env_override(tmp_path: Path, monkeypatch):
	"""Verifica que ROCKOLA_DATA_DIR redirija el directorio de datos sin tocar DB/."""
	custom_dir = tmp_path / "isolated_rockola_data"
	monkeypatch.setenv("ROCKOLA_DATA_DIR", str(custom_dir))

	resolved = get_carpincho_data_dir()
	assert resolved == custom_dir.resolve()
	assert resolved.is_dir()


def test_health_endpoint_returns_ok():
	"""Verifica que /api/health responda 200 ok para healthcheck de Playwright."""
	with TestClient(app) as client:
		res = client.get("/api/health")
		assert res.status_code == 200
		assert res.json().get("status") == "ok"


def test_reset_route_returns_404_when_disabled(monkeypatch):
	"""Verifica que POST /api/test/reset devuelva 404 si ROCKOLA_ENABLE_TEST_ROUTES no es 1."""
	monkeypatch.delenv("ROCKOLA_ENABLE_TEST_ROUTES", raising=False)
	with TestClient(app) as client:
		res = client.post("/api/test/reset")
		assert res.status_code == 404


def test_reset_route_clears_mutable_state_when_enabled(temp_db: Path, monkeypatch):
	"""Verifica que POST /api/test/reset limpie tablas mutables y cola si está habilitado."""
	monkeypatch.setenv("ROCKOLA_ENABLE_TEST_ROUTES", "1")
	container = get_container()
	state = container.ensure_orchestrator()
	state.queue = [{"track_id": "trk_1", "title": "Tema de prueba"}]

	execute_write(
		"INSERT OR REPLACE INTO favorites (track_id) VALUES (?)",
		("trk_1",),
		db_path=temp_db,
	)
	execute_write(
		"INSERT INTO play_history (track_id, played_at) VALUES (?, ?)",
		("trk_1", 1000.0),
		db_path=temp_db,
	)

	with TestClient(app) as client:
		res = client.post("/api/test/reset")
		assert res.status_code == 200
		assert res.json() == {"reset": True}

	assert state.queue == []
	assert execute_query("SELECT * FROM favorites", db_path=temp_db) == []
	assert execute_query("SELECT * FROM play_history", db_path=temp_db) == []
