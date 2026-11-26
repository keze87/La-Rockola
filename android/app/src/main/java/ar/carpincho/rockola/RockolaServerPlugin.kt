package ar.carpincho.rockola

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.view.WindowManager
import androidx.activity.result.ActivityResult
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.ActivityCallback
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONObject
import java.io.File
import java.lang.ref.WeakReference
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.roundToInt

/**
 * Plugin nativo de Capacitor para controlar el servidor embebido, enrutar eventos
 * multimedia hacia host/remoto y gestionar permisos y ventana PiP.
 */
@CapacitorPlugin(name = "RockolaServer")
class RockolaServerPlugin : Plugin() {

    companion object {
        private const val VOLUME_CHANGED_ACTION = "android.media.VOLUME_CHANGED_ACTION"

        @Volatile
        private var activePluginRef: WeakReference<RockolaServerPlugin>? = null

        fun emitNativeEvent(eventName: String, data: JSObject): Boolean {
            val plugin = activePluginRef?.get() ?: return false
            if (!plugin.hasListeners(eventName)) return false
            val webView = plugin.bridge?.webView ?: return false
            webView.post {
                plugin.notifyListeners(eventName, data)
            }
            return true
        }
    }

    private var volumeReceiver: BroadcastReceiver? = null
    private var lastNotifiedVolumeState: Pair<Int, Boolean>? = null
    private val pluginExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    override fun load() {
        super.load()
        activePluginRef = WeakReference(this)
        AndroidStorageBridge.initialize(context)
        lastNotifiedVolumeState = readMediaVolumeState()

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context?, intent: Intent?) {
                if (intent?.action == VOLUME_CHANGED_ACTION) {
                    notifyMediaVolumeIfChanged()
                }
            }
        }
        volumeReceiver = receiver
        ContextCompat.registerReceiver(
            context,
            receiver,
            IntentFilter(VOLUME_CHANGED_ACTION),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )

        RockolaForegroundService.onPipStateNeedsRefresh = {
            (activity as? MainActivity)?.let { act ->
                if (act.isFogonActive) act.refreshPipParams()
            }
        }

        RockolaForegroundService.onNativeCommandError = { cmd, code, message ->
            emitNativeEvent(
                "nativeCommandError",
                JSObject().apply {
                    put("cmd", cmd)
                    put("code", code)
                    put("message", message)
                },
            )
        }
    }

    override fun handleOnResume() {
        super.handleOnResume()
        notifyMediaVolumeIfChanged()
    }

    override fun handleOnDestroy() {
        if (activePluginRef?.get() === this) {
            activePluginRef = null
        }
        RockolaForegroundService.onPipStateNeedsRefresh = null
        RockolaForegroundService.onNativeCommandError = null
        volumeReceiver?.let {
            try {
                context.unregisterReceiver(it)
            } catch (_: Exception) {
            }
        }
        volumeReceiver = null
        pluginExecutor.shutdownNow()
        super.handleOnDestroy()
    }

    private fun notifyMediaVolumeIfChanged() {
        val current = readMediaVolumeState()
        if (current == lastNotifiedVolumeState) return
        lastNotifiedVolumeState = current
        val (percent, muted) = current
        emitNativeEvent(
            "mediaVolumeChanged",
            JSObject().apply {
                put("level", percent)
                put("muted", muted)
            },
        )
    }

    private fun readMediaVolumeState(): Pair<Int, Boolean> {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val curVol = am.getStreamVolume(AudioManager.STREAM_MUSIC).coerceIn(0, maxVol)
        val percent = ((curVol * 100f) / maxVol).roundToInt().coerceIn(0, 100)
        val muted = am.isStreamMute(AudioManager.STREAM_MUSIC) || curVol == 0
        return Pair(percent, muted)
    }

    private fun resolveConfiguredMusicDir(): String? {
        val prefs = context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
        return RockolaForegroundService.currentMusicDir
            ?: prefs.getString(RockolaForegroundService.KEY_MUSIC_DIR, null)?.trim()?.takeIf { it.isNotEmpty() }
    }

    private fun validateConfiguredFolder(target: String?): SafValidationResult {
        val cleaned = target?.trim().orEmpty()
        if (cleaned.isEmpty()) {
            return SafValidationResult(SafFolderStatus.UNCONFIGURED, "", null, null)
        }
        if (cleaned.startsWith("content://")) {
            return AndroidStorageBridge.validateTreeUri(context, cleaned)
        }
        val dir = File(cleaned)
        return if (dir.isDirectory && dir.canRead()) {
            SafValidationResult(SafFolderStatus.OK, cleaned, dir.name, null)
        } else {
            SafValidationResult(
                SafFolderStatus.UNAVAILABLE,
                cleaned,
                dir.name,
                "La carpeta configurada no existe o no se puede leer.",
            )
        }
    }

    private fun buildStatusObject(): JSObject {
        val prefs = context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
        val port = RockolaForegroundService.currentPort
        val musicDir = RockolaForegroundService.currentMusicDir
            ?: prefs.getString(RockolaForegroundService.KEY_MUSIC_DIR, null)
        return JSObject().apply {
            put("running", RockolaForegroundService.isRunning)
            put("hasActiveWorker", RockolaForegroundService.hasActiveWorker)
            put("hostState", RockolaForegroundService.hostState.wireName())
            put("lastError", RockolaForegroundService.lastHostError ?: JSONObject.NULL)
            put("port", port)
            put("localIp", RockolaForegroundService.currentLocalIp)
            put("serverUrl", RockolaForegroundService.currentServerUrl)
            put("musicDir", musicDir ?: "")
            put("bootStage", EmbeddedPythonHost.currentBootStage)
            put("extractProgress", EmbeddedPythonHost.currentExtractProgress)
        }
    }

    private fun safeStartService(
        intent: Intent,
        foreground: Boolean = false,
        allowForegroundFallback: Boolean = false,
    ): String? {
        return try {
            if (foreground) {
                intent.putExtra(RockolaForegroundService.EXTRA_STARTED_AS_FOREGROUND, true)
                ContextCompat.startForegroundService(context, intent)
            } else {
                context.startService(intent)
            }
            null
        } catch (e: IllegalStateException) {
            if (!foreground && allowForegroundFallback) {
                return try {
                    intent.putExtra(RockolaForegroundService.EXTRA_STARTED_AS_FOREGROUND, true)
                    ContextCompat.startForegroundService(context, intent)
                    null
                } catch (fallbackErr: IllegalStateException) {
                    fallbackErr.message?.takeIf { it.isNotBlank() }
                        ?: "Android bloqueó el inicio del servicio en segundo plano. Volvé a abrir la app."
                } catch (fallbackErr: SecurityException) {
                    fallbackErr.message?.takeIf { it.isNotBlank() } ?: "Sin permiso para iniciar el servicio."
                }
            }
            // Incluye ForegroundServiceStartNotAllowedException en Android 12+ cuando la app está en segundo plano
            e.message?.takeIf { it.isNotBlank() }
                ?: "Android bloqueó el inicio del servicio en segundo plano. Volvé a abrir la app."
        } catch (e: SecurityException) {
            e.message?.takeIf { it.isNotBlank() } ?: "Sin permiso para iniciar el servicio."
        }
    }

    @PluginMethod
    fun markUiReady(call: PluginCall) {
        val jsNowMs = call.getDouble("jsNowMs")
        (activity as? MainActivity)?.markUiReady(jsNowMs)
        call.resolve(JSObject().apply { put("ready", true) })
    }

    @PluginMethod
    fun reportFullyDrawn(call: PluginCall) {
        val reason = call.getString("reason")?.trim()?.takeIf { it.isNotEmpty() } ?: "ui"
        (activity as? MainActivity)?.reportFullyDrawnOnce(reason)
        call.resolve(JSObject().apply { put("reported", true) })
    }

    @PluginMethod
    fun logStartupMark(call: PluginCall) {
        val stage = call.getString("stage")?.trim().orEmpty().take(64)
        val jsNowMs = call.getDouble("jsNowMs")
        if (stage.isNotEmpty()) {
            val jsPart = jsNowMs?.let { " jsNowMs=${it.roundToInt()}" } ?: ""
            android.util.Log.i(
                "RockolaStartup",
                "stage=$stage processElapsedMs=${RockolaApplication.elapsedSinceProcessStartMs()}$jsPart",
            )
        }
        call.resolve(JSObject().apply { put("logged", true) })
    }

    @PluginMethod
    fun setBackHandlerEnabled(call: PluginCall) {
        val enabled = call.getBoolean("enabled") ?: false
        (activity as? MainActivity)?.setBackHandlerEnabled(enabled)
        call.resolve(JSObject().apply { put("enabled", enabled) })
    }

    @PluginMethod
    fun logWebError(call: PluginCall) {
        val message = call.getString("message")?.trim().orEmpty().take(1000)
        val source = call.getString("source")?.trim().orEmpty().take(200)
        if (message.isNotEmpty()) {
            android.util.Log.e("RockolaWebError", if (source.isNotEmpty()) "[$source] $message" else message)
        }
        call.resolve(JSObject().apply { put("logged", true) })
    }

    @PluginMethod
    fun startServer(call: PluginCall) {
        val port = call.getInt("port") ?: RockolaForegroundService.currentPort
        val musicDir = call.getString("musicDir")

        val intent = Intent(context, RockolaForegroundService::class.java).apply {
            action = RockolaForegroundService.ACTION_START
            putExtra(RockolaForegroundService.EXTRA_PORT, port)
            if (!musicDir.isNullOrBlank()) {
                putExtra(RockolaForegroundService.EXTRA_MUSIC_DIR, musicDir)
            }
        }
        val err = safeStartService(intent, foreground = false, allowForegroundFallback = true)
        if (err != null) {
            call.reject(err, "SERVICE_START_NOT_ALLOWED")
            return
        }
        call.resolve(buildStatusObject())
    }

    private fun resolveNotificationPermissionStatus(): Pair<String, Boolean> {
        val enabledInSystem = NotificationManagerCompat.from(context).areNotificationsEnabled()
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return if (enabledInSystem) Pair("granted", true) else Pair("denied", false)
        }
        val granted = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted && enabledInSystem) {
            return Pair("granted", true)
        }
        val prefs = context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
        val askedBefore = prefs.getBoolean("notif_permission_asked", false)
        val hostAct = activity
        val shouldShowRationale = hostAct != null &&
            ActivityCompat.shouldShowRequestPermissionRationale(hostAct, Manifest.permission.POST_NOTIFICATIONS)
        val status = if (!granted && askedBefore && !shouldShowRationale) {
            "denied"
        } else if (granted && !enabledInSystem) {
            "denied"
        } else {
            "prompt"
        }
        return Pair(status, false)
    }

    @PluginMethod
    fun getNotificationPermissionStatus(call: PluginCall) {
        val (status, granted) = resolveNotificationPermissionStatus()
        call.resolve(
            JSObject().apply {
                put("status", status)
                put("granted", granted)
            },
        )
    }

    @PluginMethod
    fun requestNotificationPermission(call: PluginCall) {
        val mainActivity = activity as? MainActivity
        if (mainActivity == null) {
            val (status, granted) = resolveNotificationPermissionStatus()
            call.resolve(JSObject().apply { put("status", status); put("granted", granted) })
            return
        }
        mainActivity.requestNotificationPermissionWithResult { granted ->
            val (status, resolvedGranted) = resolveNotificationPermissionStatus()
            val finalStatus = if (granted && resolvedGranted) "granted" else if (granted) "granted" else status
            call.resolve(
                JSObject().apply {
                    put("status", finalStatus)
                    put("granted", granted)
                },
            )
        }
    }

    @PluginMethod
    fun openNotificationSettings(call: PluginCall) {
        val hostActivity = activity ?: run {
            call.resolve(JSObject().apply { put("opened", false) })
            return
        }
        hostActivity.runOnUiThread {
            val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                    putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                }
            } else {
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.fromParts("package", context.packageName, null)
                }
            }
            try {
                hostActivity.startActivity(intent)
                call.resolve(JSObject().apply { put("opened", true) })
            } catch (_: Exception) {
                call.resolve(JSObject().apply { put("opened", false) })
            }
        }
    }

    @PluginMethod
    fun stopServer(call: PluginCall) {
        pluginExecutor.execute {
            val stopped = RockolaForegroundService.requestStopAndAwait(context, timeoutMs = 4500L)
            call.resolve(
                JSObject().apply {
                    put("stopped", stopped)
                    put("hostState", RockolaForegroundService.hostState.wireName())
                },
            )
        }
    }

    @PluginMethod
    fun getStatus(call: PluginCall) {
        call.resolve(buildStatusObject())
    }

    @PluginMethod
    fun setMediaTarget(call: PluginCall) {
        val modeStr = call.getString("mode") ?: "host"
        val origin = call.getString("origin")?.trim()?.trimEnd('/')
            ?: "http://127.0.0.1:${RockolaForegroundService.currentPort}"
        val authHeader = call.getString("authHeader")
        val generation = call.getInt("generation")?.toLong() ?: 0L

        val mode = if (modeStr == "remote") MediaTargetMode.REMOTE else MediaTargetMode.HOST
        val target = MediaTarget(
            mode = mode,
            origin = origin,
            authHeader = authHeader,
            generation = generation,
        )
        RockolaForegroundService.applyMediaTargetDirect(context, target)
        call.resolve(JSObject().apply { put("updated", true) })
    }

    @PluginMethod
    fun updateMediaNotification(call: PluginCall) {
        val isRemote = RockolaForegroundService.currentMediaTarget.mode == MediaTargetMode.REMOTE
        if (!isRemote) {
            // En modo HOST la única fuente de verdad es Python/ExoPlayer
            call.resolve(JSObject().apply { put("updated", false) })
            return
        }
        val title = call.getString("title") ?: "La Rockola del Carpincho"
        val artist = call.getString("artist") ?: "La Rockola del Carpincho"
        val album = call.getString("album")?.takeIf { it.isNotBlank() }
        val paused = call.getBoolean("paused") ?: true
        val coverUrl = call.getString("coverUrl")
        val trackPath = call.getString("trackPath")
        val durationMs = ((call.getDouble("duration") ?: 0.0) * 1000.0).toLong().coerceAtLeast(0L)
        val positionMs = ((call.getDouble("position") ?: 0.0) * 1000.0).toLong().coerceAtLeast(0L)
        val isFavorite = call.getBoolean("isFavorite") ?: false
        val isPauseAfter = call.getBoolean("isPauseAfter") ?: false

        val handledDirectly = RockolaForegroundService.applyMediaUpdateDirect(
            title = title,
            artist = artist,
            album = album,
            paused = paused,
            coverUrl = coverUrl,
            trackPath = trackPath,
            durationMs = durationMs,
            positionMs = positionMs,
            isFavorite = isFavorite,
            isPauseAfter = isPauseAfter,
        )
        if (!handledDirectly && !paused && !trackPath.isNullOrBlank()) {
            val intent = Intent(context, RockolaForegroundService::class.java).apply {
                action = RockolaForegroundService.ACTION_UPDATE_MEDIA
                putExtra(RockolaForegroundService.EXTRA_TITLE, title)
                putExtra(RockolaForegroundService.EXTRA_ARTIST, artist)
                putExtra(RockolaForegroundService.EXTRA_PAUSED, paused)
                putExtra(RockolaForegroundService.EXTRA_DURATION_MS, durationMs)
                putExtra(RockolaForegroundService.EXTRA_POSITION_MS, positionMs)
                putExtra(RockolaForegroundService.EXTRA_IS_FAVORITE, isFavorite)
                putExtra(RockolaForegroundService.EXTRA_IS_PAUSE_AFTER, isPauseAfter)
                if (album != null) putExtra(RockolaForegroundService.EXTRA_ALBUM, album)
                if (!coverUrl.isNullOrBlank()) putExtra(RockolaForegroundService.EXTRA_COVER_URL, coverUrl)
                putExtra(RockolaForegroundService.EXTRA_TRACK_PATH, trackPath)
            }
            val startErr = safeStartService(intent, foreground = true)
            if (startErr != null) {
                call.reject(startErr, "SERVICE_START_NOT_ALLOWED")
                return
            }
        }
        val mainActivity = activity as? MainActivity
        if (mainActivity?.isFogonActive == true) {
            mainActivity.refreshPipParams()
        }
        call.resolve(JSObject().apply { put("updated", true) })
    }

    @PluginMethod
    fun updateMediaPosition(call: PluginCall) {
        val isRemote = RockolaForegroundService.currentMediaTarget.mode == MediaTargetMode.REMOTE
        if (!isRemote) {
            call.resolve(JSObject().apply { put("updated", false) })
            return
        }
        val durationMs = ((call.getDouble("duration") ?: 0.0) * 1000.0).toLong().coerceAtLeast(0L)
        val positionMs = ((call.getDouble("position") ?: 0.0) * 1000.0).toLong().coerceAtLeast(0L)
        val paused = call.getBoolean("paused") ?: true

        val updated = RockolaForegroundService.applyPositionUpdateDirect(durationMs, positionMs, paused)
        val mainActivity = activity as? MainActivity
        if (updated && mainActivity?.isFogonActive == true) {
            mainActivity.refreshPipParams()
        }
        call.resolve(JSObject().apply { put("updated", updated) })
    }

    @PluginMethod
    fun validateMusicFolder(call: PluginCall) {
        val requested = call.getString("uri") ?: resolveConfiguredMusicDir()
        val result = validateConfiguredFolder(requested)
        call.resolve(
            JSObject().apply {
                put("valid", result.status == SafFolderStatus.OK)
                put("status", result.status.wireName())
                put("uri", result.uri)
                put("displayName", result.displayName ?: JSONObject.NULL)
                put("error", result.error ?: JSONObject.NULL)
            },
        )
    }

    @PluginMethod
    fun hapticFeedback(call: PluginCall) {
        val kind = HapticPolicy.normalizeKind(
            kind = call.getString("kind"),
            heavy = call.getBoolean("heavy") ?: false,
        )
        val webView = bridge?.webView
        if (webView == null) {
            call.resolve(JSObject().apply { put("performed", false) })
            return
        }
        val constant = HapticPolicy.resolveConstant(kind)
        webView.post {
            // Sin FLAG_IGNORE_VIEW_SETTING ni FLAG_IGNORE_GLOBAL_SETTING: respeta los ajustes del sistema
            val performed = webView.performHapticFeedback(constant)
            call.resolve(JSObject().apply { put("performed", performed) })
        }
    }

    @PluginMethod
    fun getMediaVolume(call: PluginCall) {
        val (percent, muted) = readMediaVolumeState()
        call.resolve(JSObject().apply {
            put("level", percent)
            put("muted", muted)
        })
    }

    @PluginMethod
    fun setMediaVolume(call: PluginCall) {
        val requested = (call.getInt("level") ?: 50).coerceIn(0, 100)
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val target = ((requested / 100f) * maxVol).roundToInt().coerceIn(0, maxVol)
        am.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
        val (percent, muted) = readMediaVolumeState()
        call.resolve(JSObject().apply {
            put("level", percent)
            put("muted", muted)
        })
    }

    @PluginMethod
    fun setKeepScreenOn(call: PluginCall) {
        val enabled = call.getBoolean("enabled") ?: false
        val hostActivity = activity
        if (hostActivity == null) {
            call.resolve(JSObject().apply { put("enabled", false) })
            return
        }
        hostActivity.runOnUiThread {
            if (enabled) {
                hostActivity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            } else {
                hostActivity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            call.resolve(JSObject().apply { put("enabled", enabled) })
        }
    }

    @PluginMethod
    fun shareUrl(call: PluginCall) {
        val url = call.getString("url")?.trim()
        if (url.isNullOrEmpty()) {
            call.reject("Se requiere una URL válida para compartir")
            return
        }
        val title = call.getString("title") ?: "La Rockola del Carpincho"
        val text = call.getString("text")
        val body = if (!text.isNullOrBlank()) "$text\n$url" else url
        val hostActivity = activity
        if (hostActivity == null) {
            call.resolve(JSObject().apply { put("shared", false) })
            return
        }
        hostActivity.runOnUiThread {
            val sendIntent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_SUBJECT, title)
                putExtra(Intent.EXTRA_TEXT, body)
            }
            val chooser = Intent.createChooser(sendIntent, title)
            hostActivity.startActivity(chooser)
            call.resolve(JSObject().apply { put("shared", true) })
        }
    }

    @PluginMethod
    fun consumePendingShortcut(call: PluginCall) {
        val action = MainActivity.consumePendingShortcutAction()
        call.resolve(JSObject().apply {
            put("action", action ?: JSONObject.NULL)
        })
    }

    @PluginMethod
    fun setFogonState(call: PluginCall) {
        val active = call.getBoolean("active") ?: false
        (activity as? MainActivity)?.setFogonActive(active)
        call.resolve(JSObject().apply { put("active", active) })
    }

    @PluginMethod
    fun enterPipMode(call: PluginCall) {
        val mainActivity = activity as? MainActivity
        if (mainActivity == null) {
            call.resolve(JSObject().apply {
                put("entered", false)
                put("reason", "NO_ACTIVITY")
            })
            return
        }
        mainActivity.enterPipIfSupported { entered, reason ->
            call.resolve(JSObject().apply {
                put("entered", entered)
                put("reason", reason ?: JSONObject.NULL)
            })
        }
    }

    @PluginMethod
    fun pickMusicFolder(call: PluginCall) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            addFlags(Intent.FLAG_GRANT_PREFIX_URI_PERMISSION)
        }
        startActivityForResult(call, intent, "onFolderPicked")
    }

    @ActivityCallback
    private fun onFolderPicked(call: PluginCall?, result: ActivityResult) {
        if (call == null) return
        val uri = result.data?.data
        if (result.resultCode != Activity.RESULT_OK || uri == null) {
            call.resolve(
                JSObject().apply {
                    put("path", JSONObject.NULL)
                    put("uri", JSONObject.NULL)
                    put("displayName", JSONObject.NULL)
                    put("status", JSONObject.NULL)
                    put("error", JSONObject.NULL)
                },
            )
            return
        }

        val uriStr = uri.toString()
        AndroidStorageBridge.persistTreePermission(context, uri, result.data?.flags ?: 0)
        context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(RockolaForegroundService.KEY_MUSIC_DIR, uriStr)
            .apply()
        RockolaForegroundService.updateMusicDir(uriStr)

        call.resolve(
            JSObject().apply {
                put("path", uriStr)
                put("uri", uriStr)
                put("displayName", uri.lastPathSegment ?: JSONObject.NULL)
                put("status", SafFolderStatus.OK.wireName())
                put("error", JSONObject.NULL)
            },
        )
    }
}
