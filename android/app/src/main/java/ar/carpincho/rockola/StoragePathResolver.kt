package ar.carpincho.rockola

import android.content.Context
import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import java.io.File

/**
 * Resuelve URIs del Storage Access Framework (ACTION_OPEN_DOCUMENT_TREE)
 * a rutas reales POSIX de almacenamiento interno o tarjeta MicroSD.
 */
object StoragePathResolver {
    fun resolveTreeUri(context: Context, treeUri: Uri): String? {
        val docId = try {
            DocumentsContract.getTreeDocumentId(treeUri)
        } catch (_: Exception) {
            return null
        } ?: return null

        val parts = docId.split(":", limit = 2)
        val volumeId = parts.getOrNull(0) ?: return null
        val relativePath = parts.getOrNull(1)?.trim('/') ?: ""

        val baseDir = if (volumeId.equals("primary", ignoreCase = true)) {
            Environment.getExternalStorageDirectory().absolutePath
        } else {
            val directMount = File("/storage/$volumeId")
            if (directMount.exists()) {
                directMount.absolutePath
            } else {
                // Respaldo buscando volúmenes externos montados por Android
                context.getExternalFilesDirs(null)
                    .asSequence()
                    .filterNotNull()
                    .mapNotNull { appDir ->
                        val abs = appDir.absolutePath
                        val marker = "/Android/data/"
                        val idx = abs.indexOf(marker)
                        if (idx > 0) abs.substring(0, idx) else null
                    }
                    .firstOrNull { root ->
                        File(root).name.equals(volumeId, ignoreCase = true)
                    } ?: "/storage/$volumeId"
            }
        }

        return if (relativePath.isEmpty()) {
            baseDir
        } else {
            "$baseDir/$relativePath"
        }
    }
}
