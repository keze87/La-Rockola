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
        album: String?,
    ) -> Unit)? = null,
    private val onPositionNotification: ((
        durationMs: Long,
        positionMs: Long,
        paused: Boolean,
    ) -> Unit)? = null,
) {
    interface RemotePlaybackListener {
        fun onRemoteDuration(durationSec: Double)
        fun onRemotePosition(positionSec: Double, durationSec: Double)
        fun onRemotePauseChanged(paused: Boolean)
        fun onRemoteEnded()
        fun onRemoteError(message: String)
    }

    companion object {
        private const val TAG = "RockolaExoPlayer"
        private const val POSITION_TICK_MS = 500L
        private const val MAX_CONSECUTIVE_ERRORS = 3
        private const val BED_FADE_IN_MS = 1000L
        private const val BED_FADE_OUT_MS = 1500L
        private const val BED_FADE_TICK_MS = 50L

        @Volatile
        private var activeInstance: AndroidAudioPlayer? = null

        @JvmStatic
        fun getActiveInstance(): AndroidAudioPlayer? = activeInstance

        fun clampSeekPositionMs(positionSec: Double, durationMs: Long): Long {
            val rawMs = if (positionSec.isFinite()) (positionSec * 1000.0).toLong() else 0L
            val nonNegMs = rawMs.coerceAtLeast(0L)
            return if (durationMs > 0L && durationMs != C.TIME_UNSET) {
                nonNegMs.coerceAtMost(durationMs)
            } else {
                nonNegMs
            }
        }

        fun shouldKeepPlaybackActive(
            isPlaying: Boolean,
            playWhenReady: Boolean,
            playbackState: Int,
            isLoadingMedia: Boolean,
        ): Boolean {
            if (isPlaying) return true
            if (!playWhenReady) return false
            return isLoadingMedia ||
                playbackState == Player.STATE_BUFFERING ||
                playbackState == Player.STATE_ENDED
        }

        fun computePlayerGain(volPercent: Double, muted: Boolean): Float {
            if (muted) return 0f
            return (volPercent.coerceIn(0.0, 100.0) / 100.0).toFloat()
        }

        fun computeStreamIndex(volPercent: Double, maxStreamVolume: Int): Int {
            val maxVol = maxStreamVolume.coerceAtLeast(1)
            val clamped = if (volPercent.isFinite()) volPercent.coerceIn(0.0, 100.0) else 0.0
            return ((clamped / 100.0) * maxVol).roundToInt().coerceIn(0, maxVol)
        }

        fun computePercentFromStream(currentStreamVolume: Int, maxStreamVolume: Int): Int {
            val maxVol = maxStreamVolume.coerceAtLeast(1)
            return ((currentStreamVolume.coerceIn(0, maxVol) * 100f) / maxVol).roundToInt().coerceIn(0, 100)
        }

        fun computeBedGain(
            volPercent: Double,
            muted: Boolean,
            bedRatio: Float,
            fadeEnvelope: Float,
        ): Float {
            val master = computePlayerGain(volPercent, muted)
            val safeRatio = bedRatio.coerceIn(0f, 1f)
            val safeEnv = fadeEnvelope.coerceIn(0f, 1f)
            return master * safeRatio * safeEnv
        }

        fun isBedSuppressed(suppressionReason: Int): Boolean {
            return suppressionReason == Player.PLAYBACK_SUPPRESSION_REASON_TRANSIENT_AUDIO_FOCUS_LOSS
        }

        fun computeBedFadeEnvelope(elapsedMs: Long, durationMs: Long): Float {
            val safeElapsed = elapsedMs.coerceAtLeast(0L)
            val fadeIn = (safeElapsed.toFloat() / BED_FADE_IN_MS.toFloat()).coerceIn(0f, 1f)
            if (durationMs <= BED_FADE_IN_MS + BED_FADE_OUT_MS) {
                return fadeIn
            }
            val remainingMs = (durationMs - safeElapsed).coerceAtLeast(0L)
            val fadeOut = (remainingMs.toFloat() / BED_FADE_OUT_MS.toFloat()).coerceIn(0f, 1f)
            return minOf(fadeIn, fadeOut)
        }
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private val pythonCallbackExecutor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "RockolaPyCallback").apply { isDaemon = true }
    }
    private var player: ExoPlayer? = null
    private var bedPlayer: ExoPlayer? = null
    @Volatile
    private var currentVolumePercent: Double = 100.0
    @Volatile
    private var isMuted: Boolean = false
    private var bedTargetVolumeRatio: Float = 0.1f
    private var bedFadeEnvelope: Float = 0f
    private var consecutiveErrors: Int = 0
    private var lastReportedPaused: Boolean? = null
    private var isLoadingMedia: Boolean = false

    @Volatile
    private var pendingPauseState: Boolean? = null

    @Volatile
    private var pyCallbackHandler: PyObject? = null

    @Volatile
    var isRemoteMode: Boolean = false
        private set

    @Volatile
    var remotePlaybackListener: RemotePlaybackListener? = null

    private val positionTicker = object : Runnable {
        override fun run() {
            val p = player ?: return
            if (p.isPlaying) {
                val posSec = (p.currentPosition.coerceAtLeast(0L)) / 1000.0
                val durMs = p.duration
                val durSec = if (durMs > 0L && durMs != C.TIME_UNSET) durMs / 1000.0 else 0.0
                emitPlayerEvent("on_position", posSec, durSec)
                mainHandler.postDelayed(this, POSITION_TICK_MS)
            }
        }
    }

    private val bedFadeTicker = object : Runnable {
        override fun run() {
            val bp = bedPlayer ?: return
            val p = player
            if (p != null && bp.playbackState != Player.STATE_IDLE) {
                val posMs = p.currentPosition.coerceAtLeast(0L)
                val rawDur = p.duration
                val durMs = if (rawDur > 0L && rawDur != C.TIME_UNSET) rawDur else 0L
                bedFadeEnvelope = computeBedFadeEnvelope(posMs, durMs)
                applyBedVolume()
                mainHandler.postDelayed(this, BED_FADE_TICK_MS)
            }
        }
    }

    private fun applyBedVolume() {
        // El volumen maestro en Android lo gobierna STREAM_MUSIC; ExoPlayer queda a ganancia 100% salvo mute.
        bedPlayer?.volume = computeBedGain(100.0, isMuted, bedTargetVolumeRatio, bedFadeEnvelope)
    }

    private fun parseMediaUri(pathOrUrl: String): Uri {
        return if (
            pathOrUrl.startsWith("http://") ||
            pathOrUrl.startsWith("https://") ||
            pathOrUrl.startsWith("content://")
        ) {
            Uri.parse(pathOrUrl)
        } else {
            Uri.fromFile(File(pathOrUrl))
        }
    }

    private fun stopBedInternal() {
        mainHandler.removeCallbacks(bedFadeTicker)
        bedFadeEnvelope = 0f
        val bp = bedPlayer ?: return
        bp.stop()
        bp.clearMediaItems()
    }

    private fun emitPauseIfChanged(paused: Boolean) {
        if (lastReportedPaused == paused) return
        lastReportedPaused = paused
        emitPlayerEvent("on_pause_changed", paused)
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
                .setWakeMode(C.WAKE_MODE_NETWORK)
                .build()
                .apply {
                    addListener(object : Player.Listener {
                        override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                            bedPlayer?.let { bp ->
                                if (bp.playbackState != Player.STATE_IDLE) {
                                    bp.playWhenReady = playWhenReady && !isBedSuppressed(playbackSuppressionReason)
                                }
                            }
                            emitPauseIfChanged(!playWhenReady)
                        }

                        override fun onPlaybackSuppressionReasonChanged(playbackSuppressionReason: Int) {
                            val suppressed = isBedSuppressed(playbackSuppressionReason)
                            bedPlayer?.let { bp ->
                                if (bp.playbackState != Player.STATE_IDLE) {
                                    bp.playWhenReady = playWhenReady && !suppressed
                                }
                            }
                        }

                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            val p = player
                            val active = p != null && shouldKeepPlaybackActive(
                                isPlaying = isPlaying,
                                playWhenReady = p.playWhenReady,
                                playbackState = p.playbackState,
                                isLoadingMedia = isLoadingMedia,
                            )
                            onPlaybackActiveChanged(active)
                            mainHandler.removeCallbacks(positionTicker)
                            if (isPlaying) {
                                mainHandler.post(positionTicker)
                            }
                        }

                        override fun onPlaybackStateChanged(playbackState: Int) {
                            val p = player ?: return
                            if (playbackState == Player.STATE_READY) {
                                isLoadingMedia = false
                                consecutiveErrors = 0
                                val durMs = p.duration
                                if (durMs > 0L && durMs != C.TIME_UNSET) {
                                    emitPlayerEvent("on_duration", durMs / 1000.0)
                                }
                            } else if (playbackState == Player.STATE_ENDED) {
                                isLoadingMedia = false
                                consecutiveErrors = 0
                                mainHandler.removeCallbacks(positionTicker)
                                stopBedInternal()
                                emitPlayerEvent("on_eof")
                            }
                        }

                        override fun onPlayerError(error: PlaybackException) {
                            Log.e(TAG, "Error de reproducción en ExoPlayer: ${error.message}", error)
                            isLoadingMedia = false
                            mainHandler.removeCallbacks(positionTicker)
                            consecutiveErrors += 1
                            if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                                stopInternal()
                                emitPauseIfChanged(true)
                                emitPlayerEvent("on_playback_error", error.message ?: "Error en ExoPlayer")
                            } else {
                                emitPlayerEvent("on_eof")
                            }
                        }
                    })
                }
        }
    }

    private fun stopInternal() {
        stopBedInternal()
        val p = player ?: return
        isLoadingMedia = false
        p.stop()
        p.clearMediaItems()
        onPlaybackActiveChanged(false)
    }

    fun setPythonCallbackHandler(handler: PyObject?) {
        pyCallbackHandler = handler
    }

    fun loadFile(pathOrUrl: String) {
        prepareMediaSource(pathOrUrl, remote = false, startPausedOverride = null)
    }

    fun loadRemoteUrl(url: String, startPaused: Boolean = false) {
        prepareMediaSource(url, remote = true, startPausedOverride = startPaused)
    }

    private fun prepareMediaSource(pathOrUrl: String, remote: Boolean, startPausedOverride: Boolean?) {
        mainHandler.post {
            stopBedInternal()
            val p = player ?: return@post
            try {
                isRemoteMode = remote
                if (remote) {
                    consecutiveErrors = 0
                }
                val uri = parseMediaUri(pathOrUrl)
                lastReportedPaused = null
                val shouldStartPaused = startPausedOverride ?: (pendingPauseState == true)
                pendingPauseState = null
                isLoadingMedia = true
                p.setMediaItem(MediaItem.fromUri(uri))
                p.prepare()
                p.playWhenReady = !shouldStartPaused
            } catch (e: Exception) {
                isLoadingMedia = false
                Log.e(TAG, "No pude cargar audio en ExoPlayer: $pathOrUrl", e)
                emitPlayerEvent("on_eof")
            }
        }
    }

    fun startRadioBed(pathOrUrl: String, offsetSec: Double = 0.0, volumeRatio: Double = 0.1) {
        mainHandler.post {
            try {
                val bp = bedPlayer ?: ExoPlayer.Builder(context.applicationContext)
                    .setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(C.USAGE_MEDIA)
                            .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                            .build(),
                        false,
                    )
                    .build()
                    .apply {
                        addListener(object : Player.Listener {
                            override fun onPlayerError(error: PlaybackException) {
                                Log.w(TAG, "Error en cortina radial ExoPlayer: ${error.message}")
                                stopBedInternal()
                            }
                        })
                    }
                    .also { bedPlayer = it }

                bedTargetVolumeRatio = volumeRatio.toFloat().coerceIn(0f, 1f)
                bedFadeEnvelope = 0f
                val p = player
                bp.volume = 0f
                val startMs = (offsetSec * 1000.0).toLong().coerceAtLeast(0L)
                bp.setMediaItem(MediaItem.fromUri(parseMediaUri(pathOrUrl)), startMs)
                bp.prepare()
                val suppressed = p != null && isBedSuppressed(p.playbackSuppressionReason)
                bp.playWhenReady = (p?.playWhenReady ?: true) && !suppressed
                mainHandler.removeCallbacks(bedFadeTicker)
                mainHandler.post(bedFadeTicker)
            } catch (e: Exception) {
                Log.w(TAG, "No pude iniciar cortina radial en ExoPlayer: $pathOrUrl", e)
                stopBedInternal()
            }
        }
    }

    fun stopRadioBed() {
        mainHandler.post {
            stopBedInternal()
        }
    }

    fun setPause(paused: Boolean) {
        pendingPauseState = paused
        mainHandler.post {
            val p = player ?: return@post
            pendingPauseState = null
            p.playWhenReady = !paused
            emitPauseIfChanged(paused)
        }
    }

    fun seekAbsolute(positionSec: Double) {
        mainHandler.post {
            val p = player ?: return@post
            val targetMs = clampSeekPositionMs(positionSec, p.duration)
            p.seekTo(targetMs)
            val durMs = p.duration
            val durSec = if (durMs > 0L && durMs != C.TIME_UNSET) durMs / 1000.0 else 0.0
            emitPlayerEvent("on_position", targetMs / 1000.0, durSec)
        }
    }

    fun seekRelative(deltaSec: Double) {
        mainHandler.post {
            val p = player ?: return@post
            val targetMs = (p.currentPosition + (deltaSec * 1000.0).toLong()).coerceAtLeast(0L)
            p.seekTo(targetMs)
            val durMs = p.duration
            val durSec = if (durMs > 0L && durMs != C.TIME_UNSET) durMs / 1000.0 else 0.0
            emitPlayerEvent("on_position", targetMs / 1000.0, durSec)
        }
    }

    fun setVolume(volPercent: Double) {
        val clamped = if (volPercent.isFinite()) volPercent.coerceIn(0.0, 100.0) else 0.0
        currentVolumePercent = clamped
        mainHandler.post {
            try {
                val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
                if (am != null) {
                    val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
                    val targetIdx = computeStreamIndex(clamped, maxVol)
                    am.setStreamVolume(AudioManager.STREAM_MUSIC, targetIdx, 0)
                }
            } catch (_: Exception) {
                // Algunos entornos restringidos o de test pueden bloquear setStreamVolume
            }
            val p = player ?: return@post
            p.volume = computePlayerGain(100.0, isMuted)
            applyBedVolume()
        }
    }

    fun getPlayerVolumePercent(): Int {
        return currentVolumePercent.roundToInt().coerceIn(0, 100)
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
        album: String? = null,
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
                album,
            )
        }
    }

    fun updateNotificationPosition(durationMs: Long, positionMs: Long, paused: Boolean) {
        mainHandler.post {
            onPositionNotification?.invoke(durationMs, positionMs, paused)
        }
    }

    fun setMute(muted: Boolean) {
        isMuted = muted
        mainHandler.post {
            val p = player ?: return@post
            p.volume = computePlayerGain(100.0, muted)
            applyBedVolume()
        }
    }

    fun stopPlayback() {
        pendingPauseState = null
        mainHandler.post {
            mainHandler.removeCallbacks(positionTicker)
            consecutiveErrors = 0
            lastReportedPaused = null
            stopInternal()
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
            mainHandler.removeCallbacks(bedFadeTicker)
            bedPlayer?.release()
            bedPlayer = null
            player?.release()
            player = null
        }
    }

    private fun emitPlayerEvent(method: String, vararg args: Any) {
        if (isRemoteMode) {
            val listener = remotePlaybackListener ?: return
            when (method) {
                "on_duration" -> listener.onRemoteDuration((args.getOrNull(0) as? Double) ?: 0.0)
                "on_position" -> listener.onRemotePosition(
                    (args.getOrNull(0) as? Double) ?: 0.0,
                    (args.getOrNull(1) as? Double) ?: 0.0,
                )
                "on_pause_changed" -> listener.onRemotePauseChanged((args.getOrNull(0) as? Boolean) ?: false)
                "on_eof" -> listener.onRemoteEnded()
                "on_playback_error" -> listener.onRemoteError((args.getOrNull(0) as? String) ?: "Error en ExoPlayer")
            }
            return
        }
        dispatchToPython(method, *args)
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
