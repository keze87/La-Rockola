# Reglas ProGuard/R8 para La Rockola del Carpincho (Capacitor + Chaquopy + MediaCompat)

# Capacitor y plugins propios registrados por reflexión
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod
-keep class com.getcapacitor.** { *; }
-keepclassmembers class * extends com.getcapacitor.Plugin {
    @com.getcapacitor.PluginMethod public *;
    @com.getcapacitor.annotation.ActivityCallback *;
    @com.getcapacitor.annotation.PermissionCallback *;
}
-keep class ar.carpincho.rockola.** { *; }

# Chaquopy JVM <-> Python puente nativo y JNI
-keep class com.chaquo.python.** { *; }
-dontwarn com.chaquo.python.**

# AndroidX MediaSession / MediaStyle
-keep class androidx.media.** { *; }
-keep class android.support.v4.media.** { *; }
