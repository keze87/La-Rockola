package ar.carpincho.rockola

import android.app.ApplicationExitInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class LocalCrashDiagnosticsTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun `appendBoundedLog persiste errores y respeta limite de 16 KB conservando el ultimo`() {
        val logFile = File(tempFolder.root, "rockola_last_error.log")
        val maxBytes = 1024

        repeat(40) { idx ->
            LocalCrashDiagnostics.appendBoundedLog(
                logFile,
                "[2026-11-25T00:00:${idx.toString().padStart(2, '0')}Z] [python] Error de prueba numero $idx con detalle extra para llenar buffer",
                maxBytes = maxBytes,
            )
        }

        assertTrue(logFile.exists())
        assertTrue(logFile.length() <= maxBytes.toLong())
        val content = logFile.readText(Charsets.UTF_8)
        assertTrue(content.contains("Error de prueba numero 39"))
    }

    @Test
    fun `formatExitReason traduce codigos de ApplicationExitInfo a descripciones legibles`() {
        assertEquals("ANR", LocalCrashDiagnostics.formatExitReason(ApplicationExitInfo.REASON_ANR))
        assertEquals("LOW_MEMORY", LocalCrashDiagnostics.formatExitReason(ApplicationExitInfo.REASON_LOW_MEMORY))
        assertEquals("CRASH", LocalCrashDiagnostics.formatExitReason(ApplicationExitInfo.REASON_CRASH))
        assertEquals(
            "EXCESSIVE_RESOURCE_USAGE",
            LocalCrashDiagnostics.formatExitReason(ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE),
        )
        assertEquals("USER_REQUESTED", LocalCrashDiagnostics.formatExitReason(ApplicationExitInfo.REASON_USER_REQUESTED))
        assertTrue(LocalCrashDiagnostics.formatExitReason(9999).contains("9999"))
    }
}
