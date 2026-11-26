package ar.carpincho.rockola

import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HostLifecycleRestartRaceTest {

    @Test
    fun `start esperando limpieza reinicia el servidor si se llama mientras el anterior esta en STOPPING`() {
        val coordinator = HostLifecycleCoordinator()
        val firstStarted = CountDownLatch(1)
        val allowFirstExit = CountDownLatch(1)
        val secondReady = CountDownLatch(1)
        val runCount = AtomicInteger(0)

        assertTrue(
            coordinator.start(
                port = 1729,
                musicDir = null,
                onRequestStop = {
                    // Simula apagado de Uvicorn que tarda unos ms
                    Thread {
                        Thread.sleep(120)
                        allowFirstExit.countDown()
                    }.start()
                },
            ) { onReady ->
                runCount.incrementAndGet()
                onReady()
                firstStarted.countDown()
                allowFirstExit.await(3, TimeUnit.SECONDS)
            },
        )
        assertTrue(firstStarted.await(2, TimeUnit.SECONDS))

        // Dispara stop en segundo plano y enseguida intenta arrancar de nuevo
        val stopThread = Thread { coordinator.stop(2000L) }
        stopThread.start()
        Thread.sleep(30)

        val restarted = coordinator.startWaitingForCleanup(
            port = 1729,
            musicDir = null,
            waitTimeoutMs = 3000L,
            onRequestStop = {},
        ) { onReady ->
            runCount.incrementAndGet()
            onReady()
            secondReady.countDown()
        }

        assertTrue("El segundo arranque debería esperar al stop y comenzar", restarted)
        assertTrue(secondReady.await(2, TimeUnit.SECONDS))
        assertEquals(2, runCount.get())

        stopThread.join(2000L)
        coordinator.stop(1000L)
    }
}
