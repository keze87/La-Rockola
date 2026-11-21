package ar.carpincho.rockola

import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Servicio en primer plano orquestador que mantiene vivo el servidor FastAPI/Uvicorn
 * sobre Chaquopy, junto con WakeLock, WifiLock, AudioFocus, protección al desconectar
 * auriculares y el administrador de notificaciones multimedia.
 */
class RockolaForegroundService : Service() {

    companion object {
        const val PREFS_NAME = "rockola_android_prefs"
        const val KEY_MUSIC_DIR = "music_dir"
        const val KEY_PORT = "port"

        const val ACTION_START = "ar.carpincho.rockola.ACTION_START"
        const val ACTION_STOP = "ar.carpincho.rockola.ACTION_STOP"
        const val ACTION_MEDIA_PREV = "ar.carpincho.rockola.ACTION_MEDIA_PREV"
        const val ACTION_MEDIA_PLAY_PAUSE = "ar.carpincho.rockola.ACTION_MEDIA_PLAY_PAUSE"
        const val ACTION_MEDIA_NEXT = "ar.carpincho.rockola.ACTION_MEDIA_NEXT"
        const val ACTION_MEDIA_FAVORITE = "ar.carpincho.rockola.ACTION_MEDIA_FAVORITE"
        const val ACTION_MEDIA_PAUSE_AFTER = "ar.carpincho.rockola.ACTION_MEDIA_PAUSE_AFTER"
        const val ACTION_UPDATE_MEDIA = "ar.carpincho.rockola.ACTION_UPDATE_MEDIA"
        const val ACTION_UPDATE_POSITION = "ar.carpincho.rockola.ACTION_UPDATE_POSITION"

        const val CUSTOM_ACTION_FAVORITE = "ar.carpincho.rockola.CUSTOM_FAVORITE"
        const val CUSTOM_ACTION_PAUSE_AFTER = "ar.carpincho.rockola.CUSTOM_PAUSE_AFTER"

        const val EXTRA_PORT = "port"
        const val EXTRA_MUSIC_DIR = "music_dir"
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

        @Volatile
        var isRunning: Boolean = false
            private set

        @Volatile
        var isActivelyPlaying: Boolean = false
            private set

        @Volatile
        var currentPort: Int = DEFAULT_PORT
            private set

        @Volatile
        var currentMusicDir: String? = null
            private set

        @Volatile
        var currentServerUrl: String = "http://127.0.0.1:$DEFAULT_PORT"
            private set

        @Volatile
        var currentLocalIp: String = "127.0.0.1"
            private set
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var serverThread: Thread? = null

    private lateinit var commandClient: LocalCommandClient
    private lateinit var pythonHost: EmbeddedPythonHost
    private lateinit var notificationManager: MediaNotificationManager
    private lateinit var audioManager: AudioManager
    private var focusRequest: AudioFocusRequest? = null
    private var hasAudioFocus: Boolean = false
    private var pausedByTransientFocusLoss: Boolean = false

    private val noisyReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY && !notificationManager.isPaused) {
                commandClient.sendCommand("pause")
            }
        }
    }

    private val audioFocusListener = AudioManager.OnAudioFocusChangeListener { focusChange ->
        when (focusChange) {
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> {
                hasAudioFocus = false
                if (!notificationManager.isPaused) {
                    pausedByTransientFocusLoss = true
                    commandClient.sendCommand("pause")
                }
            }
            AudioManager.AUDIOFOCUS_LOSS -> {
                hasAudioFocus = false
                pausedByTransientFocusLoss = false
                if (!notificationManager.isPaused) {
                    commandClient.sendCommand("pause")
                }
            }
            AudioManager.AUDIOFOCUS_GAIN -> {
                hasAudioFocus = true
                if (pausedByTransientFocusLoss) {
                    pausedByTransientFocusLoss = false
                    if (notificationManager.isPaused) {
                        commandClient.sendCommand("pause")
                    }
                }
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        commandClient = LocalCommandClient { currentPort }
        pythonHost = EmbeddedPythonHost(this)
        notificationManager = MediaNotificationManager(
            service = this,
            channelId = CHANNEL_ID,
            notificationId = NOTIFICATION_ID,
            onCommand = { cmd, extra -> commandClient.sendCommand(cmd, extra) },
            onRequestArtwork = { coverUrl ->
                commandClient.fetchArtwork(coverUrl) { bmp ->
                    notificationManager.applyArtworkIfCurrent(coverUrl, bmp)
                }
            },
            onPlayRequested = { requestAudioFocus() },
        )
        notificationManager.initialize()

        ContextCompat.registerReceiver(
            this,
            noisyReceiver,
            IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopServerAndService()
                return START_NOT_STICKY
            }
            ACTION_MEDIA_PREV -> {
                commandClient.sendCommand("prev")
                return START_STICKY
            }
            ACTION_MEDIA_PLAY_PAUSE -> {
                if (notificationManager.isPaused) {
                    requestAudioFocus()
                }
                commandClient.sendCommand("pause")
                return START_STICKY
            }
            ACTION_MEDIA_NEXT -> {
                commandClient.sendCommand("skip")
                return START_STICKY
            }
            ACTION_MEDIA_FAVORITE -> {
                notificationManager.toggleFavorite()
                return START_STICKY
            }
            ACTION_MEDIA_PAUSE_AFTER -> {
                notificationManager.togglePauseAfter()
                return START_STICKY
            }
            ACTION_UPDATE_POSITION -> {
                val durationMs = intent.getLongExtra(EXTRA_DURATION_MS, 0L).coerceAtLeast(0L)
                val positionMs = intent.getLongExtra(EXTRA_POSITION_MS, 0L).coerceAtLeast(0L)
                val paused = intent.getBooleanExtra(EXTRA_PAUSED, notificationManager.isPaused)
                isActivelyPlaying = isRunning && !paused
                if (!paused) requestAudioFocus()
                notificationManager.updatePosition(durationMs, positionMs, paused)
                return START_STICKY
            }
            ACTION_UPDATE_MEDIA -> {
                val title = intent.getStringExtra(EXTRA_TITLE)?.takeIf { it.isNotBlank() }
                    ?: "La Rockola del Carpincho"
                val artist = intent.getStringExtra(EXTRA_ARTIST)?.takeIf { it.isNotBlank() }
                    ?: "En espera"
                val paused = intent.getBooleanExtra(EXTRA_PAUSED, true)
                val coverUrl = intent.getStringExtra(EXTRA_COVER_URL)?.takeIf { it.isNotBlank() }
                val trackPath = intent.getStringExtra(EXTRA_TRACK_PATH)?.takeIf { it.isNotBlank() }
                val durationMs = intent.getLongExtra(EXTRA_DURATION_MS, 0L).coerceAtLeast(0L)
                val positionMs = intent.getLongExtra(EXTRA_POSITION_MS, 0L).coerceAtLeast(0L)
                val isFavorite = intent.getBooleanExtra(EXTRA_IS_FAVORITE, false)
                val isPauseAfter = intent.getBooleanExtra(EXTRA_IS_PAUSE_AFTER, false)

                isActivelyPlaying = isRunning && !paused
                if (!paused) {
                    pausedByTransientFocusLoss = false
                    requestAudioFocus()
                }
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
                )
                return START_STICKY
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

        startForegroundWithNotification("Iniciando servidor en el puerto $port...")
        acquireLocks()

        if (!isRunning) {
            isRunning = true
            startEmbeddedPythonServer(port, musicDir)
        }

        return START_STICKY
    }

    private fun startEmbeddedPythonServer(port: Int, musicDir: String?) {
        serverThread = Thread({
            try {
                pythonHost.startBlocking(port = port, musicDir = musicDir) { endpoint ->
                    currentLocalIp = endpoint.localIp
                    currentServerUrl = endpoint.serverUrl
                    notificationManager.updateServerEndpoint(
                        serverUrl = endpoint.serverUrl,
                        statusText = "Sonando en ${endpoint.serverUrl}",
                    )
                }
            } catch (e: Exception) {
                Log.e("RockolaService", "Error fatal en servidor Python embebido", e)
                notificationManager.notify("Error en servidor: ${e.message ?: "fallo desconocido"}")
            } finally {
                isRunning = false
                isActivelyPlaying = false
                releaseLocks()
            }
        }, "RockolaUvicornThread").apply {
            isDaemon = true
            start()
        }
    }

    private fun requestAudioFocus() {
        if (hasAudioFocus) return
        val result = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val req = focusRequest ?: AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build(),
                )
                .setOnAudioFocusChangeListener(audioFocusListener)
                .build()
                .also { focusRequest = it }
            audioManager.requestAudioFocus(req)
        } else {
            @Suppress("DEPRECATION")
            audioManager.requestAudioFocus(
                audioFocusListener,
                AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN,
            )
        }
        hasAudioFocus = (result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED)
    }

    private fun abandonAudioFocus() {
        hasAudioFocus = false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            focusRequest?.let { audioManager.abandonAudioFocusRequest(it) }
        } else {
            @Suppress("DEPRECATION")
            audioManager.abandonAudioFocus(audioFocusListener)
        }
    }

    private fun acquireLocks() {
        if (wakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "RockolaCarpincho::ServerWakeLock").apply {
                setReferenceCounted(false)
                acquire()
            }
        }
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
                acquire()
            }
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

    private fun stopServerAndService() {
        pythonHost.stop()
        isRunning = false
        isActivelyPlaying = false
        abandonAudioFocus()
        releaseLocks()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    override fun onDestroy() {
        pythonHost.stop()
        try {
            unregisterReceiver(noisyReceiver)
        } catch (_: Exception) {
        }
        notificationManager.release()
        commandClient.shutdown()
        abandonAudioFocus()
        isRunning = false
        isActivelyPlaying = false
        releaseLocks()
        super.onDestroy()
    }

    private fun startForegroundWithNotification(text: String) {
        val notification = notificationManager.buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }
}
