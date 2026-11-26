package ar.carpincho.rockola

import android.app.ActivityManager
import android.app.ApplicationExitInfo
import android.content.Context
import android.os.Build
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.atomic.AtomicBoolean

internal data class DiagnosticsSnapshot(
    val lastError: String?,
    val lastExit: String?,
)

/**
 * Diagnóstico local sin telemetría externa:
 * persiste el último error no capturado (Kotlin, Python, WebView) en almacenamiento privado
 * y registra `ApplicationExitInfo` (API 30+) en logcat + archivo local.
 */
internal object LocalCrashDiagnostics {
    private const val TAG = "RockolaDiagnostics"
    private const val LAST_ERROR_FILENAME = "rockola_last_error.log"
    private const val LAST_EXIT_FILENAME = "rockola_last_exit.log"
    private const val MAX_LOG_BYTES = 16 * 1024

    private val fileLock = Any()
    private val handlerInstalled = AtomicBoolean(false)

    private fun utcTimestamp(epochMs: Long = System.currentTimeMillis()): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        return fmt.format(Date(epochMs))
    }

    fun formatExitReason(reason: Int): String {
        return when (reason) {
            ApplicationExitInfo.REASON_EXIT_SELF -> "EXIT_SELF"
            ApplicationExitInfo.REASON_SIGNALED -> "SIGNALED"
            ApplicationExitInfo.REASON_LOW_MEMORY -> "LOW_MEMORY"
            ApplicationExitInfo.REASON_CRASH -> "CRASH"
            ApplicationExitInfo.REASON_CRASH_NATIVE -> "CRASH_NATIVE"
            ApplicationExitInfo.REASON_ANR -> "ANR"
            ApplicationExitInfo.REASON_INITIALIZATION_FAILURE -> "INITIALIZATION_FAILURE"
            ApplicationExitInfo.REASON_PERMISSION_CHANGE -> "PERMISSION_CHANGE"
            ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE -> "EXCESSIVE_RESOURCE_USAGE"
            ApplicationExitInfo.REASON_USER_REQUESTED -> "USER_REQUESTED"
            ApplicationExitInfo.REASON_USER_STOPPED -> "USER_STOPPED"
            ApplicationExitInfo.REASON_DEPENDENCY_DIED -> "DEPENDENCY_DIED"
            ApplicationExitInfo.REASON_OTHER -> "OTHER"
            else -> "UNKNOWN($reason)"
        }
    }

    fun appendBoundedLog(file: File, entry: String, maxBytes: Int = MAX_LOG_BYTES) {
        val cleaned = entry.trimEnd()
        if (cleaned.isEmpty() || maxBytes <= 0) return
        synchronized(fileLock) {
            file.parentFile?.mkdirs()
            val existing = if (file.isFile) runCatching { file.readText(Charsets.UTF_8) }.getOrDefault("") else ""
            val combined = if (existing.isEmpty()) "$cleaned\n" else "${existing.trimEnd()}\n$cleaned\n"
            val bytes = combined.toByteArray(Charsets.UTF_8)
            if (bytes.size <= maxBytes) {
                file.writeBytes(bytes)
                return
            }
            // Conservamos siempre las líneas más recientes dentro del límite máximo
            val lines = combined.lineSequence().filter { it.isNotEmpty() }.toList()
            val kept = ArrayDeque<String>()
            var total = 0
            for (line in lines.asReversed()) {
                val lineBytes = (line.toByteArray(Charsets.UTF_8).size + 1)
                if (kept.isNotEmpty() && total + lineBytes > maxBytes) break
                kept.addFirst(line)
                total += lineBytes
                if (total >= maxBytes) break
            }
            val finalBytes = (kept.joinToString("\n") + "\n").toByteArray(Charsets.UTF_8)
            if (finalBytes.size <= maxBytes) {
                file.writeBytes(finalBytes)
            } else {
                file.writeBytes(finalBytes.copyOfRange(finalBytes.size - maxBytes, finalBytes.size))
            }
        }
    }

    fun recordError(context: Context, source: String, message: String, throwable: Throwable? = null) {
        val safeSource = source.trim().ifEmpty { "kotlin" }
        val safeMsg = message.trim().ifEmpty { throwable?.javaClass?.simpleName ?: "Unknown error" }
        val stack = if (throwable != null) {
            val sw = StringWriter()
            throwable.printStackTrace(PrintWriter(sw))
            "\n${sw.toString().trim().take(4000)}"
        } else {
            ""
        }
        val entry = "[${utcTimestamp()}] [$safeSource] $safeMsg$stack"
        runCatching {
            val file = File(context.applicationContext.filesDir, LAST_ERROR_FILENAME)
            appendBoundedLog(file, entry)
        }
    }

    fun installUncaughtExceptionHandler(context: Context) {
        if (!handlerInstalled.compareAndSet(false, true)) return
        val appContext = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                recordError(
                    appContext,
                    "kotlin:${thread.name}",
                    throwable.message ?: throwable.javaClass.simpleName,
                    throwable,
                )
            } catch (_: Throwable) {
                // Nunca ocultar el crash original
            } finally {
                previous?.uncaughtException(thread, throwable)
            }
        }
    }

    fun logAndPersistLastExitInfo(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        runCatching {
            val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager ?: return
            val reasons = am.getHistoricalProcessExitReasons(context.packageName, 0, 3)
            if (reasons.isEmpty()) return
            val summaryLines = reasons.map { info ->
                val reasonStr = formatExitReason(info.reason)
                val ts = utcTimestamp(info.timestamp)
                val desc = info.description?.trim().orEmpty()
                val pssKb = info.pss
                "[$ts] reason=$reasonStr status=${info.status} importance=${info.importance} pssKb=$pssKb" +
                    if (desc.isNotEmpty()) " desc=$desc" else ""
            }
            Log.i(TAG, "Última salida del proceso: ${summaryLines.first()}")
            val exitFile = File(context.applicationContext.filesDir, LAST_EXIT_FILENAME)
            synchronized(fileLock) {
                exitFile.parentFile?.mkdirs()
                exitFile.writeText(summaryLines.joinToString("\n") + "\n", Charsets.UTF_8)
            }
        }.onFailure { err ->
            Log.w(TAG, "No se pudo leer ApplicationExitInfo: ${err.message}")
        }
    }

    fun readDiagnosticsSnapshot(context: Context): DiagnosticsSnapshot {
        val baseDir = context.applicationContext.filesDir
        val lastError = synchronized(fileLock) {
            val f = File(baseDir, LAST_ERROR_FILENAME)
            if (f.isFile) runCatching { f.readText(Charsets.UTF_8).trim().ifEmpty { null } }.getOrNull() else null
        }
        val lastExit = synchronized(fileLock) {
            val f = File(baseDir, LAST_EXIT_FILENAME)
            if (f.isFile) runCatching { f.readText(Charsets.UTF_8).trim().ifEmpty { null } }.getOrNull() else null
        }
        return DiagnosticsSnapshot(lastError = lastError, lastExit = lastExit)
    }
}
