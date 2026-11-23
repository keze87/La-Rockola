package ar.carpincho.rockola

import android.content.Context
import android.os.Build
import android.util.Log
import com.chaquo.python.Python
import java.io.File
import java.io.FileOutputStream

/**
 * Reglas puras para calcular el progreso porcentual de extracción de assets.
 */
internal object BootProgressPolicy {
    fun computeExtractPercent(done: Int, total: Int): Int {
        if (total <= 0 || done <= 0) return 0
        return ((done * 100L) / total).toInt().coerceIn(0, 100)
    }
}

/**
 * Administra el ciclo de vida del intérprete Python embebido (Chaquopy),
 * la extracción versionada del frontend en `assets/public` y el arranque único
 * del servidor Uvicorn sin doble inicialización de entorno.
 */
class EmbeddedPythonHost(
    private val context: Context,
) {
    companion object {
        @Volatile
        var currentBootStage: String = "idle"
            private set

        @Volatile
        var currentExtractProgress: Int = 0
            private set
    }

    data class ServerEndpointInfo(
        val localIp: String,
        val serverUrl: String,
    )

    fun startBlocking(
        port: Int,
        musicDir: String?,
        onConfigured: (ServerEndpointInfo) -> Unit,
        onReady: () -> Unit,
    ) {
        currentBootStage = "starting_python"
        RockolaApplication.ensurePythonStarted(context)

        val dataDir = File(context.filesDir, "rockola_data").apply { mkdirs() }
        val distDir = File(context.filesDir, "dist")
        ensureDistExtracted(distDir)

        currentBootStage = "starting_server"
        val py = Python.getInstance()
        val entry = py.getModule("app.android_entry")

        val infoObj = entry.callAttr(
            "configure_android_environment",
            dataDir.absolutePath,
            distDir.absolutePath,
            musicDir ?: "",
            port,
            "0.0.0.0",
        )
        val infoMap = infoObj.asMap()
        val localIp = infoMap[py.builtins.callAttr("str", "local_ip")]?.toString() ?: "127.0.0.1"
        val serverUrl = infoMap[py.builtins.callAttr("str", "server_url")]?.toString()
            ?: "http://$localIp:$port"

        onConfigured(ServerEndpointInfo(localIp = localIp, serverUrl = serverUrl))

        Log.i("RockolaPythonHost", "Arrancando Uvicorn embebido en $serverUrl...")
        val started = entry.callAttr(
            "start_embedded_server",
            dataDir.absolutePath,
            distDir.absolutePath,
            musicDir ?: "",
            port,
            "0.0.0.0",
            true,
            Runnable {
                currentBootStage = "ready"
                currentExtractProgress = 100
                onReady()
            },
        ).toBoolean()
        if (!started) {
            val statusObj = entry.callAttr("get_server_info").asMap()
            val currentState = statusObj[py.builtins.callAttr("str", "host_state")]?.toString() ?: "desconocido"
            throw IllegalStateException("El servidor embebido rechazó el arranque (estado: $currentState)")
        }
    }

    fun stop() {
        try {
            if (Python.isStarted()) {
                Python.getInstance().getModule("app.android_entry").callAttr("stop_embedded_server")
            }
        } catch (e: Exception) {
            Log.w("RockolaPythonHost", "Error solicitando apagado de Python embebido", e)
        }
    }

    private fun ensureDistExtracted(distDir: File) {
        val currentStamp = currentBuildStamp()
        val stampFile = File(distDir, ".dist_stamp")
        val indexFile = File(distDir, "index.html")

        if (stampFile.isFile && indexFile.isFile && stampFile.readText().trim() == currentStamp) {
            currentExtractProgress = 100
            return
        }

        currentBootStage = "extracting_assets"
        currentExtractProgress = 0
        val parentDir = distDir.parentFile ?: context.filesDir
        val tempDir = File(parentDir, "${distDir.name}.tmp-${System.currentTimeMillis()}")
        try {
            tempDir.mkdirs()
            val filesToExtract = mutableListOf<String>()
            collectAssetFiles("public", filesToExtract)
            val totalFiles = filesToExtract.size
            for ((index, assetFile) in filesToExtract.withIndex()) {
                val relativePath = assetFile.removePrefix("public/").removePrefix("public")
                if (relativePath.isNotEmpty()) {
                    val outFile = File(tempDir, relativePath)
                    outFile.parentFile?.mkdirs()
                    try {
                        context.assets.open(assetFile).use { input ->
                            FileOutputStream(outFile).use { output ->
                                input.copyTo(output)
                            }
                        }
                    } catch (_: Exception) {
                        // Si era un subdirectorio vacío en assets, lo omitimos sin abortar
                    }
                }
                currentExtractProgress = BootProgressPolicy.computeExtractPercent(index + 1, totalFiles)
            }
            File(tempDir, ".dist_stamp").writeText(currentStamp)

            if (distDir.exists() && !distDir.deleteRecursively()) {
                throw IllegalStateException("No se pudo limpiar la versión web anterior en ${distDir.absolutePath}")
            }
            if (!tempDir.renameTo(distDir)) {
                tempDir.copyRecursively(distDir, overwrite = true)
                tempDir.deleteRecursively()
            }
            currentExtractProgress = 100
            currentBootStage = "starting_server"
        } catch (e: Exception) {
            tempDir.deleteRecursively()
            throw e
        }
    }

    private fun collectAssetFiles(assetPath: String, out: MutableList<String>) {
        val entries = context.assets.list(assetPath) ?: return
        if (entries.isEmpty()) {
            out.add(assetPath)
            return
        }
        for (entry in entries) {
            collectAssetFiles("$assetPath/$entry", out)
        }
    }

    private fun currentBuildStamp(): String {
        return try {
            val info = context.packageManager.getPackageInfo(context.packageName, 0)
            val version = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info.longVersionCode
            } else {
                @Suppress("DEPRECATION")
                info.versionCode.toLong()
            }
            "$version-${info.lastUpdateTime}"
        } catch (_: Exception) {
            "unknown"
        }
    }
}
