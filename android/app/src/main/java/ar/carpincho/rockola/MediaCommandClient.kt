package ar.carpincho.rockola

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.util.concurrent.Executors

enum class MediaTargetMode {
    HOST,
    REMOTE,
}

data class MediaTarget(
    val mode: MediaTargetMode,
    val origin: String,
    val authHeader: String? = null,
    val generation: Long = 0L,
) {
    fun normalizedOrigin(): String = origin.trim().trimEnd('/')
}

sealed class CommandResult {
    object Success : CommandResult()
    data class StaleTarget(val expectedGen: Long, val currentGen: Long) : CommandResult()
    data class AuthFailed(val httpCode: Int) : CommandResult()
    data class EndpointUnavailable(val httpCode: Int) : CommandResult()
    data class ServerError(val httpCode: Int) : CommandResult()
    data class Timeout(val message: String) : CommandResult()
    data class Disconnected(val message: String) : CommandResult()

    fun isSuccess(): Boolean = this is Success

    fun errorCode(): String = when (this) {
        is Success -> "OK"
        is StaleTarget -> "STALE_TARGET"
        is AuthFailed -> "AUTH_FAILED"
        is EndpointUnavailable -> "ENDPOINT_UNAVAILABLE"
        is ServerError -> "SERVER_ERROR"
        is Timeout -> "TIMEOUT"
        is Disconnected -> "DISCONNECTED"
    }

    fun userMessage(): String = when (this) {
        is Success -> ""
        is StaleTarget -> "El comando quedó viejo porque cambiaste de servidor."
        is AuthFailed -> "El servidor rechazó la autenticación (HTTP $httpCode)."
        is EndpointUnavailable -> "El endpoint /command no está disponible (HTTP $httpCode)."
        is ServerError -> "El servidor falló al ejecutar el comando (HTTP $httpCode)."
        is Timeout -> "Se agotó el tiempo esperando respuesta del servidor."
        is Disconnected -> "No se pudo conectar con el servidor activo."
    }
}

/**
 * Cliente HTTP consciente del origen activo (host local o servidor remoto) con pool acotado,
 * validación de generación de destino, reporte explícito de fallos y caché LRU en memoria de carátulas.
 */
class MediaCommandClient(
    initialTarget: MediaTarget = MediaTarget(MediaTargetMode.HOST, "http://127.0.0.1:1729"),
    private val timeoutMs: Int = 10_000,
    private val artworkTimeoutMs: Int = 12_000,
    private val artworkMaxBytes: Int = 6 * 1024 * 1024,
    private val bitmapDecoder: (InputStream) -> Bitmap? = { stream -> BitmapFactory.decodeStream(stream) },
    private val logWarn: (String) -> Unit = { msg ->
        try {
            Log.w("RockolaCmdClient", msg)
        } catch (_: Throwable) {
        }
    },
) {
    @Volatile
    var currentTarget: MediaTarget = initialTarget
        private set

    private val commandExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaMediaCmd").apply { isDaemon = true }
    }

    private val artworkExecutor = Executors.newFixedThreadPool(2) { runnable ->
        Thread(runnable, "RockolaArtworkFetch").apply { isDaemon = true }
    }

    private val cacheLock = Any()
    private var artworkCacheBytes = 0
    private val artworkCache = object : LinkedHashMap<String, Bitmap>(32, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Bitmap>?): Boolean {
            if (artworkCacheBytes > artworkMaxBytes && eldest != null) {
                artworkCacheBytes = (artworkCacheBytes - bitmapSize(eldest.value)).coerceAtLeast(0)
                return true
            }
            return false
        }
    }

    fun setTarget(target: MediaTarget) {
        val cleanTarget = target.copy(origin = target.normalizedOrigin())
        val changed = cleanTarget.origin != currentTarget.origin ||
            cleanTarget.mode != currentTarget.mode ||
            cleanTarget.generation != currentTarget.generation
        currentTarget = cleanTarget
        if (changed) {
            synchronized(cacheLock) {
                artworkCache.clear()
                artworkCacheBytes = 0
            }
        }
    }

    fun sendCommand(
        cmd: String,
        extraFields: Map<String, Any> = emptyMap(),
        expectedGeneration: Long? = null,
        onResult: ((CommandResult) -> Unit)? = null,
    ) {
        val scheduledTarget = currentTarget
        if (expectedGeneration != null && expectedGeneration != scheduledTarget.generation) {
            onResult?.invoke(CommandResult.StaleTarget(expectedGeneration, scheduledTarget.generation))
            return
        }
        if (commandExecutor.isShutdown) {
            onResult?.invoke(CommandResult.Disconnected("Cliente de comandos detenido"))
            return
        }

        commandExecutor.execute {
            val activeNow = currentTarget
            if (expectedGeneration != null && expectedGeneration != activeNow.generation) {
                onResult?.invoke(CommandResult.StaleTarget(expectedGeneration, activeNow.generation))
                return@execute
            }
            if (activeNow.generation != scheduledTarget.generation || activeNow.origin != scheduledTarget.origin) {
                onResult?.invoke(CommandResult.StaleTarget(scheduledTarget.generation, activeNow.generation))
                return@execute
            }

            val result = executeCommandPost(activeNow, cmd, extraFields)
            if (!result.isSuccess()) {
                logWarn("Fallo enviando '$cmd' a ${activeNow.origin}: ${result.errorCode()} ${result.userMessage()}")
            }
            onResult?.invoke(result)
        }
    }

    private fun executeCommandPost(
        target: MediaTarget,
        cmd: String,
        extraFields: Map<String, Any>,
    ): CommandResult {
        val baseOrigin = target.normalizedOrigin()
        if (baseOrigin.isEmpty()) {
            return CommandResult.Disconnected("Origen del servidor vacío")
        }

        val payloadJson = serializeCommandJson(cmd, extraFields)
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL("$baseOrigin/command").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Content-Type", "application/json")
                target.authHeader?.takeIf { it.isNotBlank() }?.let { setRequestProperty("Authorization", it) }
                doOutput = true
                connectTimeout = timeoutMs
                readTimeout = timeoutMs
            }
            conn.outputStream.use { out ->
                out.write(payloadJson.toByteArray(Charsets.UTF_8))
            }
            val code = conn.responseCode
            when (code) {
                in 200..299 -> CommandResult.Success
                401, 403 -> CommandResult.AuthFailed(code)
                404, 405 -> CommandResult.EndpointUnavailable(code)
                in 500..599 -> CommandResult.ServerError(code)
                else -> CommandResult.EndpointUnavailable(code)
            }
        } catch (e: SocketTimeoutException) {
            CommandResult.Timeout(e.message ?: "Timeout")
        } catch (e: IOException) {
            CommandResult.Disconnected(e.message ?: "Error de red")
        } catch (e: Exception) {
            CommandResult.Disconnected(e.message ?: "Fallo inesperado")
        } finally {
            conn?.disconnect()
        }
    }

    fun getCachedArtwork(coverUrl: String, expectedGeneration: Long? = null): Bitmap? {
        val target = currentTarget
        if (expectedGeneration != null && expectedGeneration != target.generation) return null
        val cacheKey = "${target.generation}|${target.normalizedOrigin()}|$coverUrl"
        val cached = synchronized(cacheLock) { artworkCache[cacheKey] }
        return if (cached != null && !cached.isRecycled) cached else null
    }

    fun fetchArtwork(
        coverUrl: String,
        expectedGeneration: Long? = null,
        onLoaded: (Bitmap) -> Unit,
    ) {
        val target = currentTarget
        if (expectedGeneration != null && expectedGeneration != target.generation) return

        val cacheKey = "${target.generation}|${target.normalizedOrigin()}|$coverUrl"
        val cached = synchronized(cacheLock) { artworkCache[cacheKey] }
        if (cached != null && !cached.isRecycled) {
            onLoaded(cached)
            return
        }
        if (artworkExecutor.isShutdown) return

        artworkExecutor.execute {
            val activeNow = currentTarget
            if (activeNow.generation != target.generation) return@execute

            for (attempt in 0..1) {
                var conn: HttpURLConnection? = null
                try {
                    conn = (URL(coverUrl).openConnection() as HttpURLConnection).apply {
                        connectTimeout = artworkTimeoutMs
                        readTimeout = artworkTimeoutMs
                        val origin = target.normalizedOrigin()
                        if (origin.isNotEmpty() && coverUrl.startsWith(origin)) {
                            target.authHeader?.takeIf { it.isNotBlank() }?.let {
                                setRequestProperty("Authorization", it)
                            }
                        }
                    }
                    val code = conn.responseCode
                    if (code !in 200..299) {
                        if (code >= 500 && attempt == 0) {
                            Thread.sleep(250)
                            continue
                        }
                        return@execute
                    }
                    val bmp = conn.inputStream.use { bitmapDecoder(it) } ?: return@execute
                    if (currentTarget.generation != target.generation) return@execute

                    synchronized(cacheLock) {
                        artworkCache[cacheKey] = bmp
                        artworkCacheBytes += bitmapSize(bmp)
                    }
                    onLoaded(bmp)
                    return@execute
                } catch (_: Exception) {
                    if (attempt == 0) {
                        try {
                            Thread.sleep(250)
                        } catch (_: InterruptedException) {
                            return@execute
                        }
                    }
                } finally {
                    conn?.disconnect()
                }
            }
        }
    }

    fun shutdown() {
        commandExecutor.shutdownNow()
        artworkExecutor.shutdownNow()
        synchronized(cacheLock) {
            artworkCache.clear()
            artworkCacheBytes = 0
        }
    }

    private fun bitmapSize(bmp: Bitmap): Int = try {
        bmp.allocationByteCount.coerceAtLeast(1)
    } catch (_: Throwable) {
        1
    }

    companion object {
        internal fun serializeCommandJson(cmd: String, extraFields: Map<String, Any>): String {
            val sb = StringBuilder(64)
            sb.append('{')
            sb.append("\"cmd\":").append(quoteJson(cmd))
            for ((k, v) in extraFields) {
                sb.append(',').append(quoteJson(k)).append(':')
                when (v) {
                    is Boolean -> sb.append(v)
                    is Number -> sb.append(v)
                    else -> sb.append(quoteJson(v.toString()))
                }
            }
            sb.append('}')
            return sb.toString()
        }

        private fun quoteJson(value: String): String {
            val sb = StringBuilder(value.length + 2)
            sb.append('"')
            for (ch in value) {
                when (ch) {
                    '"' -> sb.append("\\\"")
                    '\\' -> sb.append("\\\\")
                    '\b' -> sb.append("\\b")
                    '\u000C' -> sb.append("\\f")
                    '\n' -> sb.append("\\n")
                    '\r' -> sb.append("\\r")
                    '\t' -> sb.append("\\t")
                    else -> {
                        if (ch < ' ') {
                            sb.append(String.format("\\u%04x", ch.code))
                        } else {
                            sb.append(ch)
                        }
                    }
                }
            }
            sb.append('"')
            return sb.toString()
        }
    }
}
