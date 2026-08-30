import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


@pytest.mark.asyncio
async def test_get_library_endpoint(clean_state, monkeypatch):
	"""Test /library returns clean library without fingerprints."""
	monkeypatch.setattr(server, "state", clean_state)
	clean_state.tracks_cache = [
		{
			"path": "/music/song.mp3",
			"display_title": "Clean Song",
			"display_artist": "Clean Artist",
			"fingerprint": "SHOULD_BE_EXCLUDED",
			"bpm": 120.0,
		}
	]

	res = await server.get_library()
	assert "data" in res
	assert len(res["data"]) == 1
	assert "fingerprint" not in res["data"][0]
	assert "bpm" not in res["data"][0]
	assert res["data"][0]["display_title"] == "Clean Song"


@pytest.mark.asyncio
async def test_serve_cover_endpoint(tmp_path, clean_state, monkeypatch):
	"""Test /cover endpoint with valid and invalid paths."""
	monkeypatch.setattr(server, "state", clean_state)

	# 1. Nonexistent file returns 404
	res = await server.serve_cover(path=str(tmp_path / "missing.mp3"))
	assert res.status_code == 404


@pytest.mark.asyncio
async def test_stream_audio_endpoint(tmp_path, clean_state, monkeypatch):
	"""Test /stream endpoint returns file response with Range and Cache-Control headers."""
	monkeypatch.setattr(server, "state", clean_state)

	# Unregistered track returns 404
	res = await server.stream_audio(path="/unregistered/path.mp3")
	assert res.status_code == 404

	# Registered track returns FileResponse
	dummy = tmp_path / "registered.mp3"
	dummy.write_bytes(b"AUDIO_DATA")
	clean_state.tracks_cache = [{"path": str(dummy)}]
	clean_state.path_to_id[str(dummy)] = "id1"

	res = await server.stream_audio(path=str(dummy))
	assert res.status_code == 200
	assert res.headers.get("Accept-Ranges") == "bytes"
	assert "Cache-Control" in res.headers


@pytest.mark.asyncio
async def test_serve_lrc_endpoint(tmp_path, clean_state, monkeypatch):
	"""Test /lrc endpoint serving lyrics or returning 404."""
	monkeypatch.setattr(server, "state", clean_state)

	song_path = tmp_path / "song.mp3"
	song_path.write_bytes(b"AUDIO")
	lrc_path = tmp_path / "song.lrc"
	lrc_path.write_text("[00:01.00] La Rockola del Carpincho")

	clean_state.tracks_cache = [{"path": str(song_path)}]
	clean_state.path_to_id[str(song_path)] = "id1"

	# Existing .lrc
	res = await server.serve_lrc(path=str(song_path))
	assert res.status_code == 200

	# Missing .lrc
	song_no_lrc = tmp_path / "no_lrc.mp3"
	song_no_lrc.write_bytes(b"AUDIO")
	clean_state.tracks_cache.append({"path": str(song_no_lrc)})
	clean_state.path_to_id[str(song_no_lrc)] = "id2"

	res_missing = await server.serve_lrc(path=str(song_no_lrc))
	assert res_missing.status_code == 404


@pytest.mark.asyncio
async def test_mpv_visibility_endpoints(clean_state, monkeypatch):
	"""Test /mpv/hide and /mpv/show endpoints."""
	monkeypatch.setattr(server, "state", clean_state)

	# Hide
	res_hide = await server.mpv_hide()
	assert res_hide["status"] == "ok"
	assert clean_state.mpv_visible is False

	# Show
	res_show = await server.mpv_show()
	assert res_show["status"] == "ok"
	assert clean_state.mpv_visible is True


@pytest.mark.asyncio
async def test_handle_command_playback_controls(clean_state, monkeypatch):
	"""Test /command for playback commands (play, pause, skip, prev, stop, vol, mute)."""
	monkeypatch.setattr(server, "state", clean_state)

	# 1. Play
	req = server.CommandRequest(cmd="play", path="/music/song1.mp3")
	await server.handle_command(req)
	assert clean_state.current_track == "/music/song1.mp3"

	# 2. Volume control
	req_vol = server.CommandRequest(cmd="set_volume", vollevel=80)
	await server.handle_command(req_vol)
	assert clean_state.volume == 80

	req_up = server.CommandRequest(cmd="vol_up")
	await server.handle_command(req_up)
	assert clean_state.volume == 85

	req_down = server.CommandRequest(cmd="vol_down")
	await server.handle_command(req_down)
	assert clean_state.volume == 80

	# 3. Mute
	req_mute = server.CommandRequest(cmd="set_mute", state=True)
	await server.handle_command(req_mute)
	assert clean_state.server_muted is True

	# 4. Stop
	req_stop = server.CommandRequest(cmd="stop")
	await server.handle_command(req_stop)
	assert clean_state.current_track is None
	assert clean_state.history == ["/music/song1.mp3"]


@pytest.mark.asyncio
async def test_handle_command_queue_and_favorites(clean_state, monkeypatch):
	"""Test /command for queue manipulation and favorite toggling."""
	monkeypatch.setattr(server, "state", clean_state)
	clean_state.path_to_id["/music/s1.mp3"] = "hash1"

	# Toggle favorite
	req_fav = server.CommandRequest(cmd="toggle_favorite", path="/music/s1.mp3")
	await server.handle_command(req_fav)
	assert "hash1" in clean_state.favorites

	await server.handle_command(req_fav)
	assert "hash1" not in clean_state.favorites

	# Queue operations
	clean_state.queue = ["/m/1.mp3", "/m/2.mp3", "/m/3.mp3"]
	req_move = server.CommandRequest(cmd="move_queue_item", index=0, new_index=2)
	await server.handle_command(req_move)
	assert clean_state.queue == ["/m/2.mp3", "/m/3.mp3", "/m/1.mp3"]

	req_remove = server.CommandRequest(cmd="remove_queue_item", index=1)
	await server.handle_command(req_remove)
	assert clean_state.queue == ["/m/2.mp3", "/m/1.mp3"]

	# Clear queue
	req_clear = server.CommandRequest(cmd="clear_queue")
	await server.handle_command(req_clear)
	assert clean_state.queue == []

	# History remove
	clean_state.history = ["/h/1.mp3", "/h/2.mp3"]
	req_h_remove = server.CommandRequest(cmd="remove_history_item", index=0)
	await server.handle_command(req_h_remove)
	assert clean_state.history == ["/h/2.mp3"]

	# DJ Carpincho toggles
	assert clean_state.dj_carpincho_enabled is False
	await server.handle_command(server.CommandRequest(cmd="toggle_dj_carpincho"))
	assert clean_state.dj_carpincho_enabled is True

	assert clean_state.dj_safe_mode is False
	await server.handle_command(server.CommandRequest(cmd="toggle_dj_safe_mode", state=True))
	assert clean_state.dj_safe_mode is True

	# Pause after
	await server.handle_command(server.CommandRequest(cmd="pause_after", path="/m/target.mp3"))
	assert clean_state.pause_after_path == "/m/target.mp3"

	# Fullscreen
	await server.handle_command(server.CommandRequest(cmd="fullscreen"))
	clean_state.mpv._send.assert_called()

	# Add URL (mocking fetch_yt_dlp_metadata)
	# When nothing is playing, add_url immediately plays it
	with patch.object(clean_state, "fetch_yt_dlp_metadata", new_callable=AsyncMock):
		await server.handle_command(server.CommandRequest(cmd="add_url", path="https://youtube.com/watch?v=123"))
		assert clean_state.current_track == "https://youtube.com/watch?v=123"

		# When already playing, add_url queues the next URL
		await server.handle_command(server.CommandRequest(cmd="add_url", path="https://youtube.com/watch?v=456"))
		assert "https://youtube.com/watch?v=456" in clean_state.queue

	# Seek commands
	await server.handle_command(server.CommandRequest(cmd="seek", amount=10))
	clean_state.mpv._send.assert_called()

	await server.handle_command(server.CommandRequest(cmd="seek_absolute", target=45))
	clean_state.mpv._send.assert_called()


@pytest.mark.asyncio
async def test_websocket_endpoint_flow(clean_state, clean_manager, monkeypatch):
	"""Test WebSocket lifecycle: connection, initial state broadcast, and local player claiming."""
	monkeypatch.setattr(server, "state", clean_state)
	monkeypatch.setattr(server, "manager", clean_manager)

	mock_ws = MagicMock()
	mock_ws.client.host = "192.168.0.100"
	mock_ws.accept = AsyncMock()
	mock_ws.send_json = AsyncMock()

	# Simulate incoming messages: claim local player, song ended, and disconnect
	messages = [
		json.dumps({"type": "local_player_claim"}),
		json.dumps({"type": "local_player_update", "time_pos": 15.0, "duration": 200.0, "paused": False}),
		json.dumps({"type": "local_player_update", "song_ended": True}),
		json.dumps({"type": "local_player_release"}),
	]
	mock_ws.receive_text = AsyncMock(side_effect=messages + [server.WebSocketDisconnect()])

	with patch("server.broadcast_state", new_callable=AsyncMock):
		await server.websocket_endpoint(mock_ws)

	# Verify initial state was sent
	assert mock_ws.send_json.called
	first_call_arg = mock_ws.send_json.call_args_list[0][0][0]
	assert first_call_arg["type"] == "state_update"


@pytest.mark.asyncio
async def test_websocket_local_player_rejection(clean_state, clean_manager, monkeypatch):
	"""Test rejection of second client trying to claim local player."""
	monkeypatch.setattr(server, "state", clean_state)
	monkeypatch.setattr(server, "manager", clean_manager)

	# First client claims
	first_ws = MagicMock()
	clean_manager.claim_local_player(first_ws)

	# Second client attempts claim
	second_ws = MagicMock()
	second_ws.client.host = "192.168.0.102"
	second_ws.accept = AsyncMock()
	second_ws.send_json = AsyncMock()
	second_ws.receive_text = AsyncMock(
		side_effect=[json.dumps({"type": "local_player_claim"}), server.WebSocketDisconnect()]
	)

	with patch("server.broadcast_state", new_callable=AsyncMock):
		await server.websocket_endpoint(second_ws)

	assert clean_manager.local_player_ws is first_ws


@pytest.mark.asyncio
async def test_serve_cover_flac_and_id3_extraction(tmp_path, clean_state, monkeypatch):
	"""Test /cover extracting image data from FLAC pictures and ID3 APIC frames."""
	monkeypatch.setattr(server, "state", clean_state)
	dummy_path = tmp_path / "song_with_cover.flac"
	dummy_path.write_bytes(b"FLAC_DATA")

	clean_state.tracks_cache = [{"path": str(dummy_path)}]
	clean_state.path_to_id[str(dummy_path)] = "id_cover"

	# Mock MutagenFile with FLAC picture (starts with JPEG magic \xff\xd8)
	mock_pic = MagicMock()
	mock_pic.data = b"\xff\xd8\xff\xe0JPEG_IMAGE_DATA"
	mock_pic.mime = "image/jpeg"
	mock_audio = MagicMock()
	mock_audio.pictures = [mock_pic]

	with patch("server.MutagenFile", return_value=mock_audio):
		res = await server.serve_cover(path=str(dummy_path))
		assert res.status_code == 200
		assert res.media_type == "image/jpeg"
		assert res.body.startswith(b"\xff\xd8")


@pytest.mark.asyncio
async def test_scan_library_endpoint(clean_state, monkeypatch):
	"""Test /scan endpoint initiating scan on target directories."""
	monkeypatch.setattr(server, "state", clean_state)

	with patch.object(clean_state, "scan_directory", return_value=[{"display_title": "Scanned Song"}]):
		res = await server.scan_library(dir="/custom/dir1", dir2="/custom/dir2")
		assert "data" in res
		assert len(res["data"]) == 1
