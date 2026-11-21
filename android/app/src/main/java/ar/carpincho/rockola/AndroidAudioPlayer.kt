package ar.carpincho.rockola

import android.content.Context
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

/**
 * Motor de reproducción nativo basado en AndroidX Media3 ExoPlayer.
 * Vive dentro de RockolaForegroundService para sobrevivir pantalla apagada,
 * cambio de app y cierre de la Activity, con manejo nativo de AudioFocus.
 */
class AndroidAudioPlayer(
    private val context: Context,
    private val onPlaybackActiveChanged: (active: Boolean) -> Unit,
) {
    companion object {
        private const val TAG = "RockolaExoPlayer"
        private const val POSITION_TICK_MS = 500L

        @Volatile
        private var activeInstance: AndroidAudioPlayer? = null

        @JvmStatic
        fun getActiveInstance(): AndroidAudioPlayer? = activeInstance
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private var player: ExoPlayer? = null
    private var lastVolume: Float = 1.0f
    private var isMuted: Boolean = false

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
                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            onPlaybackActiveChanged(isPlaying)
                            dispatchToPython("on_pause_changed", !isPlaying)
                            mainHandler.removeCallbacks(positionTicker)
                            if (isPlaying) {
                                mainHandler.post(positionTicker)
                            }
                        }

                        override fun onPlaybackStateChanged(playbackState: Int) {
                            val p = player ?: return
                            if (playbackState == Player.STATE_READY) {
                                val durMs = p.duration
                                if (durMs > 0L && durMs != C.TIME_UNSET) {
                                    dispatchToPython("on_duration", durMs / 1000.0)
                                }
                            } else if (playbackState == Player.STATE_ENDED) {
                                mainHandler.removeCallbacks(positionTicker)
                                dispatchToPython("on_eof")
                            }
                        }

                        override fun onPlayerError(error: PlaybackException) {
                            Log.e(TAG, "Error de reproducción en ExoPlayer: ${error.message}", error)
                            mainHandler.removeCallbacks(positionTicker)
                            dispatchToPython("on_eof")
                        }
                    })
                }
        }
    }

    fun setPythonCallbackHandler(handler: PyObject?) {
        pyCallbackHandler = handler
    }

    fun loadFile(pathOrUrl: String) {
        mainHandler.post {
            val p = player ?: return@post
            try {
                val uri = if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
                    Uri.parse(pathOrUrl)
                } else {
                    Uri.fromFile(File(pathOrUrl))
                }
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
        mainHandler.post {
            val p = player ?: return@post
            val clamped = (volPercent / 100.0).toFloat().coerceIn(0f, 1f)
            lastVolume = clamped
            if (!isMuted) {
                p.volume = clamped
            }
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
            val p = player ?: return@post
            mainHandler.removeCallbacks(positionTicker)
            p.stop()
            p.clearMediaItems()
            onPlaybackActiveChanged(false)
        }
    }

    fun release() {
        if (activeInstance === this) {
            activeInstance = null
        }
        pyCallbackHandler = null
        mainHandler.post {
            mainHandler.removeCallbacks(positionTicker)
            player?.release()
            player = null
        }
    }

    private fun dispatchToPython(method: String, vararg args: Any) {
        val handler = pyCallbackHandler ?: return
        try {
            handler.callAttr(method, *args)
        } catch (e: Exception) {
            Log.w(TAG, "Error despachando callback '$method' a Python: ${e.message}")
        }
    }
}
