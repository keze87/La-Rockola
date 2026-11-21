package ar.carpincho.rockola

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.os.Build
import android.os.Bundle
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.media.app.NotificationCompat.MediaStyle

/**
 * Administra la MediaSession, los metadatos, el progreso en vivo (seekbar),
 * las acciones personalizadas (favorito y pausa al terminar) y la notificación MediaStyle.
 */
class MediaNotificationManager(
    private val service: Service,
    private val channelId: String,
    private val notificationId: Int,
    private val onCommand: (cmd: String, extra: Map<String, Any>) -> Unit,
    private val onRequestArtwork: (coverUrl: String) -> Unit,
) {
    private var mediaSession: MediaSessionCompat? = null

    @Volatile
    private var currentTitle: String = "La Rockola del Carpincho"

    @Volatile
    private var currentArtist: String = "En espera"

    @Volatile
    private var currentPaused: Boolean = true

    @Volatile
    private var currentCoverUrl: String? = null

    private var currentArtwork: Bitmap? = null
    private var currentTrackPath: String? = null
    private var currentDurationMs: Long = 0L
    private var currentPositionMs: Long = 0L
    private var currentIsFavorite: Boolean = false
    private var currentIsPauseAfter: Boolean = false
    private var currentServerUrl: String = "http://127.0.0.1:1729"

    private val defaultArtwork: Bitmap? by lazy {
        BitmapFactory.decodeResource(service.resources, R.mipmap.ic_launcher)
            ?: ContextCompat.getDrawable(service, R.mipmap.ic_launcher)?.let { drawable ->
                val size = 192
                Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).also { bmp ->
                    val canvas = Canvas(bmp)
                    drawable.setBounds(0, 0, canvas.width, canvas.height)
                    drawable.draw(canvas)
                }
            }
    }

    val isPaused: Boolean
        get() = currentPaused

    fun initialize() {
        createNotificationChannel()
        mediaSession = MediaSessionCompat(service, "RockolaMediaSession").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() {
                    if (currentPaused) {
                        onCommand("pause", emptyMap())
                    }
                }

                override fun onPause() {
                    if (!currentPaused) onCommand("pause", emptyMap())
                }

                override fun onSkipToNext() {
                    onCommand("skip", emptyMap())
                }

                override fun onSkipToPrevious() {
                    onCommand("prev", emptyMap())
                }

                override fun onSeekTo(pos: Long) {
                    seekTo(pos)
                }

                override fun onCustomAction(action: String?, extras: Bundle?) {
                    when (action) {
                        RockolaForegroundService.CUSTOM_ACTION_FAVORITE -> toggleFavorite()
                        RockolaForegroundService.CUSTOM_ACTION_PAUSE_AFTER -> togglePauseAfter()
                    }
                }
            })
            isActive = true
        }
        syncMediaSessionState()
    }

    @Synchronized
    fun updateServerEndpoint(serverUrl: String, statusText: String) {
        currentServerUrl = serverUrl
        currentTitle = "La Rockola del Carpincho"
        currentArtist = statusText
        syncMediaSessionState()
        notify(statusText)
    }

    @Synchronized
    fun updateMedia(
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
        val coverChanged = coverUrl != currentCoverUrl
        currentTitle = title
        currentArtist = artist
        currentPaused = paused
        currentCoverUrl = coverUrl
        currentTrackPath = trackPath
        currentDurationMs = durationMs.coerceAtLeast(0L)
        currentPositionMs = positionMs.coerceAtLeast(0L)
        currentIsFavorite = isFavorite
        currentIsPauseAfter = isPauseAfter

        if (coverChanged) {
            currentArtwork = null
            if (coverUrl != null) {
                onRequestArtwork(coverUrl)
            }
        }
        syncMediaSessionState()
        notify(currentArtist)
    }

    @Synchronized
    fun updatePosition(durationMs: Long, positionMs: Long, paused: Boolean) {
        currentDurationMs = durationMs.coerceAtLeast(0L)
        currentPositionMs = positionMs.coerceAtLeast(0L)
        currentPaused = paused
        syncMediaSessionState()
    }

    @Synchronized
    fun applyArtworkIfCurrent(coverUrl: String, bitmap: Bitmap) {
        if (coverUrl != currentCoverUrl) return
        currentArtwork = bitmap
        syncMediaSessionState()
        notify(currentArtist)
    }

    @Synchronized
    fun toggleFavorite() {
        val path = currentTrackPath ?: return
        currentIsFavorite = !currentIsFavorite
        syncMediaSessionState()
        notify(currentArtist)
        onCommand("toggle_favorite", mapOf("path" to path))
    }

    @Synchronized
    fun togglePauseAfter() {
        val path = currentTrackPath ?: return
        currentIsPauseAfter = !currentIsPauseAfter
        syncMediaSessionState()
        notify(currentArtist)
        onCommand("pause_after", mapOf("path" to path))
    }

    @Synchronized
    private fun seekTo(pos: Long) {
        val clamped = pos.coerceAtLeast(0L)
        currentPositionMs = clamped
        syncMediaSessionState()
        onCommand("seek_absolute", mapOf("amount" to (clamped / 1000.0)))
    }

    @Synchronized
    fun buildNotification(contentText: String): Notification {
        val openIntent = Intent(service, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPending = PendingIntent.getActivity(
            service,
            0,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val favPending = serviceActionPendingIntent(RockolaForegroundService.ACTION_MEDIA_FAVORITE, 5)
        val prevPending = serviceActionPendingIntent(RockolaForegroundService.ACTION_MEDIA_PREV, 2)
        val playPausePending = serviceActionPendingIntent(RockolaForegroundService.ACTION_MEDIA_PLAY_PAUSE, 3)
        val nextPending = serviceActionPendingIntent(RockolaForegroundService.ACTION_MEDIA_NEXT, 4)
        val pauseAfterPending = serviceActionPendingIntent(RockolaForegroundService.ACTION_MEDIA_PAUSE_AFTER, 6)

        val favIcon = if (currentIsFavorite) {
            R.drawable.ic_notif_favorite_filled
        } else {
            R.drawable.ic_notif_favorite_border
        }
        val favLabel = if (currentIsFavorite) "Quitar de favoritos" else "Agregar a favoritos"
        val playPauseIcon = if (currentPaused) android.R.drawable.ic_media_play else android.R.drawable.ic_media_pause
        val playPauseLabel = if (currentPaused) "Reproducir" else "Pausar"
        val pauseAfterIcon = if (currentIsPauseAfter) {
            R.drawable.ic_notif_pause_after_on
        } else {
            R.drawable.ic_notif_pause_after_off
        }
        val pauseAfterLabel = if (currentIsPauseAfter) "Cancelar pausa al terminar" else "Pausar al terminar"

        val largeIcon = currentArtwork ?: defaultArtwork

        val mediaStyle = MediaStyle().setShowActionsInCompactView(1, 2, 3)
        mediaSession?.sessionToken?.let { mediaStyle.setMediaSession(it) }

        return NotificationCompat.Builder(service, channelId)
            .setContentTitle(currentTitle)
            .setContentText(contentText)
            .setSubText(currentServerUrl)
            .setSmallIcon(R.drawable.ic_stat_carpincho)
            .setColor(0xFFA67C52.toInt())
            .setLargeIcon(largeIcon)
            .setContentIntent(openPending)
            .setOngoing(!currentPaused)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(favIcon, favLabel, favPending)
            .addAction(android.R.drawable.ic_media_previous, "Anterior", prevPending)
            .addAction(playPauseIcon, playPauseLabel, playPausePending)
            .addAction(android.R.drawable.ic_media_next, "Siguiente", nextPending)
            .addAction(pauseAfterIcon, pauseAfterLabel, pauseAfterPending)
            .setStyle(mediaStyle)
            .build()
    }

    fun notify(text: String) {
        val manager = service.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(notificationId, buildNotification(text))
    }

    fun release() {
        mediaSession?.isActive = false
        mediaSession?.release()
        mediaSession = null
    }

    @Synchronized
    private fun syncMediaSessionState() {
        val session = mediaSession ?: return
        val stateCode = if (currentPaused) PlaybackStateCompat.STATE_PAUSED else PlaybackStateCompat.STATE_PLAYING
        val speed = if (currentPaused) 0.0f else 1.0f
        val actions = PlaybackStateCompat.ACTION_PLAY or
            PlaybackStateCompat.ACTION_PAUSE or
            PlaybackStateCompat.ACTION_PLAY_PAUSE or
            PlaybackStateCompat.ACTION_SKIP_TO_NEXT or
            PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS or
            PlaybackStateCompat.ACTION_SEEK_TO

        val stateBuilder = PlaybackStateCompat.Builder()
            .setActions(actions)
            .setState(stateCode, currentPositionMs, speed)

        if (!currentTrackPath.isNullOrBlank()) {
            val favIcon = if (currentIsFavorite) {
                R.drawable.ic_notif_favorite_filled
            } else {
                R.drawable.ic_notif_favorite_border
            }
            val favLabel = if (currentIsFavorite) "Quitar de favoritos" else "Agregar a favoritos"
            stateBuilder.addCustomAction(
                PlaybackStateCompat.CustomAction.Builder(
                    RockolaForegroundService.CUSTOM_ACTION_FAVORITE,
                    favLabel,
                    favIcon,
                ).build(),
            )

            val pauseAfterIcon = if (currentIsPauseAfter) {
                R.drawable.ic_notif_pause_after_on
            } else {
                R.drawable.ic_notif_pause_after_off
            }
            val pauseAfterLabel = if (currentIsPauseAfter) "Cancelar pausa al terminar" else "Pausar al terminar"
            stateBuilder.addCustomAction(
                PlaybackStateCompat.CustomAction.Builder(
                    RockolaForegroundService.CUSTOM_ACTION_PAUSE_AFTER,
                    pauseAfterLabel,
                    pauseAfterIcon,
                ).build(),
            )
        }

        session.setPlaybackState(stateBuilder.build())

        val metaBuilder = MediaMetadataCompat.Builder()
            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, currentTitle)
            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, currentArtist)
            .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, "La Rockola del Carpincho")

        if (currentDurationMs > 0L) {
            metaBuilder.putLong(MediaMetadataCompat.METADATA_KEY_DURATION, currentDurationMs)
        }
        currentArtwork?.let { metaBuilder.putBitmap(MediaMetadataCompat.METADATA_KEY_ALBUM_ART, it) }
        session.setMetadata(metaBuilder.build())
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Servidor de La Rockola",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "Mantiene el servidor musical, la reproducción y los controles activos"
            }
            val manager = service.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun serviceActionPendingIntent(action: String, requestCode: Int): PendingIntent {
        val intent = Intent(service, RockolaForegroundService::class.java).apply {
            this.action = action
        }
        return PendingIntent.getService(
            service,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }
}
