package ar.carpincho.rockola

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MainActivityPolicyTest {
    @Test
    fun `solo procesa intents de acceso directo en creacion inicial y no tras recreacion`() {
        assertTrue(
            MainActivityPolicy.shouldHandleShortcutOnCreate(
                hasSavedInstanceState = false,
                action = MainActivity.ACTION_OPEN_FOGON,
            ),
        )
        assertTrue(
            MainActivityPolicy.shouldHandleShortcutOnCreate(
                hasSavedInstanceState = false,
                action = MainActivity.ACTION_OPEN_QUEUE,
            ),
        )
        assertFalse(
            MainActivityPolicy.shouldHandleShortcutOnCreate(
                hasSavedInstanceState = true,
                action = MainActivity.ACTION_OPEN_FOGON,
            ),
        )
        assertFalse(
            MainActivityPolicy.shouldHandleShortcutOnCreate(
                hasSavedInstanceState = false,
                action = "android.intent.action.MAIN",
            ),
        )
    }

    @Test
    fun `splash nativo espera a que la UI este lista hasta el tope de seguridad`() {
        org.junit.Assert.assertEquals(1200L, SplashHoldPolicy.MAX_HOLD_MS)
        assertTrue(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 0L))
        assertTrue(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 1199L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 1200L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 2500L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = true, elapsedMs = 200L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = true, elapsedMs = 0L))
    }

    @Test
    fun `progreso de extraccion calcula porcentaje seguro`() {
        org.junit.Assert.assertEquals(0, BootProgressPolicy.computeExtractPercent(0, 0))
        org.junit.Assert.assertEquals(50, BootProgressPolicy.computeExtractPercent(5, 10))
        org.junit.Assert.assertEquals(100, BootProgressPolicy.computeExtractPercent(15, 10))
    }

    @Test
    fun `callback nativo de back solo se habilita cuando hay una capa cerrable`() {
        assertFalse(BackNavigationPolicy.shouldEnableCallback(false))
        assertTrue(BackNavigationPolicy.shouldEnableCallback(true))
    }

    @Test
    fun `accesos directos dinamicos incluyen los 4 base y suman Reanudar lo ultimo cuando hay tema`() {
        assertTrue(MainActivityPolicy.isSupportedShortcutAction(MainActivity.ACTION_RESUME_LAST))

        val withoutLast = ShortcutPolicy.buildSpecs(lastTrackTitle = null)
        org.junit.Assert.assertEquals(4, withoutLast.size)

        val withLast = ShortcutPolicy.buildSpecs(lastTrackTitle = "El Viejo - Pappo")
        org.junit.Assert.assertEquals(5, withLast.size)
        org.junit.Assert.assertEquals("resume_last", withLast.first().id)
        org.junit.Assert.assertEquals(R.drawable.ic_shortcut_resume, withLast.first().iconRes)
        org.junit.Assert.assertTrue(withLast.first().longLabel.contains("El Viejo"))
    }

    @Test
    fun `politica de zoom de texto de WebView acota fontScale al rango seguro`() {
        org.junit.Assert.assertEquals(100, WebViewDisplayPolicy.computeTextZoom(1.0f))
        org.junit.Assert.assertEquals(90, WebViewDisplayPolicy.computeTextZoom(0.7f))
        org.junit.Assert.assertEquals(110, WebViewDisplayPolicy.computeTextZoom(1.1f))
        org.junit.Assert.assertEquals(115, WebViewDisplayPolicy.computeTextZoom(1.3f))
        org.junit.Assert.assertEquals(115, WebViewDisplayPolicy.computeTextZoom(1.6f))
        org.junit.Assert.assertEquals(100, WebViewDisplayPolicy.computeTextZoom(Float.NaN))
        org.junit.Assert.assertEquals(100, WebViewDisplayPolicy.computeTextZoom(0f))
        org.junit.Assert.assertEquals(100, WebViewDisplayPolicy.computeTextZoom(-1f))
    }

    @Test
    fun `throttler de progreso back omite micro variaciones pero siempre emite fin o salto`() {
        val throttler = BackProgressThrottler(minDelta = 0.02f, minIntervalMs = 16L)

        // Primera emisión pasa siempre
        assertTrue(throttler.shouldEmit(0.05f, nowMs = 100L))
        // Delta < 0.02 y tiempo < 16ms -> bloqueado
        assertFalse(throttler.shouldEmit(0.06f, nowMs = 108L))
        // Tiempo >= 16ms aunque delta chico -> emite
        assertTrue(throttler.shouldEmit(0.065f, nowMs = 120L))
        // Delta >= 0.02 inmediato -> emite
        assertTrue(throttler.shouldEmit(0.10f, nowMs = 122L))
        // Vuelta a 0f (cancelación / fin) siempre emite aunque sea inmediato
        assertTrue(throttler.shouldEmit(0f, nowMs = 123L))
    }
}
