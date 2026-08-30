import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import server


def test_mpris_root_properties():
	"""Test MPRISRoot metadata and interface properties."""
	if not server.DBUS_AVAILABLE:
		pytest.skip("DBus not available on this platform")

	root = server.MPRISRoot()
	assert root.Identity == "La Rockola del Carpincho"
	assert root.DesktopEntry == "carpincho"
	assert "file" in root.SupportedUriSchemes
	assert "audio/mpeg" in root.SupportedMimeTypes
	assert root.CanQuit is False
	assert root.CanRaise is False
	assert root.HasTrackList is False
	assert root.Fullscreen is False
	assert root.CanSetFullscreen is False

	# Methods should execute without error
	root.Quit()
	root.Raise()


@pytest.mark.asyncio
async def test_mpris_player_playback_status_and_properties(clean_state):
	"""Test MPRISPlayer properties reflecting state."""
	if not server.DBUS_AVAILABLE:
		pytest.skip("DBus not available on this platform")

	state = clean_state
	player = server.MPRISPlayer(state)

	# Stopped status
	state.current_track = None
	assert player.PlaybackStatus == "Stopped"

	# Playing status
	state.current_track = "/music/song.mp3"
	state.mpv_paused = False
	assert player.PlaybackStatus == "Playing"

	# Paused status
	state.mpv_paused = True
	assert player.PlaybackStatus == "Paused"

	# Volume property
	state.volume = 75
	assert player.Volume == 0.75

	# Position property (in microseconds)
	state.time_pos = 10.5
	assert player.Position == 10500000

	# Rate, Loop, Shuffle, Capabilities
	assert player.Rate == 1.0
	assert player.LoopStatus == "None"
	assert player.Shuffle is False
	assert player.CanControl is True
	assert player.CanPlay is True
	assert player.CanPause is True
	assert player.CanSeek is True


@pytest.mark.asyncio
async def test_mpris_player_metadata_formatting(clean_state):
	"""Test MPRISPlayer Metadata formatting with TrackList and cover URI."""
	if not server.DBUS_AVAILABLE:
		pytest.skip("DBus not available on this platform")

	state = clean_state
	player = server.MPRISPlayer(state)

	# No track returns NoTrack
	state.current_track = None
	meta_none = player.Metadata
	assert meta_none["mpris:trackid"].value == "/org/mpris/MediaPlayer2/TrackList/NoTrack"

	# Active track with metadata in tracks_cache
	track_path = "/music/rock.mp3"
	state.current_track = track_path
	state.duration = 180.0
	state.tracks_cache = [
		{
			"path": track_path,
			"display_title": "Rock Nacional",
			"display_artist": "Charly García",
			"album": "Clics Modernos",
		}
	]

	meta = player.Metadata
	assert meta["xesam:title"].value == "Rock Nacional"
	assert meta["xesam:artist"].value == ["Charly García"]
	assert meta["xesam:album"].value == "Clics Modernos"
	assert meta["mpris:length"].value == 180000000


@pytest.mark.asyncio
async def test_mpris_player_control_methods(clean_state):
	"""Test MPRISPlayer action methods dispatching commands."""
	if not server.DBUS_AVAILABLE:
		pytest.skip("DBus not available on this platform")

	state = clean_state
	player = server.MPRISPlayer(state)

	with patch("server.handle_command", new_callable=AsyncMock) as mock_cmd:
		# Next & Previous
		player.Next()
		player.Previous()
		# PlayPause, Stop, OpenUri
		player.PlayPause()
		player.Stop()
		player.OpenUri("https://radio.stream/live")
		# Seek (in microseconds)
		player.Seek(5000000)  # 5 seconds
		player.SetPosition("/org/mpris/MediaPlayer2/TrackList/Track0", 25000000)  # 25 seconds

		await asyncio.sleep(0.02)
		assert mock_cmd.call_count >= 7
