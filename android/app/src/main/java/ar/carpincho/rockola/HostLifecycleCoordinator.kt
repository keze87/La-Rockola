package ar.carpincho.rockola

import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/**
 * Estados explícitos del ciclo de vida del servidor embebido Android.
 */
enum class HostServerState {
    STOPPED,
    STARTING,
    READY,
    STOPPING,
    STOP_TIMED_OUT,
    FAILED;

    fun wireName(): String = name.lowercase()
}

/**
 * Resultado explícito de la ejecución del stop hook.
 */
enum class StopHookOutcome {
    NONE,
    COMPLETED,
    FAILED,
    TIMED_OUT,
    REJECTED,
}

/**
 * Coordina el hilo del servidor FastAPI/Uvicorn embebido con transiciones sincronizadas,
 * inicio idempotente, snapshots ordenados, recolección real del thread (Thread.join)
 * y apagado acotado libre de deadlocks o ventanas de carrera.
 */
class HostLifecycleCoordinator(
    private val onStateChanged: (HostServerState, String?) -> Unit = { _, _ -> },
    private val threadFactory: (String, Runnable) -> Thread = { name, runnable ->
        Thread(runnable, name).apply { isDaemon = true }
    },
) {
    private data class StateSnapshot(
        val version: Long,
        val state: HostServerState,
        val error: String?,
    )

    private data class StopHookExecutionResult(
        val outcome: StopHookOutcome,
        val error: String? = null,
    )

    private val lock = Any()
    private val notificationLock = Any()
    private var stateVersion: Long = 0L
    private var lastNotifiedVersion: Long = 0L
    private var runIdCounter: Long = 0L
    private var activeRunId: Long = 0L
    private var finishingRunId: Long = 0L
    private var activeThread: Thread? = null
    private var activeStopHook: (() -> Unit)? = null
    private var activeStopFuture: Future<StopHookExecutionResult>? = null
    private var stopRequestedForRun: Boolean = false
    private var pendingTerminalState: HostServerState? = null
    private var pendingTerminalError: String? = null

    private val stopHookExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaStopHook").apply { isDaemon = true }
    }
    private val reaperExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaWorkerReaper").apply { isDaemon = true }
    }

    @Volatile
    var state: HostServerState = HostServerState.STOPPED
        private set

    @Volatile
    var lastError: String? = null
        private set

    @Volatile
    var lastStopHookOutcome: StopHookOutcome = StopHookOutcome.NONE
        private set

    @Volatile
    var lastStopHookError: String? = null
        private set

    val isRunning: Boolean
        get() = state == HostServerState.STARTING || state == HostServerState.READY

    val hasActiveWorker: Boolean
        get() = synchronized(lock) {
            activeThread != null ||
                finishingRunId != 0L ||
                state == HostServerState.STARTING ||
                state == HostServerState.READY ||
                state == HostServerState.STOPPING ||
                state == HostServerState.STOP_TIMED_OUT
        }

    fun start(
        port: Int,
        @Suppress("UNUSED_PARAMETER") musicDir: String?,
        onRequestStop: () -> Unit,
        runner: (onReady: () -> Unit) -> Unit,
    ): Boolean {
        val snapshot: StateSnapshot
        synchronized(lock) {
            if (state == HostServerState.STARTING ||
                state == HostServerState.READY ||
                state == HostServerState.STOPPING ||
                state == HostServerState.STOP_TIMED_OUT ||
                finishingRunId != 0L ||
                activeThread != null
            ) {
                return false
            }
            runIdCounter += 1L
            val runId = runIdCounter
            activeRunId = runId
            finishingRunId = 0L
            activeStopFuture = null
            stopRequestedForRun = false
            pendingTerminalState = null
            pendingTerminalError = null
            lastStopHookOutcome = StopHookOutcome.NONE
            lastStopHookError = null
            activeStopHook = onRequestStop
            snapshot = setStateLocked(HostServerState.STARTING, null)

            lateinit var workerThread: Thread
            workerThread = threadFactory("RockolaUvicornThread-$port") {
                val cancelledBeforeStart = synchronized(lock) {
                    activeRunId != runId || stopRequestedForRun
                }
                if (cancelledBeforeStart) {
                    beginFinishRun(runId, workerThread, error = null)
                    return@threadFactory
                }
                try {
                    runner {
                        markReady(runId)
                    }
                    beginFinishRun(runId, workerThread, error = null)
                } catch (t: Throwable) {
                    val message = t.message?.takeIf { it.isNotBlank() } ?: t.javaClass.simpleName
                    beginFinishRun(runId, workerThread, error = message)
                }
            }
            activeThread = workerThread
            workerThread.start()
        }
        notifySnapshot(snapshot)
        return true
    }

    private fun markReady(runId: Long) {
        val snapshot = synchronized(lock) {
            if (activeRunId == runId && state == HostServerState.STARTING && !stopRequestedForRun) {
                setStateLocked(HostServerState.READY, null)
            } else {
                null
            }
        }
        if (snapshot != null) {
            notifySnapshot(snapshot)
        }
    }

    /**
     * Marca el inicio de finalización desde el propio hilo worker SIN liberar `activeThread`
     * ni transicionar aún a STOPPED/FAILED: delega al reaper externo la confirmación física
     * mediante `Thread.join()`, evitando self-join y ventanas de carrera con `start()`.
     */
    private fun beginFinishRun(runId: Long, workerThread: Thread, error: String?) {
        synchronized(lock) {
            if (activeRunId != runId) return
            finishingRunId = runId
            val wasStopping = stopRequestedForRun ||
                state == HostServerState.STOPPING ||
                state == HostServerState.STOP_TIMED_OUT
            if (error != null && !wasStopping) {
                pendingTerminalState = HostServerState.FAILED
                pendingTerminalError = error
            } else {
                pendingTerminalState = HostServerState.STOPPED
                pendingTerminalError = null
            }
        }
        try {
            reaperExecutor.execute {
                reapWorkerThread(runId, workerThread)
            }
        } catch (_: RejectedExecutionException) {
            // Fallback sin bloquear el worker si el reaper fue cerrado
        }
    }

    private fun reapWorkerThread(runId: Long, workerThread: Thread) {
        if (Thread.currentThread() !== workerThread) {
            try {
                workerThread.join()
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                return
            }
        }
        if (workerThread.isAlive) return
        val snapshot = finalizeIfWorkerTerminatedLocked(runId, workerThread)
        if (snapshot != null) {
            notifySnapshot(snapshot)
        }
    }

    private fun finalizeIfWorkerTerminatedLocked(runId: Long, workerThread: Thread): StateSnapshot? {
        return synchronized(lock) {
            if (activeRunId != runId) return@synchronized null
            if (workerThread.isAlive) return@synchronized null
            val wasStopping = stopRequestedForRun ||
                state == HostServerState.STOPPING ||
                state == HostServerState.STOP_TIMED_OUT
            val targetState = when {
                state == HostServerState.STOPPED || state == HostServerState.FAILED -> null
                pendingTerminalState == HostServerState.FAILED && !wasStopping -> HostServerState.FAILED
                else -> HostServerState.STOPPED
            }
            val targetError = if (targetState == HostServerState.FAILED) pendingTerminalError else null
            activeThread = null
            activeStopHook = null
            activeStopFuture = null
            finishingRunId = 0L
            pendingTerminalState = null
            pendingTerminalError = null
            if (targetState != null) {
                setStateLocked(targetState, targetError)
            } else {
                null
            }
        }
    }

    fun stop(timeoutMs: Long = 4000L): Boolean {
        val threadToJoin: Thread?
        val stopHook: (() -> Unit)?
        val runId: Long
        val stoppingSnapshot: StateSnapshot?
        synchronized(lock) {
            when (state) {
                HostServerState.STOPPED, HostServerState.FAILED -> {
                    val alive = activeThread
                    if (finishingRunId == 0L && (alive == null || !alive.isAlive)) {
                        activeThread = null
                        activeStopHook = null
                        activeStopFuture = null
                        return true
                    }
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = alive
                    stopHook = activeStopHook
                    stoppingSnapshot = null
                }
                HostServerState.STARTING, HostServerState.READY -> {
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = activeThread
                    stopHook = activeStopHook
                    stoppingSnapshot = setStateLocked(HostServerState.STOPPING, null)
                }
                HostServerState.STOPPING, HostServerState.STOP_TIMED_OUT -> {
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = activeThread
                    stopHook = activeStopHook
                    stoppingSnapshot = null
                }
            }
        }
        if (stoppingSnapshot != null) {
            notifySnapshot(stoppingSnapshot)
        }

        val deadlineNs = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMs.coerceAtLeast(0L))
        var hookTimedOut = false
        if (stopHook != null) {
            val hookResult = runStopHookWithBudget(runId, stopHook, deadlineNs)
            lastStopHookOutcome = hookResult.outcome
            lastStopHookError = hookResult.error
            hookTimedOut = hookResult.outcome == StopHookOutcome.TIMED_OUT
        } else {
            lastStopHookOutcome = StopHookOutcome.NONE
            lastStopHookError = null
        }

        // Esperamos fuera del lock usando únicamente el presupuesto restante de tiempo
        val remainingAfterHookMs = TimeUnit.NANOSECONDS.toMillis(deadlineNs - System.nanoTime()).coerceAtLeast(0L)
        if (threadToJoin != null && Thread.currentThread() !== threadToJoin && remainingAfterHookMs > 0L) {
            try {
                threadToJoin.join(remainingAfterHookMs)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            }
        }

        val resultSnapshot: StateSnapshot?
        val timedOut: Boolean
        synchronized(lock) {
            val threadDead = threadToJoin == null || !threadToJoin.isAlive
            val workerStillAlive = !threadDead || hookTimedOut
            if (activeRunId == runId && workerStillAlive) {
                timedOut = true
                resultSnapshot = setStateLocked(
                    HostServerState.STOP_TIMED_OUT,
                    "El servidor embebido no respondió al apagado en ${timeoutMs}ms",
                )
            } else if (activeRunId == runId && threadDead) {
                timedOut = false
                if (state == HostServerState.STOPPED || state == HostServerState.FAILED) {
                    activeThread = null
                    activeStopHook = null
                    activeStopFuture = null
                    finishingRunId = 0L
                    pendingTerminalState = null
                    pendingTerminalError = null
                    resultSnapshot = null
                } else {
                    val targetState = if (pendingTerminalState == HostServerState.FAILED && !stopRequestedForRun) {
                        HostServerState.FAILED
                    } else {
                        HostServerState.STOPPED
                    }
                    val targetError = if (targetState == HostServerState.FAILED) pendingTerminalError else null
                    activeThread = null
                    activeStopHook = null
                    activeStopFuture = null
                    finishingRunId = 0L
                    pendingTerminalState = null
                    pendingTerminalError = null
                    resultSnapshot = setStateLocked(targetState, targetError)
                }
            } else {
                timedOut = state == HostServerState.STOP_TIMED_OUT || (threadToJoin != null && threadToJoin.isAlive)
                resultSnapshot = null
            }
        }
        if (resultSnapshot != null) {
            notifySnapshot(resultSnapshot)
        }
        return !timedOut
    }

    private fun runStopHookWithBudget(
        runId: Long,
        stopHook: () -> Unit,
        deadlineNs: Long,
    ): StopHookExecutionResult {
        val futureToAwait: Future<StopHookExecutionResult> = synchronized(lock) {
            val existing = if (activeRunId == runId) activeStopFuture else null
            if (existing != null && !existing.isDone) {
                existing
            } else {
                try {
                    stopHookExecutor.submit(
                        Callable {
                            try {
                                stopHook()
                                StopHookExecutionResult(StopHookOutcome.COMPLETED, null)
                            } catch (t: Throwable) {
                                val msg = t.message?.takeIf { it.isNotBlank() } ?: t.javaClass.simpleName
                                StopHookExecutionResult(StopHookOutcome.FAILED, msg)
                            }
                        },
                    ).also { submitted ->
                        if (activeRunId == runId) {
                            activeStopFuture = submitted
                        }
                    }
                } catch (rej: RejectedExecutionException) {
                    return StopHookExecutionResult(
                        StopHookOutcome.REJECTED,
                        rej.message ?: "Executor de apagado detenido",
                    )
                }
            }
        }

        val remainingMs = TimeUnit.NANOSECONDS.toMillis(deadlineNs - System.nanoTime()).coerceAtLeast(1L)
        return try {
            val res = futureToAwait.get(remainingMs, TimeUnit.MILLISECONDS)
            synchronized(lock) {
                if (activeRunId == runId && activeStopFuture === futureToAwait && futureToAwait.isDone) {
                    activeStopFuture = null
                }
            }
            res
        } catch (_: TimeoutException) {
            StopHookExecutionResult(StopHookOutcome.TIMED_OUT, "El stop hook excedió el tiempo límite")
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            StopHookExecutionResult(StopHookOutcome.TIMED_OUT, "Espera del stop hook interrumpida")
        } catch (t: Throwable) {
            val msg = t.cause?.message ?: t.message ?: t.javaClass.simpleName
            StopHookExecutionResult(StopHookOutcome.FAILED, msg)
        }
    }

    private fun setStateLocked(next: HostServerState, err: String?): StateSnapshot {
        stateVersion += 1L
        state = next
        lastError = err
        return StateSnapshot(stateVersion, next, err)
    }

    private fun notifySnapshot(snapshot: StateSnapshot) {
        synchronized(notificationLock) {
            if (snapshot.version <= lastNotifiedVersion) return
            lastNotifiedVersion = snapshot.version
            onStateChanged(snapshot.state, snapshot.error)
        }
    }
}
