package ar.carpincho.rockola

import android.app.Application
import android.os.SystemClock
import android.util.Log
import androidx.appcompat.app.AppCompatDelegate
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Application propia que precalienta el intérprete Python de Chaquopy en segundo plano
 * apenas arranca el proceso, evitando esperar a que Activity/Service lo solicite.
 */
class RockolaApplication : Application() {
    companion object {
        private val pythonInitLock = Any()

        @Volatile
        var processStartElapsedMs: Long = 0L
            private set

        fun elapsedSinceProcessStartMs(): Long {
            val start = processStartElapsedMs
            return if (start > 0L) (SystemClock.elapsedRealtime() - start).coerceAtLeast(0L) else 0L
        }

        fun ensurePythonStarted(application: android.content.Context) {
            synchronized(pythonInitLock) {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(application.applicationContext))
                }
            }
        }
    }

    override fun onCreate() {
        processStartElapsedMs = SystemClock.elapsedRealtime()
        Log.i("RockolaStartup", "stage=app_on_create elapsedMs=0")
        super.onCreate()
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        val prefs = getSharedPreferences(RockolaForegroundService.PREFS_NAME, MODE_PRIVATE)
        val savedMode = prefs.getString(RockolaForegroundService.KEY_TARGET_MODE, "host")
        if (savedMode == "remote") {
            return
        }
        Thread(
            {
                try {
                    ensurePythonStarted(this)
                } catch (t: Throwable) {
                    Log.w("RockolaApp", "Precalentamiento Python diferido al servicio: ${t.message}")
                }
            },
            "RockolaPythonWarmup",
        ).apply {
            isDaemon = true
            priority = Thread.MIN_PRIORITY
            start()
        }
    }
}
