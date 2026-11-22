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
import android.os.Environment
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.Settings
import android.view.HapticFeedbackConstants
import android.view.WindowManager
import androidx.activity.result.ActivityResult
import androidx.core.content.ContextCompat
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.ActivityCallback
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import org.json.JSONObject
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.roundToInt

/**
 * Plugin nativo de Capacitor para controlar el servidor embebido, enrutar eventos
 * multimedia hacia host/remoto y gestionar permisos y ventana PiP.
 */
@CapacitorPlugin(
    name = "RockolaServer",
    permissions = [
        Permission(
            alias = "storageLegacy",
            strings = [Manifest.permission.READ_EXTERNAL_STORAGE]
        ),
        Permission(
            alias = "audioMedia",
            strings = [Manifest.permission.READ_MEDIA_AUDIO]
        )
    ]
)
class RockolaServerPlugin : Plugin() {

    companion object {
        private const val ACTION_VOLUME_CHANGED = "android.media.VOLUME_CHANGED_ACTION"
    }

    private var volumeReceiver: BroadcastReceiver? = null
    private val pluginExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    override fun load() {
        super.load()
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context?, intent: Intent?) {
                if (intent?.action != ACTION_VOLUME_CHANGED) return
                val (percent, muted) = readMediaVolumeState()
                bridge?.webView?.post {
                    bridge?.webView?.evaluateJavascript(
                        "window.__rockolaOnMediaVolumeChanged && window.__rockolaOnMediaVolumeChanged($percent, $muted)",
                        null,
                    )
                }
            }
        }
        volumeReceiver = receiver
        ContextCompat.registerReceiver(
            context,
            receiver,
            IntentFilter(ACTION_VOLUME_CHANGED),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )

        RockolaForegroundService.onPipStateNeedsRefresh = {
            (activity as? MainActivity)?.let { act ->
                if (act.isFogonActive) act.refreshPipParams()
            }
        }

        RockolaForegroundService.onNativeCommandError = { cmd, code, message ->
            val cmdJson = JSONObject.quote(cmd)
            val codeJson = JSONObject.quote(code)
            val msgJson = JSONObject.quote(message)
            bridge?.webView?.post {
                bridge?.webView?.evaluateJavascript(
                    "window.__rockolaOnNativeCommandError && window.__rockolaOnNativeCommandError($cmdJson, $codeJson, $msgJson)",
                    null,
                )
            }
        }
    }

    override fun handleOnDestroy() {
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

    private fun readMediaVolumeState(): Pair<Int, Boolean> {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val curVol = am.getStreamVolume(AudioManager.STREAM_MUSIC).coerceIn(0, maxVol)
        val percent = ((curVol * 100f) / maxVol).roundToInt().coerceIn(0, 100)
        val muted = am.isStreamMute(AudioManager.STREAM_MUSIC) || curVol == 0
        return Pair(percent, muted)
    }

    private fun getSystemVibrator(): Vibrator? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
            vm?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
    }

    private fun hasFullStorageAccess(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Environment.isExternalStorageManager()
        } else {
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.READ_EXTERNAL_STORAGE
            ) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun buildStatusObject(): JSObject {
        val prefs = context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
        val port = RockolaForegroundService.currentPort
        val musicDir = RockolaForegroundService.currentMusicDir
            ?: prefs.getString(RockolaForegroundService.KEY_MUSIC_DIR, null)
        return JSObject().apply {
            put("running", RockolaForegroundService.isRunning)
            put("hostState", RockolaForegroundService.hostState.wireName())
            put("lastError", RockolaForegroundService.lastHostError ?: JSONObject.NULL)
            put("port", port)
            put("localIp", RockolaForegroundService.currentLocalIp)
            put("serverUrl", RockolaForegroundService.currentServerUrl)
            put("musicDir", musicDir ?: "")
        }
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
        context.startService(intent)
        call.resolve(buildStatusObject())
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
        RockolaForegroundService.currentMediaTarget = MediaTarget(
            mode = mode,
            origin = origin,
            authHeader = authHeader,
            generation = generation,
        )

        val intent = Intent(context, RockolaForegroundService::class.java).apply {
            action = RockolaForegroundService.ACTION_SET_MEDIA_TARGET
            putExtra(RockolaForegroundService.EXTRA_TARGET_MODE, modeStr)
            putExtra(RockolaForegroundService.EXTRA_TARGET_ORIGIN, origin)
            putExtra(RockolaForegroundService.EXTRA_TARGET_GENERATION, generation)
            if (!authHeader.isNullOrBlank()) {
                putExtra(RockolaForegroundService.EXTRA_TARGET_AUTH, authHeader)
            }
        }
        context.startService(intent)
        call.resolve(JSObject().apply { put("updated", true) })
    }

    @PluginMethod
    fun updateMediaNotification(call: PluginCall) {
        val isRemote = RockolaForegroundService.currentMediaTarget.mode == MediaTargetMode.REMOTE
        if (!RockolaForegroundService.isRunning && !isRemote) {
            call.resolve(JSObject().apply { put("updated", false) })
            return
        }
        val title = call.getString("title") ?: "La Rockola del Carpincho"
        val artist = call.getString("artist") ?: "La Rockola del Carpincho"
        val paused = call.getBoolean("paused") ?: true
        val coverUrl = call.getString("coverUrl")
        val trackPath = call.getString("trackPath")
        val durationSec = call.getDouble("duration") ?: 0.0
        val positionSec = call.getDouble("position") ?: 0.0
        val isFavorite = call.getBoolean("isFavorite") ?: false
        val isPauseAfter = call.getBoolean("isPauseAfter") ?: false

        val intent = Intent(context, RockolaForegroundService::class.java).apply {
            action = RockolaForegroundService.ACTION_UPDATE_MEDIA
            putExtra(RockolaForegroundService.EXTRA_TITLE, title)
            putExtra(RockolaForegroundService.EXTRA_ARTIST, artist)
            putExtra(RockolaForegroundService.EXTRA_PAUSED, paused)
            putExtra(RockolaForegroundService.EXTRA_DURATION_MS, (durationSec * 1000.0).toLong().coerceAtLeast(0L))
            putExtra(RockolaForegroundService.EXTRA_POSITION_MS, (positionSec * 1000.0).toLong().coerceAtLeast(0L))
            putExtra(RockolaForegroundService.EXTRA_IS_FAVORITE, isFavorite)
            putExtra(RockolaForegroundService.EXTRA_IS_PAUSE_AFTER, isPauseAfter)
            if (!coverUrl.isNullOrBlank()) {
                putExtra(RockolaForegroundService.EXTRA_COVER_URL, coverUrl)
            }
            if (!trackPath.isNullOrBlank()) {
                putExtra(RockolaForegroundService.EXTRA_TRACK_PATH, trackPath)
            }
        }
        if (!paused && !trackPath.isNullOrBlank()) {
            intent.putExtra(RockolaForegroundService.EXTRA_STARTED_AS_FOREGROUND, true)
            ContextCompat.startForegroundService(context, intent)
        } else {
            context.startService(intent)
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
        if (!RockolaForegroundService.isRunning && !isRemote) {
            call.resolve(JSObject().apply { put("updated", false) })
            return
        }
        val durationSec = call.getDouble("duration") ?: 0.0
        val positionSec = call.getDouble("position") ?: 0.0
        val paused = call.getBoolean("paused") ?: true

        val intent = Intent(context, RockolaForegroundService::class.java).apply {
            action = RockolaForegroundService.ACTION_UPDATE_POSITION
            putExtra(RockolaForegroundService.EXTRA_DURATION_MS, (durationSec * 1000.0).toLong().coerceAtLeast(0L))
            putExtra(RockolaForegroundService.EXTRA_POSITION_MS, (positionSec * 1000.0).toLong().coerceAtLeast(0L))
            putExtra(RockolaForegroundService.EXTRA_PAUSED, paused)
        }
        context.startService(intent)
        val mainActivity = activity as? MainActivity
        if (mainActivity?.isFogonActive == true) {
            mainActivity.refreshPipParams()
        }
        call.resolve(JSObject().apply { put("updated", true) })
    }

    @PluginMethod
    fun hasStoragePermission(call: PluginCall) {
        call.resolve(JSObject().apply { put("granted", hasFullStorageAccess()) })
    }

    @PluginMethod
    fun hapticFeedback(call: PluginCall) {
        val heavy = call.getBoolean("heavy") ?: false
        val vibrator = getSystemVibrator()
        if (vibrator?.hasVibrator() == true) {
            try {
                val durationMs = if (heavy) 36L else 14L
                val amplitude = if (heavy) 210 else 110
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator.vibrate(VibrationEffect.createOneShot(durationMs, amplitude))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator.vibrate(durationMs)
                }
                call.resolve(JSObject().apply { put("performed", true) })
                return
            } catch (_: Exception) {
                // Caemos al feedback táctil del WebView si el dispositivo restringe Vibrator
            }
        }

        val webView = bridge?.webView
        if (webView == null) {
            call.resolve(JSObject().apply { put("performed", false) })
            return
        }
        val constant = if (heavy) {
            HapticFeedbackConstants.LONG_PRESS
        } else {
            HapticFeedbackConstants.VIRTUAL_KEY
        }
        webView.post {
            @Suppress("DEPRECATION")
            val performed = webView.performHapticFeedback(
                constant,
                HapticFeedbackConstants.FLAG_IGNORE_VIEW_SETTING,
            )
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
    fun requestStoragePermission(call: PluginCall) {
        if (hasFullStorageAccess()) {
            call.resolve(JSObject().apply { put("granted", true) })
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                data = Uri.parse("package:${context.packageName}")
            }
            try {
                startActivityForResult(call, intent, "onManageStorageResult")
            } catch (_: Exception) {
                val fallback = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                startActivityForResult(call, fallback, "onManageStorageResult")
            }
        } else {
            requestPermissionForAlias("storageLegacy", call, "onLegacyStoragePermResult")
        }
    }

    @ActivityCallback
    private fun onManageStorageResult(call: PluginCall?, _result: ActivityResult) {
        call?.resolve(JSObject().apply { put("granted", hasFullStorageAccess()) })
    }

    @PermissionCallback
    private fun onLegacyStoragePermResult(call: PluginCall?) {
        val granted = getPermissionState("storageLegacy") == PermissionState.GRANTED || hasFullStorageAccess()
        call?.resolve(JSObject().apply { put("granted", granted) })
    }

    @PluginMethod
    fun pickMusicFolder(call: PluginCall) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && !Environment.isExternalStorageManager()) {
            val permIntent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                data = Uri.parse("package:${context.packageName}")
            }
            try {
                startActivityForResult(call, permIntent, "onEnsurePermissionBeforePick")
                return
            } catch (_: Exception) {
                // Continuamos con el selector SAF si el fabricante oculta esa pantalla
            }
        }
        launchDocumentTreePicker(call)
    }

    @ActivityCallback
    private fun onEnsurePermissionBeforePick(call: PluginCall?, _result: ActivityResult) {
        if (call == null) return
        launchDocumentTreePicker(call)
    }

    private fun launchDocumentTreePicker(call: PluginCall) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        startActivityForResult(call, intent, "onFolderPicked")
    }

    @ActivityCallback
    private fun onFolderPicked(call: PluginCall?, result: ActivityResult) {
        if (call == null) return
        val uri = result.data?.data
        if (result.resultCode != Activity.RESULT_OK || uri == null) {
            call.resolve(JSObject().apply {
                put("path", JSONObject.NULL)
                put("uri", JSONObject.NULL)
            })
            return
        }

        try {
            val flags = result.data?.flags ?: 0
            val takeFlags = flags and (Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if (takeFlags != 0) {
                context.contentResolver.takePersistableUriPermission(uri, takeFlags)
            }
        } catch (_: Exception) {
        }

        val resolvedPath = StoragePathResolver.resolveTreeUri(context, uri)
        if (!resolvedPath.isNullOrBlank()) {
            context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(RockolaForegroundService.KEY_MUSIC_DIR, resolvedPath)
                .apply()
        }

        call.resolve(JSObject().apply {
            put("path", resolvedPath ?: "")
            put("uri", uri.toString())
        })
    }
}
