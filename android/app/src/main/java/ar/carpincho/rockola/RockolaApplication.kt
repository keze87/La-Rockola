package ar.carpincho.rockola

import android.app.Application
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

        fun ensurePythonStarted(application: android.content.Context) {
            synchronized(pythonInitLock) {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(application.applicationContext))
                }
            }
        }
    }

    override fun onCreate() {
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
            start()
        }
    }
}
