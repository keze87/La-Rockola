package ar.carpincho.rockola

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeSafProvider(
    private val persistedTrees: Set<String> = emptySet(),
    private val validTreeUris: Set<String> = emptySet(),
    private val roots: Map<String, SafDocumentEntry?> = emptyMap(),
    private val throwSecurityOnTree: Set<String> = emptySet(),
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

    override fun listChildren(treeUri: String, parentDocumentId: String): List<SafDocumentEntry> =
        treeChildren[Pair(treeUri, parentDocumentId)].orEmpty()

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
        assertEquals(".ass", lyrics?.first)
        assertEquals("[Script Info]\nTitle: Zamba", lyrics?.second)
        assertNull(browser.readSiblingText(rootTrackUri, listOf(".ass", ".lrc")))
    }
}
