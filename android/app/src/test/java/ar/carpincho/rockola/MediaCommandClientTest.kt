package ar.carpincho.rockola

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketException
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

private class MiniHttpServer(
    private val onRequest: (method: String, path: String, headers: Map<String, String>, body: String) -> Pair<Int, String>,
) {
    private val serverSocket = ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))
    private val running = AtomicBoolean(true)
    val port: Int get() = serverSocket.localPort

    private val worker = thread(isDaemon = true, name = "MiniHttp-${serverSocket.localPort}") {
        while (running.get()) {
            try {
                val client = serverSocket.accept()
                thread(isDaemon = true) {
                    client.use { sock ->
                        val input = BufferedInputStream(sock.getInputStream())
                        val reqLine = readLine(input) ?: return@use
                        val parts = reqLine.split(" ")
                        val method = parts.getOrNull(0) ?: "GET"
                        val path = parts.getOrNull(1) ?: "/"

                        val headers = LinkedHashMap<String, String>()
                        while (true) {
                            val line = readLine(input) ?: break
                            if (line.isEmpty()) break
                            val idx = line.indexOf(':')
                            if (idx > 0) {
                                headers[line.substring(0, idx).trim().lowercase()] = line.substring(idx + 1).trim()
                            }
                        }

                        val contentLength = headers["content-length"]?.toIntOrNull() ?: 0
                        val bodyBytes = ByteArray(contentLength)
                        var read = 0
                        while (read < contentLength) {
                            val n = input.read(bodyBytes, read, contentLength - read)
                            if (n <= 0) break
                            read += n
                        }
                        val body = String(bodyBytes, 0, read, Charsets.UTF_8)

                        val (code, respBody) = onRequest(method, path, headers, body)
                        val respBytes = respBody.toByteArray(Charsets.UTF_8)
                        val out = sock.getOutputStream()
                        val headerText =
                            "HTTP/1.1 $code OK\r\nContent-Type: application/json\r\nContent-Length: ${respBytes.size}\r\nConnection: close\r\n\r\n"
                        out.write(headerText.toByteArray(Charsets.US_ASCII))
                        out.write(respBytes)
                        out.flush()
                    }
                }
            } catch (_: SocketException) {
                break
            }
        }
    }

    private fun readLine(input: BufferedInputStream): String? {
        val baos = ByteArrayOutputStream()
        while (true) {
            val b = input.read()
            if (b == -1) return if (baos.size() == 0) null else String(baos.toByteArray(), Charsets.UTF_8)
            if (b == '\n'.code) break
            if (b != '\r'.code) baos.write(b)
        }
        return String(baos.toByteArray(), Charsets.UTF_8)
    }

    fun stop() {
        running.set(false)
        try {
            serverSocket.close()
        } catch (_: Exception) {
        }
        worker.join(500)
    }
}

class MediaCommandClientTest {

    private lateinit var hostServer: MiniHttpServer
    private lateinit var remoteServer: MiniHttpServer
    private val hostRequests = CopyOnWriteArrayList<String>()
    private val remoteRequests = CopyOnWriteArrayList<Pair<String, String?>>()
    private val remoteStatus = AtomicInteger(200)
    private val remoteDelayMs = AtomicInteger(0)

    @Before
    fun setUp() {
        hostRequests.clear()
        remoteRequests.clear()
        remoteStatus.set(200)
        remoteDelayMs.set(0)

        hostServer = MiniHttpServer { _, _, _, body ->
            hostRequests.add(body)
            200 to """{"status":"ok"}"""
        }

        remoteServer = MiniHttpServer { _, _, headers, body ->
            val delay = remoteDelayMs.get()
            if (delay > 0) {
                Thread.sleep(delay.toLong())
            }
            remoteRequests.add(body to headers["authorization"])
            remoteStatus.get() to """{"status":"ok"}"""
        }
    }

    @After
    fun tearDown() {
        hostServer.stop()
        remoteServer.stop()
    }

    @Test
    fun commandsRouteStrictlyToActiveTargetWithoutTouchingLocalHostInRemoteMode() {
        val hostOrigin = "http://127.0.0.1:${hostServer.port}"
        val remoteOrigin = "http://127.0.0.1:${remoteServer.port}"
        val client = MediaCommandClient(
            initialTarget = MediaTarget(MediaTargetMode.HOST, hostOrigin, null, 1L),
            timeoutMs = 500,
        )

        val latch1 = CountDownLatch(1)
        val res1 = AtomicReference<CommandResult>()
        client.sendCommand("pause", mapOf("state" to true)) {
            res1.set(it)
            latch1.countDown()
        }
        assertTrue(latch1.await(2, TimeUnit.SECONDS))
        assertTrue(res1.get() is CommandResult.Success)
        assertEquals(1, hostRequests.size)
        assertEquals(0, remoteRequests.size)

        client.setTarget(MediaTarget(MediaTargetMode.REMOTE, remoteOrigin, "Bearer secreto", 2L))
        val latch2 = CountDownLatch(1)
        val res2 = AtomicReference<CommandResult>()
        client.sendCommand("skip", emptyMap(), expectedGeneration = 2L) {
            res2.set(it)
            latch2.countDown()
        }
        assertTrue(latch2.await(2, TimeUnit.SECONDS))
        assertTrue(res2.get() is CommandResult.Success)
        assertEquals(1, hostRequests.size)
        assertEquals(1, remoteRequests.size)
        assertEquals("Bearer secreto", remoteRequests[0].second)
        assertTrue(remoteRequests[0].first.contains("\"cmd\":\"skip\""))

        client.shutdown()
    }

    @Test
    fun dropsStaleGenerationCommandsAfterTargetSwitch() {
        val hostOrigin = "http://127.0.0.1:${hostServer.port}"
        val remoteOrigin = "http://127.0.0.1:${remoteServer.port}"
        val client = MediaCommandClient(
            initialTarget = MediaTarget(MediaTargetMode.REMOTE, remoteOrigin, null, 10L),
            timeoutMs = 500,
        )
        client.setTarget(MediaTarget(MediaTargetMode.HOST, hostOrigin, null, 11L))

        val latch = CountDownLatch(1)
        val result = AtomicReference<CommandResult>()
        client.sendCommand("prev", emptyMap(), expectedGeneration = 10L) {
            result.set(it)
            latch.countDown()
        }
        assertTrue(latch.await(2, TimeUnit.SECONDS))
        assertTrue(result.get() is CommandResult.StaleTarget)
        assertEquals(0, remoteRequests.size)
        assertEquals(0, hostRequests.size)

        client.shutdown()
    }

    @Test
    fun reportsAuthFailureUnavailableEndpointServerErrorTimeoutAndDisconnectedExplicitly() {
        val remoteOrigin = "http://127.0.0.1:${remoteServer.port}"
        val client = MediaCommandClient(
            initialTarget = MediaTarget(MediaTargetMode.REMOTE, remoteOrigin, null, 1L),
            timeoutMs = 250,
        )

        fun execAndAwait(): CommandResult {
            val latch = CountDownLatch(1)
            val ref = AtomicReference<CommandResult>()
            client.sendCommand("pause") {
                ref.set(it)
                latch.countDown()
            }
            assertTrue(latch.await(3, TimeUnit.SECONDS))
            return ref.get()
        }

        remoteStatus.set(401)
        assertEquals(CommandResult.AuthFailed(401), execAndAwait())

        remoteStatus.set(404)
        assertEquals(CommandResult.EndpointUnavailable(404), execAndAwait())

        remoteStatus.set(503)
        assertEquals(CommandResult.ServerError(503), execAndAwait())

        remoteStatus.set(200)
        remoteDelayMs.set(600)
        assertTrue(execAndAwait() is CommandResult.Timeout)

        remoteServer.stop()
        remoteDelayMs.set(0)
        assertTrue(execAndAwait() is CommandResult.Disconnected)

        client.shutdown()
    }

    @Test
    fun fetchArtworkRetriesTransientFailureAndInvokesDecoder() {
        val attempts = AtomicInteger(0)
        val artServer = MiniHttpServer { _, _, _, _ ->
            if (attempts.incrementAndGet() == 1) {
                503 to "busy"
            } else {
                200 to "FAKE_JPG"
            }
        }
        val decodedPayloads = java.util.concurrent.CopyOnWriteArrayList<String>()
        val retryLatch = CountDownLatch(1)
        val client = MediaCommandClient(
            initialTarget = MediaTarget(MediaTargetMode.HOST, "http://127.0.0.1:${artServer.port}", null, 1L),
            timeoutMs = 500,
            artworkTimeoutMs = 1500,
            bitmapDecoder = { stream ->
                decodedPayloads.add(stream.readBytes().toString(Charsets.UTF_8))
                retryLatch.countDown()
                null
            },
        )
        client.fetchArtwork("http://127.0.0.1:${artServer.port}/cover?path=a.mp3", expectedGeneration = 1L) {}
        assertTrue(retryLatch.await(3, TimeUnit.SECONDS))
        assertEquals(2, attempts.get())
        assertEquals(listOf("FAKE_JPG"), decodedPayloads)
        assertNull(client.getCachedArtwork("http://127.0.0.1:${artServer.port}/cover?path=a.mp3", 1L))
        artServer.stop()
        client.shutdown()
    }
}
