package ar.carpincho.rockola

import android.os.Build
import android.view.HapticFeedbackConstants

/**
 * Mapeo semántico de acciones de UI a constantes nativas de `HapticFeedbackConstants`
 * respetando la configuración del sistema operativo y el nivel de API.
 */
internal object HapticPolicy {
    fun normalizeKind(kind: String?, heavy: Boolean): String {
        val cleaned = kind?.trim()?.lowercase().orEmpty()
        if (cleaned.isNotEmpty()) return cleaned
        return if (heavy) "long_press" else "tap"
    }

    fun resolveConstant(kind: String, sdkInt: Int = Build.VERSION.SDK_INT): Int {
        return when (kind.trim().lowercase()) {
            "long_press" -> HapticFeedbackConstants.LONG_PRESS
            "confirm" -> {
                if (sdkInt >= Build.VERSION_CODES.R) {
                    HapticFeedbackConstants.CONFIRM
                } else {
                    HapticFeedbackConstants.VIRTUAL_KEY
                }
            }
            "reject" -> {
                if (sdkInt >= Build.VERSION_CODES.R) {
                    HapticFeedbackConstants.REJECT
                } else {
                    HapticFeedbackConstants.LONG_PRESS
                }
            }
            "gesture_start" -> {
                if (sdkInt >= Build.VERSION_CODES.R) {
                    HapticFeedbackConstants.GESTURE_START
                } else {
                    HapticFeedbackConstants.VIRTUAL_KEY
                }
            }
            "gesture_end" -> {
                if (sdkInt >= Build.VERSION_CODES.R) {
                    HapticFeedbackConstants.GESTURE_END
                } else {
                    HapticFeedbackConstants.VIRTUAL_KEY
                }
            }
            "toggle_on" -> {
                if (sdkInt >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    HapticFeedbackConstants.TOGGLE_ON
                } else {
                    HapticFeedbackConstants.VIRTUAL_KEY
                }
            }
            "toggle_off" -> {
                if (sdkInt >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    HapticFeedbackConstants.TOGGLE_OFF
                } else {
                    HapticFeedbackConstants.VIRTUAL_KEY
                }
            }
            "tick" -> {
                if (sdkInt >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    HapticFeedbackConstants.SEGMENT_TICK
                } else {
                    HapticFeedbackConstants.CLOCK_TICK
                }
            }
            else -> HapticFeedbackConstants.VIRTUAL_KEY
        }
    }
}
