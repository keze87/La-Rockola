package ar.carpincho.rockola

import android.content.pm.ServiceInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RemoteExoPlayerPolicyTest {

    @Test
    fun `cliente remoto reproduciendo con ExoPlayer retiene foreground tipo mediaPlayback aunque host local este apagado`() {
        val useFg = ServicePowerPolicy.shouldUseForeground(
            isHostRunning = false,
            isMediaPlaying = true,
            isRadioSynthesizing = false,
            hasRemoteClients = false,
            isRemotePlaybackActive = true,
        )
        assertTrue(useFg)

        val fgType = ServicePowerPolicy.foregroundServiceType(
            isMediaPlaying = true,
            hasRemoteClients = false,
            isRadioSynthesizing = false,
        )
        assertEquals(ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK, fgType)

        val needsWifiLock = ServicePowerPolicy.shouldAcquireWifiLock(
            mode = MediaTargetMode.REMOTE,
            hasRemoteClients = false,
            isActivePlaybackOrRadio = true,
        )
        assertTrue(needsWifiLock)
    }

    @Test
    fun `cliente remoto en pausa o sin pista no retiene foreground innecesario`() {
        val useFg = ServicePowerPolicy.shouldUseForeground(
            isHostRunning = false,
            isMediaPlaying = false,
            isRadioSynthesizing = false,
            hasRemoteClients = false,
            isRemotePlaybackActive = false,
        )
        assertFalse(useFg)
    }

    @Test
    fun `seek remoto clampa a cero y duracion conocida`() {
        assertEquals(0L, AndroidAudioPlayer.clampSeekPositionMs(-5.0, durationMs = 180_000L))
        assertEquals(42_500L, AndroidAudioPlayer.clampSeekPositionMs(42.5, durationMs = 180_000L))
        assertEquals(180_000L, AndroidAudioPlayer.clampSeekPositionMs(250.0, durationMs = 180_000L))
        assertEquals(15_000L, AndroidAudioPlayer.clampSeekPositionMs(15.0, durationMs = 0L))
    }
}
