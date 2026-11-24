package ar.carpincho.rockola

import android.content.Context
import android.content.res.AssetManager
import android.os.Build
import android.util.Log
import com.chaquo.python.Python
import java.io.File
import java.io.FileNotFoundException
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream

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
 * Abstracción testeable en JVM sobre el origen de assets comprimidos (AssetManager en Android).
 */
internal interface DistAssetSource {
    fun list(path: String): Array<String>?
    fun open(path: String): InputStream
}

private class AndroidDistAssetSource(private val assets: AssetManager) : DistAssetSource {
    override fun list(path: String): Array<String>? = assets.list(path)
    override fun open(path: String): InputStream = assets.open(path)
}

/**
 * Extractor atómico con validación integral y rollback de la distribución web `assets/public`.
 */
internal class DistAssetExtractor(
    private val source: DistAssetSource,
    private val onProgress: (Int) -> Unit = {},
) {
    companion object {
        private const val STAMP_FILENAME = ".dist_stamp"
        private const val MIN_INDEX_BYTES = 32L
        private val REF_REGEX = Regex("""(?:src|href)\s*=\s*["']([^"']+)["']""", RegexOption.IGNORE_CASE)
    }

    fun ensureExtracted(distDir: File, currentStamp: String) {
        val parentDir = distDir.parentFile ?: throw IllegalStateException("Directorio padre inválido para dist")
        cleanupTempDirs(parentDir, distDir.name)

        // Si la distribución actual está sana y coincide con el build stamp, no re-extraemos
        if (isDistributionValidForStamp(distDir, currentStamp)) {
            cleanupBackups(parentDir, distDir.name)
            onProgress(100)
            return
        }

        // Si hubo caída durante un reemplazo previo y quedó un backup sano del stamp actual, lo recuperamos
        val matchingBackup = findValidBackup(parentDir, distDir.name, expectedStamp = currentStamp)
        if (matchingBackup != null) {
            if (distDir.exists()) {
                distDir.deleteRecursively()
            }
            if (restoreBackup(matchingBackup, distDir) && isDistributionValidForStamp(distDir, currentStamp)) {
                cleanupBackups(parentDir, distDir.name)
                onProgress(100)
                return
            }
        }

        val tempDir = File(parentDir, "${distDir.name}.tmp-${System.currentTimeMillis()}")
        var backupDir: File? = null
        try {
            if (!tempDir.mkdirs() && !tempDir.isDirectory) {
                throw IOException("No se pudo crear directorio temporal de extracción: ${tempDir.absolutePath}")
            }

            val assetFiles = mutableListOf<String>()
            collectAssetFiles("public", assetFiles)
            val totalFiles = assetFiles.size
            if (totalFiles == 0) {
                throw IllegalStateException("No se encontraron assets web en 'public/' para extraer")
            }

            for ((index, assetFile) in assetFiles.withIndex()) {
                val relativePath = assetFile.removePrefix("public/").removePrefix("public")
                if (relativePath.isNotEmpty()) {
                    val outFile = File(tempDir, relativePath)
                    val outParent = outFile.parentFile
                    if (outParent != null && !outParent.isDirectory && !outParent.mkdirs()) {
                        throw IOException("No se pudo crear directorio para asset: ${outParent.absolutePath}")
                    }
                    copySingleAsset(assetFile, relativePath, outFile)
                }
                onProgress(BootProgressPolicy.computeExtractPercent(index + 1, totalFiles))
            }

            val validationErrors = validateDistribution(tempDir)
            if (validationErrors.isNotEmpty()) {
                throw IllegalStateException(
                    "Distribución web incompleta tras extraer assets: ${validationErrors.joinToString("; ")}",
                )
            }

            File(tempDir, STAMP_FILENAME).writeText(currentStamp)

            // Reemplazo atómico con respaldo para rollback si algo falla
            if (distDir.exists()) {
                val bak = File(parentDir, "${distDir.name}.bak-${System.currentTimeMillis()}")
                moveOrCopyDir(distDir, bak)
                backupDir = bak
            }

            if (!tempDir.renameTo(distDir)) {
                tempDir.copyRecursively(distDir, overwrite = true)
            }

            val finalStampOk = runCatching {
                File(distDir, STAMP_FILENAME).readText().trim() == currentStamp
            }.getOrDefault(false)
            val destErrors = validateDistribution(distDir)
            if (!finalStampOk || destErrors.isNotEmpty()) {
                throw IllegalStateException(
                    "Validación final de destino falló (${destErrors.joinToString("; ")})",
                )
            }

            backupDir?.deleteRecursively()
            tempDir.deleteRecursively()
            cleanupBackups(parentDir, distDir.name)
            onProgress(100)
        } catch (t: Throwable) {
            if (backupDir != null && backupDir.exists()) {
                if (distDir.exists()) {
                    distDir.deleteRecursively()
                }
                restoreBackup(backupDir, distDir)
            }
            tempDir.deleteRecursively()
            throw t
        }
    }

    fun validateDistribution(dir: File): List<String> {
        val errors = mutableListOf<String>()
        if (!dir.isDirectory) {
            return listOf("Directorio dist inexistente: ${dir.absolutePath}")
        }
        val indexFile = File(dir, "index.html")
        if (!indexFile.isFile || indexFile.length() < MIN_INDEX_BYTES) {
            errors.add("index.html ausente o vacío")
            return errors
        }

        val html = try {
            indexFile.readText(Charsets.UTF_8)
        } catch (e: Exception) {
            errors.add("No se pudo leer index.html: ${e.message}")
            return errors
        }

        val referencedFiles = extractLocalAssetRefs(html)
        for (rel in referencedFiles) {
            val target = File(dir, rel)
            if (!target.isFile || target.length() <= 0L) {
                errors.add("Recurso esencial ausente o vacío: $rel")
            }
        }

        val allFiles = dir.walkTopDown().filter { it.isFile }.toList()
        val hasJs = allFiles.any {
            (it.name.endsWith(".js", ignoreCase = true) || it.name.endsWith(".mjs", ignoreCase = true)) &&
                it.name != "sw.js" &&
                it.length() > 0L
        }
        if (!hasJs) {
            errors.add("JavaScript principal ausente o vacío")
        }

        val hasCss = allFiles.any { it.name.endsWith(".css", ignoreCase = true) && it.length() > 0L }
        if (!hasCss) {
            errors.add("CSS principal ausente o vacío")
        }

        val manifestFile = File(dir, "manifest.webmanifest")
        if (referencedFiles.any { it.equals("manifest.webmanifest", ignoreCase = true) } &&
            (!manifestFile.isFile || manifestFile.length() <= 0L)
        ) {
            errors.add("manifest.webmanifest ausente o vacío")
        }

        return errors
    }

    private fun extractLocalAssetRefs(html: String): List<String> {
        val refs = LinkedHashSet<String>()
        for (match in REF_REGEX.findAll(html)) {
            val raw = match.groupValues[1].trim()
            if (raw.isEmpty() ||
                raw.startsWith("#") ||
                raw.startsWith("http://", ignoreCase = true) ||
                raw.startsWith("https://", ignoreCase = true) ||
                raw.startsWith("data:", ignoreCase = true)
            ) {
                continue
            }
            val noQuery = raw.substringBefore('?').substringBefore('#')
            val clean = noQuery.removePrefix("./").removePrefix("/")
            if (clean.isNotEmpty() && !clean.startsWith("..")) {
                refs.add(clean)
            }
        }
        return refs.toList()
    }

    private fun copySingleAsset(assetFile: String, relativePath: String, outFile: File) {
        val inputStream = try {
            source.open(assetFile)
        } catch (fnf: FileNotFoundException) {
            // AssetManager.list() incluye subdirectorios vacíos con entries.isEmpty();
            // si no tiene extensión de archivo ni es un asset conocido sin extensión, lo omitimos como directorio vacío.
            if (!isExpectedAssetFile(relativePath)) {
                return
            }
            throw fnf
        }
        inputStream.use { input ->
            FileOutputStream(outFile).use { output ->
                input.copyTo(output)
                output.flush()
            }
        }
        if (!outFile.isFile) {
            throw IOException("Archivo no creado tras copia: ${outFile.absolutePath}")
        }
    }

    private fun isExpectedAssetFile(relativePath: String): Boolean {
        val name = relativePath.substringAfterLast('/')
        return name.contains('.')
    }

    private fun collectAssetFiles(assetPath: String, out: MutableList<String>, isRoot: Boolean = true) {
        val entries = source.list(assetPath)
        if (entries == null || entries.isEmpty()) {
            if (!isRoot) {
                out.add(assetPath)
            }
            return
        }
        for (entry in entries) {
            collectAssetFiles("$assetPath/$entry", out, isRoot = false)
        }
    }

    private fun isDistributionValidForStamp(distDir: File, expectedStamp: String): Boolean {
        val stampFile = File(distDir, STAMP_FILENAME)
        if (!stampFile.isFile) return false
        val actualStamp = runCatching { stampFile.readText().trim() }.getOrNull() ?: return false
        if (actualStamp != expectedStamp) return false
        return validateDistribution(distDir).isEmpty()
    }

    private fun findValidBackup(parentDir: File, distName: String, expectedStamp: String): File? {
        val candidates = parentDir.listFiles { f ->
            f.isDirectory && f.name.startsWith("$distName.bak-")
        }?.sortedByDescending { it.lastModified() } ?: return null
        return candidates.firstOrNull { isDistributionValidForStamp(it, expectedStamp) }
    }

    private fun moveOrCopyDir(src: File, dst: File) {
        if (src.renameTo(dst)) return
        src.copyRecursively(dst, overwrite = true)
        if (!src.deleteRecursively()) {
            throw IOException("No se pudo limpiar origen tras copia: ${src.absolutePath}")
        }
    }

    private fun restoreBackup(backupDir: File, distDir: File): Boolean {
        if (backupDir.renameTo(distDir)) return true
        return try {
            backupDir.copyRecursively(distDir, overwrite = true)
            backupDir.deleteRecursively()
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun cleanupTempDirs(parentDir: File, distName: String) {
        parentDir.listFiles { f -> f.isDirectory && f.name.startsWith("$distName.tmp-") }
            ?.forEach { it.deleteRecursively() }
    }

    private fun cleanupBackups(parentDir: File, distName: String) {
        parentDir.listFiles { f -> f.isDirectory && f.name.startsWith("$distName.bak-") }
            ?.forEach { it.deleteRecursively() }
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
        currentBootStage = "extracting_assets"
        currentExtractProgress = 0
        val extractor = DistAssetExtractor(AndroidDistAssetSource(context.assets)) { pct ->
            currentExtractProgress = pct
        }
        extractor.ensureExtracted(distDir, currentBuildStamp())
        currentExtractProgress = 100
        currentBootStage = "starting_server"
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
