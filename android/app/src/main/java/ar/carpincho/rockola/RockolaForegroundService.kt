package ar.carpincho.rockola

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.io.FileOutputStream

/**
 * Servicio en primer plano que mantiene vivo el servidor FastAPI/Uvicorn
 * ejecutado sobre Chaquopy, junto con WakeLock y WifiLock para evitar cortes con pantalla apagada.
 */
class RockolaForegroundService : Service() {

    companion object {
        const val PREFS_NAME = "rockola_android_prefs"
        const val KEY_MUSIC_DIR = "music_dir"
        const val KEY_PORT = "port"

        const val ACTION_START = "ar.carpincho.rockola.ACTION_START"
        const val ACTION_STOP = "ar.carpincho.rockola.ACTION_STOP"
        const val EXTRA_PORT = "port"
        const val EXTRA_MUSIC_DIR = "music_dir"

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

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopServerAndService()
            return START_NOT_STICKY
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
                updateNotification("Sonando en $serverUrl (red local)")

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
                description = "Mantiene el servidor musical y el streaming activos en segundo plano"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
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

        val stopIntent = Intent(this, RockolaForegroundService::class.java).apply {
            action = ACTION_STOP
        }
        val stopPending = PendingIntent.getService(
            this,
            1,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("La Rockola del Carpincho")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(openPending)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Detener", stopPending)
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
