package ar.carpincho.rockola

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException
import java.io.InputStream

private class FakeDistAssetSource(
    private val tree: Map<String, Array<String>>,
    private val files: Map<String, ByteArray>,
    private val failOnOpen: Map<String, Exception> = emptyMap(),
    private val failOnRead: Set<String> = emptySet(),
) : DistAssetSource {
    override fun list(path: String): Array<String>? = tree[path]

    override fun open(path: String): InputStream {
        failOnOpen[path]?.let { throw it }
        val bytes = files[path] ?: throw FileNotFoundException("Asset no encontrado: $path")
        if (path in failOnRead) {
            return object : InputStream() {
                override fun read(): Int = throw IOException("Error de lectura simulado en $path")
            }
        }
        return ByteArrayInputStream(bytes)
    }
}

class EmbeddedPythonHostTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun validIndexHtml(): ByteArray =
        """<!doctype html><html><head><link rel="stylesheet" href="./assets/main.css"><link rel="manifest" href="./manifest.webmanifest"></head><body><div id="app">La Rockola</div><script type="module" src="./assets/main.js"></script></body></html>"""
            .toByteArray(Charsets.UTF_8)

    private fun validSource(
        extraFailures: Map<String, Exception> = emptyMap(),
        failOnRead: Set<String> = emptySet(),
        omitIndex: Boolean = false,
        omitJs: Boolean = false,
    ): FakeDistAssetSource {
        val rootEntries = mutableListOf("assets", "manifest.webmanifest")
        if (!omitIndex) rootEntries.add(0, "index.html")
        val assetEntries = mutableListOf("main.css", "empty_dir")
        if (!omitJs) assetEntries.add(0, "main.js")
        val files = mutableMapOf(
            "public/assets/main.css" to "body{background:#120e0b;color:#f5efe6;}".toByteArray(),
            "public/manifest.webmanifest" to """{"name":"La Rockola"}""".toByteArray(),
        )
        if (!omitIndex) files["public/index.html"] = validIndexHtml()
        if (!omitJs) files["public/assets/main.js"] = "console.log('rockola ready');".toByteArray()

        return FakeDistAssetSource(
            tree = mapOf(
                "public" to rootEntries.toTypedArray(),
                "public/assets" to assetEntries.toTypedArray(),
                // Subdirectorio vacío simulado en assets: list() devuelve vacío y open() lanza FileNotFoundException
                "public/assets/empty_dir" to emptyArray(),
            ),
            files = files,
            failOnOpen = extraFailures,
            failOnRead = failOnRead,
        )
    }

    @Test
    fun `extraccion limpia copia todos los archivos requeridos, valida y escribe el sello al final`() {
        val distDir = File(tmp.root, "dist")
        val progressHistory = mutableListOf<Int>()
        val extractor = DistAssetExtractor(validSource(), onProgress = { progressHistory.add(it) })

        extractor.ensureExtracted(distDir, currentStamp = "100-1")

        assertTrue(File(distDir, "index.html").isFile)
        assertTrue(File(distDir, "assets/main.js").isFile)
        assertTrue(File(distDir, "assets/main.css").isFile)
        assertEquals("100-1", File(distDir, ".dist_stamp").readText().trim())
        assertEquals(emptyList<String>(), extractor.validateDistribution(distDir))
        assertEquals(100, progressHistory.last())
    }

    @Test
    fun `distribucion ya instalada y valida no se reextrae pero repara si falta un asset esencial`() {
        val distDir = File(tmp.root, "dist")
        val extractor = DistAssetExtractor(validSource())
        extractor.ensureExtracted(distDir, currentStamp = "100-1")

        val sentinel = File(distDir, "assets/main.js").lastModified()
        extractor.ensureExtracted(distDir, currentStamp = "100-1")
        assertEquals(sentinel, File(distDir, "assets/main.js").lastModified())

        // Si alguien borró main.js aunque exista index.html y .dist_stamp, repara automáticamente
        assertTrue(File(distDir, "assets/main.js").delete())
        extractor.ensureExtracted(distDir, currentStamp = "100-1")
        assertTrue(File(distDir, "assets/main.js").isFile)
    }

    @Test
    fun `cambio de build stamp sustituye atomica y validamente la distribucion`() {
        val distDir = File(tmp.root, "dist")
        DistAssetExtractor(validSource()).ensureExtracted(distDir, currentStamp = "100-1")
        File(distDir, "obsolete.js").writeText("old")

        DistAssetExtractor(validSource()).ensureExtracted(distDir, currentStamp = "101-2")
        assertEquals("101-2", File(distDir, ".dist_stamp").readText().trim())
        assertFalse(File(distDir, "obsolete.js").exists())
        assertTrue(File(distDir, "assets/main.js").isFile)
    }

    @Test
    fun `falla explicitamente si falta index o falla copia de JS preservando distribucion previa`() {
        val distDir = File(tmp.root, "dist")
        DistAssetExtractor(validSource()).ensureExtracted(distDir, currentStamp = "100-1")

        var failedMissingIndex = false
        try {
            DistAssetExtractor(validSource(omitIndex = true)).ensureExtracted(distDir, currentStamp = "101-2")
        } catch (_: Exception) {
            failedMissingIndex = true
        }
        assertTrue(failedMissingIndex)
        assertEquals("100-1", File(distDir, ".dist_stamp").readText().trim())
        assertTrue(File(distDir, "index.html").isFile)

        var failedJsIo = false
        try {
            DistAssetExtractor(
                validSource(failOnRead = setOf("public/assets/main.js")),
            ).ensureExtracted(distDir, currentStamp = "102-3")
        } catch (_: IOException) {
            failedJsIo = true
        }
        assertTrue(failedJsIo)
        assertEquals("100-1", File(distDir, ".dist_stamp").readText().trim())
        assertTrue(File(distDir, "assets/main.js").isFile)
    }

    @Test
    fun `fallo de escritura o falta de espacio conserva la distribucion valida anterior mediante rollback`() {
        val distDir = File(tmp.root, "dist")
        DistAssetExtractor(validSource()).ensureExtracted(distDir, currentStamp = "100-1")

        var failedDiskFull = false
        try {
            DistAssetExtractor(
                validSource(extraFailures = mapOf("public/assets/main.css" to IOException("No space left on device"))),
            ).ensureExtracted(distDir, currentStamp = "103-4")
        } catch (_: IOException) {
            failedDiskFull = true
        }
        assertTrue(failedDiskFull)
        assertEquals("100-1", File(distDir, ".dist_stamp").readText().trim())
        assertTrue(File(distDir, "assets/main.css").isFile)
        assertTrue(tmp.root.listFiles()?.none { it.name.startsWith("dist.tmp-") } == true)
    }

    @Test
    fun `recupera backup previo si hubo interrupcion durante reemplazo anterior`() {
        val distDir = File(tmp.root, "dist")
        val backupDir = File(tmp.root, "dist.bak")
        DistAssetExtractor(validSource()).ensureExtracted(backupDir, currentStamp = "99-0")
        // Simula carpeta dist incompleta dejada por caída durante reemplazo
        distDir.mkdirs()
        File(distDir, "partial.txt").writeText("incomplete")

        val extractor = DistAssetExtractor(validSource())
        extractor.ensureExtracted(distDir, currentStamp = "99-0")

        assertEquals("99-0", File(distDir, ".dist_stamp").readText().trim())
        assertTrue(File(distDir, "index.html").isFile)
        assertTrue(File(distDir, "assets/main.js").isFile)
        assertFalse(File(distDir, "partial.txt").exists())
    }
}
