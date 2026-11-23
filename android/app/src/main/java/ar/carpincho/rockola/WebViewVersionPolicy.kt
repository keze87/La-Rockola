package ar.carpincho.rockola

/**
 * Política de versión mínima de Android System WebView requerida por el frontend
 * (Chromium 108+ por soporte nativo de `100dvh`, `content-visibility` y `:has()`).
 */
internal object WebViewVersionPolicy {
    const val MIN_CHROMIUM_MAJOR = 108

    fun parseMajorVersion(versionName: String?): Int? {
        val cleaned = versionName?.trim().orEmpty()
        if (cleaned.isEmpty()) return null
        val majorSegment = cleaned.substringBefore('.').takeWhile { it.isDigit() }
        return majorSegment.toIntOrNull()
    }

    fun isSupported(versionName: String?, minMajor: Int = MIN_CHROMIUM_MAJOR): Boolean {
        val major = parseMajorVersion(versionName) ?: return true
        return major >= minMajor
    }
}
