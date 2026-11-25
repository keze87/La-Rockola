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
    fun `stop ante hilo colgado pasa a STOP_TIMED_OUT, bloquea reinicios y pasa a STOPPED al terminar`() {
        val coordinator = HostLifecycleCoordinator()
        val readyLatch = CountDownLatch(1)
        val releaseZombie = CountDownLatch(1)
        val zombieExited = CountDownLatch(1)
        val stopHookCalls = AtomicInteger(0)

        assertTrue(
            coordinator.start(
                port = 1729,
                musicDir = null,
                onRequestStop = { stopHookCalls.incrementAndGet() },
            ) { onReady ->
                onReady()
                readyLatch.countDown()
                releaseZombie.await(5, TimeUnit.SECONDS)
                zombieExited.countDown()
            },
        )
        assertTrue(readyLatch.await(2, TimeUnit.SECONDS))

        val startNs = System.nanoTime()
        val clean = coordinator.stop(timeoutMs = 120L)
        val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNs)

        assertFalse(clean)
        assertTrue("El stop acotado tardó demasiado: ${elapsedMs}ms", elapsedMs < 1000L)
        assertEquals(HostServerState.STOP_TIMED_OUT, coordinator.state)
        assertTrue(coordinator.hasActiveWorker)
        assertTrue((coordinator.lastError ?: "").isNotBlank())

        // No debe permitir iniciar otro servidor mientras el worker anterior sigue vivo
        val secondSpawned = AtomicBoolean(false)
        assertFalse(
            coordinator.start(1729, null, {}) {
                secondSpawned.set(true)
            },
        )
        assertFalse(secondSpawned.get())

        // Un nuevo intento de stop() sigue invocando el stopHook sin perder la referencia al worker
        assertFalse(coordinator.stop(timeoutMs = 50L))
        assertEquals(2, stopHookCalls.get())
        assertEquals(HostServerState.STOP_TIMED_OUT, coordinator.state)
        assertTrue(coordinator.hasActiveWorker)

        // Cuando el worker anterior finalmente termina, el estado pasa a STOPPED y permite reiniciar
        releaseZombie.countDown()
        assertTrue(zombieExited.await(2, TimeUnit.SECONDS))
        val deadline = System.currentTimeMillis() + 2000L
        while (coordinator.state != HostServerState.STOPPED && System.currentTimeMillis() < deadline) {
            Thread.sleep(10L)
        }
        assertEquals(HostServerState.STOPPED, coordinator.state)
        assertFalse(coordinator.hasActiveWorker)
        assertNull(coordinator.lastError)

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
        assertEquals(HostServerState.READY, coordinator.state)

        assertTrue(coordinator.stop(1000L))
        assertEquals(HostServerState.STOPPED, coordinator.state)
    }

    @Test
    fun `stop concurrente espera al mismo worker y termina en STOPPED`() {
        val coordinator = HostLifecycleCoordinator()
        val readyLatch = CountDownLatch(1)
        val allowExit = CountDownLatch(1)
        val stopCalls = AtomicInteger(0)

        assertTrue(
            coordinator.start(
                port = 1731,
                musicDir = null,
                onRequestStop = {
                    if (stopCalls.incrementAndGet() == 1) {
                        Thread {
                            Thread.sleep(80L)
                            allowExit.countDown()
                        }.start()
                    }
                },
            ) { onReady ->
                onReady()
                readyLatch.countDown()
                allowExit.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(readyLatch.await(2, TimeUnit.SECONDS))

        val results = CopyOnWriteArrayList<Boolean>()
        val done = CountDownLatch(3)
        repeat(3) {
            Thread {
                results.add(coordinator.stop(timeoutMs = 2000L))
                done.countDown()
            }.start()
        }
        assertTrue(done.await(3, TimeUnit.SECONDS))
        assertEquals(listOf(true, true, true), results.toList())
        assertEquals(HostServerState.STOPPED, coordinator.state)
        assertFalse(coordinator.hasActiveWorker)
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

    @Test
    fun `politica de locks y onTaskRemoved solo mantiene vivo en pausa si hay cliente remoto`() {
        assertFalse(ServicePowerPolicy.shouldAcquireWifiLock(MediaTargetMode.HOST, hasRemoteClients = false))
        assertTrue(ServicePowerPolicy.shouldAcquireWifiLock(MediaTargetMode.HOST, hasRemoteClients = true))
        assertTrue(ServicePowerPolicy.shouldAcquireWifiLock(MediaTargetMode.REMOTE, hasRemoteClients = false))

        assertTrue(ServicePowerPolicy.shouldStopOnTaskRemoved(isMediaPlaying = false, hasRemoteClients = false))
        assertFalse(ServicePowerPolicy.shouldStopOnTaskRemoved(isMediaPlaying = false, hasRemoteClients = true))
        assertFalse(ServicePowerPolicy.shouldStopOnTaskRemoved(isMediaPlaying = true, hasRemoteClients = false))

        assertTrue(
            ServicePowerPolicy.shouldStopForeground(
                isHostRunning = true,
                hasRemoteClients = false,
                isUiVisible = false,
            ),
        )
        assertFalse(
            ServicePowerPolicy.shouldStopForeground(
                isHostRunning = true,
                hasRemoteClients = false,
                isUiVisible = true,
            ),
        )
        assertFalse(
            ServicePowerPolicy.shouldStopForeground(
                isHostRunning = true,
                hasRemoteClients = true,
            ),
        )
        assertTrue(
            ServicePowerPolicy.shouldStopForeground(
                isHostRunning = true,
                hasRemoteClients = true,
                isUiVisible = true,
                forceStop = true,
            ),
        )
        assertTrue(ServicePowerPolicy.shouldStopForeground(isHostRunning = false, isUiVisible = true))

        // Mientras la radio sintetiza entre temas, no se debe bajar el foreground ni soltar locks Wi-Fi
        assertFalse(
            ServicePowerPolicy.shouldStopForeground(
                isHostRunning = true,
                hasRemoteClients = false,
                isUiVisible = false,
                isRadioSynthesizing = true,
            ),
        )
        assertTrue(
            ServicePowerPolicy.shouldAcquireWifiLock(
                MediaTargetMode.HOST,
                hasRemoteClients = false,
                isActivePlaybackOrRadio = true,
            ),
        )
        assertTrue(
            ServicePowerPolicy.shouldDelayDemote(
                isMediaPlaying = false,
                isRadioSynthesizing = true,
            ),
        )
        assertFalse(
            ServicePowerPolicy.shouldDelayDemote(
                isMediaPlaying = false,
                isRadioSynthesizing = false,
            ),
        )
    }

    @Test
    fun `shutdown cierra los executors internos del coordinador`() {
        val coord = HostLifecycleCoordinator()
        coord.shutdown()
        assertFalse(coord.isRunning)
    }

    @Test
    fun `stop respeta timeout aunque el hook de apagado se bloquee`() {
        val hookRelease = CountDownLatch(1)
        val workerRelease = CountDownLatch(1)
        val startedLatch = CountDownLatch(1)
        val coord = HostLifecycleCoordinator()

        assertTrue(
            coord.start(
                port = 1729,
                musicDir = null,
                onRequestStop = {
                    hookRelease.await(5, TimeUnit.SECONDS)
                },
            ) { onReady ->
                onReady()
                startedLatch.countDown()
                workerRelease.await(5, TimeUnit.SECONDS)
            },
        )
        assertTrue(startedLatch.await(2, TimeUnit.SECONDS))

        val t0 = System.currentTimeMillis()
        val stopped = coord.stop(timeoutMs = 120L)
        val elapsedMs = System.currentTimeMillis() - t0

        assertFalse(stopped)
        assertTrue("El stop debe respetar el timeout acotado (tardó ${elapsedMs}ms)", elapsedMs < 900L)
        assertEquals(HostServerState.STOP_TIMED_OUT, coord.state)
        assertTrue(coord.hasActiveWorker)

        // Liberamos hook y worker: pasa a STOPPED y vuelve a permitir start
        hookRelease.countDown()
        workerRelease.countDown()
        val deadline = System.currentTimeMillis() + 2000L
        while (coord.state != HostServerState.STOPPED && System.currentTimeMillis() < deadline) {
            Thread.sleep(15)
        }
        assertEquals(HostServerState.STOPPED, coord.state)
        assertFalse(coord.hasActiveWorker)
    }

    @Test
    fun `stop ante excepcion en hook de apagado igualmente espera y finaliza el worker`() {
        val stopSignal = CountDownLatch(1)
        val startedLatch = CountDownLatch(1)
        val coord = HostLifecycleCoordinator()

        assertTrue(
            coord.start(
                port = 1729,
                musicDir = null,
                onRequestStop = {
                    stopSignal.countDown()
                    throw RuntimeException("Error simulado en Python")
                },
            ) { onReady ->
                onReady()
                startedLatch.countDown()
                stopSignal.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(startedLatch.await(2, TimeUnit.SECONDS))
        assertTrue(coord.stop(timeoutMs = 1000L))
        assertEquals(HostServerState.STOPPED, coord.state)
        assertFalse(coord.hasActiveWorker)
    }

    @Test
    fun `notificaciones de estado nunca entregan STOPPED despues de STARTING mas reciente`() {
        val observed = java.util.concurrent.CopyOnWriteArrayList<HostServerState>()
        val coord = HostLifecycleCoordinator(
            onStateChanged = { st, _ -> observed.add(st) },
        )
        val ready1 = CountDownLatch(1)
        assertTrue(
            coord.start(1729, null, {}) { onReady ->
                onReady()
                ready1.countDown()
            },
        )
        assertTrue(ready1.await(2, TimeUnit.SECONDS))
        val deadline = System.currentTimeMillis() + 2000L
        while (coord.state != HostServerState.STOPPED && System.currentTimeMillis() < deadline) {
            Thread.sleep(10)
        }
        assertTrue(coord.stop(500L))
        val ready2 = CountDownLatch(1)
        val stop2 = CountDownLatch(1)
        assertTrue(
            coord.start(1729, null, { stop2.countDown() }) { onReady ->
                onReady()
                ready2.countDown()
                stop2.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(ready2.await(2, TimeUnit.SECONDS))
        val lastStoppedIdx = observed.lastIndexOf(HostServerState.STOPPED)
        val lastStartingIdx = observed.lastIndexOf(HostServerState.STARTING)
        assertTrue(lastStartingIdx > lastStoppedIdx)
        coord.stop(500L)
    }

    @Test
    fun `politica de tipo foreground y cierre tras gracia de clientes remotos`() {
        assertEquals(
            android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
            ServicePowerPolicy.foregroundServiceType(isMediaPlaying = true, hasRemoteClients = true),
        )
        assertEquals(
            android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            ServicePowerPolicy.foregroundServiceType(isMediaPlaying = false, hasRemoteClients = true),
        )
        assertTrue(
            ServicePowerPolicy.shouldStopAfterRemoteGrace(
                taskRemoved = true,
                isMediaPlaying = false,
                hasRemoteClients = false,
            ),
        )
        assertFalse(
            ServicePowerPolicy.shouldStopAfterRemoteGrace(
                taskRemoved = true,
                isMediaPlaying = false,
                hasRemoteClients = true,
            ),
        )
    }

    @Test
    fun `resolveTimeout degrada a mediaPlayback si hay reproduccion activa y detiene si es dataSync sin musica`() {
        assertEquals(
            TimeoutResolution.DEGRADE_TO_MEDIA_PLAYBACK,
            ServicePowerPolicy.resolveTimeout(
                fgsType = android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
                isMediaPlaying = true,
            ),
        )
        assertEquals(
            TimeoutResolution.STOP_SERVICE,
            ServicePowerPolicy.resolveTimeout(
                fgsType = android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
                isMediaPlaying = false,
            ),
        )
        assertEquals(
            TimeoutResolution.STOP_SERVICE,
            ServicePowerPolicy.resolveTimeout(
                fgsType = android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
                isMediaPlaying = true,
            ),
        )
    }

    @Test
    fun `registra StopHookOutcome FAILED cuando el hook lanza excepcion y TIMED_OUT sin duplicar hooks bloqueados`() {
        val stopSignal = CountDownLatch(1)
        val started = CountDownLatch(1)
        val coordFail = HostLifecycleCoordinator()

        assertTrue(
            coordFail.start(
                port = 1740,
                musicDir = null,
                onRequestStop = {
                    stopSignal.countDown()
                    throw IllegalStateException("fallo critico de hook")
                },
            ) { onReady ->
                onReady()
                started.countDown()
                stopSignal.await(2, TimeUnit.SECONDS)
            },
        )
        assertTrue(started.await(2, TimeUnit.SECONDS))
        assertTrue(coordFail.stop(timeoutMs = 1500L))
        assertEquals(StopHookOutcome.FAILED, coordFail.lastStopHookOutcome)
        assertTrue(coordFail.lastStopHookError?.contains("fallo critico de hook") == true)
        assertEquals(HostServerState.STOPPED, coordFail.state)

        // Hook bloqueado: dos llamadas a stop() coalescen sobre la misma invocación pendiente
        val hookCalls = AtomicInteger(0)
        val hookRelease = CountDownLatch(1)
        val workerRelease = CountDownLatch(1)
        val started2 = CountDownLatch(1)
        val coordTimeout = HostLifecycleCoordinator()

        assertTrue(
            coordTimeout.start(
                port = 1741,
                musicDir = null,
                onRequestStop = {
                    hookCalls.incrementAndGet()
                    hookRelease.await(5, TimeUnit.SECONDS)
                },
            ) { onReady ->
                onReady()
                started2.countDown()
                workerRelease.await(5, TimeUnit.SECONDS)
            },
        )
        assertTrue(started2.await(2, TimeUnit.SECONDS))
        assertFalse(coordTimeout.stop(timeoutMs = 80L))
        assertEquals(StopHookOutcome.TIMED_OUT, coordTimeout.lastStopHookOutcome)
        assertEquals(HostServerState.STOP_TIMED_OUT, coordTimeout.state)

        // Segundo stop mientras el primer hook sigue colgado: no debe encolar otro hook duplicado
        assertFalse(coordTimeout.stop(timeoutMs = 80L))
        assertEquals(1, hookCalls.get())

        hookRelease.countDown()
        workerRelease.countDown()
        val deadline = System.currentTimeMillis() + 2000L
        while (coordTimeout.hasActiveWorker && System.currentTimeMillis() < deadline) {
            Thread.sleep(10L)
        }
        assertEquals(HostServerState.STOPPED, coordTimeout.state)
        assertFalse(coordTimeout.hasActiveWorker)
    }

    @Test
    fun `es imposible iniciar un segundo worker antes de que el primero termine fisicamente su thread`() {
        val coord = HostLifecycleCoordinator()
        val activeRunners = AtomicInteger(0)
        val maxConcurrentRunners = AtomicInteger(0)

        repeat(25) { idx ->
            val entered = CountDownLatch(1)
            val allowExit = CountDownLatch(1)
            val started = coord.start(
                port = 1750 + idx,
                musicDir = null,
                onRequestStop = { allowExit.countDown() },
            ) { onReady ->
                val cur = activeRunners.incrementAndGet()
                maxConcurrentRunners.updateAndGet { prev -> maxOf(prev, cur) }
                onReady()
                entered.countDown()
                allowExit.await(2, TimeUnit.SECONDS)
                Thread.sleep(8L)
                activeRunners.decrementAndGet()
            }
            assertTrue("Iteración $idx falló al iniciar", started)
            assertTrue(entered.await(2, TimeUnit.SECONDS))

            // Intentos paralelos de start() mientras termina tardíamente no pueden crear un segundo worker
            val stopThread = Thread {
                allowExit.countDown()
                coord.stop(timeoutMs = 2000L)
            }.apply { start() }

            var restartedImmediately = false
            val deadline = System.currentTimeMillis() + 2000L
            while (System.currentTimeMillis() < deadline) {
                if (coord.start(1750 + idx, null, {}) {
                        val cur = activeRunners.incrementAndGet()
                        maxConcurrentRunners.updateAndGet { prev -> maxOf(prev, cur) }
                        activeRunners.decrementAndGet()
                    }
                ) {
                    restartedImmediately = true
                    break
                }
                Thread.yield()
            }
            stopThread.join(2000L)
            assertTrue("Iteración $idx no pudo reiniciar tras confirmar terminación", restartedImmediately)
            assertTrue(coord.stop(timeoutMs = 2000L))
        }
        assertEquals(1, maxConcurrentRunners.get())
    }

    @Test
    fun `shutdown con servidor detenido cierra limpio y con worker bloqueado difiere cierre sin matar el reaper`() {
        val idleCoord = HostLifecycleCoordinator()
        assertFalse(idleCoord.hasPendingCleanup)
        idleCoord.shutdown()
        assertTrue(idleCoord.isShutdownRequested)

        // Worker bloqueado: shutdown() NO debe destruir el reaper antes de que el worker termine físicamente
        val coord = HostLifecycleCoordinator()
        val started = CountDownLatch(1)
        val allowExit = CountDownLatch(1)
        val workerFinished = AtomicBoolean(false)

        assertTrue(
            coord.start(
                port = 1760,
                musicDir = null,
                onRequestStop = {},
            ) { onReady ->
                onReady()
                started.countDown()
                allowExit.await(5, TimeUnit.SECONDS)
                workerFinished.set(true)
            },
        )
        assertTrue(started.await(2, TimeUnit.SECONDS))
        assertFalse(coord.stop(timeoutMs = 80L))
        assertEquals(HostServerState.STOP_TIMED_OUT, coord.state)
        assertTrue(coord.isWorkerAlive)
        assertTrue(coord.hasPendingCleanup)

        // Solicitamos shutdown con el worker aún bloqueado: el reaper debe seguir vivo para recolectarlo
        coord.shutdown()
        assertTrue(coord.isShutdownRequested)
        assertTrue(coord.hasActiveWorker)
        assertFalse(workerFinished.get())

        // Destrabamos el worker: el reaper debe recolectar el thread y completar el cierre diferido
        allowExit.countDown()
        val deadline = System.currentTimeMillis() + 3000L
        while (coord.hasPendingCleanup && System.currentTimeMillis() < deadline) {
            Thread.sleep(10L)
        }
        assertTrue(workerFinished.get())
        assertFalse(coord.isWorkerAlive)
        assertFalse(coord.hasActiveWorker)
        assertFalse(coord.hasPendingCleanup)
        assertEquals(HostServerState.STOPPED, coord.state)
    }

    @Test
    fun `recrear servicio con worker anterior vivo bloquea segundo arranque y desacopla callbacks viejos`() {
        val sharedCoordinator = HostLifecycleCoordinator()
        val oldServiceEvents = CopyOnWriteArrayList<HostServerState>()
        val newServiceEvents = CopyOnWriteArrayList<HostServerState>()
        val started = CountDownLatch(1)
        val allowExit = CountDownLatch(1)

        sharedCoordinator.setStateListener { st, _ -> oldServiceEvents.add(st) }
        assertTrue(
            sharedCoordinator.start(
                port = 1761,
                musicDir = null,
                onRequestStop = { allowExit.countDown() },
            ) { onReady ->
                onReady()
                started.countDown()
                allowExit.await(5, TimeUnit.SECONDS)
            },
        )
        assertTrue(started.await(2, TimeUnit.SECONDS))

        // Simulamos onDestroy del primer Service sin esperar que el worker cuelgue el main thread
        sharedCoordinator.setStateListener(null)
        val oldEventsAtDestroy = oldServiceEvents.size

        // Nuevo Service se crea y se adjunta al coordinador único del proceso mientras el worker viejo sigue vivo
        sharedCoordinator.setStateListener { st, _ -> newServiceEvents.add(st) }
        assertTrue(sharedCoordinator.hasActiveWorker)
        assertFalse(
            sharedCoordinator.start(
                port = 1761,
                musicDir = null,
                onRequestStop = {},
            ) {},
        )

        // Detenemos el worker viejo y verificamos que el viejo listener no recibe nada y luego permite nuevo arranque
        assertTrue(sharedCoordinator.stop(timeoutMs = 2000L))
        assertEquals(oldEventsAtDestroy, oldServiceEvents.size)
        assertTrue(newServiceEvents.contains(HostServerState.STOPPED))
        assertFalse(sharedCoordinator.hasActiveWorker)

        assertTrue(
            sharedCoordinator.start(
                port = 1761,
                musicDir = null,
                onRequestStop = {},
            ) { onReady -> onReady() },
        )
        assertTrue(sharedCoordinator.stop(timeoutMs = 2000L))
    }

    @Test
    fun `si el reaper se interrumpe mientras el worker sigue vivo no declara STOPPED y conserva hasActiveWorker`() {
        val started = CountDownLatch(1)
        val allowExit = CountDownLatch(1)
        val persistedDuringShutdown = AtomicBoolean(false)
        val reaperThreadRef = java.util.concurrent.atomic.AtomicReference<Thread?>(null)

        val coord = HostLifecycleCoordinator(
            threadFactory = { name, runnable ->
                Thread(runnable, name).apply {
                    isDaemon = true
                    if (name == "RockolaWorkerReaper") {
                        reaperThreadRef.set(this)
                    }
                }
            },
        )

        assertTrue(
            coord.start(
                port = 1762,
                musicDir = null,
                onRequestStop = {
                    persistedDuringShutdown.set(true)
                    allowExit.countDown()
                },
            ) { onReady ->
                onReady()
                started.countDown()
                allowExit.await(5, TimeUnit.SECONDS)
                Thread.sleep(60L)
            },
        )
        assertTrue(started.await(2, TimeUnit.SECONDS))

        // Esperamos a que se haya instanciado el reaper o forzamos un ciclo stop breve para iniciarlo
        assertFalse(coord.stop(timeoutMs = 10L))
        assertTrue(coord.hasActiveWorker)
        reaperThreadRef.get()?.interrupt()

        // Mientras el worker siga vivo tras la interrupción, NO puede haber declarado STOPPED
        assertTrue(coord.isWorkerAlive)
        assertTrue(coord.hasActiveWorker)
        assertFalse(coord.state == HostServerState.STOPPED)

        assertTrue(coord.stop(timeoutMs = 2500L))
        assertTrue(persistedDuringShutdown.get())
        assertEquals(HostServerState.STOPPED, coord.state)
        assertFalse(coord.hasActiveWorker)
    }
}
