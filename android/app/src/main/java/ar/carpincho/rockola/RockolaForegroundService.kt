package ar.carpincho.rockola

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.media.app.NotificationCompat.MediaStyle
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * Servicio en primer plano que mantiene vivo el servidor FastAPI/Uvicorn
 * ejecutado sobre Chaquopy, junto con WakeLock, WifiLock y controles MediaStyle
 * en la barra de notificaciones y pantalla de bloqueo.
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
        const val ACTION_UPDATE_MEDIA = "ar.carpincho.rockola.ACTION_UPDATE_MEDIA"

        const val EXTRA_PORT = "port"
        const val EXTRA_MUSIC_DIR = "music_dir"
        const val EXTRA_TITLE = "media_title"
        const val EXTRA_ARTIST = "media_artist"
        const val EXTRA_PAUSED = "media_paused"
        const val EXTRA_COVER_URL = "media_cover_url"

        private const val CHANNEL_ID = "rockola_server_channel"
        private const val NOTIFICATION_ID = 1729
        private const val DEFAULT_PORT = 1729

        @Volatile
        var isRunning: Boolean = false
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
    private var mediaSession: MediaSessionCompat? = null

    private var currentTitle: String = "La Rockola del Carpincho"
    private var currentArtist: String = "En espera"
    private var currentPaused: Boolean = true
    private var currentCoverUrl: String? = null
    private var currentArtwork: Bitmap? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        initMediaSession()
    }

    private fun initMediaSession() {
        mediaSession = MediaSessionCompat(this, "RockolaMediaSession").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() {
                    if (currentPaused) sendPlaybackCommand("pause")
                }

                override fun onPause() {
                    if (!currentPaused) sendPlaybackCommand("pause")
                }

                override fun onSkipToNext() {
                    sendPlaybackCommand("skip")
                }

                override fun onSkipToPrevious() {
                    sendPlaybackCommand("prev")
                }
            })
            isActive = true
        }
        syncMediaSessionState()
    }

    private fun syncMediaSessionState() {
        val session = mediaSession ?: return
        val stateCode = if (currentPaused) PlaybackStateCompat.STATE_PAUSED else PlaybackStateCompat.STATE_PLAYING
        val actions = PlaybackStateCompat.ACTION_PLAY or
            PlaybackStateCompat.ACTION_PAUSE or
            PlaybackStateCompat.ACTION_PLAY_PAUSE or
            PlaybackStateCompat.ACTION_SKIP_TO_NEXT or
            PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS

        session.setPlaybackState(
            PlaybackStateCompat.Builder()
                .setActions(actions)
                .setState(stateCode, PlaybackStateCompat.PLAYBACK_POSITION_UNKNOWN, 1.0f)
                .build()
        )
        session.setMetadata(
            MediaMetadataCompat.Builder()
                .putString(MediaMetadataCompat.METADATA_KEY_TITLE, currentTitle)
                .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, currentArtist)
                .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, "La Rockola del Carpincho")
                .apply {
                    currentArtwork?.let { putBitmap(MediaMetadataCompat.METADATA_KEY_ALBUM_ART, it) }
                }
                .build()
        )
    }

    private fun sendPlaybackCommand(cmd: String) {
        Thread({
            try {
                val url = URL("http://127.0.0.1:$currentPort/command")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    setRequestProperty("Content-Type", "application/json")
                    doOutput = true
                    connectTimeout = 2000
                    readTimeout = 2000
                }
                conn.outputStream.use { out ->
                    out.write("""{"cmd":"$cmd"}""".toByteArray(Charsets.UTF_8))
                }
                conn.responseCode
                conn.disconnect()
            } catch (e: Exception) {
                Log.w("RockolaService", "No se pudo despachar comando '$cmd' desde notificación: ${e.message}")
            }
        }, "RockolaMediaCmd-$cmd").apply {
            isDaemon = true
            start()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopServerAndService()
                return START_NOT_STICKY
            }
            ACTION_MEDIA_PREV -> {
                sendPlaybackCommand("prev")
                return START_STICKY
            }
            ACTION_MEDIA_PLAY_PAUSE -> {
                sendPlaybackCommand("pause")
                return START_STICKY
            }
            ACTION_MEDIA_NEXT -> {
                sendPlaybackCommand("skip")
                return START_STICKY
            }
            ACTION_UPDATE_MEDIA -> {
                val title = intent.getStringExtra(EXTRA_TITLE)?.takeIf { it.isNotBlank() }
                    ?: "La Rockola del Carpincho"
                val artist = intent.getStringExtra(EXTRA_ARTIST)?.takeIf { it.isNotBlank() }
                    ?: "En espera"
                val paused = intent.getBooleanExtra(EXTRA_PAUSED, true)
                val coverUrl = intent.getStringExtra(EXTRA_COVER_URL)?.takeIf { it.isNotBlank() }

                val coverChanged = coverUrl != currentCoverUrl
                currentTitle = title
                currentArtist = artist
                currentPaused = paused
                currentCoverUrl = coverUrl

                if (coverChanged) {
                    currentArtwork = null
                    if (coverUrl != null) {
                        fetchArtworkAsync(coverUrl)
                    }
                }
                syncMediaSessionState()
                updateNotification(currentArtist)
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

    private fun fetchArtworkAsync(coverUrl: String) {
        Thread({
            try {
                val conn = (URL(coverUrl).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 2500
                    readTimeout = 2500
                }
                val bmp = conn.inputStream.use { BitmapFactory.decodeStream(it) }
                conn.disconnect()
                if (bmp != null && coverUrl == currentCoverUrl) {
                    currentArtwork = bmp
                    syncMediaSessionState()
                    updateNotification(currentArtist)
                }
            } catch (_: Exception) {
            }
        }, "RockolaArtworkFetch").apply {
            isDaemon = true
            start()
        }
    }

    private fun startEmbeddedPythonServer(port: Int, musicDir: String?) {
        serverThread = Thread({
            try {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(applicationContext))
                }

                val dataDir = File(filesDir, "rockola_data").apply { mkdirs() }
                val distDir = File(filesDir, "dist")
                extractAssetFolder("dist", distDir)

                val py = Python.getInstance()
                val entry = py.getModule("app.android_entry")

                val infoObj = entry.callAttr(
                    "configure_android_environment",
                    dataDir.absolutePath,
                    distDir.absolutePath,
                    musicDir ?: "",
                    port,
                    "0.0.0.0"
                )
                val infoMap = infoObj.asMap()
                val localIp = infoMap[py.builtins.callAttr("str", "local_ip")]?.toString() ?: "127.0.0.1"
                val serverUrl = infoMap[py.builtins.callAttr("str", "server_url")]?.toString()
                    ?: "http://$localIp:$port"

                currentLocalIp = localIp
                currentServerUrl = serverUrl
                currentTitle = "La Rockola del Carpincho"
                currentArtist = "Sonando en $serverUrl"
                syncMediaSessionState()
                updateNotification(currentArtist)

                Log.i("RockolaService", "Arrancando Uvicorn embebido en $serverUrl...")
                entry.callAttr(
                    "start_embedded_server",
                    dataDir.absolutePath,
                    distDir.absolutePath,
                    musicDir ?: "",
                    port,
                    "0.0.0.0"
                )
            } catch (e: Exception) {
                Log.e("RockolaService", "Error fatal en servidor Python embebido", e)
                updateNotification("Error en servidor: ${e.message ?: "fallo desconocido"}")
            } finally {
                isRunning = false
                releaseLocks()
            }
        }, "RockolaUvicornThread").apply {
            isDaemon = true
            start()
        }
    }

    private fun extractAssetFolder(assetPath: String, targetDir: File) {
        val entries = assets.list(assetPath) ?: return
        if (entries.isEmpty()) {
            targetDir.parentFile?.mkdirs()
            assets.open(assetPath).use { input ->
                FileOutputStream(targetDir).use { output ->
                    input.copyTo(output)
                }
            }
            return
        }
        targetDir.mkdirs()
        for (entry in entries) {
            extractAssetFolder("$assetPath/$entry", File(targetDir, entry))
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
        try {
            if (Python.isStarted()) {
                Python.getInstance().getModule("app.android_entry").callAttr("stop_embedded_server")
            }
        } catch (_: Exception) {
        }
        isRunning = false
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
        try {
            if (Python.isStarted()) {
                Python.getInstance().getModule("app.android_entry").callAttr("stop_embedded_server")
            }
        } catch (_: Exception) {
        }
        mediaSession?.isActive = false
        mediaSession?.release()
        mediaSession = null
        isRunning = false
        releaseLocks()
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Servidor de La Rockola",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Mantiene el servidor musical, la reproducción y los controles activos"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun serviceActionPendingIntent(action: String, requestCode: Int): PendingIntent {
        val intent = Intent(this, RockolaForegroundService::class.java).apply {
            this.action = action
        }
        return PendingIntent.getService(
            this,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun buildNotification(contentText: String): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPending = PendingIntent.getActivity(
            this,
            0,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val prevPending = serviceActionPendingIntent(ACTION_MEDIA_PREV, 2)
        val playPausePending = serviceActionPendingIntent(ACTION_MEDIA_PLAY_PAUSE, 3)
        val nextPending = serviceActionPendingIntent(ACTION_MEDIA_NEXT, 4)
        val stopPending = serviceActionPendingIntent(ACTION_STOP, 1)

        val playPauseIcon = if (currentPaused) android.R.drawable.ic_media_play else android.R.drawable.ic_media_pause
        val playPauseLabel = if (currentPaused) "Reproducir" else "Pausar"

        val largeIcon = currentArtwork ?: BitmapFactory.decodeResource(resources, R.mipmap.ic_launcher)

        val mediaStyle = MediaStyle()
            .setShowActionsInCompactView(0, 1, 2)
        mediaSession?.sessionToken?.let { mediaStyle.setMediaSession(it) }

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(currentTitle)
            .setContentText(contentText)
            .setSubText(currentServerUrl)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setLargeIcon(largeIcon)
            .setContentIntent(openPending)
            .setOngoing(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(android.R.drawable.ic_media_previous, "Anterior", prevPending)
            .addAction(playPauseIcon, playPauseLabel, playPausePending)
            .addAction(android.R.drawable.ic_media_next, "Siguiente", nextPending)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Detener", stopPending)
            .setStyle(mediaStyle)
            .build()
    }

    private fun startForegroundWithNotification(text: String) {
        val notification = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }
}
