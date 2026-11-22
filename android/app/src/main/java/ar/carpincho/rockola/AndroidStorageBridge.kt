package ar.carpincho.rockola

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLDecoder
import java.util.concurrent.ConcurrentHashMap

enum class SafFolderStatus {
    OK,
    UNCONFIGURED,
    PERMISSION_REVOKED,
    UNAVAILABLE,
    UNSUPPORTED_PROVIDER;

    fun wireName(): String = when (this) {
        OK -> "ok"
        UNCONFIGURED -> "unconfigured"
        PERMISSION_REVOKED -> "permission_denied"
        UNAVAILABLE -> "storage_unavailable"
        UNSUPPORTED_PROVIDER -> "unsupported_provider"
    }
}

data class SafValidationResult(
    val status: SafFolderStatus,
    val uri: String,
    val displayName: String? = null,
    val error: String? = null,
)

data class SafDocumentEntry(
    val documentId: String,
    val name: String,
    val mimeType: String,
    val size: Long,
    val lastModifiedMs: Long,
    val uri: String,
)

data class SafAudioTrackEntry(
    val uri: String,
    val name: String,
    val relativePath: String,
    val size: Long,
    val mtimeSec: Double,
    val mimeType: String,
)

interface SafTreeProvider {
    fun isTreeUri(raw: String): Boolean
    fun hasPersistedReadPermission(treeUri: String): Boolean
    fun queryRootInfo(treeUri: String): SafDocumentEntry?
    fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry>
    fun readDocumentText(docUri: String): String?
}

/**
 * Núcleo puro (testeable en JVM) para validación, recorrido recursivo y resolución de letras en SAF.
 */
class SafTreeBrowser(
    private val provider: SafTreeProvider,
    private val audioExtensions: Set<String> = DEFAULT_AUDIO_EXTENSIONS,
) {
    companion object {
        const val MIME_TYPE_DIR = "vnd.android.document/directory"
        val DEFAULT_AUDIO_EXTENSIONS = setOf(
            ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".mp4", ".mkv", ".avi", ".webm",
        )
    }

    private val parentCache = ConcurrentHashMap<String, Triple<String, String, String>>()

    fun validateTreeUri(uriString: String?): SafValidationResult {
        val cleaned = uriString?.trim().orEmpty()
        if (cleaned.isEmpty()) {
            return SafValidationResult(SafFolderStatus.UNCONFIGURED, "", null, null)
        }
        if (!cleaned.startsWith("content://") || !provider.isTreeUri(cleaned)) {
            return SafValidationResult(
                SafFolderStatus.UNSUPPORTED_PROVIDER,
                cleaned,
                null,
                "El proveedor elegido no expone un árbol de documentos SAF compatible.",
            )
        }
        if (!provider.hasPersistedReadPermission(cleaned)) {
            return SafValidationResult(
                SafFolderStatus.PERMISSION_REVOKED,
                cleaned,
                null,
                "El permiso sobre la carpeta fue revocado; volvé a seleccionarla.",
            )
        }
        return try {
            val root = provider.queryRootInfo(cleaned)
            if (root == null) {
                SafValidationResult(
                    SafFolderStatus.UNAVAILABLE,
                    cleaned,
                    null,
                    "La carpeta o tarjeta SD no está disponible actualmente.",
                )
            } else {
                SafValidationResult(SafFolderStatus.OK, cleaned, root.name, null)
            }
        } catch (_: SecurityException) {
            SafValidationResult(
                SafFolderStatus.PERMISSION_REVOKED,
                cleaned,
                null,
                "Sin permisos persistentes para leer esta carpeta.",
            )
        } catch (e: Exception) {
            SafValidationResult(
                SafFolderStatus.UNAVAILABLE,
                cleaned,
                null,
                e.message ?: "No se pudo acceder a la carpeta seleccionada.",
            )
        }
    }

    fun listAudioFiles(treeUriString: String): List<SafAudioTrackEntry> {
        val root = try {
            provider.queryRootInfo(treeUriString)
        } catch (_: Exception) {
            null
        } ?: return emptyList()

        val collected = ArrayList<SafAudioTrackEntry>()
        val visitedDirs = HashSet<String>()
        val queue = ArrayDeque<Pair<String, String>>()
        queue.add(Pair(root.documentId, ""))
        visitedDirs.add(root.documentId)

        while (queue.isNotEmpty()) {
            val (dirDocId, prefix) = queue.removeFirst()
            val children = try {
                provider.listChildren(treeUriString, dirDocId)
            } catch (_: Exception) {
                emptyList()
            }
            for (child in children) {
                if (child.mimeType == MIME_TYPE_DIR) {
                    if (visitedDirs.add(child.documentId)) {
                        val nextPrefix = if (prefix.isEmpty()) child.name else "$prefix/${child.name}"
                        queue.add(Pair(child.documentId, nextPrefix))
                    }
                    continue
                }
                parentCache[child.uri] = Triple(treeUriString, dirDocId, child.name)
                val dotIdx = child.name.lastIndexOf('.')
                val ext = if (dotIdx >= 0) child.name.substring(dotIdx).lowercase() else ""
                if (ext !in audioExtensions) continue

                val relPath = if (prefix.isEmpty()) child.name else "$prefix/${child.name}"
                collected.add(
                    SafAudioTrackEntry(
                        uri = child.uri,
                        name = child.name,
                        relativePath = relPath,
                        size = child.size,
                        mtimeSec = child.lastModifiedMs / 1000.0,
                        mimeType = child.mimeType,
                    ),
                )
            }
        }
        return collected
    }

    fun readSiblingText(docUriString: String, extensions: List<String>): Pair<String, String>? {
        val cached = parentCache[docUriString]
        val (treeUri, parentDocId, fileName) = cached ?: parseLocationFromDocUri(docUriString) ?: return null
        val dotIdx = fileName.lastIndexOf('.')
        val stem = if (dotIdx > 0) fileName.substring(0, dotIdx) else fileName
        if (stem.isBlank()) return null

        val siblings = try {
            provider.listChildren(treeUri, parentDocId)
        } catch (_: Exception) {
            emptyList()
        }
        for (rawExt in extensions) {
            val normalizedExt = if (rawExt.startsWith('.')) rawExt.lowercase() else ".${rawExt.lowercase()}"
            val targetName = "$stem$normalizedExt"
            val match = siblings.firstOrNull {
                it.mimeType != MIME_TYPE_DIR && it.name.equals(targetName, ignoreCase = true)
            } ?: continue
            val content = provider.readDocumentText(match.uri)
            if (content != null) {
                return Pair(normalizedExt, content)
            }
        }
        return null
    }

    private fun parseLocationFromDocUri(docUri: String): Triple<String, String, String>? {
        val docMarker = "/document/"
        val treeMarker = "/tree/"
        val docIdx = docUri.indexOf(docMarker)
        val treeIdx = docUri.indexOf(treeMarker)
        if (docIdx < 0 || treeIdx < 0 || treeIdx > docIdx) return null

        val treeUri = docUri.substring(0, docIdx)
        val treeIdDecoded = URLDecoder.decode(treeUri.substring(treeIdx + treeMarker.length), "UTF-8")
        val docIdDecoded = URLDecoder.decode(docUri.substring(docIdx + docMarker.length), "UTF-8")

        val fileName = docIdDecoded.substringAfterLast('/').substringAfterLast(':')
        val parentDocId = if (docIdDecoded.contains('/')) {
            val candidate = docIdDecoded.substringBeforeLast('/')
            if (candidate.startsWith(treeIdDecoded)) candidate else treeIdDecoded
        } else {
            treeIdDecoded
        }
        return Triple(treeUri, parentDocId, fileName)
    }
}

private class AndroidSafTreeProvider(private val context: Context) : SafTreeProvider {
    private val resolver = context.contentResolver
    private val projection = arrayOf(
        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
        DocumentsContract.Document.COLUMN_MIME_TYPE,
        DocumentsContract.Document.COLUMN_SIZE,
        DocumentsContract.Document.COLUMN_LAST_MODIFIED,
    )

    override fun isTreeUri(raw: String): Boolean {
        return try {
            val uri = Uri.parse(raw)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                DocumentsContract.isTreeUri(uri)
            } else {
                uri.pathSegments.contains("tree")
            }
        } catch (_: Exception) {
            false
        }
    }

    override fun hasPersistedReadPermission(treeUri: String): Boolean {
        return resolver.persistedUriPermissions.any { perm ->
            perm.uri.toString() == treeUri && perm.isReadPermission
        }
    }

    override fun queryRootInfo(treeUri: String): SafDocumentEntry? {
        val parsedTree = Uri.parse(treeUri)
        val rootDocId = DocumentsContract.getTreeDocumentId(parsedTree)
        val rootDocUri = DocumentsContract.buildDocumentUriUsingTree(parsedTree, rootDocId)
        resolver.query(rootDocUri, projection, null, null, null)?.use { cursor ->
            if (!cursor.moveToFirst()) return null
            return readCursorRow(parsedTree, rootDocUri, cursor)
        }
        return null
    }

    override fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry> {
        val parsedTree = Uri.parse(treeUri)
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(parsedTree, parentDocumentId)
        val entries = ArrayList<SafDocumentEntry>()
        resolver.query(childrenUri, projection, null, null, null)?.use { cursor ->
            while (cursor.moveToNext()) {
                val docId = cursor.getString(0) ?: continue
                val docUri = DocumentsContract.buildDocumentUriUsingTree(parsedTree, docId)
                entries.add(readCursorRow(parsedTree, docUri, cursor))
            }
        }
        return entries
    }

    override fun readDocumentText(docUri: String): String? {
        return try {
            resolver.openInputStream(Uri.parse(docUri))?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
        } catch (_: Exception) {
            null
        }
    }

    private fun readCursorRow(
        @Suppress("UNUSED_PARAMETER") parsedTree: Uri,
        docUri: Uri,
        cursor: android.database.Cursor,
    ): SafDocumentEntry {
        val docId = cursor.getString(0) ?: ""
        val name = cursor.getString(1) ?: ""
        val mime = cursor.getString(2) ?: "application/octet-stream"
        val size = if (cursor.isNull(3)) 0L else cursor.getLong(3).coerceAtLeast(0L)
        val modified = if (cursor.isNull(4)) 0L else cursor.getLong(4).coerceAtLeast(0L)
        return SafDocumentEntry(
            documentId = docId,
            name = name,
            mimeType = mime,
            size = size,
            lastModifiedMs = modified,
            uri = docUri.toString(),
        )
    }
}

/**
 * Puente estático invocado desde Kotlin (plugin/servicio) y Python (Chaquopy) para SAF real.
 */
object AndroidStorageBridge {
    @Volatile
    private var appContext: Context? = null

    @Volatile
    private var browser: SafTreeBrowser? = null

    @JvmStatic
    fun initialize(context: Context) {
        val appCtx = context.applicationContext
        appContext = appCtx
        browser = SafTreeBrowser(AndroidSafTreeProvider(appCtx))
    }

    fun persistTreePermission(context: Context, uri: Uri, flags: Int) {
        initialize(context)
        val readFlag = flags and Intent.FLAG_GRANT_READ_URI_PERMISSION
        val takeFlags = if (readFlag != 0) readFlag else Intent.FLAG_GRANT_READ_URI_PERMISSION
        try {
            context.contentResolver.takePersistableUriPermission(uri, takeFlags)
        } catch (_: Exception) {
            // Algunos proveedores emiten grants no persistibles; lo detectará validateTreeUri
        }
    }

    fun validateTreeUri(context: Context, treeUriString: String?): SafValidationResult {
        initialize(context)
        val activeBrowser = browser ?: return SafValidationResult(SafFolderStatus.UNCONFIGURED, "", null, null)
        return activeBrowser.validateTreeUri(treeUriString)
    }

    @JvmStatic
    fun validateTreeUriJson(treeUriString: String?): String {
        val activeBrowser = browser
        val res = activeBrowser?.validateTreeUri(treeUriString)
            ?: SafValidationResult(
                SafFolderStatus.UNAVAILABLE,
                treeUriString ?: "",
                null,
                "AndroidStorageBridge no inicializado",
            )
        return JSONObject().apply {
            put("status", res.status.wireName())
            put("uri", res.uri)
            put("display_name", res.displayName ?: JSONObject.NULL)
            put("error", res.error ?: JSONObject.NULL)
        }.toString()
    }

    @JvmStatic
    fun listAudioFilesJson(treeUriString: String): String {
        val activeBrowser = browser ?: return "[]"
        val files = activeBrowser.listAudioFiles(treeUriString)
        val arr = JSONArray()
        for (entry in files) {
            arr.put(
                JSONObject().apply {
                    put("uri", entry.uri)
                    put("name", entry.name)
                    put("relative_path", entry.relativePath)
                    put("size", entry.size)
                    put("mtime", entry.mtimeSec)
                    put("mime_type", entry.mimeType)
                },
            )
        }
        return arr.toString()
    }

    @JvmStatic
    fun statDocumentJson(docUriString: String): String? {
        val ctx = appContext ?: return null
        val projection = arrayOf(
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_SIZE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
        )
        return try {
            ctx.contentResolver.query(Uri.parse(docUriString), projection, null, null, null)?.use { cursor ->
                if (!cursor.moveToFirst()) return null
                val name = cursor.getString(0) ?: ""
                val size = if (cursor.isNull(1)) 0L else cursor.getLong(1).coerceAtLeast(0L)
                val mtimeMs = if (cursor.isNull(2)) 0L else cursor.getLong(2).coerceAtLeast(0L)
                val mime = cursor.getString(3) ?: "application/octet-stream"
                JSONObject().apply {
                    put("name", name)
                    put("size", size)
                    put("mtime", mtimeMs / 1000.0)
                    put("mime_type", mime)
                }.toString()
            }
        } catch (_: Exception) {
            null
        }
    }

    @JvmStatic
    fun openFileDescriptorForRead(docUriString: String): Int {
        val ctx = appContext ?: return -1
        return try {
            val pfd = ctx.contentResolver.openFileDescriptor(Uri.parse(docUriString), "r") ?: return -1
            pfd.detachFd()
        } catch (_: Exception) {
            -1
        }
    }

    @JvmStatic
    fun findSiblingTextJson(docUriString: String, extensionsCsv: String): String? {
        val activeBrowser = browser ?: return null
        val exts = extensionsCsv.split(',').map { it.trim() }.filter { it.isNotEmpty() }
        val result = activeBrowser.readSiblingText(docUriString, exts) ?: return null
        return JSONObject().apply {
            put("ext", result.first)
            put("content", result.second)
        }.toString()
    }

    @JvmStatic
    fun isDocumentReadable(docUriString: String): Boolean {
        return statDocumentJson(docUriString) != null
    }
}
