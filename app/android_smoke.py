"""
Prueba de humo en proceso para verificar el runtime embebido Android (Chaquopy Python 3.14).
Valida imports críticos y responde endpoints básicos de FastAPI sin efectos secundarios globales.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from typing import Any

CRITICAL_MODULES = (
	"fastapi",
	"uvicorn",
	"httpx",
	"pydantic",
	"pydantic_core",
	"pydantic_settings",
	"mutagen",
	"websockets",
	"edge_tts",
	"aiohttp",
	"frozenlist",
	"multidict",
	"yarl",
	"app.android_entry",
)


def run_embedded_smoke_check(work_dir: str | Path | None = None) -> dict[str, Any]:
	"""Ejecuta verificación rápida de imports, migraciones y endpoints FastAPI en memoria."""
	from fastapi.testclient import TestClient

	from app import android_entry
	from app.core import config as config_mod
	from app.core.container import get_container, set_container
	from app.main import create_app

	checked: list[str] = []
	for mod_name in CRITICAL_MODULES:
		importlib.import_module(mod_name)
		checked.append(mod_name)

	prev_env = {k: os.environ.get(k) for k in ("ROCKOLA_DATA_DIR", "ROCKOLA_DIST_DIR", "ROCKOLA_SKIP_FRONTEND_BUILD")}
	prev_container = get_container()
	prev_settings = config_mod.get_settings()

	tmp_ctx = tempfile.TemporaryDirectory(prefix="rockola_smoke_") if work_dir is None else None
	try:
		base_dir = Path(work_dir) if work_dir is not None else Path(tmp_ctx.name)  # type: ignore[union-attr]
		data_dir = base_dir / "smoke_data"
		dist_dir = base_dir / "smoke_dist"
		data_dir.mkdir(parents=True, exist_ok=True)
		(dist_dir / "assets").mkdir(parents=True, exist_ok=True)
		(dist_dir / "index.html").write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")

		android_entry.configure_android_environment(
			data_dir=str(data_dir),
			dist_dir=str(dist_dir),
			music_dir="",
			port=1899,
		)
		fastapi_app = create_app()
		client = TestClient(fastapi_app)
		health_res = client.get("/api/v1/health")
		sys_res = client.get("/api/v1/system/info")
		ok = (
			health_res.status_code == 200
			and health_res.json().get("status") == "ok"
			and sys_res.status_code == 200
			and "folder_status" in sys_res.json()
		)
		return {
			"ok": bool(ok),
			"checked_modules": checked,
			"health_status": health_res.status_code,
			"system_info_status": sys_res.status_code,
		}
	finally:
		set_container(prev_container)
		config_mod.set_settings(prev_settings)
		for key, old_val in prev_env.items():
			if old_val is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = old_val
		if tmp_ctx is not None:
			tmp_ctx.cleanup()
