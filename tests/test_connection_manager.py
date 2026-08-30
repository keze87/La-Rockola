import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_claim_and_release_local_player(clean_manager):
	"""Test claiming local player role with single-client ownership and release."""
	manager = clean_manager
	ws1 = MagicMock()
	ws2 = MagicMock()

	# First client claims successfully
	assert manager.claim_local_player(ws1) is True
	assert manager.local_player_ws is ws1

	# Second client is rejected while first is active
	assert manager.claim_local_player(ws2) is False
	assert manager.local_player_ws is ws1

	# First client releases role
	manager.release_local_player(ws1)
	assert manager.local_player_ws is None

	# Second client can now claim
	assert manager.claim_local_player(ws2) is True
	assert manager.local_player_ws is ws2


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
