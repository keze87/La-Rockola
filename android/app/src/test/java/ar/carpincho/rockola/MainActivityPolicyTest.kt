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
        assertTrue(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 0L))
        assertTrue(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 2499L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 2500L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = false, elapsedMs = 4000L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = true, elapsedMs = 200L))
        assertFalse(SplashHoldPolicy.shouldKeepOnScreen(uiReady = true, elapsedMs = 0L))
    }

    @Test
    fun `progreso de extraccion calcula porcentaje seguro`() {
        org.junit.Assert.assertEquals(0, BootProgressPolicy.computeExtractPercent(0, 0))
        org.junit.Assert.assertEquals(50, BootProgressPolicy.computeExtractPercent(5, 10))
        org.junit.Assert.assertEquals(100, BootProgressPolicy.computeExtractPercent(15, 10))
    }
}
