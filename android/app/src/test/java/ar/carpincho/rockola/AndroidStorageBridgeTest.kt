package ar.carpincho.rockola

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeSafProvider(
    private val persistedTrees: Set<String> = emptySet(),
    private val validTreeUris: Set<String> = emptySet(),
    private val roots: Map<String, SafDocumentEntry?> = emptyMap(),
    private val documents: Map<String, SafDocumentEntry?> = emptyMap(),
    private val throwSecurityOnTree: Set<String> = emptySet(),
    private val throwSecurityOnDir: Set<String> = emptySet(),
    private val throwIoOnDir: Set<String> = emptySet(),
    private val treeChildren: Map<Pair<String, String>, List<SafDocumentEntry>> = emptyMap(),
    private val textFiles: Map<String, String> = emptyMap(),
) : SafTreeProvider {
    override fun isTreeUri(raw: String): Boolean = raw in validTreeUris

    override fun hasPersistedReadPermission(treeUri: String): Boolean = treeUri in persistedTrees

    override fun queryRootInfo(treeUri: String): SafDocumentEntry? {
        if (treeUri in throwSecurityOnTree) {
            throw SecurityException("Permiso revocado")
        }
        return roots[treeUri]
    }

    override fun queryDocumentInfo(treeUri: String, docUri: String): SafDocumentEntry? = documents[docUri]

    override fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry> {
        if (parentDocumentId in throwSecurityOnDir) throw SecurityException("Subcarpeta sin permiso")
        if (parentDocumentId in throwIoOnDir) throw IllegalStateException("Error del proveedor")
        return treeChildren[Pair(treeUri, parentDocumentId)].orEmpty()
    }

    override fun readDocumentText(docUri: String): String? = textFiles[docUri]
}

class AndroidStorageBridgeTest {

    @Test
    fun `validateTreeUri clasifica unconfigured, unsupported, permission revoked, unavailable y ok`() {
        val emptyResult = SafTreeBrowser(FakeSafProvider()).validateTreeUri("")
        assertEquals(SafFolderStatus.UNCONFIGURED, emptyResult.status)

        val rawPosix = SafTreeBrowser(FakeSafProvider()).validateTreeUri("/storage/emulated/0/Music")
        assertEquals(SafFolderStatus.UNSUPPORTED_PROVIDER, rawPosix.status)

        val nonTreeContent = SafTreeBrowser(
            FakeSafProvider(validTreeUris = emptySet()),
        ).validateTreeUri("content://media/external/audio/media")
        assertEquals(SafFolderStatus.UNSUPPORTED_PROVIDER, nonTreeContent.status)

        val revokedUri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        val revoked = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(revokedUri),
                persistedTrees = emptySet(),
            ),
        ).validateTreeUri(revokedUri)
        assertEquals(SafFolderStatus.PERMISSION_REVOKED, revoked.status)

        val sdUri = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
        val ejectedSd = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(sdUri),
                persistedTrees = setOf(sdUri),
                roots = emptyMap(),
            ),
        ).validateTreeUri(sdUri)
        assertEquals(SafFolderStatus.UNAVAILABLE, ejectedSd.status)

        val okSec = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(sdUri),
                persistedTrees = setOf(sdUri),
                throwSecurityOnTree = setOf(sdUri),
            ),
        ).validateTreeUri(sdUri)
        assertEquals(SafFolderStatus.PERMISSION_REVOKED, okSec.status)

        val valid = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(sdUri),
                persistedTrees = setOf(sdUri),
                roots = mapOf(
                    sdUri to SafDocumentEntry(
                        documentId = "ABCD-1234:Music",
                        name = "Musica SD",
                        mimeType = SafTreeBrowser.MIME_TYPE_DIR,
                        size = 0L,
                        lastModifiedMs = 1000L,
                        uri = "$sdUri/document/ABCD-1234%3AMusic",
                    ),
                ),
            ),
        ).validateTreeUri(sdUri)
        assertEquals(SafFolderStatus.OK, valid.status)
        assertEquals("Musica SD", valid.displayName)
    }

    @Test
    fun `listAudioFiles recorre subcarpetas, filtra audio y encuentra letras hermanas sin bucles`() {
        val treeUri = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
        val rootDocId = "ABCD-1234:Music"
        val subDocId = "ABCD-1234:Music/Folklore"
        val trackUri = "$treeUri/document/ABCD-1234%3AMusic%2FFolklore%2Fzamba.flac"
        val rootTrackUri = "$treeUri/document/ABCD-1234%3AMusic%2Frock.mp3"
        val assUri = "$treeUri/document/ABCD-1234%3AMusic%2FFolklore%2Fzamba.ass"
        val lrcUri = "$treeUri/document/ABCD-1234%3AMusic%2FFolklore%2Fzamba.lrc"

        val provider = FakeSafProvider(
            validTreeUris = setOf(treeUri),
            persistedTrees = setOf(treeUri),
            roots = mapOf(
                treeUri to SafDocumentEntry(
                    documentId = rootDocId,
                    name = "Music",
                    mimeType = SafTreeBrowser.MIME_TYPE_DIR,
                    size = 0L,
                    lastModifiedMs = 100L,
                    uri = "$treeUri/document/$rootDocId",
                ),
            ),
            treeChildren = mapOf(
                Pair(treeUri, rootDocId) to listOf(
                    SafDocumentEntry(subDocId, "Folklore", SafTreeBrowser.MIME_TYPE_DIR, 0L, 200L, "$treeUri/document/sub"),
                    SafDocumentEntry("ABCD-1234:Music/rock.mp3", "rock.mp3", "audio/mpeg", 4096L, 5000L, rootTrackUri),
                    SafDocumentEntry("ABCD-1234:Music/notas.txt", "notas.txt", "text/plain", 32L, 4000L, "$treeUri/document/notas"),
                ),
                Pair(treeUri, subDocId) to listOf(
                    // Referencia cíclica simulada hacia root que no debe colgar el recorrido
                    SafDocumentEntry(rootDocId, "..", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, "$treeUri/document/root"),
                    SafDocumentEntry("ABCD-1234:Music/Folklore/zamba.flac", "zamba.flac", "audio/flac", 98765L, 9000L, trackUri),
                    SafDocumentEntry("ABCD-1234:Music/Folklore/zamba.ass", "zamba.ass", "text/plain", 120L, 8000L, assUri),
                    SafDocumentEntry("ABCD-1234:Music/Folklore/zamba.lrc", "zamba.lrc", "text/plain", 80L, 8000L, lrcUri),
                ),
            ),
            textFiles = mapOf(
                assUri to "[Script Info]\nTitle: Zamba",
                lrcUri to "[00:01.00]Zamba",
            ),
        )

        val browser = SafTreeBrowser(provider)
        val found = browser.listAudioFiles(treeUri)
        assertEquals(2, found.size)
        assertTrue(found.any { it.uri == trackUri && it.relativePath == "Folklore/zamba.flac" && it.size == 98765L })
        assertTrue(found.any { it.uri == rootTrackUri && it.relativePath == "rock.mp3" })

        val lyrics = browser.readSiblingText(trackUri, listOf(".ass", ".lrc"))
        assertEquals(".ass", lyrics?.ext)
        assertEquals("[Script Info]\nTitle: Zamba", lyrics?.content)
        assertEquals(assUri, lyrics?.uri)
        assertNull(browser.readSiblingText(rootTrackUri, listOf(".ass", ".lrc")))
    }

    @Test
    fun `readSiblingText resuelve URI real y funciona con IDs opacos cacheados`() {
        val treeUri = "content://com.example.provider/tree/root-1"
        val folderDocId = "opaque-folder-99"
        val songDocId = "opaque-song-42"
        val lrcDocId = "opaque-lrc-43"
        val songUri = "$treeUri/document/$songDocId"
        val lrcUri = "$treeUri/document/$lrcDocId"

        val provider = FakeSafProvider(
            validTreeUris = setOf(treeUri),
            persistedTrees = setOf(treeUri),
            roots = mapOf(
                treeUri to SafDocumentEntry("root-1", "Music", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, "$treeUri/document/root-1"),
            ),
            treeChildren = mapOf(
                Pair(treeUri, "root-1") to listOf(
                    SafDocumentEntry(folderDocId, "Cumbia", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, "$treeUri/document/$folderDocId"),
                ),
                Pair(treeUri, folderDocId) to listOf(
                    SafDocumentEntry(songDocId, "la_cumbia.mp3", "audio/mpeg", 1024L, 100L, songUri),
                    SafDocumentEntry(lrcDocId, "la_cumbia.lrc", "text/plain", 64L, 100L, lrcUri),
                ),
            ),
            textFiles = mapOf(lrcUri to "[00:01.00]Cumbia"),
        )

        val browser = SafTreeBrowser(provider)
        assertEquals(1, browser.listAudioFiles(treeUri).size)
        val sibling = browser.readSiblingText(songUri, listOf(".ass", ".lrc"))
        assertNotNull(sibling)
        assertEquals(".lrc", sibling!!.ext)
        assertEquals("[00:01.00]Cumbia", sibling.content)
        assertEquals(lrcUri, sibling.uri)
    }

    @Test
    fun `isAuthorizedDocumentUri restringe acceso al arbol permitido y rechaza carpetas u otros proveedores`() {
        val treeOk = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
        val treeOtherSameProvider = "content://com.android.externalstorage.documents/tree/ABCD-1234%3ADocuments"
        val validSong = "$treeOk/document/ABCD-1234%3AMusic%2Fzamba.mp3"
        val folderDoc = "$treeOk/document/ABCD-1234%3AMusic"
        val outsideDoc = "$treeOtherSameProvider/document/ABCD-1234%3ADocuments%2Fprivado.txt"
        val otherProvider = "content://com.android.providers.downloads.documents/document/99"
        val missingDoc = "$treeOk/document/ABCD-1234%3AMusic%2Fno_existe.mp3"

        val browser = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(treeOk, treeOtherSameProvider),
                persistedTrees = setOf(treeOk, treeOtherSameProvider),
                documents = mapOf(
                    validSong to SafDocumentEntry("id1", "zamba.mp3", "audio/mpeg", 1024L, 100L, validSong),
                    folderDoc to SafDocumentEntry("id2", "Music", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, folderDoc),
                    outsideDoc to SafDocumentEntry("id3", "privado.txt", "text/plain", 50L, 100L, outsideDoc),
                    otherProvider to SafDocumentEntry("99", "otro.mp3", "audio/mpeg", 500L, 100L, otherProvider),
                ),
            ),
        )

        assertTrue(browser.isAuthorizedDocumentUri(validSong, listOf(treeOk), requireAudioExtension = true))
        org.junit.Assert.assertFalse(browser.isAuthorizedDocumentUri(outsideDoc, listOf(treeOk)))
        org.junit.Assert.assertFalse(browser.isAuthorizedDocumentUri(folderDoc, listOf(treeOk)))
        org.junit.Assert.assertFalse(browser.isAuthorizedDocumentUri(otherProvider, listOf(treeOk)))
        org.junit.Assert.assertFalse(browser.isAuthorizedDocumentUri(missingDoc, listOf(treeOk)))

        // Si se revoca el permiso persistente del árbol, rechaza también la canción válida
        val revokedBrowser = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(treeOk),
                persistedTrees = emptySet(),
                documents = mapOf(
                    validSong to SafDocumentEntry("id1", "zamba.mp3", "audio/mpeg", 1024L, 100L, validSong),
                ),
            ),
        )
        org.junit.Assert.assertFalse(revokedBrowser.isAuthorizedDocumentUri(validSong, listOf(treeOk)))
    }

    @Test
    fun `scanAudioFiles diferencia carpeta vacia, permiso revocado, SD ausente, fallo parcial y tamano desconocido`() {
        val treeOk = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic"
        val rootDocId = "ABCD-1234:Music"
        val subBadId = "ABCD-1234:Music/Prohibida"
        val unknownSizeTrack = "$treeOk/document/ABCD-1234%3AMusic%2Fstream.flac"

        // 1. Carpeta válida pero vacía -> SUCCESS_EMPTY
        val emptyRes = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(treeOk),
                persistedTrees = setOf(treeOk),
                roots = mapOf(
                    treeOk to SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, -1L, -1L, treeOk),
                ),
            ),
        ).scanAudioFiles(treeOk)
        assertEquals(SafScanStatus.SUCCESS_EMPTY, emptyRes.status)
        assertTrue(emptyRes.files.isEmpty())

        // 2. Permiso revocado -> PERMISSION_DENIED (no SUCCESS_EMPTY)
        val deniedRes = SafTreeBrowser(
            FakeSafProvider(validTreeUris = setOf(treeOk), persistedTrees = emptySet()),
        ).scanAudioFiles(treeOk)
        assertEquals(SafScanStatus.PERMISSION_DENIED, deniedRes.status)

        // 3. Tarjeta SD retirada -> STORAGE_UNAVAILABLE
        val unavailRes = SafTreeBrowser(
            FakeSafProvider(validTreeUris = setOf(treeOk), persistedTrees = setOf(treeOk), roots = emptyMap()),
        ).scanAudioFiles(treeOk)
        assertEquals(SafScanStatus.STORAGE_UNAVAILABLE, unavailRes.status)

        // 4. Subcarpeta inaccesible -> PARTIAL_FAILURE preservando las canciones leídas y tamaño desconocido (-1L)
        val partialRes = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(treeOk),
                persistedTrees = setOf(treeOk),
                roots = mapOf(
                    treeOk to SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, -1L, -1L, treeOk),
                ),
                throwSecurityOnDir = setOf(subBadId),
                treeChildren = mapOf(
                    Pair(treeOk, rootDocId) to listOf(
                        SafDocumentEntry(subBadId, "Prohibida", SafTreeBrowser.MIME_TYPE_DIR, -1L, -1L, "$treeOk/sub"),
                        SafDocumentEntry(
                            "ABCD-1234:Music/stream.flac",
                            "stream.flac",
                            "audio/flac",
                            -1L,
                            -1L,
                            unknownSizeTrack,
                        ),
                    ),
                ),
            ),
        ).scanAudioFiles(treeOk)
        assertEquals(SafScanStatus.PARTIAL_FAILURE, partialRes.status)
        assertEquals(1, partialRes.files.size)
        assertEquals(listOf(subBadId), partialRes.failedDirs)
        assertEquals(-1L, partialRes.files[0].size)
        assertTrue(partialRes.files[0].mtimeSec < 0.0)
    }

    @Test
    fun `escaneo paginado soporta 10000 archivos, cancelacion y acota parentCache`() {
        val treeOk = "content://com.android.externalstorage.documents/tree/BIG-SD%3AMusic"
        val rootDocId = "BIG-SD:Music"
        val dirCount = 20
        val perDir = 500 // 20 * 500 = 10.000 archivos
        val rootChildren = ArrayList<SafDocumentEntry>(dirCount)
        val childrenMap = HashMap<Pair<String, String>, List<SafDocumentEntry>>()

        for (d in 0 until dirCount) {
            val dirId = "$rootDocId/dir_$d"
            rootChildren.add(
                SafDocumentEntry(dirId, "dir_$d", SafTreeBrowser.MIME_TYPE_DIR, -1L, 100L, "$treeOk/dir_$d"),
            )
            val tracks = ArrayList<SafDocumentEntry>(perDir)
            for (i in 0 until perDir) {
                val docId = "$dirId/track_${d}_$i.mp3"
                tracks.add(
                    SafDocumentEntry(
                        docId,
                        "track_${d}_$i.mp3",
                        "audio/mpeg",
                        1024L,
                        1000L,
                        "$treeOk/document/$docId",
                    ),
                )
            }
            childrenMap[Pair(treeOk, dirId)] = tracks
        }
        childrenMap[Pair(treeOk, rootDocId)] = rootChildren

        val browser = SafTreeBrowser(
            FakeSafProvider(
                validTreeUris = setOf(treeOk),
                persistedTrees = setOf(treeOk),
                roots = mapOf(
                    treeOk to SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, -1L, 100L, treeOk),
                ),
                treeChildren = childrenMap,
            ),
            maxParentCacheSize = 256,
        )

        val sessionId = browser.startScanSession(treeOk)
        val seenUris = HashSet<String>()
        var batches = 0
        while (true) {
            val batch = browser.nextScanBatch(sessionId, batchSize = 500)
            batches += 1
            for (f in batch.files) {
                assertTrue("Entrada duplicada: ${f.uri}", seenUris.add(f.uri))
            }
            if (!batch.hasMore) break
        }
        assertEquals(10_000, seenUris.size)
        assertTrue(batches >= 20)
        assertTrue(browser.parentCacheSize() <= 256)

        // Cancelación temprana corta el recorrido sin procesar los 10.000
        val cancelSessionId = browser.startScanSession(treeOk)
        val firstBatch = browser.nextScanBatch(cancelSessionId, batchSize = 250)
        assertTrue(firstBatch.files.isNotEmpty())
        browser.cancelScanSession(cancelSessionId)
        val afterCancel = browser.nextScanBatch(cancelSessionId, batchSize = 250)
        assertTrue(afterCancel.files.isEmpty())
        assertEquals(false, afterCancel.hasMore)
    }

    @Test
    fun `readSiblingText cachea indice de letras por carpeta y evita re-listar en cada cancion`() {
        val treeUri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        val doc1 = "$treeUri/document/primary%3AMusic%2Ftema1.mp3"
        val doc2 = "$treeUri/document/primary%3AMusic%2Ftema2.mp3"
        val lrc1 = "$treeUri/document/primary%3AMusic%2Ftema1.lrc"
        var listCalls = 0
        var queryDocCalls = 0

        val baseProvider = FakeSafProvider(
            validTreeUris = setOf(treeUri),
            persistedTrees = setOf(treeUri),
            treeChildren = mapOf(
                Pair(treeUri, "primary:Music") to listOf(
                    SafDocumentEntry("primary:Music/tema1.mp3", "tema1.mp3", "audio/mpeg", 1024L, 100L, doc1),
                    SafDocumentEntry("primary:Music/tema2.mp3", "tema2.mp3", "audio/mpeg", 1024L, 100L, doc2),
                    SafDocumentEntry("primary:Music/tema1.lrc", "tema1.lrc", "text/plain", 64L, 100L, lrc1),
                ),
            ),
            textFiles = mapOf(lrc1 to "[00:01.00]Tema 1"),
        )
        val countingProvider = object : SafTreeProvider by baseProvider {
            override fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry> {
                listCalls += 1
                return baseProvider.listChildren(treeUri, parentDocumentId)
            }

            override fun queryDocumentInfo(treeUri: String, docUri: String): SafDocumentEntry? {
                queryDocCalls += 1
                return baseProvider.queryDocumentInfo(treeUri, docUri)
            }
        }

        val browser = SafTreeBrowser(countingProvider)
        val found1 = browser.readSiblingText(doc1, listOf(".ass", ".lrc"))
        assertEquals("[00:01.00]Tema 1", found1?.content)
        val missing2 = browser.readSiblingText(doc2, listOf(".ass", ".lrc"))
        assertNull(missing2)
        val found1Again = browser.readSiblingText(doc1, listOf(".ass", ".lrc"))
        assertEquals("[00:01.00]Tema 1", found1Again?.content)

        assertEquals(1, listCalls)
        assertEquals(0, queryDocCalls)
    }

    @Test
    fun `error en subcarpeta reporta PARTIAL_FAILURE y error en raiz reporta PROVIDER_ERROR sin fingir carpeta vacia`() {
        val treeUri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        val rootDocId = "primary:Music"
        val subBadId = "primary:Music/Corrupta"
        val subOkId = "primary:Music/Buena"
        val songOk = "$treeUri/document/primary%3AMusic%2FBuena%2Ftema.mp3"

        val partialProvider = FakeSafProvider(
            validTreeUris = setOf(treeUri),
            persistedTrees = setOf(treeUri),
            roots = mapOf(
                treeUri to SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, 0L, -1L, "$treeUri/document/$rootDocId"),
            ),
            throwIoOnDir = setOf(subBadId),
            treeChildren = mapOf(
                Pair(treeUri, rootDocId) to listOf(
                    SafDocumentEntry(subBadId, "Corrupta", SafTreeBrowser.MIME_TYPE_DIR, 0L, -1L, "$treeUri/document/bad"),
                    SafDocumentEntry(subOkId, "Buena", SafTreeBrowser.MIME_TYPE_DIR, 0L, -1L, "$treeUri/document/ok"),
                ),
                Pair(treeUri, subOkId) to listOf(
                    SafDocumentEntry("primary:Music/Buena/tema.mp3", "tema.mp3", "audio/mpeg", -1L, -1L, songOk),
                ),
            ),
        )
        val browser = SafTreeBrowser(partialProvider)
        val partialRes = browser.scanAudioFiles(treeUri)
        assertEquals(SafScanStatus.PARTIAL_FAILURE, partialRes.status)
        assertEquals(1, partialRes.files.size)
        assertEquals(listOf(subBadId), partialRes.failedDirs)

        // Si falla directamente la raíz (ej. cursor null -> IllegalStateException), reporta PROVIDER_ERROR
        val rootFailProvider = FakeSafProvider(
            validTreeUris = setOf(treeUri),
            persistedTrees = setOf(treeUri),
            roots = mapOf(
                treeUri to SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, 0L, -1L, "$treeUri/document/$rootDocId"),
            ),
            throwIoOnDir = setOf(rootDocId),
        )
        val failRes = SafTreeBrowser(rootFailProvider).scanAudioFiles(treeUri)
        assertEquals(SafScanStatus.PROVIDER_ERROR, failRes.status)
        assertTrue(failRes.files.isEmpty())
    }

    @Test
    fun `cancelScanSession libera la sesion sin requerir otro nextScanBatch y limita sesiones activas`() {
        val treeUri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        val rootDocId = "primary:Music"
        val song = "$treeUri/document/primary%3AMusic%2Ftema.mp3"
        val provider = FakeSafProvider(
            validTreeUris = setOf(treeUri),
            persistedTrees = setOf(treeUri),
            roots = mapOf(
                treeUri to SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, "$treeUri/document/$rootDocId"),
            ),
            treeChildren = mapOf(
                Pair(treeUri, rootDocId) to listOf(
                    SafDocumentEntry("primary:Music/tema.mp3", "tema.mp3", "audio/mpeg", 100L, 100L, song),
                ),
            ),
        )
        val browser = SafTreeBrowser(provider)
        val s1 = browser.startScanSession(treeUri)
        assertEquals(1, browser.activeScanSessionCount())
        browser.cancelScanSession(s1)
        assertEquals(0, browser.activeScanSessionCount())

        // Sesiones abandonadas se acotan al límite máximo
        repeat(6) {
            browser.startScanSession(treeUri)
        }
        assertTrue(browser.activeScanSessionCount() <= 4)
    }

    @Test
    fun `cancelacion concurrente espera fin de batch y expiracion determinista limpia sesiones vencidas`() {
        val treeUri = "content://com.android.externalstorage.documents/tree/primary%3AMusic"
        val rootDocId = "primary:Music"
        val subDocId = "primary:Music/Sub"
        val enteredList = java.util.concurrent.CountDownLatch(1)
        val allowListReturn = java.util.concurrent.CountDownLatch(1)
        var nowMs = 1_000_000L

        val slowProvider = object : SafTreeProvider {
            override fun isTreeUri(raw: String): Boolean = raw == treeUri
            override fun hasPersistedReadPermission(treeUri: String): Boolean = true
            override fun queryRootInfo(treeUri: String): SafDocumentEntry =
                SafDocumentEntry(rootDocId, "Music", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, treeUri)
            override fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry> {
                if (parentDocumentId == rootDocId) {
                    enteredList.countDown()
                    allowListReturn.await(2, java.util.concurrent.TimeUnit.SECONDS)
                    return listOf(
                        SafDocumentEntry(subDocId, "Sub", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, "$treeUri/sub"),
                        SafDocumentEntry("s1", "a.mp3", "audio/mpeg", 10L, 100L, "$treeUri/document/a.mp3"),
                    )
                }
                return emptyList()
            }
            override fun readDocumentText(docUri: String): String? = null
        }

        val browser = SafTreeBrowser(
            provider = slowProvider,
            clockMs = { nowMs },
            sessionTtlMs = 60_000L,
            maxScanSessions = 4,
        )
        val s1 = browser.startScanSession(treeUri)
        val batchResult = java.util.concurrent.atomic.AtomicReference<SafScanBatch>()
        val worker = Thread {
            batchResult.set(browser.nextScanBatch(s1, batchSize = 50))
        }.apply { start() }

        assertTrue(enteredList.await(2, java.util.concurrent.TimeUnit.SECONDS))
        // Cancelar mientras el hilo procesa el batch no borra ni corrompe la sesión antes de salir
        browser.cancelScanSession(s1)
        assertEquals(1, browser.activeScanSessionCount())

        allowListReturn.countDown()
        worker.join(2000L)
        assertEquals(false, batchResult.get().hasMore)
        assertEquals(0, browser.activeScanSessionCount())

        // Expiración determinista con reloj inyectado
        nowMs += 1_000L
        browser.startScanSession(treeUri)
        assertEquals(1, browser.activeScanSessionCount())
        nowMs += 65_000L
        browser.startScanSession(treeUri)
        // La expirada fue podada antes de crear la nueva -> sigue habiendo 1 sola sesión activa
        assertEquals(1, browser.activeScanSessionCount())
    }

    @Test
    fun `multiples bibliotecas SAF conviven en caches sin pisarse al escanear ni buscar letras`() {
        val treeA = "content://com.android.externalstorage.documents/tree/primary%3AMusicA"
        val treeB = "content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusicB"
        val docA = "$treeA/document/primary%3AMusicA%2Funo.mp3"
        val lrcA = "$treeA/document/primary%3AMusicA%2Funo.lrc"
        val docB = "$treeB/document/ABCD-1234%3AMusicB%2Fdos.mp3"
        val lrcB = "$treeB/document/ABCD-1234%3AMusicB%2Fdos.lrc"

        val baseProvider = FakeSafProvider(
            validTreeUris = setOf(treeA, treeB),
            persistedTrees = setOf(treeA, treeB),
            roots = mapOf(
                treeA to SafDocumentEntry("primary:MusicA", "MusicA", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, treeA),
                treeB to SafDocumentEntry("ABCD-1234:MusicB", "MusicB", SafTreeBrowser.MIME_TYPE_DIR, 0L, 100L, treeB),
            ),
            treeChildren = mapOf(
                Pair(treeA, "primary:MusicA") to listOf(
                    SafDocumentEntry("primary:MusicA/uno.mp3", "uno.mp3", "audio/mpeg", 100L, 100L, docA),
                    SafDocumentEntry("primary:MusicA/uno.lrc", "uno.lrc", "text/plain", 30L, 100L, lrcA),
                ),
                Pair(treeB, "ABCD-1234:MusicB") to listOf(
                    SafDocumentEntry("ABCD-1234:MusicB/dos.mp3", "dos.mp3", "audio/mpeg", 100L, 100L, docB),
                    SafDocumentEntry("ABCD-1234:MusicB/dos.lrc", "dos.lrc", "text/plain", 30L, 100L, lrcB),
                ),
            ),
            textFiles = mapOf(lrcA to "[00:01]Uno", lrcB to "[00:01]Dos"),
        )
        val listCalls = java.util.concurrent.atomic.AtomicInteger(0)
        val countingProvider = object : SafTreeProvider by baseProvider {
            override fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry> {
                listCalls.incrementAndGet()
                return baseProvider.listChildren(treeUri, parentDocumentId)
            }
        }
        val browser = SafTreeBrowser(countingProvider)
        val sA = browser.startScanSession(treeA)
        assertEquals(1, browser.nextScanBatch(sA).files.size)
        val sB = browser.startScanSession(treeB)
        assertEquals(1, browser.nextScanBatch(sB).files.size)
        assertEquals(2, listCalls.get())

        // Buscar letras de ambos árboles debe resolverse desde cache sin re-listar ninguno de los dos
        assertEquals("[00:01]Uno", browser.readSiblingText(docA, listOf(".lrc"))?.content)
        assertEquals("[00:01]Dos", browser.readSiblingText(docB, listOf(".lrc"))?.content)
        assertEquals(2, listCalls.get())
    }
}
