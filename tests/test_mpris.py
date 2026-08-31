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


def test_build_mpris_metadata_no_track(clean_state):
	"""Test build_mpris_metadata returns NoTrack when no current track."""
	clean_state.current_track = None
	meta = server.build_mpris_metadata(clean_state)

	assert "mpris:trackid" in meta
	assert meta["mpris:trackid"].value == "/org/mpris/MediaPlayer2/TrackList/NoTrack"
	assert meta["mpris:trackid"].signature == "o"


def test_build_mpris_metadata_local_track_with_cache_and_cover(clean_state):
	"""Test build_mpris_metadata for local track in cache with cover art."""
	clean_state.current_track = "/music/tango.mp3"
	clean_state.duration = 152.5
	clean_state.tracks_cache = [
		{
			"path": "/music/tango.mp3",
			"display_title": "Por una Cabeza",
			"display_artist": "Carlos Gardel",
			"album": "Tango Classics",
		}
	]

	with patch("server.get_cover_art_uri", return_value="file:///tmp/cover.jpg"):
		meta = server.build_mpris_metadata(clean_state)

		assert meta["mpris:trackid"].value == "/org/mpris/MediaPlayer2/TrackList/Track0"
		assert meta["xesam:title"].value == "Por una Cabeza"
		assert meta["xesam:artist"].value == ["Carlos Gardel"]
		assert meta["xesam:album"].value == "Tango Classics"
		assert meta["mpris:length"].value == 152500000
		assert meta["xesam:url"].value.startswith("file://")
		assert meta["xesam:url"].value.endswith("tango.mp3")
		assert meta["mpris:artUrl"].value == "file:///tmp/cover.jpg"


def test_build_mpris_metadata_url_track_youtube(clean_state):
	"""Test build_mpris_metadata for URL/YouTube track using url_metadata."""
	clean_state.current_track = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
	clean_state.duration = 212.0
	clean_state.url_metadata = {
		"https://www.youtube.com/watch?v=dQw4w9WgXcQ": {
			"display_title": "Never Gonna Give You Up",
			"display_artist": "Rick Astley",
			"album": "Whenever You Need Somebody",
		}
	}

	with patch("server.get_cover_art_uri", return_value=""):
		meta = server.build_mpris_metadata(clean_state)

		assert meta["xesam:title"].value == "Never Gonna Give You Up"
		assert meta["xesam:artist"].value == ["Rick Astley"]
		assert meta["xesam:album"].value == "Whenever You Need Somebody"
		assert meta["mpris:length"].value == 212000000
		assert meta["xesam:url"].value == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
		assert "mpris:artUrl" not in meta


def test_build_mpris_metadata_defaults_and_custom_variant(clean_state):
	"""Test build_mpris_metadata fallback defaults when uncached, and custom variant class."""
	clean_state.current_track = "/music/unknown.mp3"
	clean_state.tracks_cache = []
	clean_state.url_metadata = {}
	clean_state.duration = 0.0

	class CustomVariant:
		def __init__(self, sig, val):
			self.sig = sig
			self.val = val

	with patch("server.get_cover_art_uri", return_value=""):
		meta = server.build_mpris_metadata(clean_state, variant_cls=CustomVariant)

		assert meta["xesam:title"].val == "Desconocido"
		assert meta["xesam:artist"].val == ["Desconocido"]
		assert meta["xesam:album"].val == "La Rockola del Carpincho"
		assert meta["mpris:length"].val == 0
		assert meta["xesam:url"].val.startswith("file://")
		assert "mpris:artUrl" not in meta
