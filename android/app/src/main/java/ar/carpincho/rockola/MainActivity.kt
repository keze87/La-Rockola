package ar.carpincho.rockola

import android.Manifest
import android.app.PendingIntent
import android.app.PictureInPictureParams
import android.app.RemoteAction
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.drawable.Icon
import android.os.Build
import android.os.Bundle
import android.util.Rational
import androidx.activity.OnBackPressedCallback
import androidx.annotation.RequiresApi
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
        private const val REQ_PIP_PREV = 201
        private const val REQ_PIP_PLAY_PAUSE = 202
        private const val REQ_PIP_NEXT = 203
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

    @Volatile
    var isFogonActive: Boolean = false
        private set

    fun setFogonActive(active: Boolean) {
        isFogonActive = active
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            refreshPipParams()
        }
    }

    fun refreshPipParams() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)) return
        runOnUiThread {
            try {
                setPictureInPictureParams(buildPipParams(autoEnter = isFogonActive))
            } catch (_: Exception) {
                // Algunos fabricantes bloquean setPictureInPictureParams en estados transitorios
            }
        }
    }

    fun enterPipIfSupported(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return false
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)) return false
        val params = buildPipParams(autoEnter = isFogonActive)
        runOnUiThread {
            try {
                enterPictureInPictureMode(params)
            } catch (_: Exception) {
                // Ignoramos si la actividad no está en primer plano para entrar a PiP
            }
        }
        return true
    }

    @RequiresApi(Build.VERSION_CODES.O)
    private fun buildPipParams(autoEnter: Boolean): PictureInPictureParams {
        val builder = PictureInPictureParams.Builder()
            .setAspectRatio(Rational(1, 1))
            .setActions(buildPipActions())
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            builder.setAutoEnterEnabled(autoEnter)
            builder.setSeamlessResizeEnabled(true)
        }
        return builder.build()
    }

    @RequiresApi(Build.VERSION_CODES.O)
    private fun buildPipActions(): List<RemoteAction> {
        val isPlaying = RockolaForegroundService.isActivelyPlaying
        val playPauseIconRes = if (isPlaying) {
            android.R.drawable.ic_media_pause
        } else {
            android.R.drawable.ic_media_play
        }
        val playPauseLabel = if (isPlaying) "Pausar" else "Reproducir"

        return listOf(
            createPipAction(
                iconRes = android.R.drawable.ic_media_previous,
                title = "Anterior",
                serviceAction = RockolaForegroundService.ACTION_MEDIA_PREV,
                requestCode = REQ_PIP_PREV,
            ),
            createPipAction(
                iconRes = playPauseIconRes,
                title = playPauseLabel,
                serviceAction = RockolaForegroundService.ACTION_MEDIA_PLAY_PAUSE,
                requestCode = REQ_PIP_PLAY_PAUSE,
            ),
            createPipAction(
                iconRes = android.R.drawable.ic_media_next,
                title = "Siguiente",
                serviceAction = RockolaForegroundService.ACTION_MEDIA_NEXT,
                requestCode = REQ_PIP_NEXT,
            ),
        )
    }

    @RequiresApi(Build.VERSION_CODES.O)
    private fun createPipAction(
        iconRes: Int,
        title: String,
        serviceAction: String,
        requestCode: Int,
    ): RemoteAction {
        val intent = Intent(this, RockolaForegroundService::class.java).apply {
            action = serviceAction
        }
        val pendingIntent = PendingIntent.getService(
            this,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return RemoteAction(Icon.createWithResource(this, iconRes), title, title, pendingIntent)
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
        val inPip = Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && isInPictureInPictureMode
        if (RockolaForegroundService.isActivelyPlaying || inPip) {
            bridge?.webView?.resumeTimers()
        }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (Build.VERSION.SDK_INT in Build.VERSION_CODES.O until Build.VERSION_CODES.S &&
            isFogonActive &&
            !isInPictureInPictureMode
        ) {
            enterPipIfSupported()
        }
    }

    override fun onPictureInPictureModeChanged(
        isInPictureInPictureMode: Boolean,
        newConfig: Configuration,
    ) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        bridge?.webView?.post {
            bridge?.webView?.evaluateJavascript(
                "window.__rockolaSetPipMode && window.__rockolaSetPipMode($isInPictureInPictureMode)",
                null,
            )
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
            startService(intent)
        }
    }
}
