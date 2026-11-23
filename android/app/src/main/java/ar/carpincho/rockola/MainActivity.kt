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
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.util.Rational
import androidx.activity.BackEventCompat
import androidx.activity.OnBackPressedCallback
import androidx.annotation.RequiresApi
import androidx.appcompat.app.AlertDialog
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.webkit.WebViewCompat
import com.getcapacitor.BridgeActivity
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.roundToInt

/**
 * Política de retención del splash nativo hasta el primer frame útil de Vue.
 */
internal object SplashHoldPolicy {
    const val MAX_HOLD_MS = 2500L

    fun shouldKeepOnScreen(uiReady: Boolean, elapsedMs: Long, maxHoldMs: Long = MAX_HOLD_MS): Boolean {
        if (uiReady) return false
        return elapsedMs < maxHoldMs
    }
}

/**
 * Política de atrás predictivo: el callback nativo solo se habilita si JS tiene capas cerrables.
 */
internal object BackNavigationPolicy {
    fun shouldEnableCallback(hasClosableLayer: Boolean): Boolean = hasClosableLayer
}

/**
 * Reglas puras de ciclo de vida y accesos directos de MainActivity (testeables en JVM).
 */
internal object MainActivityPolicy {
    fun isSupportedShortcutAction(action: String?): Boolean {
        return action == MainActivity.ACTION_OPEN_FOGON ||
            action == MainActivity.ACTION_OPEN_LIBRARY ||
            action == MainActivity.ACTION_OPEN_QUEUE ||
            action == MainActivity.ACTION_OPEN_TOPS
    }

    fun shouldHandleShortcutOnCreate(hasSavedInstanceState: Boolean, action: String?): Boolean {
        return !hasSavedInstanceState && isSupportedShortcutAction(action)
    }
}

/**
 * Actividad principal de Capacitor. Registra el plugin RockolaServer,
 * configura barras edge-to-edge transparentes con íconos claros,
 * gestiona PiP con confirmación real del sistema operativo y delega navegación atrás y shortcuts a Vue.
 */
class MainActivity : BridgeActivity() {

    companion object {
        private const val REQ_POST_NOTIFICATIONS = 1001
        private const val STATE_PENDING_SHORTCUT = "rockola_pending_shortcut"
        private const val REQ_PIP_PREV = 201
        private const val REQ_PIP_PLAY_PAUSE = 202
        private const val REQ_PIP_NEXT = 203
        private const val STATE_FOGON_ACTIVE = "rockola_fogon_active"
        const val ACTION_OPEN_FOGON = "ar.carpincho.rockola.ACTION_OPEN_FOGON"
        const val ACTION_OPEN_LIBRARY = "ar.carpincho.rockola.ACTION_OPEN_LIBRARY"
        const val ACTION_OPEN_QUEUE = "ar.carpincho.rockola.ACTION_OPEN_QUEUE"
        const val ACTION_OPEN_TOPS = "ar.carpincho.rockola.ACTION_OPEN_TOPS"

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
        if (isFinishing || isDestroyed) return
        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread
            try {
                setPictureInPictureParams(buildPipParams(autoEnter = isFogonActive))
            } catch (_: Exception) {
                // Algunos fabricantes bloquean setPictureInPictureParams en estados transitorios
            }
        }
    }

    fun enterPipIfSupported(onResult: (entered: Boolean, reason: String?) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            onResult(false, "ANDROID_VERSION_UNSUPPORTED")
            return
        }
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)) {
            onResult(false, "PIP_FEATURE_UNAVAILABLE")
            return
        }
        if (isFinishing || isDestroyed) {
            onResult(false, "ACTIVITY_FINISHING")
            return
        }
        runOnUiThread {
            if (isFinishing || isDestroyed) {
                onResult(false, "ACTIVITY_FINISHING")
                return@runOnUiThread
            }
            if (isInPictureInPictureMode) {
                onResult(true, null)
                return@runOnUiThread
            }
            try {
                val params = buildPipParams(autoEnter = isFogonActive)
                val entered = enterPictureInPictureMode(params)
                onResult(entered, if (entered) null else "PIP_DENIED")
            } catch (e: Exception) {
                onResult(false, e.message ?: "PIP_FAILED")
            }
        }
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
        val isPlaying = RockolaForegroundService.isMediaPlaying
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

    private var notificationPermissionRequested = false
    private var pendingNotificationPermissionCallback: ((Boolean) -> Unit)? = null
    private val uiReady = AtomicBoolean(false)
    private var splashStartedAtMs: Long = 0L
    private var backCallback: OnBackPressedCallback? = null
    private var lastImeBottomCssPx: Int = -1

    fun markUiReady() {
        uiReady.set(true)
    }

    fun setBackHandlerEnabled(enabled: Boolean) {
        val shouldEnable = BackNavigationPolicy.shouldEnableCallback(enabled)
        runOnUiThread {
            backCallback?.isEnabled = shouldEnable
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        splashStartedAtMs = SystemClock.elapsedRealtime()
        val splashScreen = installSplashScreen()
        splashScreen.setKeepOnScreenCondition {
            SplashHoldPolicy.shouldKeepOnScreen(
                uiReady = uiReady.get(),
                elapsedMs = SystemClock.elapsedRealtime() - splashStartedAtMs,
            )
        }
        registerPlugin(RockolaServerPlugin::class.java)
        isFogonActive = savedInstanceState?.getBoolean(STATE_FOGON_ACTIVE, false) ?: false
        if (savedInstanceState != null) {
            pendingShortcutAction = savedInstanceState.getString(STATE_PENDING_SHORTCUT)
        }
        super.onCreate(savedInstanceState)

        applyHeadbarSystemBars()
        registerImeInsetsObserver()
        registerBackNavigationHandler()
        bridge?.webView?.apply {
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.rockola_bg))
            settings.mediaPlaybackRequiresUserGesture = false
        }
        if (MainActivityPolicy.shouldHandleShortcutOnCreate(savedInstanceState != null, intent?.action)) {
            handleShortcutIntent(intent)
        }
        checkWebViewCompatibility()
    }

    private fun checkWebViewCompatibility() {
        val webViewPkg = try {
            WebViewCompat.getCurrentWebViewPackage(this)
        } catch (_: Exception) {
            null
        }
        val versionName = webViewPkg?.versionName
        if (!WebViewVersionPolicy.isSupported(versionName)) {
            markUiReady()
            val pkgId = webViewPkg?.packageName ?: "com.google.android.webview"
            AlertDialog.Builder(this)
                .setTitle("Actualizá Android System WebView")
                .setMessage(
                    "Tu versión de WebView (${versionName ?: "antigua"}) es muy vieja para mostrar La Rockola correctamente. " +
                        "Actualizala desde la tienda para evitar fallas visuales.",
                )
                .setPositiveButton("Actualizar en la tienda") { _, _ ->
                    openWebViewStore(pkgId)
                }
                .setNegativeButton("Seguir igual", null)
                .show()
        }
    }

    private fun openWebViewStore(packageName: String) {
        val marketIntent = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$packageName"))
        val webIntent = Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$packageName"))
        try {
            startActivity(marketIntent)
        } catch (_: Exception) {
            try {
                startActivity(webIntent)
            } catch (_: Exception) {
                // Sin tienda o navegador disponible
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean(STATE_FOGON_ACTIVE, isFogonActive)
        outState.putString(STATE_PENDING_SHORTCUT, pendingShortcutAction)
        super.onSaveInstanceState(outState)
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
        val inPip = Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && isInPictureInPictureMode
        evaluateJsSafely("window.__rockolaSetPipMode && window.__rockolaSetPipMode($inPip)")
    }

    override fun onPause() {
        super.onPause()
        val inPip = Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && isInPictureInPictureMode
        if (RockolaForegroundService.isMediaPlaying || inPip) {
            bridge?.webView?.resumeTimers()
        }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (Build.VERSION.SDK_INT in Build.VERSION_CODES.O until Build.VERSION_CODES.S &&
            isFogonActive &&
            !isInPictureInPictureMode
        ) {
            enterPipIfSupported { _, _ -> }
        }
    }

    override fun onPictureInPictureModeChanged(
        isInPictureInPictureMode: Boolean,
        newConfig: Configuration,
    ) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        evaluateJsSafely("window.__rockolaSetPipMode && window.__rockolaSetPipMode($isInPictureInPictureMode)")
    }

    private fun registerBackNavigationHandler() {
        val callback = object : OnBackPressedCallback(false) {
            override fun handleOnBackProgressed(backEvent: BackEventCompat) {
                val p = backEvent.progress.coerceIn(0f, 1f)
                evaluateJsSafely("window.__rockolaOnBackProgress && window.__rockolaOnBackProgress($p)")
            }

            override fun handleOnBackCancelled() {
                evaluateJsSafely("window.__rockolaOnBackProgress && window.__rockolaOnBackProgress(0)")
            }

            override fun handleOnBackPressed() {
                evaluateJsSafely("window.__rockolaOnBackProgress && window.__rockolaOnBackProgress(0)")
                val webView = bridge?.webView
                if (webView == null) {
                    isEnabled = false
                    moveTaskToBack(true)
                    return
                }
                webView.evaluateJavascript("Boolean(window.__rockolaHandleBack && window.__rockolaHandleBack())") { res ->
                    if (res != "true") {
                        isEnabled = false
                        moveTaskToBack(true)
                    }
                }
            }
        }
        backCallback = callback
        onBackPressedDispatcher.addCallback(this, callback)
    }

    private fun registerImeInsetsObserver() {
        ViewCompat.setOnApplyWindowInsetsListener(window.decorView) { view, insets ->
            val imeBottomPx = insets.getInsets(WindowInsetsCompat.Type.ime()).bottom
            val density = resources.displayMetrics.density.coerceAtLeast(1f)
            val imeCssPx = (imeBottomPx / density).roundToInt().coerceAtLeast(0)
            if (imeCssPx != lastImeBottomCssPx) {
                lastImeBottomCssPx = imeCssPx
                evaluateJsSafely("window.__rockolaSetImeInsets && window.__rockolaSetImeInsets($imeCssPx)")
            }
            ViewCompat.onApplyWindowInsets(view, insets)
        }
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

    internal fun requestNotificationPermissionWithResult(onResult: (Boolean) -> Unit) {
        if (isFinishing || isDestroyed) {
            onResult(false)
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            onResult(true)
            return
        }
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) {
            onResult(true)
            return
        }
        notificationPermissionRequested = true
        pendingNotificationPermissionCallback = onResult
        getSharedPreferences(RockolaForegroundService.PREFS_NAME, MODE_PRIVATE)
            .edit()
            .putBoolean("notif_permission_asked", true)
            .apply()
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQ_POST_NOTIFICATIONS,
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_POST_NOTIFICATIONS) {
            val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
            val cb = pendingNotificationPermissionCallback
            pendingNotificationPermissionCallback = null
            cb?.invoke(granted)
        }
    }

    private fun evaluateJsSafely(script: String, callback: ((String?) -> Unit)? = null) {
        if (isFinishing || isDestroyed) return
        val webView = bridge?.webView ?: return
        webView.post {
            if (isFinishing || isDestroyed) return@post
            bridge?.webView?.evaluateJavascript(script, callback)
        }
    }

    private fun handleShortcutIntent(intent: Intent?) {
        val action = intent?.action ?: return
        val jsHook = when (action) {
            ACTION_OPEN_FOGON -> "__rockolaOpenFogon"
            ACTION_OPEN_LIBRARY -> "__rockolaOpenLibrary"
            ACTION_OPEN_QUEUE -> "__rockolaOpenQueue"
            ACTION_OPEN_TOPS -> "__rockolaOpenTops"
            else -> return
        }
        pendingShortcutAction = action
        evaluateJsSafely(
            "(function(){ if (typeof window.$jsHook === 'function') { window.$jsHook(); return 'ok'; } return 'pending'; })()",
        ) { result ->
            if (result == "\"ok\"") {
                pendingShortcutAction = null
            }
        }
    }
}
