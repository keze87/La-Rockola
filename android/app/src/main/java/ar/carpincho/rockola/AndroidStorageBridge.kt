package ar.carpincho.rockola

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLDecoder
import java.util.Collections
import java.util.UUID
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

enum class SafScanStatus {
    SUCCESS_EMPTY,
    SUCCESS_WITH_FILES,
    PERMISSION_DENIED,
    STORAGE_UNAVAILABLE,
    UNSUPPORTED_PROVIDER,
    PARTIAL_FAILURE,
    PROVIDER_ERROR;

    fun wireName(): String = name.lowercase()
}

data class SafAudioTrackEntry(
    val uri: String,
    val name: String,
    val relativePath: String,
    val size: Long,
    val mtimeSec: Double,
    val mimeType: String,
)

data class SafScanResult(
    val status: SafScanStatus,
    val files: List<SafAudioTrackEntry>,
    val failedDirs: List<String> = emptyList(),
    val error: String? = null,
)

data class SafScanBatch(
    val status: SafScanStatus,
    val files: List<SafAudioTrackEntry>,
    val hasMore: Boolean,
    val failedDirs: List<String> = emptyList(),
    val error: String? = null,
)

interface SafTreeProvider {
    fun isTreeUri(raw: String): Boolean
    fun isDocumentUri(raw: String): Boolean = raw.startsWith("content://") && raw.contains("/document/")
    fun hasPersistedReadPermission(treeUri: String): Boolean
    fun queryRootInfo(treeUri: String): SafDocumentEntry?
    fun queryDocumentInfo(treeUri: String, docUri: String): SafDocumentEntry? = null
    fun belongsToTree(treeUri: String, docUri: String): Boolean = docUri.startsWith("$treeUri/document/")
    fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry>
    fun readDocumentText(docUri: String): String?
}

/**
 * Núcleo puro (testeable en JVM) para validación, recorrido recursivo y resolución de letras en SAF.
 */
class SafTreeBrowser(
    private val provider: SafTreeProvider,
    private val audioExtensions: Set<String> = DEFAULT_AUDIO_EXTENSIONS,
    private val maxParentCacheSize: Int = MAX_PARENT_CACHE_ENTRIES,
) {
    companion object {
        const val MIME_TYPE_DIR = "vnd.android.document/directory"
        const val MAX_PARENT_CACHE_ENTRIES = 2048
        val DEFAULT_AUDIO_EXTENSIONS = setOf(
            ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".mp4", ".mkv", ".avi", ".webm",
        )
    }

    private data class ScanSession(
        val treeUri: String,
        val queue: ArrayDeque<Pair<String, String>>,
        val visitedDirs: HashSet<String>,
        val seenFiles: HashSet<String> = HashSet(),
        val pendingBuffer: ArrayDeque<SafAudioTrackEntry> = ArrayDeque(),
        val failedDirs: ArrayList<String> = ArrayList(),
        var firstError: String? = null,
        var terminalStatus: SafScanStatus? = null,
        @Volatile var cancelled: Boolean = false,
    )

    private data class CachedDirLyrics(
        val fetchedAtMs: Long,
        val byLowerName: Map<String, String>,
    )

    private val cacheLock = Any()
    private var activeTreeForCache: String? = null
    private val parentCache = object : LinkedHashMap<String, Triple<String, String, String>>(128, 0.75f, true) {
        override fun removeEldestEntry(
            eldest: MutableMap.MutableEntry<String, Triple<String, String, String>>?,
        ): Boolean = size > maxParentCacheSize.coerceAtLeast(16)
    }
    private val dirLyricsCache = object : LinkedHashMap<String, CachedDirLyrics>(64, 0.75f, true) {
        override fun removeEldestEntry(
            eldest: MutableMap.MutableEntry<String, CachedDirLyrics>?,
        ): Boolean = size > 128
    }
    private val scanSessions = ConcurrentHashMap<String, ScanSession>()

    fun parentCacheSize(): Int = synchronized(cacheLock) { parentCache.size }

    private fun putParentCache(docUri: String, treeUri: String, dirDocId: String, name: String) {
        synchronized(cacheLock) {
            if (activeTreeForCache != null && activeTreeForCache != treeUri) {
                parentCache.clear()
                dirLyricsCache.clear()
            }
            activeTreeForCache = treeUri
            parentCache[docUri] = Triple(treeUri, dirDocId, name)
        }
    }

    private fun getParentCache(docUri: String): Triple<String, String, String>? =
        synchronized(cacheLock) { parentCache[docUri] }

    private fun indexDirLyrics(treeUri: String, dirDocId: String, children: List<SafDocumentEntry>): Map<String, String> {
        val map = HashMap<String, String>()
        for (child in children) {
            if (child.mimeType == MIME_TYPE_DIR) continue
            val lower = child.name.lowercase()
            if (lower.endsWith(".ass") || lower.endsWith(".lrc")) {
                map[lower] = child.uri
            }
        }
        synchronized(cacheLock) {
            if (activeTreeForCache != null && activeTreeForCache != treeUri) {
                parentCache.clear()
                dirLyricsCache.clear()
            }
            activeTreeForCache = treeUri
            dirLyricsCache["$treeUri|$dirDocId"] = CachedDirLyrics(System.currentTimeMillis(), map)
        }
        return map
    }

    private fun getOrFetchDirLyrics(treeUri: String, dirDocId: String): Map<String, String> {
        val now = System.currentTimeMillis()
        val key = "$treeUri|$dirDocId"
        synchronized(cacheLock) {
            val cached = dirLyricsCache[key]
            if (cached != null && (now - cached.fetchedAtMs) < 120_000L) {
                return cached.byLowerName
            }
        }
        val children = try {
            provider.listChildren(treeUri, dirDocId)
        } catch (_: Exception) {
            return emptyMap()
        }
        return indexDirLyrics(treeUri, dirDocId, children)
    }

    fun startScanSession(treeUriString: String): String {
        val sessionId = UUID.randomUUID().toString()
        synchronized(cacheLock) {
            if (activeTreeForCache != null && activeTreeForCache != treeUriString) {
                parentCache.clear()
            }
            dirLyricsCache.clear()
            activeTreeForCache = treeUriString
        }
        val validation = validateTreeUri(treeUriString)
        val terminal = when (validation.status) {
            SafFolderStatus.OK -> null
            SafFolderStatus.PERMISSION_REVOKED -> SafScanStatus.PERMISSION_DENIED
            SafFolderStatus.UNSUPPORTED_PROVIDER -> SafScanStatus.UNSUPPORTED_PROVIDER
            SafFolderStatus.UNCONFIGURED, SafFolderStatus.UNAVAILABLE -> SafScanStatus.STORAGE_UNAVAILABLE
        }
        if (terminal != null) {
            scanSessions[sessionId] = ScanSession(
                treeUri = treeUriString,
                queue = ArrayDeque(),
                visitedDirs = HashSet(),
                firstError = validation.error,
                terminalStatus = terminal,
            )
            return sessionId
        }

        val root = try {
            provider.queryRootInfo(treeUriString)
        } catch (sec: SecurityException) {
            scanSessions[sessionId] = ScanSession(
                treeUri = treeUriString,
                queue = ArrayDeque(),
                visitedDirs = HashSet(),
                firstError = sec.message ?: "Permiso SAF revocado.",
                terminalStatus = SafScanStatus.PERMISSION_DENIED,
            )
            return sessionId
        } catch (e: Exception) {
            scanSessions[sessionId] = ScanSession(
                treeUri = treeUriString,
                queue = ArrayDeque(),
                visitedDirs = HashSet(),
                firstError = e.message ?: "Error consultando raíz SAF.",
                terminalStatus = SafScanStatus.PROVIDER_ERROR,
            )
            return sessionId
        }

        if (root == null) {
            scanSessions[sessionId] = ScanSession(
                treeUri = treeUriString,
                queue = ArrayDeque(),
                visitedDirs = HashSet(),
                firstError = "La carpeta seleccionada no está disponible.",
                terminalStatus = SafScanStatus.STORAGE_UNAVAILABLE,
            )
            return sessionId
        }

        val queue = ArrayDeque<Pair<String, String>>()
        val visited = HashSet<String>()
        queue.add(Pair(root.documentId, ""))
        visited.add(root.documentId)
        scanSessions[sessionId] = ScanSession(treeUri = treeUriString, queue = queue, visitedDirs = visited)
        return sessionId
    }

    fun nextScanBatch(sessionId: String, batchSize: Int = 250): SafScanBatch {
        val session = scanSessions[sessionId]
            ?: return SafScanBatch(SafScanStatus.STORAGE_UNAVAILABLE, emptyList(), hasMore = false, error = "Sesión inexistente")
        if (session.cancelled) {
            scanSessions.remove(sessionId)
            return SafScanBatch(SafScanStatus.SUCCESS_EMPTY, emptyList(), hasMore = false)
        }
        session.terminalStatus?.let { term ->
            scanSessions.remove(sessionId)
            return SafScanBatch(term, emptyList(), hasMore = false, session.failedDirs, session.firstError)
        }

        val limit = batchSize.coerceAtLeast(1)
        val out = ArrayList<SafAudioTrackEntry>(limit)
        while (out.size < limit && session.pendingBuffer.isNotEmpty()) {
            out.add(session.pendingBuffer.removeFirst())
        }

        while (out.size < limit && session.queue.isNotEmpty() && !session.cancelled) {
            val (dirDocId, prefix) = session.queue.removeFirst()
            val children = try {
                provider.listChildren(session.treeUri, dirDocId)
            } catch (e: Exception) {
                session.failedDirs.add(dirDocId)
                if (session.firstError == null) {
                    session.firstError = e.message ?: e.javaClass.simpleName
                }
                continue
            }
            indexDirLyrics(session.treeUri, dirDocId, children)
            for (child in children) {
                if (child.mimeType == MIME_TYPE_DIR) {
                    if (session.visitedDirs.add(child.documentId)) {
                        val nextPrefix = if (prefix.isEmpty()) child.name else "$prefix/${child.name}"
                        session.queue.add(Pair(child.documentId, nextPrefix))
                    }
                    continue
                }
                putParentCache(child.uri, session.treeUri, dirDocId, child.name)
                val dotIdx = child.name.lastIndexOf('.')
                val ext = if (dotIdx >= 0) child.name.substring(dotIdx).lowercase() else ""
                if (ext !in audioExtensions) continue
                if (!session.seenFiles.add(child.uri)) continue

                val relPath = if (prefix.isEmpty()) child.name else "$prefix/${child.name}"
                val entry = SafAudioTrackEntry(
                    uri = child.uri,
                    name = child.name,
                    relativePath = relPath,
                    size = child.size,
                    mtimeSec = if (child.lastModifiedMs >= 0L) child.lastModifiedMs / 1000.0 else -1.0,
                    mimeType = child.mimeType,
                )
                if (out.size < limit) {
                    out.add(entry)
                } else {
                    session.pendingBuffer.addLast(entry)
                }
            }
        }

        if (session.cancelled) {
            scanSessions.remove(sessionId)
            return SafScanBatch(SafScanStatus.SUCCESS_EMPTY, emptyList(), hasMore = false)
        }

        val hasMore = session.pendingBuffer.isNotEmpty() || session.queue.isNotEmpty()
        val status = when {
            session.failedDirs.isNotEmpty() -> SafScanStatus.PARTIAL_FAILURE
            out.isNotEmpty() || session.seenFiles.isNotEmpty() -> SafScanStatus.SUCCESS_WITH_FILES
            else -> SafScanStatus.SUCCESS_EMPTY
        }
        if (!hasMore) {
            scanSessions.remove(sessionId)
        }
        return SafScanBatch(status, out, hasMore, session.failedDirs.toList(), session.firstError)
    }

    fun cancelScanSession(sessionId: String) {
        scanSessions[sessionId]?.cancelled = true
    }

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

    fun scanAudioFiles(treeUriString: String): SafScanResult {
        val validation = validateTreeUri(treeUriString)
        when (validation.status) {
            SafFolderStatus.OK -> Unit
            SafFolderStatus.PERMISSION_REVOKED ->
                return SafScanResult(SafScanStatus.PERMISSION_DENIED, emptyList(), error = validation.error)
            SafFolderStatus.UNSUPPORTED_PROVIDER ->
                return SafScanResult(SafScanStatus.UNSUPPORTED_PROVIDER, emptyList(), error = validation.error)
            SafFolderStatus.UNCONFIGURED, SafFolderStatus.UNAVAILABLE ->
                return SafScanResult(SafScanStatus.STORAGE_UNAVAILABLE, emptyList(), error = validation.error)
        }

        val root = try {
            provider.queryRootInfo(treeUriString)
        } catch (sec: SecurityException) {
            return SafScanResult(
                SafScanStatus.PERMISSION_DENIED,
                emptyList(),
                error = sec.message ?: "Permiso SAF revocado.",
            )
        } catch (e: Exception) {
            return SafScanResult(
                SafScanStatus.PROVIDER_ERROR,
                emptyList(),
                error = e.message ?: "Error consultando raíz SAF.",
            )
        } ?: return SafScanResult(
            SafScanStatus.STORAGE_UNAVAILABLE,
            emptyList(),
            error = "La carpeta seleccionada no está disponible.",
        )

        val collected = ArrayList<SafAudioTrackEntry>()
        val failedDirs = ArrayList<String>()
        var firstDirError: String? = null
        val visitedDirs = HashSet<String>()
        val queue = ArrayDeque<Pair<String, String>>()
        queue.add(Pair(root.documentId, ""))
        visitedDirs.add(root.documentId)

        while (queue.isNotEmpty()) {
            val (dirDocId, prefix) = queue.removeFirst()
            val children = try {
                provider.listChildren(treeUriString, dirDocId)
            } catch (e: Exception) {
                failedDirs.add(dirDocId)
                if (firstDirError == null) {
                    firstDirError = e.message ?: e.javaClass.simpleName
                }
                continue
            }
            for (child in children) {
                if (child.mimeType == MIME_TYPE_DIR) {
                    if (visitedDirs.add(child.documentId)) {
                        val nextPrefix = if (prefix.isEmpty()) child.name else "$prefix/${child.name}"
                        queue.add(Pair(child.documentId, nextPrefix))
                    }
                    continue
                }
                putParentCache(child.uri, treeUriString, dirDocId, child.name)
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
                        mtimeSec = if (child.lastModifiedMs >= 0L) child.lastModifiedMs / 1000.0 else -1.0,
                        mimeType = child.mimeType,
                    ),
                )
            }
        }
        val status = when {
            failedDirs.isNotEmpty() -> SafScanStatus.PARTIAL_FAILURE
            collected.isEmpty() -> SafScanStatus.SUCCESS_EMPTY
            else -> SafScanStatus.SUCCESS_WITH_FILES
        }
        return SafScanResult(status, collected, failedDirs, firstDirError)
    }

    fun listAudioFiles(treeUriString: String): List<SafAudioTrackEntry> = scanAudioFiles(treeUriString).files

    fun isAuthorizedDocumentUri(
        docUriString: String,
        allowedTreeUris: List<String>,
        requireAudioExtension: Boolean = false,
    ): Boolean {
        val cleanedDoc = docUriString.trim()
        if (!cleanedDoc.startsWith("content://") || !provider.isDocumentUri(cleanedDoc)) {
            return false
        }
        for (rawTree in allowedTreeUris) {
            val treeUri = rawTree.trim()
            if (treeUri.isEmpty()) continue
            if (!provider.isTreeUri(treeUri) || !provider.hasPersistedReadPermission(treeUri)) {
                continue
            }
            if (!provider.belongsToTree(treeUri, cleanedDoc)) {
                continue
            }
            val entry = try {
                provider.queryDocumentInfo(treeUri, cleanedDoc)
            } catch (_: Exception) {
                null
            } ?: continue
            if (entry.mimeType == MIME_TYPE_DIR) {
                continue
            }
            if (requireAudioExtension) {
                val dotIdx = entry.name.lastIndexOf('.')
                val ext = if (dotIdx >= 0) entry.name.substring(dotIdx).lowercase() else ""
                if (ext !in audioExtensions && !entry.mimeType.startsWith("audio/")) {
                    continue
                }
            }
            return true
        }
        return false
    }

    data class SiblingTextMatch(
        val ext: String,
        val content: String,
        val uri: String,
    )

    fun readSiblingText(docUriString: String, extensions: List<String>): SiblingTextMatch? {
        val cached = getParentCache(docUriString)
        val location = cached ?: parseLocationFromDocUri(docUriString) ?: return null
        val treeUri = location.first
        val parentDocId = location.second
        val parsedName = location.third
        val fileName = if (cached != null || parsedName.lastIndexOf('.') > 0) {
            parsedName
        } else {
            provider.queryDocumentInfo(treeUri, docUriString)?.name?.takeIf { it.isNotBlank() } ?: parsedName
        }
        val dotIdx = fileName.lastIndexOf('.')
        val stem = if (dotIdx > 0) fileName.substring(0, dotIdx) else fileName
        if (stem.isBlank()) return null

        val dirLyrics = getOrFetchDirLyrics(treeUri, parentDocId)
        if (dirLyrics.isEmpty()) return null

        for (rawExt in extensions) {
            val normalizedExt = if (rawExt.startsWith('.')) rawExt.lowercase() else ".${rawExt.lowercase()}"
            val targetKey = "$stem$normalizedExt".lowercase()
            val matchUri = dirLyrics[targetKey] ?: continue
            val content = provider.readDocumentText(matchUri)
            if (content != null) {
                return SiblingTextMatch(normalizedExt, content, matchUri)
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

    override fun isDocumentUri(raw: String): Boolean {
        return try {
            DocumentsContract.isDocumentUri(context, Uri.parse(raw))
        } catch (_: Exception) {
            false
        }
    }

    override fun belongsToTree(treeUri: String, docUri: String): Boolean {
        return try {
            val parsedTree = Uri.parse(treeUri)
            val parsedDoc = Uri.parse(docUri)
            if (parsedTree.authority != parsedDoc.authority) return false
            val treeId = DocumentsContract.getTreeDocumentId(parsedTree)
            val docTreeId = DocumentsContract.getTreeDocumentId(parsedDoc)
            treeId == docTreeId
        } catch (_: Exception) {
            false
        }
    }

    override fun queryDocumentInfo(treeUri: String, docUri: String): SafDocumentEntry? {
        return try {
            resolver.query(Uri.parse(docUri), projection, null, null, null)?.use { cursor ->
                if (!cursor.moveToFirst()) return null
                SafDocumentEntry(
                    documentId = cursor.getString(0) ?: "",
                    name = cursor.getString(1) ?: "",
                    mimeType = cursor.getString(2) ?: "application/octet-stream",
                    size = if (cursor.isNull(3)) -1L else cursor.getLong(3),
                    lastModifiedMs = if (cursor.isNull(4)) 0L else cursor.getLong(4),
                    uri = docUri,
                )
            }
        } catch (_: Exception) {
            null
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
        val size = if (cursor.isNull(3)) -1L else cursor.getLong(3).coerceAtLeast(0L)
        val modified = if (cursor.isNull(4)) -1L else cursor.getLong(4).coerceAtLeast(0L)
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
    fun startSafScanJson(treeUriString: String): String {
        val activeBrowser = browser ?: return ""
        return activeBrowser.startScanSession(treeUriString)
    }

    @JvmStatic
    fun nextSafScanBatchJson(sessionId: String, batchSize: Int = 250): String {
        val activeBrowser = browser ?: return JSONObject().apply {
            put("status", SafScanStatus.STORAGE_UNAVAILABLE.wireName())
            put("files", JSONArray())
            put("has_more", false)
            put("failed_dirs", JSONArray())
            put("error", "AndroidStorageBridge no inicializado")
        }.toString()
        val batch = activeBrowser.nextScanBatch(sessionId, batchSize)
        val arr = JSONArray()
        for (entry in batch.files) {
            arr.put(
                JSONObject().apply {
                    put("uri", entry.uri)
                    put("name", entry.name)
                    put("relative_path", entry.relativePath)
                    put("size", if (entry.size >= 0L) entry.size else JSONObject.NULL)
                    put("mtime", if (entry.mtimeSec >= 0.0) entry.mtimeSec else JSONObject.NULL)
                    put("mime_type", entry.mimeType)
                },
            )
        }
        val failedArr = JSONArray()
        for (d in batch.failedDirs) failedArr.put(d)
        return JSONObject().apply {
            put("status", batch.status.wireName())
            put("files", arr)
            put("has_more", batch.hasMore)
            put("failed_dirs", failedArr)
            put("error", batch.error ?: JSONObject.NULL)
        }.toString()
    }

    @JvmStatic
    fun cancelSafScan(sessionId: String) {
        browser?.cancelScanSession(sessionId)
    }

    @JvmStatic
    fun scanAudioFilesJson(treeUriString: String): String {
        val activeBrowser = browser ?: return JSONObject().apply {
            put("status", SafScanStatus.STORAGE_UNAVAILABLE.wireName())
            put("files", JSONArray())
            put("failed_dirs", JSONArray())
            put("error", "AndroidStorageBridge no inicializado")
        }.toString()
        val res = activeBrowser.scanAudioFiles(treeUriString)
        val arr = JSONArray()
        for (entry in res.files) {
            arr.put(
                JSONObject().apply {
                    put("uri", entry.uri)
                    put("name", entry.name)
                    put("relative_path", entry.relativePath)
                    put("size", if (entry.size >= 0L) entry.size else JSONObject.NULL)
                    put("mtime", if (entry.mtimeSec >= 0.0) entry.mtimeSec else JSONObject.NULL)
                    put("mime_type", entry.mimeType)
                },
            )
        }
        val failedArr = JSONArray()
        for (d in res.failedDirs) failedArr.put(d)
        return JSONObject().apply {
            put("status", res.status.wireName())
            put("files", arr)
            put("failed_dirs", failedArr)
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
                    put("size", if (entry.size >= 0L) entry.size else JSONObject.NULL)
                    put("mtime", if (entry.mtimeSec >= 0.0) entry.mtimeSec else JSONObject.NULL)
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
                val size: Any = if (cursor.isNull(1)) JSONObject.NULL else cursor.getLong(1).coerceAtLeast(0L)
                val mtime: Any = if (cursor.isNull(2)) JSONObject.NULL else cursor.getLong(2).coerceAtLeast(0L) / 1000.0
                val mime = cursor.getString(3) ?: "application/octet-stream"
                JSONObject().apply {
                    put("name", name)
                    put("size", size)
                    put("mtime", mtime)
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
            put("ext", result.ext)
            put("content", result.content)
            put("uri", result.uri)
        }.toString()
    }

    @JvmStatic
    fun isDocumentReadable(docUriString: String): Boolean {
        return statDocumentJson(docUriString) != null
    }

    @JvmStatic
    fun isAuthorizedDocumentUri(
        docUriString: String?,
        allowedTreesJson: String?,
        requireAudioExtension: Boolean = false,
    ): Boolean {
        val activeBrowser = browser ?: return false
        val docUri = docUriString?.trim().orEmpty()
        if (docUri.isEmpty()) return false
        val allowedTrees = try {
            val arr = JSONArray(allowedTreesJson ?: "[]")
            buildList {
                for (i in 0 until arr.length()) {
                    val item = arr.optString(i, "").trim()
                    if (item.isNotEmpty()) add(item)
                }
            }
        } catch (_: Exception) {
            emptyList()
        }
        if (allowedTrees.isEmpty()) return false
        return activeBrowser.isAuthorizedDocumentUri(docUri, allowedTrees, requireAudioExtension)
    }

    @JvmStatic
    fun isUnmeteredWifiAvailable(): Boolean {
        val ctx = appContext ?: return false
        return try {
            val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
            if (cm.isActiveNetworkMetered) return false
            val network = cm.activeNetwork ?: return false
            val caps = cm.getNetworkCapabilities(network) ?: return false
            val hasInternet = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            val isNotMetered = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
            val isWifiOrEthernet =
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
                    caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
            hasInternet && isNotMetered && isWifiOrEthernet
        } catch (_: Exception) {
            false
        }
    }
}
