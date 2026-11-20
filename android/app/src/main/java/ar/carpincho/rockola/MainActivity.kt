package ar.carpincho.rockola

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
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

        bridge?.webView?.settings?.mediaPlaybackRequiresUserGesture = false
        requestNotificationPermissionIfNeeded()
        ensureServerAutoStarted()
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
