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
 * Reglas puras de energía y ciclo de vida en segundo plano (testeables en JVM).
 */
internal object ServicePowerPolicy {
    fun shouldAcquireWifiLock(mode: MediaTargetMode, hasRemoteClients: Boolean): Boolean {
        return mode == MediaTargetMode.REMOTE || hasRemoteClients
    }

    fun shouldStopOnTaskRemoved(isMediaPlaying: Boolean, hasRemoteClients: Boolean): Boolean {
        return !isMediaPlaying && !hasRemoteClients
    }

    fun shouldStopForeground(keepDismissibleNotification: Boolean, isHostRunning: Boolean): Boolean {
        return !keepDismissibleNotification || !isHostRunning
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

        const val ACTION_START = "ar.carpincho.rockola.ACTION_START"
        const val ACTION_STOP = "ar.carpincho.rockola.ACTION_STOP"
        const val ACTION_SET_MEDIA_TARGET = "ar.carpincho.rockola.ACTION_SET_MEDIA_TARGET"
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
        const val ACTION_UPDATE_POSITION = "ar.carpincho.rockola.ACTION_UPDATE_POSITION"

        const val CUSTOM_ACTION_FAVORITE = "ar.carpincho.rockola.CUSTOM_FAVORITE"
        const val CUSTOM_ACTION_PAUSE_AFTER = "ar.carpincho.rockola.CUSTOM_PAUSE_AFTER"

        const val EXTRA_PORT = "port"
        const val EXTRA_MUSIC_DIR = "music_dir"
        const val EXTRA_STARTED_AS_FOREGROUND = "started_as_foreground"
        const val EXTRA_TARGET_MODE = "target_mode"
        const val EXTRA_TARGET_ORIGIN = "target_origin"
        const val EXTRA_TARGET_AUTH = "target_auth"
        const val EXTRA_TARGET_GENERATION = "target_generation"
        const val EXTRA_TITLE = "media_title"
        const val EXTRA_ARTIST = "media_artist"
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
        private var activeInstance: RockolaForegroundService? = null

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
        internal var onPipStateNeedsRefresh: (() -> Unit)? = null

        @Volatile
        internal var onNativeCommandError: ((cmd: String, code: String, message: String) -> Unit)? = null

        internal fun requestStopAndAwait(context: Context, timeoutMs: Long = STOP_JOIN_TIMEOUT_MS): Boolean {
            val instance = activeInstance
            if (instance != null) {
                return instance.stopServerBlocking(timeoutMs)
            }
            if (isRunning) {
                val intent = Intent(context, RockolaForegroundService::class.java).apply {
                    action = ACTION_STOP
                }
                try {
                    context.startService(intent)
                } catch (_: Exception) {
                    // Si Android bloquea startService en segundo plano al pedir stop, respetamos !isRunning
                }
            }
            return !isRunning
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private val stopExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private val nativeCommandExecutor: ExecutorService = Executors.newFixedThreadPool(2) { runnable ->
        Thread(runnable, "RockolaNativeCmd").apply { isDaemon = true }
    }

    @Volatile
    private var isInForeground: Boolean = false

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
        hostCoordinator = HostLifecycleCoordinator(
            onStateChanged = { nextState, err ->
                hostState = nextState
                lastHostError = err
                isRunning = hostCoordinator.isRunning
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
                        mainHandler.post { demoteFromForeground(keepDismissibleNotification = false) }
                    }
                }
            },
        )
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
                    nativeCommandExecutor.execute {
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
                    acquireLocks()
                    promoteToForeground("Reproduciendo")
                } else {
                    demoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
                }
            },
            onMediaNotification = { title, artist, paused, coverUrl, trackPath, durationMs, positionMs, isFavorite, isPauseAfter ->
                // En modo remoto ignoramos metadatos locales para no pisar la sesión del servidor remoto
                if (currentMediaTarget.mode != MediaTargetMode.HOST) return@AndroidAudioPlayer
                applyMediaUpdate(
                    title = title,
                    artist = artist,
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
        // Cumplimos de inmediato el contrato de startForegroundService antes de procesar demotes
        val startedAsForeground = intent?.getBooleanExtra(EXTRA_STARTED_AS_FOREGROUND, false) ?: false
        if (startedAsForeground && !isInForeground) {
            promoteToForeground("Preparando reproducción...")
        }

        when (intent?.action) {
            ACTION_STOP -> {
                stopServerAndService()
                return START_NOT_STICKY
            }
            ACTION_SET_MEDIA_TARGET -> {
                val modeStr = intent.getStringExtra(EXTRA_TARGET_MODE) ?: "host"
                val mode = if (modeStr == "remote") MediaTargetMode.REMOTE else MediaTargetMode.HOST
                val origin = intent.getStringExtra(EXTRA_TARGET_ORIGIN)
                    ?: "http://127.0.0.1:$currentPort"
                val auth = intent.getStringExtra(EXTRA_TARGET_AUTH)
                val gen = intent.getLongExtra(EXTRA_TARGET_GENERATION, currentMediaTarget.generation)
                val target = MediaTarget(mode = mode, origin = origin, authHeader = auth, generation = gen)
                currentMediaTarget = target
                isMediaPlaying = false
                isActivelyPlaying = false
                demoteFromForeground(keepDismissibleNotification = false)
                commandClient.setTarget(target)
                notificationManager.setTarget(target, allowNotificationCancel = true)
                onPipStateNeedsRefresh?.invoke()
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
            ACTION_UPDATE_POSITION -> {
                val durationMs = intent.getLongExtra(EXTRA_DURATION_MS, 0L).coerceAtLeast(0L)
                val positionMs = intent.getLongExtra(EXTRA_POSITION_MS, 0L).coerceAtLeast(0L)
                val paused = intent.getBooleanExtra(EXTRA_PAUSED, notificationManager.isPaused)
                applyPositionUpdate(durationMs, positionMs, paused)
                return START_NOT_STICKY
            }
            ACTION_UPDATE_MEDIA -> {
                val title = intent.getStringExtra(EXTRA_TITLE)?.takeIf { it.isNotBlank() }
                    ?: "La Rockola del Carpincho"
                val artist = intent.getStringExtra(EXTRA_ARTIST)?.takeIf { it.isNotBlank() }
                    ?: "La Rockola del Carpincho"
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

        if (!isMediaPlaying) {
            demoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
        }

        startEmbeddedPythonServer(port, musicDir)

        return START_NOT_STICKY
    }

    private fun applyPositionUpdate(durationMs: Long, positionMs: Long, paused: Boolean) {
        val active = (isRunning || currentMediaTarget.mode == MediaTargetMode.REMOTE) &&
            !paused && notificationManager.hasActiveTrack
        isMediaPlaying = active
        isActivelyPlaying = currentMediaTarget.mode == MediaTargetMode.HOST && active
        notificationManager.updatePosition(durationMs, positionMs, paused)
        onPipStateNeedsRefresh?.invoke()
        if (active) {
            acquireLocks()
            if (!isInForeground) {
                promoteToForeground("Reproduciendo")
            }
        } else {
            demoteFromForeground(keepDismissibleNotification = notificationManager.hasActiveTrack)
        }
    }

    private fun applyMediaUpdate(
        title: String,
        artist: String,
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
        )
        onPipStateNeedsRefresh?.invoke()
        if (active) {
            acquireLocks()
            promoteToForeground(artist)
        } else if (hasTrack && canNotify) {
            // En pausa soltamos locks y foreground dejando notificación descartable
            demoteFromForeground(keepDismissibleNotification = true)
        } else {
            demoteFromForeground(keepDismissibleNotification = false)
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
                    val endpointUrl = currentServerUrl
                    if (endpointUrl.isNotBlank()) {
                        notificationManager.updateServerEndpoint(
                            serverUrl = endpointUrl,
                            statusText = "Sonando en $endpointUrl",
                        )
                    }
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

    private fun promoteToForeground(text: String) {
        if (isInForeground) {
            notificationManager.notifyCurrentState()
            return
        }
        val notification = notificationManager.buildNotification(text)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
            isInForeground = true
        } catch (e: Exception) {
            isInForeground = false
            Log.w("RockolaService", "No se pudo promover a foreground: ${e.message}")
            notificationManager.notifyCurrentState()
        }
    }

    private fun demoteFromForeground(keepDismissibleNotification: Boolean) {
        releaseLocks()
        val shouldStopFg = ServicePowerPolicy.shouldStopForeground(keepDismissibleNotification, isRunning)
        if (isInForeground && shouldStopFg) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                val mode = if (keepDismissibleNotification) STOP_FOREGROUND_DETACH else STOP_FOREGROUND_REMOVE
                stopForeground(mode)
            } else {
                @Suppress("DEPRECATION")
                stopForeground(!keepDismissibleNotification)
            }
            isInForeground = false
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
        } else if (!isMediaPlaying && hasRemotes && !isInForeground) {
            promoteToForeground("Sirviendo a clientes remotos")
        }
        super.onTaskRemoved(rootIntent)
    }

    private fun stopServerBlocking(timeoutMs: Long): Boolean {
        isActivelyPlaying = false
        isMediaPlaying = false
        mainHandler.post {
            demoteFromForeground(keepDismissibleNotification = false)
        }
        val clean = hostCoordinator.stop(timeoutMs)
        isRunning = hostCoordinator.isRunning
        hostState = hostCoordinator.state
        lastHostError = hostCoordinator.lastError
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
        demoteFromForeground(keepDismissibleNotification = false)
        stopExecutor.execute {
            val clean = hostCoordinator.stop(STOP_JOIN_TIMEOUT_MS)
            if (clean) {
                mainHandler.post {
                    stopSelf()
                }
            }
        }
    }

    override fun onDestroy() {
        if (activeInstance === this) {
            activeInstance = null
        }
        isActivelyPlaying = false
        isMediaPlaying = false
        hostCoordinator.stop(STOP_JOIN_TIMEOUT_MS)
        stopExecutor.shutdownNow()
        nativeCommandExecutor.shutdownNow()
        onPipStateNeedsRefresh = null
        onNativeCommandError = null
        demoteFromForeground(keepDismissibleNotification = false)
        notificationManager.release()
        if (::audioPlayer.isInitialized) {
            audioPlayer.release()
        }
        commandClient.shutdown()
        isRunning = false
        hostState = hostCoordinator.state
        lastHostError = hostCoordinator.lastError
        super.onDestroy()
    }
}
