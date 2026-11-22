package ar.carpincho.rockola

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import java.io.ByteArrayOutputStream
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Redimensiona portadas de audio con API nativa de Android (BitmapFactory)
 * evitando empaquetar Pillow y su dependencia binaria libfreetype.so.
 */
object AndroidImageResizer {
    @JvmStatic
    fun resizeJpeg(data: ByteArray, maxSize: Int): ByteArray? {
        if (data.isEmpty() || maxSize <= 0) return null
        var decoded: Bitmap? = null
        var scaled: Bitmap? = null
        var flattened: Bitmap? = null
        return try {
            val boundsOpts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(data, 0, data.size, boundsOpts)
            if (boundsOpts.outWidth <= 0 || boundsOpts.outHeight <= 0) return null
            if (boundsOpts.outWidth <= maxSize && boundsOpts.outHeight <= maxSize) {
                return null
            }

            var sampleSize = 1
            while ((boundsOpts.outWidth / sampleSize) > maxSize * 2 ||
                (boundsOpts.outHeight / sampleSize) > maxSize * 2
            ) {
                sampleSize *= 2
            }

            val decodeOpts = BitmapFactory.Options().apply {
                inSampleSize = sampleSize
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            decoded = BitmapFactory.decodeByteArray(data, 0, data.size, decodeOpts) ?: return null
            val srcW = decoded.width
            val srcH = decoded.height
            if (srcW <= 0 || srcH <= 0) return null

            val ratio = maxSize.toFloat() / max(srcW, srcH).toFloat()
            val dstW = (srcW * ratio).roundToInt().coerceAtLeast(1)
            val dstH = (srcH * ratio).roundToInt().coerceAtLeast(1)
            scaled = Bitmap.createScaledBitmap(decoded, dstW, dstH, true)

            val target = if (scaled.hasAlpha()) {
                flattened = Bitmap.createBitmap(dstW, dstH, Bitmap.Config.ARGB_8888)
                val canvas = Canvas(flattened)
                canvas.drawColor(0xFF1E1A17.toInt())
                canvas.drawBitmap(scaled, 0f, 0f, null)
                flattened
            } else {
                scaled
            }

            val out = ByteArrayOutputStream()
            if (!target.compress(Bitmap.CompressFormat.JPEG, 85, out)) return null
            out.toByteArray()
        } catch (_: Throwable) {
            null
        } finally {
            flattened?.takeIf { !it.isRecycled }?.recycle()
            if (scaled != null && scaled !== decoded && !scaled.isRecycled) {
                scaled.recycle()
            }
            decoded?.takeIf { !it.isRecycled }?.recycle()
        }
    }
}
