package ar.carpincho.rockola

import android.content.Context
import android.os.Build
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.io.FileOutputStream

/**
 * Administra el ciclo de vida del intérprete Python embebido (Chaquopy),
 * la extracción versionada del frontend en `assets/public` y el arranque único
 * del servidor Uvicorn sin doble inicialización de entorno.
 */
class EmbeddedPythonHost(
    private val context: Context,
) {
    data class ServerEndpointInfo(
        val localIp: String,
        val serverUrl: String,
    )

    fun startBlocking(
        port: Int,
        musicDir: String?,
        onConfigured: (ServerEndpointInfo) -> Unit,
    ) {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context.applicationContext))
        }

        val dataDir = File(context.filesDir, "rockola_data").apply { mkdirs() }
        val distDir = File(context.filesDir, "dist")
        ensureDistExtracted(distDir)

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
        // already_configured = true evita correr migraciones e init dos veces en el arranque
        entry.callAttr(
            "start_embedded_server",
            dataDir.absolutePath,
            distDir.absolutePath,
            musicDir ?: "",
            port,
            "0.0.0.0",
            true,
        )
    }

    fun stop() {
        try {
            if (Python.isStarted()) {
                Python.getInstance().getModule("app.android_entry").callAttr("stop_embedded_server")
            }
        } catch (_: Exception) {
        }
    }

    private fun ensureDistExtracted(distDir: File) {
        val currentStamp = currentBuildStamp()
        val stampFile = File(distDir, ".dist_stamp")
        val indexFile = File(distDir, "index.html")

        if (stampFile.isFile && indexFile.isFile && stampFile.readText().trim() == currentStamp) {
            return
        }

        if (distDir.exists()) {
            distDir.deleteRecursively()
        }
        extractAssetFolder("public", distDir)
        distDir.mkdirs()
        stampFile.writeText(currentStamp)
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

    private fun extractAssetFolder(assetPath: String, target: File) {
        val entries = context.assets.list(assetPath) ?: return
        if (entries.isEmpty()) {
            target.parentFile?.mkdirs()
            try {
                context.assets.open(assetPath).use { input ->
                    FileOutputStream(target).use { output ->
                        input.copyTo(output)
                    }
                }
            } catch (_: Exception) {
                // Si era un subdirectorio vacío en assets, lo omitimos sin abortar
            }
            return
        }
        target.mkdirs()
        for (entry in entries) {
            extractAssetFolder("$assetPath/$entry", File(target, entry))
        }
    }
}
