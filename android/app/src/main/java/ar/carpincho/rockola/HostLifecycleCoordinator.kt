package ar.carpincho.rockola

import java.util.concurrent.Executors
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
 * Coordina el hilo del servidor FastAPI/Uvicorn embebido con transiciones sincronizadas,
 * inicio idempotente, snapshots ordenados y apagado acotado libre de deadlocks.
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

    private val lock = Any()
    private val notificationLock = Any()
    private var stateVersion: Long = 0L
    private var lastNotifiedVersion: Long = 0L
    private var runIdCounter: Long = 0L
    private var activeRunId: Long = 0L
    private var finishingRunId: Long = 0L
    private var activeThread: Thread? = null
    private var activeStopHook: (() -> Unit)? = null
    private var stopRequestedForRun: Boolean = false
    private val stopHookExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaStopHook").apply { isDaemon = true }
    }

    @Volatile
    var state: HostServerState = HostServerState.STOPPED
        private set

    @Volatile
    var lastError: String? = null
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
        val thread: Thread
        synchronized(lock) {
            if (state == HostServerState.STARTING ||
                state == HostServerState.READY ||
                state == HostServerState.STOPPING ||
                state == HostServerState.STOP_TIMED_OUT ||
                finishingRunId != 0L ||
                activeThread?.isAlive == true
            ) {
                return false
            }
            runIdCounter += 1L
            val runId = runIdCounter
            activeRunId = runId
            stopRequestedForRun = false
            activeStopHook = onRequestStop
            snapshot = setStateLocked(HostServerState.STARTING, null)

            thread = threadFactory("RockolaUvicornThread-$port") {
                val cancelledBeforeStart = synchronized(lock) {
                    activeRunId != runId || stopRequestedForRun
                }
                if (cancelledBeforeStart) {
                    finishRun(runId, error = null)
                    return@threadFactory
                }
                try {
                    runner {
                        markReady(runId)
                    }
                    finishRun(runId, error = null)
                } catch (t: Throwable) {
                    val message = t.message?.takeIf { it.isNotBlank() } ?: t.javaClass.simpleName
                    finishRun(runId, error = message)
                }
            }
            activeThread = thread
            thread.start()
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

    private fun finishRun(runId: Long, error: String?) {
        val snapshot = synchronized(lock) {
            if (activeRunId != runId) return
            finishingRunId = runId
            val wasStopping = stopRequestedForRun ||
                state == HostServerState.STOPPING ||
                state == HostServerState.STOP_TIMED_OUT
            if (error != null && !wasStopping) {
                setStateLocked(HostServerState.FAILED, error)
            } else {
                setStateLocked(HostServerState.STOPPED, null)
            }
        }
        try {
            notifySnapshot(snapshot)
        } finally {
            synchronized(lock) {
                if (activeRunId == runId) {
                    activeThread = null
                    activeStopHook = null
                    finishingRunId = 0L
                }
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
                HostServerState.STOPPED -> {
                    if (finishingRunId == 0L && activeThread?.isAlive != true) {
                        return true
                    }
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = activeThread
                    stopHook = activeStopHook
                    stoppingSnapshot = null
                }
                HostServerState.FAILED -> {
                    if (finishingRunId == 0L && activeThread?.isAlive != true) {
                        activeThread = null
                        activeStopHook = null
                        return true
                    }
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = activeThread
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
        var hookCompleted = true
        if (stopHook != null) {
            hookCompleted = runStopHookWithBudget(stopHook, deadlineNs)
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
            val workerStillAlive = (threadToJoin != null && threadToJoin.isAlive) || !hookCompleted
            if (activeRunId == runId && workerStillAlive) {
                timedOut = true
                resultSnapshot = setStateLocked(
                    HostServerState.STOP_TIMED_OUT,
                    "El servidor embebido no respondió al apagado en ${timeoutMs}ms",
                )
            } else if (activeRunId == runId && (state == HostServerState.STOPPING || state == HostServerState.STOP_TIMED_OUT)) {
                timedOut = false
                if (finishingRunId == 0L) {
                    activeThread = null
                    activeStopHook = null
                }
                resultSnapshot = setStateLocked(HostServerState.STOPPED, null)
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

    private fun runStopHookWithBudget(stopHook: () -> Unit, deadlineNs: Long): Boolean {
        val remainingMs = TimeUnit.NANOSECONDS.toMillis(deadlineNs - System.nanoTime()).coerceAtLeast(1L)
        return try {
            val future = stopHookExecutor.submit {
                try {
                    stopHook()
                } catch (_: Throwable) {
                }
            }
            future.get(remainingMs, TimeUnit.MILLISECONDS)
            true
        } catch (_: TimeoutException) {
            false
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            false
        } catch (_: Throwable) {
            true
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
