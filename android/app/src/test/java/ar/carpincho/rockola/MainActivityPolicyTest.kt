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
        org.junit.Assert.assertTrue(withLast.first().longLabel.contains("El Viejo"))
    }
}
