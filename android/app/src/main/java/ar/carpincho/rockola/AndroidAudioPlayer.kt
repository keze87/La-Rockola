package ar.carpincho.rockola

import android.content.Context
import android.media.AudioManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.chaquo.python.PyObject
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import kotlin.math.roundToInt

/**
 * Motor de reproducción nativo basado en AndroidX Media3 ExoPlayer.
 * Vive dentro de RockolaForegroundService para sobrevivir pantalla apagada,
 * cambio de app y cierre de la Activity, con manejo nativo de AudioFocus y becoming-noisy.
 */
class AndroidAudioPlayer(
    private val context: Context,
    private val onPlaybackActiveChanged: (active: Boolean) -> Unit,
    private val onMediaNotification: ((
        title: String,
        artist: String,
        paused: Boolean,
        coverUrl: String?,
        trackPath: String?,
        durationMs: Long,
        positionMs: Long,
        isFavorite: Boolean,
        isPauseAfter: Boolean,
    ) -> Unit)? = null,
    private val onPositionNotification: ((
        durationMs: Long,
        positionMs: Long,
        paused: Boolean,
    ) -> Unit)? = null,
) {
    companion object {
        private const val TAG = "RockolaExoPlayer"
        private const val POSITION_TICK_MS = 500L
        private const val MAX_CONSECUTIVE_ERRORS = 3

        @Volatile
        private var activeInstance: AndroidAudioPlayer? = null

        @JvmStatic
        fun getActiveInstance(): AndroidAudioPlayer? = activeInstance
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private val pythonCallbackExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaPyCallback").apply { isDaemon = true }
    }
    private var player: ExoPlayer? = null
    private var lastVolume: Float = 1.0f
    private var isMuted: Boolean = false
    private var consecutiveErrors: Int = 0
    private var lastReportedPaused: Boolean? = null

    @Volatile
    private var pyCallbackHandler: PyObject? = null

    private val positionTicker = object : Runnable {
        override fun run() {
            val p = player ?: return
            if (p.isPlaying) {
                val posSec = (p.currentPosition.coerceAtLeast(0L)) / 1000.0
                val durMs = p.duration
                val durSec = if (durMs > 0L && durMs != C.TIME_UNSET) durMs / 1000.0 else 0.0
                dispatchToPython("on_position", posSec, durSec)
                mainHandler.postDelayed(this, POSITION_TICK_MS)
            }
        }
    }

    private fun emitPauseIfChanged(paused: Boolean) {
        if (lastReportedPaused == paused) return
        lastReportedPaused = paused
        dispatchToPython("on_pause_changed", paused)
    }

    fun initialize() {
        activeInstance = this
        mainHandler.post {
            if (player != null) return@post
            val audioAttrs = AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                .build()

            player = ExoPlayer.Builder(context.applicationContext)
                .setAudioAttributes(audioAttrs, true)
                .setHandleAudioBecomingNoisy(true)
                .build()
                .apply {
                    addListener(object : Player.Listener {
                        override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                            emitPauseIfChanged(!playWhenReady)
                        }

                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            onPlaybackActiveChanged(isPlaying)
                            mainHandler.removeCallbacks(positionTicker)
                            if (isPlaying) {
                                mainHandler.post(positionTicker)
                            }
                        }

                        override fun onPlaybackStateChanged(playbackState: Int) {
                            val p = player ?: return
                            if (playbackState == Player.STATE_READY) {
                                consecutiveErrors = 0
                                val durMs = p.duration
                                if (durMs > 0L && durMs != C.TIME_UNSET) {
                                    dispatchToPython("on_duration", durMs / 1000.0)
                                }
                            } else if (playbackState == Player.STATE_ENDED) {
                                consecutiveErrors = 0
                                mainHandler.removeCallbacks(positionTicker)
                                dispatchToPython("on_eof")
                            }
                        }

                        override fun onPlayerError(error: PlaybackException) {
                            Log.e(TAG, "Error de reproducción en ExoPlayer: ${error.message}", error)
                            mainHandler.removeCallbacks(positionTicker)
                            consecutiveErrors += 1
                            if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                                p_stopInternal()
                                emitPauseIfChanged(true)
                                dispatchToPython("on_playback_error", error.message ?: "Error en ExoPlayer")
                            } else {
                                dispatchToPython("on_eof")
                            }
                        }
                    })
                }
        }
    }

    private fun p_stopInternal() {
        val p = player ?: return
        p.stop()
        p.clearMediaItems()
        onPlaybackActiveChanged(false)
    }

    fun setPythonCallbackHandler(handler: PyObject?) {
        pyCallbackHandler = handler
    }

    fun loadFile(pathOrUrl: String) {
        mainHandler.post {
            val p = player ?: return@post
            try {
                val uri = if (
                    pathOrUrl.startsWith("http://") ||
                    pathOrUrl.startsWith("https://") ||
                    pathOrUrl.startsWith("content://")
                ) {
                    Uri.parse(pathOrUrl)
                } else {
                    Uri.fromFile(File(pathOrUrl))
                }
                lastReportedPaused = null
                p.setMediaItem(MediaItem.fromUri(uri))
                p.prepare()
                p.playWhenReady = true
            } catch (e: Exception) {
                Log.e(TAG, "No pude cargar audio en ExoPlayer: $pathOrUrl", e)
                dispatchToPython("on_eof")
            }
        }
    }

    fun setPause(paused: Boolean) {
        mainHandler.post {
            val p = player ?: return@post
            p.playWhenReady = !paused
            emitPauseIfChanged(paused)
        }
    }

    fun seekAbsolute(positionSec: Double) {
        mainHandler.post {
            val p = player ?: return@post
            val targetMs = (positionSec * 1000.0).toLong().coerceAtLeast(0L)
            p.seekTo(targetMs)
            val durMs = p.duration
            val durSec = if (durMs > 0L && durMs != C.TIME_UNSET) durMs / 1000.0 else 0.0
            dispatchToPython("on_position", targetMs / 1000.0, durSec)
        }
    }

    fun seekRelative(deltaSec: Double) {
        mainHandler.post {
            val p = player ?: return@post
            val targetMs = (p.currentPosition + (deltaSec * 1000.0).toLong()).coerceAtLeast(0L)
            p.seekTo(targetMs)
            val durMs = p.duration
            val durSec = if (durMs > 0L && durMs != C.TIME_UNSET) durMs / 1000.0 else 0.0
            dispatchToPython("on_position", targetMs / 1000.0, durSec)
        }
    }

    fun setVolume(volPercent: Double) {
        val clamped = volPercent.coerceIn(0.0, 100.0)
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val target = ((clamped / 100.0) * maxVol).roundToInt().coerceIn(0, maxVol)
        am.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
        mainHandler.post {
            val p = player ?: return@post
            lastVolume = 1.0f
            p.volume = if (isMuted) 0f else 1.0f
        }
    }

    fun getSystemVolumePercent(): Int {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val curVol = am.getStreamVolume(AudioManager.STREAM_MUSIC).coerceIn(0, maxVol)
        return ((curVol * 100f) / maxVol).roundToInt().coerceIn(0, 100)
    }

    fun updateNotification(
        title: String,
        artist: String,
        paused: Boolean,
        coverUrl: String?,
        trackPath: String?,
        durationMs: Long,
        positionMs: Long,
        isFavorite: Boolean,
        isPauseAfter: Boolean,
    ) {
        mainHandler.post {
            onMediaNotification?.invoke(
                title,
                artist,
                paused,
                coverUrl,
                trackPath,
                durationMs,
                positionMs,
                isFavorite,
                isPauseAfter,
            )
        }
    }

    fun updateNotificationPosition(durationMs: Long, positionMs: Long, paused: Boolean) {
        mainHandler.post {
            onPositionNotification?.invoke(durationMs, positionMs, paused)
        }
    }

    fun setMute(muted: Boolean) {
        mainHandler.post {
            val p = player ?: return@post
            isMuted = muted
            p.volume = if (muted) 0f else lastVolume
        }
    }

    fun stopPlayback() {
        mainHandler.post {
            mainHandler.removeCallbacks(positionTicker)
            consecutiveErrors = 0
            lastReportedPaused = null
            p_stopInternal()
        }
    }

    fun release() {
        if (activeInstance === this) {
            activeInstance = null
        }
        pyCallbackHandler = null
        pythonCallbackExecutor.shutdownNow()
        mainHandler.post {
            mainHandler.removeCallbacks(positionTicker)
            player?.release()
            player = null
        }
    }

    private fun dispatchToPython(method: String, vararg args: Any) {
        val handler = pyCallbackHandler ?: return
        try {
            pythonCallbackExecutor.execute {
                try {
                    handler.callAttr(method, *args)
                } catch (e: Exception) {
                    Log.w(TAG, "Error despachando callback '$method' a Python: ${e.message}")
                }
            }
        } catch (_: RejectedExecutionException) {
            // El player ya fue liberado
        }
    }
}
