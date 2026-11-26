package ar.carpincho.rockola

import android.Manifest
import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.animation.ValueAnimator
import android.app.PendingIntent
import android.app.PictureInPictureParams
import android.app.RemoteAction
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.drawable.Icon
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.util.Rational
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.webkit.WebView
import androidx.activity.BackEventCompat
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.annotation.RequiresApi
import androidx.appcompat.app.AlertDialog
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.WebViewCompat
import com.getcapacitor.BridgeActivity
import com.getcapacitor.JSObject
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * Política de retención del splash nativo hasta el primer frame útil de Vue.
 */
internal object SplashHoldPolicy {
    const val MAX_HOLD_MS = 1200L

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
 * Política de visualización del WebView para respetar escala de texto accesible sin romper la UI.
 */
internal object WebViewDisplayPolicy {
    const val MIN_TEXT_ZOOM = 90
    const val MAX_TEXT_ZOOM = 115

    fun computeTextZoom(fontScale: Float): Int {
        if (!fontScale.isFinite() || fontScale <= 0f) return 100
        return (fontScale * 100f).roundToInt().coerceIn(MIN_TEXT_ZOOM, MAX_TEXT_ZOOM)
    }
}

/**
 * Filtra micro-variaciones en el gesto atrás predictivo para no saturar el WebView.
 */
internal class BackProgressThrottler(
    private val minDelta: Float = 0.02f,
    private val minIntervalMs: Long = 16L,
) {
    private var lastProgress: Float = -1f
    private var lastEmitMs: Long = -1L

    @Synchronized
    fun shouldEmit(progress: Float, nowMs: Long): Boolean {
        val p = progress.coerceIn(0f, 1f)
        if (lastEmitMs < 0L || p == 0f || p == 1f) {
            lastProgress = p
            lastEmitMs = nowMs
            return true
        }
        val deltaOk = abs(p - lastProgress) >= minDelta
        val timeOk = (nowMs - lastEmitMs) >= minIntervalMs
        if (!deltaOk && !timeOk) return false
        lastProgress = p
        lastEmitMs = nowMs
        return true
    }
}

/**
 * Reglas puras de ciclo de vida y accesos directos de MainActivity (testeables en JVM).
 */
internal object MainActivityPolicy {
    fun isSupportedShortcutAction(action: String?): Boolean {
        return action == MainActivity.ACTION_OPEN_FOGON ||
            action == MainActivity.ACTION_OPEN_LIBRARY ||
            action == MainActivity.ACTION_OPEN_QUEUE ||
            action == MainActivity.ACTION_OPEN_TOPS ||
            action == MainActivity.ACTION_RESUME_LAST
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
        const val ACTION_RESUME_LAST = "ar.carpincho.rockola.ACTION_RESUME_LAST"

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

    fun isCurrentlyInPipMode(): Boolean {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && isInPictureInPictureMode
    }

    val currentImeBottomCssPx: Int
        get() = lastImeBottomCssPx.coerceAtLeast(0)

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
            R.drawable.ic_media_pause
        } else {
            R.drawable.ic_media_play
        }
        val playPauseLabel = if (isPlaying) "Pausar" else "Reproducir"

        return listOf(
            createPipAction(
                iconRes = R.drawable.ic_media_previous,
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
                iconRes = R.drawable.ic_media_next,
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

    private var pendingNotificationPermissionCallback: ((Boolean) -> Unit)? = null
    private val uiReady = AtomicBoolean(false)
    private val splashReleased = AtomicBoolean(false)
    private val fullyDrawnReported = AtomicBoolean(false)
    private var splashStartedAtMs: Long = 0L
    private var backCallback: OnBackPressedCallback? = null
    private val backProgressThrottler = BackProgressThrottler()
    private var lastImeBottomCssPx: Int = -1

    fun markUiReady(jsNowMs: Double? = null) {
        if (uiReady.compareAndSet(false, true)) {
            val activityElapsed = (SystemClock.elapsedRealtime() - splashStartedAtMs).coerceAtLeast(0L)
            val procElapsed = RockolaApplication.elapsedSinceProcessStartMs()
            val jsPart = jsNowMs?.let { " jsNowMs=${it.roundToInt()}" } ?: ""
            android.util.Log.i(
                "RockolaStartup",
                "stage=mark_ui_ready_received activityElapsedMs=$activityElapsed processElapsedMs=$procElapsed$jsPart",
            )
        }
    }

    fun reportFullyDrawnOnce(reason: String = "ui") {
        if (!fullyDrawnReported.compareAndSet(false, true)) return
        val procElapsed = RockolaApplication.elapsedSinceProcessStartMs()
        val activityElapsed = (SystemClock.elapsedRealtime() - splashStartedAtMs).coerceAtLeast(0L)
        android.util.Log.i(
            "RockolaStartup",
            "stage=fully_drawn reason=$reason activityElapsedMs=$activityElapsed processElapsedMs=$procElapsed",
        )
        runOnUiThread {
            if (!isFinishing && !isDestroyed) {
                try {
                    reportFullyDrawn()
                } catch (_: Exception) {
                    // Algunos dispositivos antiguos o estados transitorios rechazan reportFullyDrawn()
                }
            }
        }
    }

    fun setBackHandlerEnabled(enabled: Boolean) {
        val shouldEnable = BackNavigationPolicy.shouldEnableCallback(enabled)
        runOnUiThread {
            backCallback?.isEnabled = shouldEnable
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        splashStartedAtMs = SystemClock.elapsedRealtime()
        android.util.Log.i(
            "RockolaStartup",
            "stage=activity_on_create processElapsedMs=${RockolaApplication.elapsedSinceProcessStartMs()}",
        )
        val splashScreen = installSplashScreen()
        splashScreen.setKeepOnScreenCondition {
            val ready = uiReady.get()
            val activityElapsed = SystemClock.elapsedRealtime() - splashStartedAtMs
            val keep = SplashHoldPolicy.shouldKeepOnScreen(
                uiReady = ready,
                elapsedMs = activityElapsed,
            )
            if (!keep && splashReleased.compareAndSet(false, true)) {
                android.util.Log.i(
                    "RockolaStartup",
                    "stage=splash_released uiReady=$ready activityElapsedMs=$activityElapsed processElapsedMs=${RockolaApplication.elapsedSinceProcessStartMs()}",
                )
            }
            keep
        }
        splashScreen.setOnExitAnimationListener { splashScreenView ->
            if (!ValueAnimator.areAnimatorsEnabled()) {
                splashScreenView.remove()
                return@setOnExitAnimationListener
            }
            val exitAnimator = ObjectAnimator.ofPropertyValuesHolder(
                splashScreenView.view,
                PropertyValuesHolder.ofFloat(View.ALPHA, 1f, 0f),
                PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.05f),
                PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.05f),
            ).apply {
                duration = 180L
                interpolator = DecelerateInterpolator()
                addListener(object : AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: Animator) {
                        splashScreenView.remove()
                    }

                    override fun onAnimationCancel(animation: Animator) {
                        splashScreenView.remove()
                    }
                })
            }
            exitAnimator.start()
        }
        registerPlugin(RockolaServerPlugin::class.java)
        isFogonActive = savedInstanceState?.getBoolean(STATE_FOGON_ACTIVE, false) ?: false
        if (savedInstanceState != null) {
            pendingShortcutAction = savedInstanceState.getString(STATE_PENDING_SHORTCUT)
        }
        super.onCreate(savedInstanceState)

        val prefs = getSharedPreferences(RockolaForegroundService.PREFS_NAME, MODE_PRIVATE)
        val savedMusicDir = prefs.getString(RockolaForegroundService.KEY_MUSIC_DIR, null)
            ?.takeIf { it.isNotBlank() }
            ?: if (BuildConfig.DEBUG) BuildConfig.DEBUG_DEFAULT_MUSIC_DIR.takeIf { it.isNotBlank() } else null
        val shouldOnboard = OnboardingPolicy.shouldShowOnboarding(
            savedMusicDir = savedMusicDir,
            savedTargetMode = prefs.getString(RockolaForegroundService.KEY_TARGET_MODE, "host"),
            savedRemoteUrl = prefs.getString(OnboardingActivity.KEY_REMOTE_URL, null),
            onboardingSkipped = prefs.getBoolean(OnboardingActivity.KEY_ONBOARDING_SKIPPED, false),
            hasShortcutAction = MainActivityPolicy.isSupportedShortcutAction(intent?.action),
        )
        if (savedInstanceState == null && shouldOnboard) {
            startActivity(Intent(this, OnboardingActivity::class.java))
            finish()
            return
        }

        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        volumeControlStream = AudioManager.STREAM_MUSIC
        registerImeInsetsObserver()
        registerBackNavigationHandler()
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        bridge?.webView?.apply {
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.rockola_bg))
            overScrollMode = View.OVER_SCROLL_NEVER
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
            settings.apply {
                mediaPlaybackRequiresUserGesture = false
                setSupportZoom(false)
                builtInZoomControls = false
                displayZoomControls = false
                textZoom = WebViewDisplayPolicy.computeTextZoom(resources.configuration.fontScale)
            }
        }
        if (MainActivityPolicy.shouldHandleShortcutOnCreate(savedInstanceState != null, intent?.action)) {
            pendingShortcutAction = intent?.action
        }
        ShortcutHelper.refreshDynamicShortcuts(this)
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
        bridge?.webView?.settings?.mediaPlaybackRequiresUserGesture = false
        val inPip = Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && isInPictureInPictureMode
        RockolaServerPlugin.emitNativeEvent("pipModeChanged", JSObject().put("active", inPip))
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
        RockolaServerPlugin.emitNativeEvent(
            "pipModeChanged",
            JSObject().put("active", isInPictureInPictureMode),
        )
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        bridge?.webView?.settings?.textZoom = WebViewDisplayPolicy.computeTextZoom(newConfig.fontScale)
    }

    private fun registerBackNavigationHandler() {
        val callback = object : OnBackPressedCallback(false) {
            override fun handleOnBackProgressed(backEvent: BackEventCompat) {
                val p = backEvent.progress.coerceIn(0f, 1f)
                if (backProgressThrottler.shouldEmit(p, SystemClock.elapsedRealtime())) {
                    RockolaServerPlugin.emitNativeEvent("backProgress", JSObject().put("progress", p))
                }
            }

            override fun handleOnBackCancelled() {
                backProgressThrottler.shouldEmit(0f, SystemClock.elapsedRealtime())
                RockolaServerPlugin.emitNativeEvent("backProgress", JSObject().put("progress", 0f))
            }

            override fun handleOnBackPressed() {
                backProgressThrottler.shouldEmit(0f, SystemClock.elapsedRealtime())
                RockolaServerPlugin.emitNativeEvent("backProgress", JSObject().put("progress", 0f))
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
        val contentView = findViewById<View>(android.R.id.content) ?: window.decorView
        ViewCompat.setOnApplyWindowInsetsListener(contentView) { view, insets ->
            val imeBottomPx = insets.getInsets(WindowInsetsCompat.Type.ime()).bottom
            val density = resources.displayMetrics.density.coerceAtLeast(1f)
            val imeCssPx = (imeBottomPx / density).roundToInt().coerceAtLeast(0)
            if (imeCssPx != lastImeBottomCssPx) {
                lastImeBottomCssPx = imeCssPx
                RockolaServerPlugin.emitNativeEvent("imeInsetsChanged", JSObject().put("bottomCssPx", imeCssPx))
            }
            ViewCompat.onApplyWindowInsets(view, insets)
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

    override fun onStart() {
        super.onStart()
        RockolaForegroundService.setUiVisible(true)
    }

    override fun onStop() {
        RockolaForegroundService.setUiVisible(false)
        super.onStop()
    }

    private fun handleShortcutIntent(intent: Intent?) {
        val action = intent?.action ?: return
        if (!MainActivityPolicy.isSupportedShortcutAction(action)) return
        val delivered = RockolaServerPlugin.emitNativeEvent("shortcutAction", JSObject().put("action", action))
        pendingShortcutAction = if (delivered) null else action
    }
}
