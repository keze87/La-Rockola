package ar.carpincho.rockola

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Prueba de humo instrumentada que valida en dispositivo real que Chaquopy Python 3.13,
 * FastAPI, Pydantic Core y los puentes Kotlin nativos carguen sin errores binarios ni de rutas.
 */
@RunWith(AndroidJUnit4::class)
class EmbeddedRuntimeSmokeTest {

    @Test
    fun embeddedPythonRuntimeBootstrapsFastApiAndBridges() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }

        AndroidStorageBridge.initialize(context)
        assertNull(AndroidImageResizer.resizeJpeg(ByteArray(0), 128))

        val py = Python.getInstance()
        val smoke = py.getModule("app.android_smoke").callAttr("run_embedded_smoke_check")
        val map = smoke.asMap()
        val okKey = py.builtins.callAttr("str", "ok")
        val healthKey = py.builtins.callAttr("str", "health_status")
        val sysKey = py.builtins.callAttr("str", "system_info_status")

        assertTrue(map[okKey]?.toBoolean() == true)
        assertEquals(200, map[healthKey]?.toInt())
        assertEquals(200, map[sysKey]?.toInt())
    }
}
