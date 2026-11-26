package ar.carpincho.rockola

import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log

/**
 * Resolución ante el callback `Service.onTimeout` introducido en Android 14/15.
 */
internal enum class TimeoutResolution {
    STOP_SERVICE,
}

/**
 * Reglas puras de energía y ciclo de vida en segundo plano (testeables en JVM).
 */
internal object ServicePowerPolicy {
    fun shouldAcquireWifiLock(
        mode: MediaTargetMode,
        hasRemoteClients: Boolean,
        isActivePlaybackOrRadio: Boolean = false,
    ): Boolean {
        return mode == MediaTargetMode.REMOTE || hasRemoteClients || isActivePlaybackOrRadio
    }

    fun shouldDelayDemote(isMediaPlaying: Boolean, isRadioSynthesizing: Boolean): Boolean {
        return isMediaPlaying || isRadioSynthesizing
    }

    fun shouldStopOnTaskRemoved(isMediaPlaying: Boolean, hasRemoteClients: Boolean): Boolean {
        return !isMediaPlaying && !hasRemoteClients
    }

    fun shouldUseForeground(
        isHostRunning: Boolean,
        isMediaPlaying: Boolean,
        isRadioSynthesizing: Boolean = false,
        hasRemoteClients: Boolean = false,
    ): Boolean {
        return isHostRunning && (isMediaPlaying || isRadioSynthesizing || hasRemoteClients)
    }

    fun shouldStopForeground(
        isHostRunning: Boolean,
        hasRemoteClients: Boolean = false,
        @Suppress("UNUSED_PARAMETER") isUiVisible: Boolean = false,
        isRadioSynthesizing: Boolean = false,
        forceStop: Boolean = false,
    ): Boolean {
        if (forceStop || !isHostRunning) return true
        // Si la UI está visible sin reproducción ni clientes remotos, la Activity ya da prioridad de primer plano:
        // no retenemos un servicio foreground dataSync para no consumir el cupo de 6 h de Android 15.
        if (isRadioSynthesizing) return false
        return !hasRemoteClients
    }

    fun foregroundServiceType(
        isMediaPlaying: Boolean,
        @Suppress("UNUSED_PARAMETER") hasRemoteClients: Boolean = false,
        isRadioSynthesizing: Boolean = false,
    ): Int {
        return if (isMediaPlaying || isRadioSynthesizing) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
        } else {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        }
    }

    fun resolveTimeout(@Suppress("UNUSED_PARAMETER") fgsType: Int, @Suppress("UNUSED_PARAMETER") isMediaPlaying: Boolean): TimeoutResolution {
        return TimeoutResolution.STOP_SERVICE
    }

    fun shouldStopAfterRemoteGrace(
        taskRemoved: Boolean,
        isMediaPlaying: Boolean,
        hasRemoteClients: Boolean,
    ): Boolean {
        return taskRemoved && !isMediaPlaying && !hasRemoteClients
    }
}

/**
 * Servicio en primer plano orquestador para el servidor FastAPI/Uvicorn embebido,
 * reproducción nativa Media3 ExoPlayer y MediaSession consciente del origen activo
 * (host local o servidor remoto).
 */
class RockolaForegroundService : Service() {

    companion object {
        const val PREFS_NAME = "rockola_android_prefs"
        const val KEY_MUSIC_DIR = "music_dir"
        const val KEY_PORT = "port"
        const val KEY_TARGET_MODE = "target_mode"

        const val ACTION_START = "ar.carpincho.rockola.ACTION_START"
        const val ACTION_STOP = "ar.carpincho.rockola.ACTION_STOP"
        const val ACTION_MEDIA_PREV = "ar.carpincho.rockola.ACTION_MEDIA_PREV"
        const val ACTION_MEDIA_PLAY_PAUSE = "ar.carpincho.rockola.ACTION_MEDIA_PLAY_PAUSE"
        const val ACTION_MEDIA_NEXT = "ar.carpincho.rockola.ACTION_MEDIA_NEXT"
        const val ACTION_MEDIA_FAVORITE = "ar.carpincho.rockola.ACTION_MEDIA_FAVORITE"

        fun mapNativeDispatchResult(status: String): CommandResult? = when (status) {
            "ok" -> CommandResult.Success
            "timeout" -> CommandResult.Timeout("Tiempo de espera agotado ejecutando comando nativo.")
            "error" -> CommandResult.ServerError(500)
            else -> null
        }
        const val ACTION_MEDIA_PAUSE_AFTER = "ar.carpincho.rockola.ACTION_MEDIA_PAUSE_AFTER"
        const val ACTION_UPDATE_MEDIA = "ar.carpincho.rockola.ACTION_UPDATE_MEDIA"

        const val CUSTOM_ACTION_FAVORITE = "ar.carpincho.rockola.CUSTOM_FAVORITE"
        const val CUSTOM_ACTION_PAUSE_AFTER = "ar.carpincho.rockola.CUSTOM_PAUSE_AFTER"

        const val EXTRA_PORT = "port"
        const val EXTRA_MUSIC_DIR = "music_dir"
        const val EXTRA_STARTED_AS_FOREGROUND = "started_as_foreground"
        const val EXTRA_TITLE = "media_title"
        const val EXTRA_ARTIST = "media_artist"
        const val EXTRA_ALBUM = "media_album"
        const val EXTRA_PAUSED = "media_paused"
        const val EXTRA_COVER_URL = "media_cover_url"
        const val EXTRA_TRACK_PATH = "media_track_path"
        const val EXTRA_DURATION_MS = "media_duration_ms"
        const val EXTRA_POSITION_MS = "media_position_ms"
        const val EXTRA_IS_FAVORITE = "media_is_favorite"
        const val EXTRA_IS_PAUSE_AFTER = "media_is_pause_after"

        private const val CHANNEL_ID = "rockola_server_channel"
        private const val NOTIFICATION_ID = 1729
        private const val DEFAULT_PORT = 1729
        private const val STOP_JOIN_TIMEOUT_MS = 4000L
        private const val WAKELOCK_TIMEOUT_MS = 4 * 60 * 60 * 1000L
        private const val DEMOTE_DEBOUNCE_MS = 30_000L

        @Volatile
        var hostState: HostServerState = HostServerState.STOPPED
            private set

        @Volatile
        var lastHostError: String? = null
            private set

        @Volatile
        var isRunning: Boolean = false
            private set

        @Volatile
        var hasActiveWorker: Boolean = false
            private set

        @Volatile
        private var activeInstance: RockolaForegroundService? = null

        // Coordinador y executor de apagado con alcance de proceso para sobrevivir recreaciones del Service
        private val processHostCoordinator = HostLifecycleCoordinator()
        private val processShutdownExecutor: ExecutorService = Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "RockolaProcessShutdown").apply { isDaemon = true }
        }

        private fun syncProcessCoordinatorSnapshot() {
            hostState = processHostCoordinator.state
            lastHostError = processHostCoordinator.lastError
            isRunning = processHostCoordinator.isRunning
            hasActiveWorker = processHostCoordinator.hasActiveWorker
        }

        @Volatile
        var isActivelyPlaying: Boolean = false
            private set

        @Volatile
        var isMediaPlaying: Boolean = false
            private set

        @Volatile
        var currentPort: Int = DEFAULT_PORT
            private set

        @Volatile
        var currentMusicDir: String? = null
            private set

        internal fun updateMusicDir(musicDir: String?) {
            currentMusicDir = musicDir?.trim()?.takeIf { it.isNotEmpty() }
        }

        @Volatile
        var currentServerUrl: String = "http://127.0.0.1:$DEFAULT_PORT"
            private set

        @Volatile
        var currentLocalIp: String = "127.0.0.1"
            private set

        @Volatile
        var currentMediaTarget: MediaTarget = MediaTarget(
            mode = MediaTargetMode.HOST,
            origin = "http://127.0.0.1:$DEFAULT_PORT",
        )
            internal set

        @Volatile
        var isUiVisible: Boolean = false
            private set

        @Volatile
        internal var onPipStateNeedsRefresh: (() -> Unit)? = null

        @Volatile
        internal var onNativeCommandError: ((cmd: String, code: String, message: String) -> Unit)? = null

        internal fun setUiVisible(visible: Boolean) {
            isUiVisible = visible
            val instance = activeInstance ?: return
            instance.mainHandler.post {
                instance.syncForegroundWithUiVisibility(visible)
            }
        }

        internal fun persistTargetMode(context: Context, mode: MediaTargetMode) {
            val wire = if (mode == MediaTargetMode.REMOTE) "remote" else "host"
            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_TARGET_MODE, wire)
                .apply()
        }

        internal fun applyMediaTargetDirect(context: Context, target: MediaTarget) {
            persistTargetMode(context, target.mode)
            currentMediaTarget = target
            val instance = activeInstance ?: return
            instance.mainHandler.post {
                instance.applyTargetOnMain(target)
            }
        }

        internal fun applyMediaUpdateDirect(
            title: String,
            artist: String,
            album: String?,
            paused: Boolean,
            coverUrl: String?,
            trackPath: String?,
            durationMs: Long,
            positionMs: Long,
            isFavorite: Boolean,
            isPauseAfter: Boolean,
        ): Boolean {
            val instance = activeInstance ?: return false
            instance.mainHandler.post {
                instance.applyMediaUpdate(
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
            }
            return true
        }

        internal fun applyPositionUpdateDirect(durationMs: Long, positionMs: Long, paused: Boolean): Boolean {
            val instance = activeInstance ?: return false
            instance.mainHandler.post {
                instance.applyPositionUpdate(durationMs, positionMs, paused)
            }
            return true
        }

        internal fun requestStopAndAwait(context: Context, timeoutMs: Long = STOP_JOIN_TIMEOUT_MS): Boolean {
            val instance = activeInstance
            if (instance != null) {
                return instance.stopServerBlocking(timeoutMs)
            }
            if (processHostCoordinator.hasActiveWorker) {
                val clean = processHostCoordinator.stop(timeoutMs)
                syncProcessCoordinatorSnapshot()
                return clean
            }
            if (isRunning) {
                val intent = Intent(context, RockolaForegroundService::class.java).apply {
                    action = ACTION_STOP
                }
                try {
                    context.startService(intent)
                } catch (_: Exception) {
                    // Si Android bloquea startService en segundo plano al pedir stop, respetamos !hasActiveWorker
                }
            }
            syncProcessCoordinatorSnapshot()
            return !processHostCoordinator.hasActiveWorker
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private val backgroundExecutor: ExecutorService = Executors.newFixedThreadPool(2) { runnable ->
        Thread(runnable, "RockolaServiceBg").apply { isDaemon = true }
    }

    @Volatile
    private var isInForeground: Boolean = false

    @Volatile
    private var currentForegroundType: Int = 0

    private var pendingDemoteRunnable: Runnable? = null

    private fun cancelPendingDemote() {
        pendingDemoteRunnable?.let { mainHandler.removeCallbacks(it) }
        pendingDemoteRunnable = null
    }

    private fun scheduleDemoteFromForeground(keepDismissibleNotification: Boolean) {
        cancelPendingDemote()
        if (keepDismissibleNotification && notificationManager.hasActiveTrack) {
            notificationManager.notifyCurrentState()
        }
        val runnable = Runnable {
            pendingDemoteRunnable = null
            val radioBusy = isRadioSynthesizing()
            if (!ServicePowerPolicy.shouldDelayDemote(isMediaPlaying, radioBusy)) {
                demoteFromForeground(keepDismissibleNotification = keepDismissibleNotification)
            } else if (!isMediaPlaying && radioBusy) {
                // Seguimos esperando mientras la radio sintetiza entre temas para no soltar wake ni foreground
                scheduleDemoteFromForeground(keepDismissibleNotification = keepDismissibleNotification)
            }
        }
        pendingDemoteRunnable = runnable
        mainHandler.postDelayed(runnable, DEMOTE_DEBOUNCE_MS)
    }

    private lateinit var hostCoordinator: HostLifecycleCoordinator
    private lateinit var commandClient: MediaCommandClient
    private lateinit var pythonHost: EmbeddedPythonHost
    private lateinit var notificationManager: MediaNotificationManager
    private lateinit var audioPlayer: AndroidAudioPlayer

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        activeInstance = this
        AndroidStorageBridge.initialize(this)
        commandClient = MediaCommandClient(initialTarget = currentMediaTarget)
        pythonHost = EmbeddedPythonHost(this)
        hostCoordinator = processHostCoordinator
        syncProcessCoordinatorSnapshot()
        hostCoordinator.setStateListener { nextState, err ->
            syncProcessCoordinatorSnapshot()
            if (activeInstance !== this) return@setStateListener
            if ((nextState == HostServerState.FAILED || nextState == HostServerState.STOP_TIMED_OUT) && err != null) {
                onNativeCommandError?.invoke("host_server", "HOST_FAILED", err)
            }
            if (nextState == HostServerState.STOPPED ||
                nextState == HostServerState.FAILED ||
                nextState == HostServerState.STOP_TIMED_OUT
            ) {
                if (currentMediaTarget.mode == MediaTargetMode.HOST) {
                    isActivelyPlaying = false
                    isMediaPlaying = false
                    mainHandler.post {
                        if (activeInstance === this) {
                            demoteFromForeground(keepDismissibleNotification = false)
                        }
                    }
                }
            }
        }
        notificationManager = MediaNotificationManager(
            service = this,
            channelId = CHANNEL_ID,
            notificationId = NOTIFICATION_ID,
            onCommand = { cmd, extra, expectedGen, onResult ->
                val targetNow = currentMediaTarget
                if (targetNow.mode == MediaTargetMode.HOST &&
                    expectedGen == targetNow.generation &&
                    com.chaquo.python.Python.isStarted()
                ) {
                    if (cmd == "pause") {
                        val requestedPaused = extra["state"] as? Boolean
                        if (requestedPaused != null) {
                            audioPlayer.setPause(requestedPaused)
                        }
                    }
                    val payloadJson = MediaCommandClient.serializeCommandJson(cmd, extra)
                    backgroundExecutor.execute {
                        val status = try {
                            com.chaquo.python.Python.getInstance()
                                .getModule("app.android_entry")
                                .callAttr("dispatch_native_command", cmd, payloadJson)
                                .toString()
                        } catch (_: Exception) {
                            "unavailable"
                        }
                        val mapped = mapNativeDispatchResult(status)
                        if (mapped != null) {
                            onResult(mapped)
                        } else {
                            commandClient.sendCommand(cmd, extra, expectedGen, onResult)
                        }
                    }
                } else {
                    commandClient.sendCommand(cmd, extra, expectedGen, onResult)
                }
            },
            onRequestArtwork = { coverUrl, expectedGen ->
                commandClient.fetchArtwork(coverUrl, expectedGen) { bmp ->
                    notificationManager.applyArtworkIfCurrent(coverUrl, expectedGen, bmp)
                }
            },
            onLookupCachedArtwork = { coverUrl, expectedGen ->
                commandClient.getCachedArtwork(coverUrl, expectedGen)
            },
            onCommandFailed = { cmd, result ->
                onNativeCommandError?.invoke(cmd, result.errorCode(), result.userMessage())
            },
        )
        notificationManager.initialize()
        notificationManager.setTarget(currentMediaTarget)
        audioPlayer = AndroidAudioPlayer(
            context = this,
            onPlaybackActiveChanged = { active ->
                if (currentMediaTarget.mode != MediaTargetMode.HOST) return@AndroidAudioPlayer
                isActivelyPlaying = isRunning && active
                isMediaPlaying = isActivelyPlaying
                onPipStateNeedsRefresh?.invoke()
                if (isActivelyPlaying) {
                    cancelPendingDemote()
                    acquireLocks()
                    promoteToForeground("Reproduciendo")
                } else {
                    scheduleDemoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
                }
            },
            onMediaNotification = { title, artist, paused, coverUrl, trackPath, durationMs, positionMs, isFavorite, isPauseAfter, album ->
                // En modo remoto ignoramos metadatos locales para no pisar la sesión del servidor remoto
                if (currentMediaTarget.mode != MediaTargetMode.HOST) return@AndroidAudioPlayer
                applyMediaUpdate(
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
            },
            onPositionNotification = { durationMs, positionMs, paused ->
                if (currentMediaTarget.mode != MediaTargetMode.HOST) return@AndroidAudioPlayer
                applyPositionUpdate(durationMs, positionMs, paused)
            },
        )
        audioPlayer.initialize()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            Intent.ACTION_MEDIA_BUTTON -> {
                if (!isInForeground) {
                    // MediaButtonReceiver inicia con startForegroundService() en Android 8+: cumplir contrato antes de retornar
                    promoteToForeground("La Rockola", ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
                }
                notificationManager.handleMediaButtonIntent(intent)
                return START_NOT_STICKY
            }
            ACTION_STOP -> {
                stopServerAndService()
                return START_NOT_STICKY
            }
            ACTION_MEDIA_PREV -> {
                notificationManager.dispatchAction("prev")
                return START_NOT_STICKY
            }
            ACTION_MEDIA_PLAY_PAUSE -> {
                val targetPaused = !notificationManager.isPaused
                notificationManager.dispatchAction("pause", mapOf("state" to targetPaused))
                return START_NOT_STICKY
            }
            ACTION_MEDIA_NEXT -> {
                notificationManager.dispatchAction("skip")
                return START_NOT_STICKY
            }
            ACTION_MEDIA_FAVORITE -> {
                notificationManager.toggleFavorite()
                return START_NOT_STICKY
            }
            ACTION_MEDIA_PAUSE_AFTER -> {
                notificationManager.togglePauseAfter()
                return START_NOT_STICKY
            }
            ACTION_UPDATE_MEDIA -> {
                val startedAsForeground = intent.getBooleanExtra(EXTRA_STARTED_AS_FOREGROUND, false)
                if (startedAsForeground && !isInForeground) {
                    promoteToForeground("La Rockola")
                }
                val title = intent.getStringExtra(EXTRA_TITLE)?.takeIf { it.isNotBlank() }
                    ?: "La Rockola del Carpincho"
                val artist = intent.getStringExtra(EXTRA_ARTIST)?.takeIf { it.isNotBlank() }
                    ?: "La Rockola del Carpincho"
                val album = intent.getStringExtra(EXTRA_ALBUM)?.takeIf { it.isNotBlank() }
                val paused = intent.getBooleanExtra(EXTRA_PAUSED, true)
                val coverUrl = intent.getStringExtra(EXTRA_COVER_URL)?.takeIf { it.isNotBlank() }
                val trackPath = intent.getStringExtra(EXTRA_TRACK_PATH)?.takeIf { it.isNotBlank() }
                val durationMs = intent.getLongExtra(EXTRA_DURATION_MS, 0L).coerceAtLeast(0L)
                val positionMs = intent.getLongExtra(EXTRA_POSITION_MS, 0L).coerceAtLeast(0L)
                val isFavorite = intent.getBooleanExtra(EXTRA_IS_FAVORITE, false)
                val isPauseAfter = intent.getBooleanExtra(EXTRA_IS_PAUSE_AFTER, false)

                applyMediaUpdate(
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
                return START_NOT_STICKY
            }
        }

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val requestedPort = intent?.getIntExtra(EXTRA_PORT, -1) ?: -1
        val port = if (requestedPort > 0) requestedPort else prefs.getInt(KEY_PORT, DEFAULT_PORT)

        val extraDir = intent?.getStringExtra(EXTRA_MUSIC_DIR)?.trim()
        val savedDir = prefs.getString(KEY_MUSIC_DIR, null)?.trim()
        val musicDir = if (!extraDir.isNullOrEmpty()) extraDir else savedDir

        prefs.edit().apply {
            putInt(KEY_PORT, port)
            if (!musicDir.isNullOrEmpty()) {
                putString(KEY_MUSIC_DIR, musicDir)
            }
            apply()
        }

        currentPort = port
        currentMusicDir = musicDir
        if (currentMediaTarget.mode == MediaTargetMode.HOST) {
            val hostTarget = MediaTarget(
                mode = MediaTargetMode.HOST,
                origin = "http://127.0.0.1:$port",
                generation = currentMediaTarget.generation,
            )
            currentMediaTarget = hostTarget
            commandClient.setTarget(hostTarget)
        }

        mainHandler.removeCallbacks(remoteIdleCheckRunnable)
        val startedAsForeground = intent?.getBooleanExtra(EXTRA_STARTED_AS_FOREGROUND, false) ?: false
        val needsForeground = ServicePowerPolicy.shouldUseForeground(
            isHostRunning = true,
            isMediaPlaying = isMediaPlaying,
            isRadioSynthesizing = isRadioSynthesizing(),
            hasRemoteClients = hasConnectedRemoteClients(),
        )
        if (startedAsForeground && !isInForeground) {
            promoteToForeground("La Rockola")
        }
        if (!needsForeground) {
            demoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
        }

        startEmbeddedPythonServer(port, musicDir)

        return START_NOT_STICKY
    }

    private fun applyTargetOnMain(target: MediaTarget) {
        currentMediaTarget = target
        isMediaPlaying = false
        isActivelyPlaying = false
        demoteFromForeground(keepDismissibleNotification = false)
        commandClient.setTarget(target)
        notificationManager.setTarget(target, allowNotificationCancel = true)
        onPipStateNeedsRefresh?.invoke()
    }

    private fun applyPositionUpdate(durationMs: Long, positionMs: Long, paused: Boolean) {
        val active = (isRunning || currentMediaTarget.mode == MediaTargetMode.REMOTE) &&
            !paused && notificationManager.hasActiveTrack
        isMediaPlaying = active
        isActivelyPlaying = currentMediaTarget.mode == MediaTargetMode.HOST && active
        notificationManager.updatePosition(durationMs, positionMs, paused)
        onPipStateNeedsRefresh?.invoke()
        if (active) {
            cancelPendingDemote()
            acquireLocks()
            promoteToForeground("Reproduciendo")
        } else {
            scheduleDemoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
        }
    }

    private fun applyMediaUpdate(
        title: String,
        artist: String,
        album: String? = null,
        paused: Boolean,
        coverUrl: String?,
        trackPath: String?,
        durationMs: Long,
        positionMs: Long,
        isFavorite: Boolean,
        isPauseAfter: Boolean,
    ) {
        val canNotify = isRunning || currentMediaTarget.mode == MediaTargetMode.REMOTE
        val hasTrack = !trackPath.isNullOrBlank()
        val active = canNotify && !paused && hasTrack
        isMediaPlaying = active
        isActivelyPlaying = currentMediaTarget.mode == MediaTargetMode.HOST && active

        notificationManager.updateMedia(
            title = title,
            artist = artist,
            paused = paused,
            coverUrl = coverUrl,
            trackPath = trackPath,
            durationMs = durationMs,
            positionMs = positionMs,
            isFavorite = isFavorite,
            isPauseAfter = isPauseAfter,
            postNotification = false,
            album = album,
        )
        if (hasTrack) {
            ShortcutHelper.saveLastTrackTitleAndRefresh(this, title)
        }
        onPipStateNeedsRefresh?.invoke()
        if (active) {
            cancelPendingDemote()
            acquireLocks()
            promoteToForeground(artist)
        } else if (hasTrack && canNotify) {
            // En pausa soltamos locks y foreground tras breve margen para no romper transiciones entre pistas
            scheduleDemoteFromForeground(keepDismissibleNotification = true)
        } else if (!canNotify) {
            demoteFromForeground(keepDismissibleNotification = false)
        } else {
            scheduleDemoteFromForeground(keepDismissibleNotification = false)
        }
    }

    private fun startEmbeddedPythonServer(port: Int, musicDir: String?) {
        hostCoordinator.start(
            port = port,
            musicDir = musicDir,
            onRequestStop = { pythonHost.stop() },
        ) { onReady ->
            pythonHost.startBlocking(
                port = port,
                musicDir = musicDir,
                onConfigured = { endpoint ->
                    currentLocalIp = endpoint.localIp
                    currentServerUrl = endpoint.serverUrl
                },
                onReady = {
                    onReady()
                },
            )
        }
    }

    private fun hasConnectedRemoteClients(): Boolean {
        if (!isRunning) return false
        return try {
            val py = com.chaquo.python.Python.getInstance()
            py.getModule("app.android_entry").callAttr("get_connected_remote_clients").toInt() > 0
        } catch (_: Throwable) {
            false
        }
    }

    private fun isRadioSynthesizing(): Boolean {
        if (!isRunning) return false
        return try {
            val py = com.chaquo.python.Python.getInstance()
            py.getModule("app.android_entry").callAttr("is_radio_synthesizing").toBoolean()
        } catch (_: Throwable) {
            false
        }
    }

    private fun acquireLocks() {
        if (wakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "RockolaCarpincho::ServerWakeLock").apply {
                setReferenceCounted(false)
            }
        }
        try {
            wakeLock?.acquire(WAKELOCK_TIMEOUT_MS)
        } catch (_: Exception) {
        }

        val needsWifi = ServicePowerPolicy.shouldAcquireWifiLock(
            currentMediaTarget.mode,
            hasConnectedRemoteClients(),
            isActivePlaybackOrRadio = isMediaPlaying || isRadioSynthesizing(),
        )
        if (needsWifi) {
            if (wifiLock == null) {
                val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    WifiManager.WIFI_MODE_FULL_LOW_LATENCY
                } else {
                    @Suppress("DEPRECATION")
                    WifiManager.WIFI_MODE_FULL_HIGH_PERF
                }
                wifiLock = wm.createWifiLock(mode, "RockolaCarpincho::ServerWifiLock").apply {
                    setReferenceCounted(false)
                }
            }
            try {
                if (wifiLock?.isHeld == false) wifiLock?.acquire()
            } catch (_: Exception) {
            }
        } else {
            try {
                if (wifiLock?.isHeld == true) wifiLock?.release()
            } catch (_: Exception) {
            }
            wifiLock = null
        }
    }

    private fun releaseLocks() {
        try {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        } catch (_: Exception) {
        }
        wakeLock = null
        try {
            if (wifiLock?.isHeld == true) wifiLock?.release()
        } catch (_: Exception) {
        }
        wifiLock = null
    }

    private val remoteIdleCheckRunnable = object : Runnable {
        override fun run() {
            if (!isRunning || isMediaPlaying) return
            if (ServicePowerPolicy.shouldStopAfterRemoteGrace(
                    taskRemoved = true,
                    isMediaPlaying = isMediaPlaying,
                    hasRemoteClients = hasConnectedRemoteClients(),
                )
            ) {
                stopServerAndService()
            } else {
                mainHandler.postDelayed(this, 15_000L)
            }
        }
    }

    private fun syncForegroundWithUiVisibility(visible: Boolean) {
        if (currentMediaTarget.mode != MediaTargetMode.HOST) return
        val needsForeground = ServicePowerPolicy.shouldUseForeground(
            isHostRunning = isRunning,
            isMediaPlaying = isMediaPlaying,
            isRadioSynthesizing = isRadioSynthesizing(),
            hasRemoteClients = hasConnectedRemoteClients(),
        )
        if (!needsForeground && isInForeground) {
            if (visible) {
                demoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
            } else {
                scheduleDemoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
            }
        }
    }

    private fun promoteToForeground(
        text: String,
        serviceType: Int = ServicePowerPolicy.foregroundServiceType(
            isMediaPlaying,
            hasConnectedRemoteClients(),
            isRadioSynthesizing(),
        ),
    ) {
        cancelPendingDemote()
        if (isInForeground && (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || currentForegroundType == serviceType)) {
            notificationManager.notifyCurrentState()
            return
        }
        val notification = notificationManager.buildNotification(text)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification, serviceType)
                currentForegroundType = serviceType
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
            isInForeground = true
        } catch (e: Exception) {
            isInForeground = false
            currentForegroundType = 0
            Log.w("RockolaService", "No se pudo promover a foreground: ${e.message}")
            notificationManager.notifyCurrentState()
        }
    }

    private fun demoteFromForeground(keepDismissibleNotification: Boolean, forceStop: Boolean = false) {
        cancelPendingDemote()
        val shouldStopFg = ServicePowerPolicy.shouldStopForeground(
            isHostRunning = isRunning,
            hasRemoteClients = hasConnectedRemoteClients(),
            isUiVisible = isUiVisible,
            isRadioSynthesizing = isRadioSynthesizing(),
            forceStop = forceStop,
        )
        if (!shouldStopFg) {
            return
        }
        releaseLocks()
        if (isInForeground) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                val mode = if (keepDismissibleNotification) STOP_FOREGROUND_DETACH else STOP_FOREGROUND_REMOVE
                stopForeground(mode)
            } else {
                @Suppress("DEPRECATION")
                stopForeground(!keepDismissibleNotification)
            }
            isInForeground = false
            currentForegroundType = 0
        }
        if (keepDismissibleNotification && notificationManager.hasActiveTrack) {
            notificationManager.notifyCurrentState()
        } else if (!keepDismissibleNotification) {
            notificationManager.cancelNotification()
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        val hasRemotes = hasConnectedRemoteClients()
        if (ServicePowerPolicy.shouldStopOnTaskRemoved(isMediaPlaying, hasRemotes)) {
            stopServerAndService()
        } else if (!isMediaPlaying && hasRemotes) {
            if (!isInForeground) {
                promoteToForeground("Sirviendo a clientes remotos", ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            }
            mainHandler.removeCallbacks(remoteIdleCheckRunnable)
            mainHandler.postDelayed(remoteIdleCheckRunnable, 15_000L)
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onTimeout(startId: Int) {
        handleServiceTimeout(startId, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        handleServiceTimeout(startId, fgsType)
    }

    private fun handleServiceTimeout(startId: Int, fgsType: Int) {
        Log.w("RockolaService", "onTimeout recibido (startId=$startId, fgsType=$fgsType, isMediaPlaying=$isMediaPlaying)")
        // Android 15 retira el estado foreground al invocar onTimeout y exige stopSelf() inmediato.
        // No se debe promover a mediaPlayback dentro de onTimeout.
        ServicePowerPolicy.resolveTimeout(fgsType = fgsType, isMediaPlaying = isMediaPlaying)
        stopOnTimeout(startId)
    }

    private fun stopOnTimeout(startId: Int) {
        onNativeCommandError?.invoke(
            "host_server",
            "FGS_TIMEOUT",
            "Android detuvo el servidor en segundo plano porque expiró el límite de sincronización sin música sonando.",
        )
        isActivelyPlaying = false
        isMediaPlaying = false
        demoteFromForeground(keepDismissibleNotification = false, forceStop = true)
        processShutdownExecutor.execute {
            hostCoordinator.stop(STOP_JOIN_TIMEOUT_MS)
            syncProcessCoordinatorSnapshot()
        }
        stopSelf(startId)
    }

    private fun syncCoordinatorSnapshot() {
        isRunning = hostCoordinator.isRunning
        hasActiveWorker = hostCoordinator.hasActiveWorker
        hostState = hostCoordinator.state
        lastHostError = hostCoordinator.lastError
    }

    private fun stopServerBlocking(timeoutMs: Long): Boolean {
        isActivelyPlaying = false
        isMediaPlaying = false
        mainHandler.post {
            demoteFromForeground(keepDismissibleNotification = false, forceStop = true)
        }
        val clean = hostCoordinator.stop(timeoutMs)
        syncCoordinatorSnapshot()
        if (clean) {
            mainHandler.post {
                stopSelf()
            }
        }
        return clean
    }

    private fun stopServerAndService() {
        isActivelyPlaying = false
        isMediaPlaying = false
        demoteFromForeground(keepDismissibleNotification = false, forceStop = true)
        backgroundExecutor.execute {
            val clean = hostCoordinator.stop(STOP_JOIN_TIMEOUT_MS)
            syncCoordinatorSnapshot()
            if (clean) {
                mainHandler.post {
                    stopSelf()
                }
            }
        }
    }

    override fun onDestroy() {
        mainHandler.removeCallbacks(remoteIdleCheckRunnable)
        cancelPendingDemote()
        val wasActiveInstance = activeInstance === this
        if (wasActiveInstance) {
            hostCoordinator.setStateListener(null)
            onPipStateNeedsRefresh = null
            onNativeCommandError = null
        }
        isActivelyPlaying = false
        isMediaPlaying = false
        demoteFromForeground(keepDismissibleNotification = false, forceStop = true)
        notificationManager.release()
        if (::audioPlayer.isInitialized) {
            audioPlayer.release()
        }
        commandClient.shutdown()
        backgroundExecutor.shutdownNow()
        if (wasActiveInstance) {
            activeInstance = null
        }
        if (hostCoordinator.hasActiveWorker) {
            // No bloquear el main thread ni destruir el coordinador del proceso mientras el worker siga vivo
            processShutdownExecutor.execute {
                hostCoordinator.stop(STOP_JOIN_TIMEOUT_MS)
                syncProcessCoordinatorSnapshot()
            }
        }
        syncProcessCoordinatorSnapshot()
        super.onDestroy()
    }
}
