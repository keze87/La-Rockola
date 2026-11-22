"""Verifica que todos los activos públicos de raíz y los íconos del manifest respondan 200."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_manifest_icons_and_public_root_assets_return_200(monkeypatch) -> None:
	public_dir = Path(__file__).resolve().parent.parent / "public"
	manifest = json.loads((public_dir / "manifest.webmanifest").read_text(encoding="utf-8"))
	monkeypatch.setenv("ROCKOLA_DIST_DIR", str(public_dir))

	app = create_app()
	client = TestClient(app)

	icon_routes = ["/" + str(icon["src"]).lstrip("./") for icon in manifest["icons"]]
	expected_routes = [
		"/manifest.webmanifest",
		"/sw.js",
		"/favicon.ico",
		"/favicon.png",
		"/radio.jpg",
		*icon_routes,
	]

	for route in expected_routes:
		res = client.get(route)
		assert res.status_code == 200, f"Ruta {route} devolvió {res.status_code}"
		assert len(res.content) > 0
