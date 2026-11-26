package ar.carpincho.rockola

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RockolaServerPluginPolicyTest {
    @Test
    fun `VolumeChangeTracker solo notifica cuando cambia nivel o estado de mute`() {
        val tracker = VolumeChangeTracker()

        // Primer seed inicializa sin disparar cambio espurio en rechequeos iguales
        tracker.seed(level = 60, muted = false)
        assertFalse(tracker.updateIfChanged(level = 60, muted = false))
        assertFalse(tracker.updateIfChanged(level = 60, muted = false))

        // Cambio en el nivel dispara notificación una sola vez
        assertTrue(tracker.updateIfChanged(level = 65, muted = false))
        assertFalse(tracker.updateIfChanged(level = 65, muted = false))

        // Cambio en mute con mismo nivel también dispara notificación
        assertTrue(tracker.updateIfChanged(level = 65, muted = true))
        assertFalse(tracker.updateIfChanged(level = 65, muted = true))

        // Si se consulta sin seed previo, el primer updateIfChanged sí registra el estado inicial
        val unseeded = VolumeChangeTracker()
        assertTrue(unseeded.updateIfChanged(level = 40, muted = false))
        assertFalse(unseeded.updateIfChanged(level = 40, muted = false))
    }
}
