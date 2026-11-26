package ar.carpincho.rockola

import android.graphics.Bitmap
import android.graphics.Color
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream

/**
 * Prueba de humo instrumentada que valida en dispositivo real (incluyendo APK minificado con R8)
 * que Chaquopy Python 3.14, FastAPI, Pydantic Core, almacenamiento SAF, redimensionado de imágenes
 * y ExoPlayer funcionen sin errores de minificación ni de rutas.
 */
@RunWith(AndroidJUnit4::class)
class EmbeddedRuntimeSmokeTest {

    @Test
    fun embeddedPythonRuntimeBootstrapsFastApiAndBridges() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }

        // 1. Almacenamiento SAF: inicialización y validación de URI sin permiso vía API pública mantenida por R8
        AndroidStorageBridge.initialize(context)
        val safJson = JSONObject(AndroidStorageBridge.validateTreeUriJson("content://invalid.provider/tree/none"))
        assertEquals("permission_denied", safJson.getString("status"))
        assertFalse(safJson.isNull("error"))

        // 2. Redimensionado de imágenes: entrada vacía devuelve null y JPEG válido se reescala
        assertNull(AndroidImageResizer.resizeJpeg(ByteArray(0), 128))
        val bmp = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
        bmp.eraseColor(Color.rgb(212, 150, 66))
        val rawJpeg = ByteArrayOutputStream().use { out ->
            bmp.compress(Bitmap.CompressFormat.JPEG, 90, out)
            out.toByteArray()
        }
        bmp.recycle()
        val resized = AndroidImageResizer.resizeJpeg(rawJpeg, 32)
        assertNotNull(resized)
        assertTrue((resized?.size ?: 0) > 0)

        // 3. Reproductor nativo ExoPlayer: inicialización, volumen del reproductor, mute y liberación
        val player = AndroidAudioPlayer(
            context = context,
            onPlaybackActiveChanged = {},
        )
        player.initialize()
        player.setVolume(45.0)
        assertEquals(45, player.getPlayerVolumePercent())
        player.setMute(true)
        player.setMute(false)
        player.release()

        // 4. Runtime Python + FastAPI + SQLite + backend SAF
        val py = Python.getInstance()
        val smoke = py.getModule("app.android_smoke").callAttr("run_embedded_smoke_check")
        val map = smoke.asMap()
        val okKey = py.builtins.callAttr("str", "ok")
        val healthKey = py.builtins.callAttr("str", "health_status")
        val sysKey = py.builtins.callAttr("str", "system_info_status")
        val storageKey = py.builtins.callAttr("str", "storage_ok")
        val playbackKey = py.builtins.callAttr("str", "playback_ok")

        assertTrue(map[okKey]?.toBoolean() == true)
        assertTrue(map[storageKey]?.toBoolean() == true)
        assertTrue(map[playbackKey]?.toBoolean() == true)
        assertEquals(200, map[healthKey]?.toInt())
        assertEquals(200, map[sysKey]?.toInt())
    }
}
