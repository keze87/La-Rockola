package ar.carpincho.rockola

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import com.getcapacitor.BridgeActivity

/**
 * Actividad principal de Capacitor. Registra el plugin RockolaServer,
 * arranca automáticamente el servidor embebido al iniciar la app y
 * mantiene activos los timers del WebView para audio en segundo plano.
 */
class MainActivity : BridgeActivity() {

    companion object {
        private const val REQ_POST_NOTIFICATIONS = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(RockolaServerPlugin::class.java)
        super.onCreate(savedInstanceState)

        applyHeadbarSystemBars()
        bridge?.webView?.settings?.mediaPlaybackRequiresUserGesture = false
        requestNotificationPermissionIfNeeded()
        ensureServerAutoStarted()
    }

    private fun applyHeadbarSystemBars() {
        val headbarColor = Color.parseColor("#1F1A17")
        @Suppress("DEPRECATION")
        window.apply {
            addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
            statusBarColor = headbarColor
            navigationBarColor = headbarColor
        }
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
        }
    }

    override fun onResume() {
        super.onResume()
        bridge?.webView?.settings?.mediaPlaybackRequiresUserGesture = false
    }

    override fun onPause() {
        super.onPause()
        if (RockolaForegroundService.isRunning) {
            bridge?.webView?.resumeTimers()
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

    private fun ensureServerAutoStarted() {
        if (!RockolaForegroundService.isRunning) {
            val intent = Intent(this, RockolaForegroundService::class.java).apply {
                action = RockolaForegroundService.ACTION_START
            }
            ContextCompat.startForegroundService(this, intent)
        }
    }
}
