package ar.carpincho.rockola

import android.content.Context
import android.content.Intent
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat

internal data class ShortcutSpec(
    val id: String,
    val action: String,
    val shortLabel: String,
    val longLabel: String,
    val iconRes: Int,
)

/**
 * Política pura de armado de accesos directos dinámicos (testeable en JVM).
 */
internal object ShortcutPolicy {
    fun buildSpecs(lastTrackTitle: String?): List<ShortcutSpec> {
        val list = mutableListOf<ShortcutSpec>()
        val cleanedTitle = lastTrackTitle?.trim().orEmpty()
        if (cleanedTitle.isNotEmpty()) {
            val truncated = if (cleanedTitle.length > 36) "${cleanedTitle.take(33)}..." else cleanedTitle
            list.add(
                ShortcutSpec(
                    id = "resume_last",
                    action = MainActivity.ACTION_RESUME_LAST,
                    shortLabel = "Reanudar",
                    longLabel = "Reanudar: $truncated",
                    iconRes = R.mipmap.ic_launcher,
                ),
            )
        }
        list.addAll(
            listOf(
                ShortcutSpec(
                    id = "open_library",
                    action = MainActivity.ACTION_OPEN_LIBRARY,
                    shortLabel = "Librería",
                    longLabel = "Abrir la librería de temas",
                    iconRes = R.drawable.ic_shortcut_library,
                ),
                ShortcutSpec(
                    id = "open_queue",
                    action = MainActivity.ACTION_OPEN_QUEUE,
                    shortLabel = "Cola",
                    longLabel = "Abrir la cola de reproducción",
                    iconRes = R.drawable.ic_shortcut_queue,
                ),
                ShortcutSpec(
                    id = "open_tops",
                    action = MainActivity.ACTION_OPEN_TOPS,
                    shortLabel = "Tops",
                    longLabel = "Abrir los temas más sonados",
                    iconRes = R.drawable.ic_shortcut_tops,
                ),
                ShortcutSpec(
                    id = "open_fogon",
                    action = MainActivity.ACTION_OPEN_FOGON,
                    shortLabel = "Modo Fogón",
                    longLabel = "Abrir en Modo Fogón",
                    iconRes = R.mipmap.ic_launcher,
                ),
            ),
        )
        return list
    }
}

/**
 * Administra los accesos directos dinámicos vía ShortcutManagerCompat.
 */
internal object ShortcutHelper {
    private const val KEY_LAST_TRACK_TITLE = "last_track_title"

    fun saveLastTrackTitleAndRefresh(context: Context, title: String?) {
        val cleaned = title?.trim()?.takeIf { it.isNotEmpty() && it != "La Rockola del Carpincho" } ?: return
        val prefs = context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
        if (prefs.getString(KEY_LAST_TRACK_TITLE, null) != cleaned) {
            prefs.edit().putString(KEY_LAST_TRACK_TITLE, cleaned).apply()
            refreshDynamicShortcuts(context, cleaned)
        }
    }

    fun refreshDynamicShortcuts(context: Context, overrideLastTitle: String? = null) {
        try {
            val prefs = context.getSharedPreferences(RockolaForegroundService.PREFS_NAME, Context.MODE_PRIVATE)
            val lastTitle = overrideLastTitle ?: prefs.getString(KEY_LAST_TRACK_TITLE, null)
            val maxAllowed = ShortcutManagerCompat.getMaxShortcutCountPerActivity(context).coerceAtLeast(4)
            val specs = ShortcutPolicy.buildSpecs(lastTitle).take(maxAllowed)
            val shortcuts = specs.mapIndexed { rank, spec ->
                val intent = Intent(context, MainActivity::class.java).apply {
                    action = spec.action
                }
                ShortcutInfoCompat.Builder(context, spec.id)
                    .setShortLabel(spec.shortLabel)
                    .setLongLabel(spec.longLabel)
                    .setIcon(IconCompat.createWithResource(context, spec.iconRes))
                    .setIntent(intent)
                    .setRank(rank)
                    .build()
            }
            ShortcutManagerCompat.setDynamicShortcuts(context, shortcuts)
        } catch (_: Exception) {
            // Algunos dispositivos restringen shortcuts dinámicos en perfiles secundarios
        }
    }
}
