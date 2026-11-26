package ar.carpincho.rockola

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OnboardingPolicyTest {

    @Test
    fun `muestra onboarding solo en arranque limpio sin carpeta ni servidor remoto`() {
        assertTrue(
            OnboardingPolicy.shouldShowOnboarding(
                savedMusicDir = null,
                savedTargetMode = "host",
                savedRemoteUrl = null,
                onboardingSkipped = false,
                hasShortcutAction = false,
            ),
        )
        assertFalse(
            OnboardingPolicy.shouldShowOnboarding(
                savedMusicDir = "content://com.android.externalstorage.documents/tree/primary%3AMusic",
                savedTargetMode = "host",
                savedRemoteUrl = null,
                onboardingSkipped = false,
                hasShortcutAction = false,
            ),
        )
        assertFalse(
            OnboardingPolicy.shouldShowOnboarding(
                savedMusicDir = null,
                savedTargetMode = "remote",
                savedRemoteUrl = "http://192.168.1.50:1729",
                onboardingSkipped = false,
                hasShortcutAction = false,
            ),
        )
        assertFalse(
            OnboardingPolicy.shouldShowOnboarding(
                savedMusicDir = null,
                savedTargetMode = "host",
                savedRemoteUrl = null,
                onboardingSkipped = true,
                hasShortcutAction = false,
            ),
        )
        assertFalse(
            OnboardingPolicy.shouldShowOnboarding(
                savedMusicDir = null,
                savedTargetMode = "host",
                savedRemoteUrl = null,
                onboardingSkipped = false,
                hasShortcutAction = true,
            ),
        )
    }

    @Test
    fun `normaliza URL remota agregando http y puerto por defecto`() {
        assertEquals("http://192.168.1.50:1729", OnboardingPolicy.normalizeRemoteUrl("192.168.1.50"))
        assertEquals("http://192.168.1.50:8080", OnboardingPolicy.normalizeRemoteUrl("192.168.1.50:8080"))
        assertEquals("http://192.168.1.50:1729", OnboardingPolicy.normalizeRemoteUrl("http://192.168.1.50:1729/"))
        assertEquals("https://rockola.local", OnboardingPolicy.normalizeRemoteUrl("https://rockola.local/"))
        assertNull(OnboardingPolicy.normalizeRemoteUrl(""))
        assertNull(OnboardingPolicy.normalizeRemoteUrl("   "))
        assertNull(OnboardingPolicy.normalizeRemoteUrl("ftp://192.168.1.50"))
    }
}
