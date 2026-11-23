package ar.carpincho.rockola

import android.os.Build
import android.view.HapticFeedbackConstants
import org.junit.Assert.assertEquals
import org.junit.Test

class HapticPolicyTest {
    @Test
    fun `resolveConstant mapea acciones semanticas segun nivel de API con fallbacks`() {
        assertEquals(HapticFeedbackConstants.VIRTUAL_KEY, HapticPolicy.resolveConstant("tap", Build.VERSION_CODES.N))
        assertEquals(HapticFeedbackConstants.LONG_PRESS, HapticPolicy.resolveConstant("long_press", Build.VERSION_CODES.N))

        // CONFIRM y REJECT en API 30+ vs fallback en API 24
        assertEquals(HapticFeedbackConstants.CONFIRM, HapticPolicy.resolveConstant("confirm", Build.VERSION_CODES.R))
        assertEquals(HapticFeedbackConstants.VIRTUAL_KEY, HapticPolicy.resolveConstant("confirm", Build.VERSION_CODES.N))
        assertEquals(HapticFeedbackConstants.REJECT, HapticPolicy.resolveConstant("reject", Build.VERSION_CODES.R))
        assertEquals(HapticFeedbackConstants.LONG_PRESS, HapticPolicy.resolveConstant("reject", Build.VERSION_CODES.N))

        // GESTURE_START / END en API 30+ vs fallback
        assertEquals(HapticFeedbackConstants.GESTURE_START, HapticPolicy.resolveConstant("gesture_start", Build.VERSION_CODES.R))
        assertEquals(HapticFeedbackConstants.GESTURE_END, HapticPolicy.resolveConstant("gesture_end", Build.VERSION_CODES.R))

        // TOGGLE_ON / TOGGLE_OFF / SEGMENT_TICK en API 34+ vs fallback
        assertEquals(HapticFeedbackConstants.TOGGLE_ON, HapticPolicy.resolveConstant("toggle_on", Build.VERSION_CODES.UPSIDE_DOWN_CAKE))
        assertEquals(HapticFeedbackConstants.TOGGLE_OFF, HapticPolicy.resolveConstant("toggle_off", Build.VERSION_CODES.UPSIDE_DOWN_CAKE))
        assertEquals(HapticFeedbackConstants.SEGMENT_TICK, HapticPolicy.resolveConstant("tick", Build.VERSION_CODES.UPSIDE_DOWN_CAKE))
        assertEquals(HapticFeedbackConstants.CLOCK_TICK, HapticPolicy.resolveConstant("tick", Build.VERSION_CODES.R))
    }

    @Test
    fun `resolveKind mantiene compatibilidad con heavy boolean cuando no se envia kind`() {
        assertEquals("long_press", HapticPolicy.normalizeKind(kind = null, heavy = true))
        assertEquals("tap", HapticPolicy.normalizeKind(kind = null, heavy = false))
        assertEquals("confirm", HapticPolicy.normalizeKind(kind = "confirm", heavy = false))
    }
}
