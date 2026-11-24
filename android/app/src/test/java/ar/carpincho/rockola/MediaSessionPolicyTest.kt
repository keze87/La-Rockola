package ar.carpincho.rockola

import android.support.v4.media.session.PlaybackStateCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaSessionPolicyTest {
    @Test
    fun `computePlaybackActions habilita seek solo cuando hay pista con duracion positiva`() {
        val noTrack = MediaSessionPolicy.computePlaybackActions(hasTrack = false, durationMs = 0L)
        assertEquals(0L, noTrack and PlaybackStateCompat.ACTION_SEEK_TO)
        assertTrue((noTrack and PlaybackStateCompat.ACTION_PLAY) != 0L)

        val unknownDuration = MediaSessionPolicy.computePlaybackActions(hasTrack = true, durationMs = 0L)
        assertEquals(0L, unknownDuration and PlaybackStateCompat.ACTION_SEEK_TO)
        assertTrue((unknownDuration and PlaybackStateCompat.ACTION_SKIP_TO_NEXT) != 0L)
        assertTrue((unknownDuration and PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS) != 0L)

        val withDuration = MediaSessionPolicy.computePlaybackActions(hasTrack = true, durationMs = 180_000L)
        assertTrue((withDuration and PlaybackStateCompat.ACTION_SEEK_TO) != 0L)
        assertTrue((withDuration and PlaybackStateCompat.ACTION_PLAY_PAUSE) != 0L)
    }

    @Test
    fun `formatSubText evita mostrar URL cruda en modo local y extrae host en modo remoto`() {
        assertEquals(
            "La Rockola",
            MediaSessionPolicy.formatSubText(MediaTarget(MediaTargetMode.HOST, "http://192.168.1.40:1729")),
        )
        assertEquals(
            "Remoto · 192.168.1.55",
            MediaSessionPolicy.formatSubText(MediaTarget(MediaTargetMode.REMOTE, "http://192.168.1.55:1729")),
        )
        assertEquals(
            "Remoto · rockola.local",
            MediaSessionPolicy.formatSubText(MediaTarget(MediaTargetMode.REMOTE, "https://rockola.local/")),
        )
    }

    @Test
    fun `resolveAlbumName devuelve album real cuando existe o fallback de La Rockola`() {
        assertEquals("Artaud", MediaSessionPolicy.resolveAlbumName("Artaud"))
        assertEquals("Artaud", MediaSessionPolicy.resolveAlbumName("  Artaud  "))
        assertEquals("La Rockola del Carpincho", MediaSessionPolicy.resolveAlbumName(null))
        assertEquals("La Rockola del Carpincho", MediaSessionPolicy.resolveAlbumName("   "))
    }
}
