from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_claim_and_replace_local_player(clean_manager):
	"""Prueba que un segundo cliente reemplace al primero en vez de ser rechazado."""
	manager = clean_manager
	ws1 = MagicMock()
	ws2 = MagicMock()

	# Primer cliente reclama el rol
	ok1, evicted1 = manager.claim_local_player(ws1)
	assert ok1 is True
	assert evicted1 is None
	assert manager.local_player_ws is ws1
	assert manager.has_local_player is True

	# Segundo cliente reclama y reemplaza al primero
	ok2, evicted2 = manager.claim_local_player(ws2)
	assert ok2 is True
	assert evicted2 is ws1
	assert manager.local_player_ws is ws2
	assert manager.has_local_player is True

	# El mismo cliente reclama de nuevo sin auto-desalojarse
	ok3, evicted3 = manager.claim_local_player(ws2)
	assert ok3 is True
	assert evicted3 is None
	assert manager.local_player_ws is ws2

	# Liberación normal
	assert manager.release_local_player(ws2) is True
	assert manager.local_player_ws is None
	assert manager.has_local_player is False


@pytest.mark.asyncio
async def test_reset_local_player(clean_manager):
	"""Prueba el reseteo del reproductor local para volver a parlantes del servidor."""
	manager = clean_manager
	ws = MagicMock()

	# Reseteo sin reproductor activo no falla
	assert manager.reset_local_player() is None

	# Reclamar rol y resetearlo forzosamente
	manager.claim_local_player(ws)
	assert manager.has_local_player is True
	evicted = manager.reset_local_player()
	assert evicted is ws
	assert manager.local_player_ws is None
	assert manager.has_local_player is False


@pytest.mark.asyncio
async def test_broadcast_sanitization_and_delivery(clean_manager):
	"""Test that broadcast cleans logs while delivering complete payload to clients."""
	manager = clean_manager
	ws = MagicMock()
	ws.accept = AsyncMock()
	ws.send_json = AsyncMock()
	await manager.connect(ws)

	test_message = {
		"type": "state_update",
		"library": [{"title": "Song 1"}, {"title": "Song 2"}],
		"top_played": [{"path": "/m/s1.mp3", "count": 10}],
		"fingerprint": "RAW_FINGERPRINT_STRING",
		"dj_next_track": {
			"display_title": "Upcoming",
			"fingerprint": "NESTED_RAW_FP",
		},
	}

	with patch("server.logger.debug") as mock_log:
		await manager.broadcast(test_message)

		# 1. Verify client received UNTRUNCATED payload
		ws.send_json.assert_called_once_with(test_message)

		# 2. Verify logger received SANITIZED dictionary string
		assert mock_log.called
		logged_str = mock_log.call_args[0][0]
		assert "<Librería omitida del log" in logged_str
		assert "<Top temas omitido del log" in logged_str
		assert "<Fingerprint omitido del log>" in logged_str
		assert "RAW_FINGERPRINT_STRING" not in logged_str
		assert "NESTED_RAW_FP" not in logged_str
