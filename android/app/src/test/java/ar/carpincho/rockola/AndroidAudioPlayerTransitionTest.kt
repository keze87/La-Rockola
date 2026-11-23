package ar.carpincho.rockola

import androidx.media3.common.Player
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidAudioPlayerTransitionTest {

    @Test
    fun `mantiene reproducción activa mientras buffering o cargando tema siguiente`() {
        assertTrue(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = true,
                playWhenReady = true,
                playbackState = Player.STATE_READY,
                isLoadingMedia = false,
            ),
        )
        assertTrue(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = true,
                playbackState = Player.STATE_BUFFERING,
                isLoadingMedia = false,
            ),
        )
        assertTrue(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = true,
                playbackState = Player.STATE_IDLE,
                isLoadingMedia = true,
            ),
        )
        assertTrue(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = true,
                playbackState = Player.STATE_ENDED,
                isLoadingMedia = false,
            ),
        )
    }

    @Test
    fun `desactiva reproducción cuando está en pausa o detenido sin carga en curso`() {
        assertFalse(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = false,
                playbackState = Player.STATE_READY,
                isLoadingMedia = false,
            ),
        )
        assertFalse(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = false,
                playbackState = Player.STATE_BUFFERING,
                isLoadingMedia = true,
            ),
        )
        assertFalse(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = true,
                playbackState = Player.STATE_IDLE,
                isLoadingMedia = false,
            ),
        )
        assertFalse(
            AndroidAudioPlayer.shouldKeepPlaybackActive(
                isPlaying = false,
                playWhenReady = false,
                playbackState = Player.STATE_ENDED,
                isLoadingMedia = false,
            ),
        )
    }

    @Test
    fun `ganancia propia del reproductor preserva volumen al mutear y desmutear`() {
        assertEquals(0.55f, AndroidAudioPlayer.computePlayerGain(55.0, muted = false), 0.001f)
        assertEquals(0.0f, AndroidAudioPlayer.computePlayerGain(55.0, muted = true), 0.001f)
        assertEquals(1.0f, AndroidAudioPlayer.computePlayerGain(150.0, muted = false), 0.001f)
        assertEquals(0.0f, AndroidAudioPlayer.computePlayerGain(-10.0, muted = false), 0.001f)
    }

    @Test
    fun `ganancia de cortina radial escala por volumen maestro, ratio, fade y mute`() {
        assertEquals(0.05f, AndroidAudioPlayer.computeBedGain(50.0, muted = false, bedRatio = 0.1f, fadeEnvelope = 1.0f), 0.0001f)
        assertEquals(0.025f, AndroidAudioPlayer.computeBedGain(50.0, muted = false, bedRatio = 0.1f, fadeEnvelope = 0.5f), 0.0001f)
        assertEquals(0.0f, AndroidAudioPlayer.computeBedGain(80.0, muted = true, bedRatio = 0.1f, fadeEnvelope = 1.0f), 0.0001f)
        assertEquals(0.0f, AndroidAudioPlayer.computeBedGain(80.0, muted = false, bedRatio = -0.2f, fadeEnvelope = 1.0f), 0.0001f)
    }

    @Test
    fun `envolvente de fade de cortina sube en fade-in y baja al acercarse el fin del anuncio`() {
        assertEquals(0.0f, AndroidAudioPlayer.computeBedFadeEnvelope(elapsedMs = 0L, durationMs = 10000L), 0.001f)
        assertEquals(0.5f, AndroidAudioPlayer.computeBedFadeEnvelope(elapsedMs = 500L, durationMs = 10000L), 0.001f)
        assertEquals(1.0f, AndroidAudioPlayer.computeBedFadeEnvelope(elapsedMs = 5000L, durationMs = 10000L), 0.001f)
        assertEquals(0.5f, AndroidAudioPlayer.computeBedFadeEnvelope(elapsedMs = 9250L, durationMs = 10000L), 0.001f)
        assertEquals(0.0f, AndroidAudioPlayer.computeBedFadeEnvelope(elapsedMs = 10000L, durationMs = 10000L), 0.001f)
    }
}
