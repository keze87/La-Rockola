"""
Tests TDD para app.engine (mpv_controller, mpris, audio_analysis).
"""

from unittest.mock import AsyncMock

import pytest

from app.engine.audio_analysis import compare_fps, parse_fp
from app.engine.mpris import build_mpris_metadata
from app.engine.mpv_controller import AsyncMpvController


def test_parse_and_compare_fingerprints():
	nums1 = [1000 + i for i in range(12)]
	nums2 = [1000 + i for i in range(11)] + [9999]
	fp1 = ",".join(str(n) for n in nums1)
	fp2 = ",".join(str(n) for n in nums2)
	parsed1 = parse_fp(fp1)
	parsed2 = parse_fp(fp2)

	assert len(parsed1) == 12
	assert len(parsed2) == 12

	score = compare_fps(parsed1, parsed2)
	assert score > 0.6  # Altamente similares

	# Mismo fp
	assert compare_fps(parsed1, parsed1) == 1.0

	# Vacío
	assert compare_fps([], []) == 0.0


def test_build_mpris_metadata():
	track = {
		"title": "Ji Ji Ji",
		"artist": "Los Redondos",
		"album": "Oktubre",
		"duration": 320,
		"path": "/music/jijiji.mp3",
	}
	meta = build_mpris_metadata(track, server_url="http://localhost:1729")
	assert meta is not None
	# En Linux con dbus_next es un dict de Variants, pero sus valores o keys contienen la data
	assert "xesam:title" in meta or "xesam:title" in str(meta)


@pytest.mark.asyncio
async def test_mpv_controller_init_and_mock_send():
	on_prop = AsyncMock()
	on_event = AsyncMock()
	controller = AsyncMpvController(
		ipc_path="/tmp/mock_mpv_ipc",
		on_property_change=on_prop,
		on_event=on_event,
	)
	assert controller.ipc_path == "/tmp/mock_mpv_ipc"
	assert not controller.is_running
