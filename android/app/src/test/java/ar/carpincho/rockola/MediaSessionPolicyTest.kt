package ar.carpincho.rockola

import android.support.v4.media.session.PlaybackStateCompat
import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
    fun `detector de doble toque en auricular distingue toque simple de doble toque`() {
        val detector = HeadsetDoubleTapDetector(doubleTapWindowMs = 350L)

        assertFalse(detector.isDoubleTap(KeyEvent.KEYCODE_HEADSETHOOK, nowMs = 1000L))
        assertTrue(detector.isDoubleTap(KeyEvent.KEYCODE_HEADSETHOOK, nowMs = 1250L))

        // Tras consumir doble toque, el siguiente vuelve a ser el primero de una nueva secuencia
        assertFalse(detector.isDoubleTap(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, nowMs = 1350L))
        // Fuera de la ventana de 350 ms ya no es doble toque
        assertFalse(detector.isDoubleTap(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, nowMs = 1800L))
    }
}
