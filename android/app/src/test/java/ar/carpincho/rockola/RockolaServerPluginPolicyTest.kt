package ar.carpincho.rockola

import com.getcapacitor.JSObject
import org.junit.Assert.assertEquals
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

    @Test
    fun `NativeEventBuffer clasifica eventos de estado vs eventos buffereados y drena en orden FIFO acotado`() {
        assertTrue(NativeEventBuffer.isBufferedEvent("nativeCommandError"))
        assertTrue(NativeEventBuffer.isBufferedEvent("shortcutAction"))
        assertFalse(NativeEventBuffer.isBufferedEvent("mediaVolumeChanged"))
        assertFalse(NativeEventBuffer.isBufferedEvent("pipModeChanged"))
        assertFalse(NativeEventBuffer.isBufferedEvent("imeInsetsChanged"))
        assertFalse(NativeEventBuffer.isBufferedEvent("backProgress"))

        val buffer = NativeEventBuffer(maxPerEvent = 2)
        // Eventos de estado no se bufferean
        assertFalse(buffer.enqueue("mediaVolumeChanged", JSObject().put("level", 50)))

        // Eventos de error/acción se bufferean con tope descartando los más viejos
        assertTrue(buffer.enqueue("nativeCommandError", JSObject().put("cmd", "play").put("seq", 1)))
        assertTrue(buffer.enqueue("nativeCommandError", JSObject().put("cmd", "skip").put("seq", 2)))
        assertTrue(buffer.enqueue("nativeCommandError", JSObject().put("cmd", "prev").put("seq", 3)))

        val drained = buffer.drain("nativeCommandError")
        assertEquals(2, drained.size)
        assertEquals("skip", drained[0].getString("cmd"))
        assertEquals("prev", drained[1].getString("cmd"))

        // Segundo drain queda vacío
        assertTrue(buffer.drain("nativeCommandError").isEmpty())
    }
}
