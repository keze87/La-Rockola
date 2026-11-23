package ar.carpincho.rockola

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WebViewVersionPolicyTest {
    @Test
    fun `parseMajorVersion extrae el numero mayor correctamente`() {
        assertEquals(120, WebViewVersionPolicy.parseMajorVersion("120.0.6099.144"))
        assertEquals(108, WebViewVersionPolicy.parseMajorVersion("108.0.5359.128"))
        assertEquals(83, WebViewVersionPolicy.parseMajorVersion("83.0.4103.106"))
        assertNull(WebViewVersionPolicy.parseMajorVersion(null))
        assertNull(WebViewVersionPolicy.parseMajorVersion(""))
        assertNull(WebViewVersionPolicy.parseMajorVersion("desconocido"))
    }

    @Test
    fun `isSupported exige Chromium 108 o superior cuando la version es legible`() {
        assertFalse(WebViewVersionPolicy.isSupported("83.0.4103.106"))
        assertFalse(WebViewVersionPolicy.isSupported("107.0.5304.141"))
        assertTrue(WebViewVersionPolicy.isSupported("108.0.0.0"))
        assertTrue(WebViewVersionPolicy.isSupported("131.0.6778.135"))
        // Fail-open si el proveedor no reporta cadena de versión
        assertTrue(WebViewVersionPolicy.isSupported(null))
        assertTrue(WebViewVersionPolicy.isSupported(""))
    }
}
