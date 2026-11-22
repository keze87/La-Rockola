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
}
