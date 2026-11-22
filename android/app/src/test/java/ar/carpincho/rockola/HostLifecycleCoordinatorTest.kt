package ar.carpincho.rockola

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class HostLifecycleCoordinatorTest {

    @Test
    fun `start es idempotente y evita hilos duplicados bajo concurrencia`() {
        val observedStates = CopyOnWriteArrayList<HostServerState>()
        val coordinator = HostLifecycleCoordinator(
            onStateChanged = { state, _ -> observedStates.add(state) },
        )

        val spawnedCount = AtomicInteger(0)
        val enteredLatch = CountDownLatch(1)
        val releaseLatch = CountDownLatch(1)

        val starterResults = CopyOnWriteArrayList<Boolean>()
        val raceLatch = CountDownLatch(4)
        val callers = (0 until 4).map {
            Thread {
                val started = coordinator.start(
                    port = 1729,
                    musicDir = null,
                    onRequestStop = { releaseLatch.countDown() },
                ) { onReady ->
                    spawnedCount.incrementAndGet()
                    onReady()
                    enteredLatch.countDown()
                    releaseLatch.await(3, TimeUnit.SECONDS)
                }
                starterResults.add(started)
                raceLatch.countDown()
            }.apply { start() }
        }

        assertTrue(raceLatch.await(3, TimeUnit.SECONDS))
        callers.forEach { it.join(1000) }
        assertTrue(enteredLatch.await(2, TimeUnit.SECONDS))

        assertEquals(1, spawnedCount.get())
        assertEquals(1, starterResults.count { it })
        assertEquals(3, starterResults.count { !it })
        assertEquals(HostServerState.READY, coordinator.state)
        assertTrue(coordinator.isRunning)

        // Llamar nuevamente en caliente tampoco crea otro hilo
        assertFalse(
            coordinator.start(1729, null, {}) {
                spawnedCount.incrementAndGet()
            },
        )
        assertEquals(1, spawnedCount.get())

        assertTrue(coordinator.stop(timeoutMs = 2000L))
        assertEquals(HostServerState.STOPPED, coordinator.state)
        assertFalse(coordinator.isRunning)
        assertTrue(observedStates.contains(HostServerState.STARTING))
        assertTrue(observedStates.contains(HostServerState.READY))
        assertTrue(observedStates.contains(HostServerState.STOPPING))
        assertEquals(HostServerState.STOPPED, observedStates.last())
    }

    @Test
    fun `stop es acotado, sin deadlock y espera al hilo del servidor`() {
        val coordinator = HostLifecycleCoordinator()
        val readyLatch = CountDownLatch(1)
        val stopRequested = AtomicBoolean(false)
        val allowExit = CountDownLatch(1)
        val finished = AtomicBoolean(false)

        assertTrue(
            coordinator.start(
                port = 1829,
                musicDir = null,
                onRequestStop = {
                    stopRequested.set(true)
                    Thread { allowExit.countDown() }.start()
                },
            ) { onReady ->
                onReady()
                readyLatch.countDown()
                allowExit.await(3, TimeUnit.SECONDS)
                // Simula consulta de estado desde el hilo worker antes de salir (sin deadlock)
                coordinator.state
                finished.set(true)
            },
        )
        assertTrue(readyLatch.await(2, TimeUnit.SECONDS))

        val clean = coordinator.stop(timeoutMs = 2000L)
        assertTrue(clean)
        assertTrue(stopRequested.get())
        assertTrue(finished.get())
        assertEquals(HostServerState.STOPPED, coordinator.state)
        // Segundo stop sobre estado STOPPED es idempotente
        assertTrue(coordinator.stop(timeoutMs = 500L))
    }

    @Test
    fun `stop ante hilo colgado respeta timeout acotado y marca error`() {
        val coordinator = HostLifecycleCoordinator()
        val readyLatch = CountDownLatch(1)
        val releaseZombie = CountDownLatch(1)
        val zombieExited = CountDownLatch(1)

        assertTrue(
            coordinator.start(
                port = 1729,
                musicDir = null,
                onRequestStop = { /* No libera el hilo a propósito */ },
            ) { onReady ->
                onReady()
                readyLatch.countDown()
                releaseZombie.await(5, TimeUnit.SECONDS)
                zombieExited.countDown()
            },
        )
        assertTrue(readyLatch.await(2, TimeUnit.SECONDS))

        val startNs = System.nanoTime()
        val clean = coordinator.stop(timeoutMs = 150L)
        val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNs)

        assertFalse(clean)
        assertTrue("El stop acotado tardó demasiado: ${elapsedMs}ms", elapsedMs < 1000L)
        assertEquals(HostServerState.FAILED, coordinator.state)
        assertTrue((coordinator.lastError ?: "").isNotBlank())

        // Liberar el hilo zombi luego no pisa el nuevo arranque
        val restartedLatch = CountDownLatch(1)
        val stopNew = CountDownLatch(1)
        assertTrue(
            coordinator.start(1729, null, { stopNew.countDown() }) { onReady ->
                onReady()
                restartedLatch.countDown()
                stopNew.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(restartedLatch.await(2, TimeUnit.SECONDS))
        releaseZombie.countDown()
        assertTrue(zombieExited.await(2, TimeUnit.SECONDS))
        assertEquals(HostServerState.READY, coordinator.state)

        assertTrue(coordinator.stop(1000L))
        assertEquals(HostServerState.STOPPED, coordinator.state)
    }

    @Test
    fun `fallo inesperado en runner pasa a FAILED y permite reintentar`() {
        val failedLatch = CountDownLatch(1)
        val coord = HostLifecycleCoordinator(
            onStateChanged = { st, _ ->
                if (st == HostServerState.FAILED) failedLatch.countDown()
            },
        )
        assertTrue(
            coord.start(1729, null, { }) {
                throw IllegalStateException("Puerto 1729 ocupado")
            },
        )
        assertTrue(failedLatch.await(2, TimeUnit.SECONDS))
        assertEquals(HostServerState.FAILED, coord.state)
        assertTrue(coord.lastError?.contains("Puerto 1729 ocupado") == true)
        assertFalse(coord.isRunning)

        // Reintento luego de FAILED vuelve a arrancar normalmente
        val okLatch = CountDownLatch(1)
        val stopLatch = CountDownLatch(1)
        assertTrue(
            coord.start(1730, null, { stopLatch.countDown() }) { onReady ->
                onReady()
                okLatch.countDown()
                stopLatch.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(okLatch.await(2, TimeUnit.SECONDS))
        assertEquals(HostServerState.READY, coord.state)
        assertNull(coord.lastError)
        assertTrue(coord.stop(1000L))
        assertEquals(HostServerState.STOPPED, coord.state)
    }

    @Test
    fun `permanece en STARTING hasta que onReady es invocado y pasa a FAILED si runner rechaza el arranque`() {
        val becameReady = CountDownLatch(1)
        val coord = HostLifecycleCoordinator(
            onStateChanged = { st, _ ->
                if (st == HostServerState.READY) becameReady.countDown()
            },
        )
        val runnerEntered = CountDownLatch(1)
        val allowReady = CountDownLatch(1)
        val allowExit = CountDownLatch(1)

        assertTrue(
            coord.start(1729, null, { allowExit.countDown() }) { onReady ->
                runnerEntered.countDown()
                allowReady.await(2, TimeUnit.SECONDS)
                onReady()
                allowExit.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(runnerEntered.await(2, TimeUnit.SECONDS))
        // Antes de que Uvicorn termine startup(), el estado debe seguir siendo STARTING (no READY)
        assertEquals(HostServerState.STARTING, coord.state)

        allowReady.countDown()
        assertTrue(becameReady.await(2, TimeUnit.SECONDS))
        assertEquals(HostServerState.READY, coord.state)

        assertTrue(coord.stop(1000L))
        assertEquals(HostServerState.STOPPED, coord.state)

        // Si el arranque es rechazado con excepción (por ej. hilo previo en stopping), queda en FAILED con lastError
        val failedLatch = CountDownLatch(1)
        val coord2 = HostLifecycleCoordinator(
            onStateChanged = { st, _ ->
                if (st == HostServerState.FAILED) failedLatch.countDown()
            },
        )
        assertTrue(
            coord2.start(1729, null, {}) {
                throw IllegalStateException("El servidor embebido rechazó el arranque (estado: stopping)")
            },
        )
        assertTrue(failedLatch.await(2, TimeUnit.SECONDS))
        assertEquals(HostServerState.FAILED, coord2.state)
        assertTrue(coord2.lastError?.contains("stopping") == true)
    }
}
