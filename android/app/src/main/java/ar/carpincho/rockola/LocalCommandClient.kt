package ar.carpincho.rockola

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import android.util.LruCache
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Cliente HTTP local con pool acotado para despachar comandos de reproducción
 * y cachear carátulas en memoria sin crear hilos sueltos por cada evento.
 */
class LocalCommandClient(
    private val portProvider: () -> Int,
) {
    private val commandExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaMediaCmd").apply { isDaemon = true }
    }

    private val artworkExecutor = Executors.newFixedThreadPool(2) { runnable ->
        Thread(runnable, "RockolaArtworkFetch").apply { isDaemon = true }
    }

    // Caché en memoria de hasta 6 MiB para evitar redescargar la misma carátula
    private val artworkCache = object : LruCache<String, Bitmap>(6 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.allocationByteCount.coerceAtLeast(1)
    }

    fun sendCommand(cmd: String, extraFields: Map<String, Any> = emptyMap()) {
        if (commandExecutor.isShutdown) return
        commandExecutor.execute {
            try {
                val payload = JSONObject().apply {
                    put("cmd", cmd)
                    for ((k, v) in extraFields) {
                        put(k, v)
                    }
                }
                val port = portProvider()
                val conn = (URL("http://127.0.0.1:$port/command").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    setRequestProperty("Content-Type", "application/json")
                    doOutput = true
                    connectTimeout = 2000
                    readTimeout = 2000
                }
                try {
                    conn.outputStream.use { out ->
                        out.write(payload.toString().toByteArray(Charsets.UTF_8))
                    }
                    conn.responseCode
                } finally {
                    conn.disconnect()
                }
            } catch (e: Exception) {
                Log.w("RockolaCmdClient", "No se pudo despachar comando '$cmd' desde notificación: ${e.message}")
            }
        }
    }

    fun fetchArtwork(coverUrl: String, onLoaded: (Bitmap) -> Unit) {
        val cached = artworkCache.get(coverUrl)
        if (cached != null && !cached.isRecycled) {
            onLoaded(cached)
            return
        }
        if (artworkExecutor.isShutdown) return

        artworkExecutor.execute {
            var conn: HttpURLConnection? = null
            try {
                conn = (URL(coverUrl).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 2500
                    readTimeout = 2500
                }
                val bmp = conn.inputStream.use { BitmapFactory.decodeStream(it) }
                if (bmp != null) {
                    artworkCache.put(coverUrl, bmp)
                    onLoaded(bmp)
                }
            } catch (_: Exception) {
                // La ausencia de carátula no frena la notificación; cae al ícono por defecto
            } finally {
                conn?.disconnect()
            }
        }
    }

    fun shutdown() {
        commandExecutor.shutdownNow()
        artworkExecutor.shutdownNow()
        artworkCache.evictAll()
    }
}
