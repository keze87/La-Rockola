package ar.carpincho.rockola

import androidx.media3.common.Player
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
}
