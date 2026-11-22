package ar.carpincho.rockola

/**
 * Estados explícitos del ciclo de vida del servidor embebido Android.
 */
enum class HostServerState {
    STOPPED,
    STARTING,
    READY,
    STOPPING,
    FAILED;

    fun wireName(): String = name.lowercase()
}

/**
 * Coordina el hilo del servidor FastAPI/Uvicorn embebido con transiciones sincronizadas,
 * inicio idempotente y apagado acotado libre de deadlocks.
 */
class HostLifecycleCoordinator(
    private val onStateChanged: (HostServerState, String?) -> Unit = { _, _ -> },
    private val threadFactory: (String, Runnable) -> Thread = { name, runnable ->
        Thread(runnable, name).apply { isDaemon = true }
    },
) {
    private val lock = Any()
    private var runIdCounter: Long = 0L
    private var activeRunId: Long = 0L
    private var activeThread: Thread? = null
    private var activeStopHook: (() -> Unit)? = null
    private var stopRequestedForRun: Boolean = false

    @Volatile
    var state: HostServerState = HostServerState.STOPPED
        private set

    @Volatile
    var lastError: String? = null
        private set

    val isRunning: Boolean
        get() = state == HostServerState.STARTING || state == HostServerState.READY

    fun start(
        port: Int,
        @Suppress("UNUSED_PARAMETER") musicDir: String?,
        onRequestStop: () -> Unit,
        runner: (onReady: () -> Unit) -> Unit,
    ): Boolean {
        val runId: Long
        val thread: Thread
        synchronized(lock) {
            if (state == HostServerState.STARTING ||
                state == HostServerState.READY ||
                state == HostServerState.STOPPING
            ) {
                return false
            }
            runIdCounter += 1L
            runId = runIdCounter
            activeRunId = runId
            stopRequestedForRun = false
            activeStopHook = onRequestStop
            setStateLocked(HostServerState.STARTING, null)

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
        notifyState()
        return true
    }

    private fun markReady(runId: Long) {
        var shouldNotify = false
        synchronized(lock) {
            if (activeRunId == runId && state == HostServerState.STARTING && !stopRequestedForRun) {
                setStateLocked(HostServerState.READY, null)
                shouldNotify = true
            }
        }
        if (shouldNotify) {
            notifyState()
        }
    }

    private fun finishRun(runId: Long, error: String?) {
        var shouldNotify = false
        synchronized(lock) {
            if (activeRunId != runId) return
            val wasStopping = stopRequestedForRun || state == HostServerState.STOPPING
            activeThread = null
            activeStopHook = null
            if (error != null && !wasStopping) {
                setStateLocked(HostServerState.FAILED, error)
            } else {
                setStateLocked(HostServerState.STOPPED, null)
            }
            shouldNotify = true
        }
        if (shouldNotify) {
            notifyState()
        }
    }

    fun stop(timeoutMs: Long = 4000L): Boolean {
        val threadToJoin: Thread?
        val stopHook: (() -> Unit)?
        val runId: Long
        var notifyStopping = false
        synchronized(lock) {
            when (state) {
                HostServerState.STOPPED, HostServerState.FAILED -> return true
                HostServerState.STARTING, HostServerState.READY -> {
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = activeThread
                    stopHook = activeStopHook
                    setStateLocked(HostServerState.STOPPING, null)
                    notifyStopping = true
                }
                HostServerState.STOPPING -> {
                    stopRequestedForRun = true
                    runId = activeRunId
                    threadToJoin = activeThread
                    stopHook = activeStopHook
                }
            }
        }
        if (notifyStopping) {
            notifyState()
        }

        try {
            stopHook?.invoke()
        } catch (_: Throwable) {
        }

        // Esperamos fuera del lock para que el hilo worker pueda finalizar sin deadlock
        if (threadToJoin != null && Thread.currentThread() !== threadToJoin && timeoutMs > 0L) {
            try {
                threadToJoin.join(timeoutMs)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            }
        }

        var timedOut = false
        var finalizedCleanly = false
        synchronized(lock) {
            if (activeRunId == runId) {
                if (threadToJoin != null && threadToJoin.isAlive) {
                    timedOut = true
                    // Avanzamos el runId para que el hilo zombi no contamine futuros reinicios
                    runIdCounter += 1L
                    activeRunId = runIdCounter
                    activeThread = null
                    activeStopHook = null
                    setStateLocked(
                        HostServerState.FAILED,
                        "El servidor embebido no respondió al apagado en ${timeoutMs}ms",
                    )
                } else if (state == HostServerState.STOPPING) {
                    activeThread = null
                    activeStopHook = null
                    setStateLocked(HostServerState.STOPPED, null)
                    finalizedCleanly = true
                }
            }
        }
        if (timedOut || finalizedCleanly) {
            notifyState()
        }
        return !timedOut
    }

    private fun setStateLocked(next: HostServerState, err: String?) {
        state = next
        lastError = err
    }

    private fun notifyState() {
        val snapState: HostServerState
        val snapError: String?
        synchronized(lock) {
            snapState = state
            snapError = lastError
        }
        onStateChanged(snapState, snapError)
    }
}
