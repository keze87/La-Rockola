# Solo para releaseSmoke: AGP deduplica dependencias compartidas entre base.apk y androidTest.apk;
# estas clases son usadas por AndroidJUnitRunner / Kotlin en androidTest y no deben desaparecer por inlining de R8.
-keep class kotlin.** { *; }
-keep class androidx.tracing.** { *; }
