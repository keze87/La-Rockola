package ar.carpincho.rockola

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import androidx.activity.OnBackPressedCallback
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.getcapacitor.BridgeActivity

/**
 * Actividad principal de Capacitor. Registra el plugin RockolaServer,
 * configura barras edge-to-edge transparentes con íconos claros,
 * arranca automáticamente el servidor embebido, delega navegación atrás y shortcuts a Vue
 * y mantiene activos los timers del WebView solo mientras suena música.
 */
class MainActivity : BridgeActivity() {

    companion object {
        private const val REQ_POST_NOTIFICATIONS = 1001
        const val ACTION_OPEN_FOGON = "ar.carpincho.rockola.ACTION_OPEN_FOGON"
        const val ACTION_OPEN_QUEUE = "ar.carpincho.rockola.ACTION_OPEN_QUEUE"

        @Volatile
        private var pendingShortcutAction: String? = null

        fun consumePendingShortcutAction(): String? {
            val action = pendingShortcutAction
            pendingShortcutAction = null
            return action
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        registerPlugin(RockolaServerPlugin::class.java)
        super.onCreate(savedInstanceState)

        applyHeadbarSystemBars()
        registerBackNavigationHandler()
        bridge?.webView?.settings?.mediaPlaybackRequiresUserGesture = false
        requestNotificationPermissionIfNeeded()
        ensureServerAutoStarted()
        handleShortcutIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleShortcutIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        applyHeadbarSystemBars()
        bridge?.webView?.settings?.mediaPlaybackRequiresUserGesture = false
    }

    override fun onPause() {
        super.onPause()
        if (RockolaForegroundService.isActivelyPlaying) {
            bridge?.webView?.resumeTimers()
        }
    }

    private fun registerBackNavigationHandler() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val webView = bridge?.webView
                if (webView == null) {
                    moveTaskToBack(true)
                    return
                }
                webView.evaluateJavascript("Boolean(window.__rockolaHandleBack && window.__rockolaHandleBack())") { res ->
                    if (res != "true") {
                        moveTaskToBack(true)
                    }
                }
            }
        })
    }

    private fun applyHeadbarSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        @Suppress("DEPRECATION")
        window.apply {
            statusBarColor = Color.TRANSPARENT
            navigationBarColor = Color.TRANSPARENT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                isStatusBarContrastEnforced = false
                isNavigationBarContrastEnforced = false
            }
        }
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    REQ_POST_NOTIFICATIONS
                )
            }
        }
    }

    private fun handleShortcutIntent(intent: Intent?) {
        val action = intent?.action ?: return
        val jsHook = when (action) {
            ACTION_OPEN_FOGON -> "__rockolaOpenFogon"
            ACTION_OPEN_QUEUE -> "__rockolaOpenQueue"
            else -> return
        }
        pendingShortcutAction = action
        val webView = bridge?.webView ?: return
        webView.post {
            webView.evaluateJavascript(
                "(function(){ if (typeof window.$jsHook === 'function') { window.$jsHook(); return 'ok'; } return 'pending'; })()",
            ) { result ->
                if (result == "\"ok\"") {
                    pendingShortcutAction = null
                }
            }
        }
    }

    private fun ensureServerAutoStarted() {
        if (!RockolaForegroundService.isRunning) {
            val intent = Intent(this, RockolaForegroundService::class.java).apply {
                action = RockolaForegroundService.ACTION_START
            }
            ContextCompat.startForegroundService(this, intent)
        }
    }
}
