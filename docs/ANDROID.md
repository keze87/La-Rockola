# Guía de Arquitectura y Compilación Android — La Rockola del Carpincho

La edición Android empaqueta la interfaz **Vue 3 + TypeScript + Tailwind CSS**, el contenedor nativo **Capacitor 8**, los componentes nativos **Kotlin + Media3 ExoPlayer**, y el servidor **FastAPI + Uvicorn** corriendo sobre **Chaquopy 17.2.0 (Python 3.14)** con verificación estricta de alineamiento **16 KB (`0x4000`)**.

---

## 🏗️ Arquitectura Real (Host Local vs Cliente Remoto)

La app maneja dos modos explícitos desde un único store reactivo (`src/stores/useServerConnectionStore.ts`):

1. **Modo Host local (`serverMode = 'host'`)**:
    - Arranca el servicio `RockolaForegroundService` coordinado por `HostLifecycleCoordinator` y el servidor Python embebido (`app/android_entry.py`) con bloqueo de concurrencia contra instancias duplicadas.
    - Escucha en `0.0.0.0:1729` (por defecto) para que otros celulares en la misma red Wi-Fi se conecten escaneando el código QR o entrando por navegador.
    - Reproduce el audio localmente fuera del WebView mediante **Media3 ExoPlayer** (`AndroidAudioPlayer.kt`).
2. **Modo Cliente remoto (`serverMode = 'remote'`)**:
    - Se conecta a un servidor Rockola ya activo (por ejemplo, tu PC en `http://192.168.0.55:1729`) verificando `/health` antes de aplicar el cambio.
    - Resetea cola, pista actual, biblioteca, carátulas y WebSocket al cambiar de origen usando contadores de generación (`mediaTargetGeneration`) para descartar paquetes atrasados.
    - Enruta controles nativos de notificación, pantalla de bloqueo y **Picture-in-Picture (PiP)** mediante `MediaCommandClient.kt` directamente hacia el origen activo (`HOST` o `REMOTE`) con reporte explícito de errores HTTP, autenticación o timeouts hacia la UI.

---

## 🔋 Ciclo de Vida del Servicio y Políticas de Android

El servidor HTTP embebido y el servicio en primer plano **no** abusan de `FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK` ni del cupo `dataSync` cuando no corresponden:

- **Reproducción activa o síntesis radial**: El servicio se promueve a foreground (`mediaPlayback`) junto con la notificación MediaStyle, carátula, barra de progreso y `PARTIAL_WAKE_LOCK` (tope 4 h renovables). El `WifiLock` (`WIFI_MODE_FULL_LOW_LATENCY` o `WIFI_MODE_FULL_HIGH_PERF` en API < 29) solo se adquiere en modo Cliente Remoto, cuando hay clientes remotos conectados o durante reproducción/síntesis radial.
- **UI visible sin música ni clientes remotos (política Android 15 `dataSync`)**: Cuando la UI (`MainActivity`) está en primer plano pero no hay música sonando, síntesis radial ni clientes remotos conectados, el proceso ya cuenta con prioridad de primer plano por la Activity; **no** se levanta ni retiene un servicio foreground `dataSync` para no quemar el cupo acumulado de **6 horas / 24 horas** introducido en Android 15.
- **En pausa**: Soltamos `WakeLock`/`WifiLock` y bajamos del modo foreground tras el margen de transición (`DEMOTE_DEBOUNCE_MS = 30 s`, reteniendo si la radio está sintetizando entre temas), manteniendo la notificación descartable cuando corresponde.
- **Detenido / cambio de destino**: Desmontamos el modo foreground con `STOP_FOREGROUND_REMOVE` al apagar el servidor (`forceStop = true`) antes de cancelar la notificación.
- **Apagado acotado y `onDestroy`**: `stop_embedded_server()` señala `should_exit = True` en Uvicorn de inmediato (y `force_exit = True` en un segundo intento) y ejecuta `flush_pending_volume_persist()` + `save_playback_session(force=True)` coalesciendo snapshots y aislando generaciones (`_server_generation`) sin bloquear `HostLifecycleCoordinator`. El coordinador usa un `reaperExecutor` dedicado que ejecuta `Thread.join()` antes de limpiar `activeThread`/`activeStopHook` y diferencia explícitamente `StopHookOutcome` (`COMPLETED`, `FAILED`, `TIMED_OUT`, `REJECTED`, `NONE`); si el worker sigue vivo tras el presupuesto único de 4 s, pasa a `STOP_TIMED_OUT` con `hasActiveWorker = true` impidiendo arranques concurrentes hasta su terminación física. `DistAssetExtractor` extrae los assets web a un directorio temporal, valida `index.html`, JS, CSS y `manifest.webmanifest`, sella `.dist_stamp` después de validar y realiza reemplazo atómico con backup/rollback para no dejar una carpeta `dist/` truncada.
- **Cierre desde Recientes (`onTaskRemoved`) y hosting remoto**: Si no hay reproducción local ni clientes remotos activos (WebSockets no-loopback o streams HTTP `/stream` activos / dentro de 30 s de gracia), el servicio detiene el servidor y se cierra limpio. Si hay clientes remotos sin audio local en segundo plano, promueve con tipo `dataSync` (no `mediaPlayback`) y monitorea cada 15 s para apagar el servidor apenas se cierre el último cliente y venza la gracia.
- **Límite `dataSync` en Android 15 (`onTimeout`)**:
    - `foregroundServiceType="dataSync"` se usa **únicamente** cuando la app está en segundo plano con clientes remotos conectados sin reproducción local ni síntesis radial.
    - Al agotarse el cupo acumulado en Android 15+ (API 35+), el sistema retira el estado foreground e invoca `onTimeout(startId, fgsType)` exigiendo detener el servicio de inmediato. `RockolaForegroundService` **no** intenta migrar a `mediaPlayback` dentro de `onTimeout`: emite el evento `nativeCommandError` (`FGS_TIMEOUT`, buffereado si la UI no está escuchando para mostrar aviso claro cuando el usuario vuelva), desmonta locks, solicita apagar el servidor embebido en `processShutdownExecutor` y llama síncronamente a `stopSelf(startId)` para evitar `ForegroundServiceDidNotStopInTimeException`.
- **Permisos mínimos y contextuales**: Se eliminaron `READ_MEDIA_AUDIO`, `READ_EXTERNAL_STORAGE` y `FileProvider` (acceso 100% SAF), se desactivó `allowBackup` (`false`), se habilitó gesto atrás predictivo (`enableOnBackInvokedCallback="true"`), y `POST_NOTIFICATIONS` se solicita de forma contextual al elegir carpeta SAF o iniciar reproducción (no en el arranque en frío).

---

## 🔔 Contrato de Eventos Nativos, Volumen, Edge-to-Edge y Diagnóstico

### Eventos nativos por listeners (`RockolaServerPlugin` ↔ `useAndroidHost.ts`)

Se reemplazaron los hooks globales `window.__rockola*` (excepto el puente síncrono puntual `window.__rockolaHandleBack` invocado por `evaluateJavascript` al confirmar un atrás interceptado) por `notifyListeners` de Capacitor y `subscribeAndroidNativeEvents`:

- **Eventos de estado** (`mediaVolumeChanged`, `pipModeChanged`, `imeInsetsChanged`, `backProgress`):
    - No se bufferean en nativo si todavía no hay listener en JS.
    - Al suscribirse, `subscribeAndroidNativeEvents` consulta `RockolaServer.getUiRuntimeState()` (con fallback a `getMediaVolume()`) para hidratar el estado vigente de PiP, altura IME y volumen sin sobreescribir eventos en vivo más recientes.
- **Eventos de error o acción** (`nativeCommandError`, `shortcutAction`):
    - Usan `NativeEventBuffer` (cola FIFO acotada a `16` entradas por evento).
    - Si Kotlin emite un evento antes de que Vue llame a `addListener`, el evento queda retenido y se drena automáticamente en `RockolaServerPlugin.addListener` apenas se registra el primer listener.

### Política de volumen en Android (`STREAM_MUSIC`)

La decisión definitiva para Android es que **el volumen multimedia del dispositivo (`AudioManager.STREAM_MUSIC`) sea la única fuente de verdad siempre que el audio salga por el teléfono**, de modo que los botones físicos laterales y el slider de la app muevan exactamente el mismo control:

| Escenario                                                | Qué mueve el slider                                                                                                         | Qué hacen los botones físicos                                          | Ganancia interna de `ExoPlayer` / `<audio>` |
| :------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------- | :------------------------------------------ |
| **Android Servidor local (`HOST`)**                      | Ajusta `STREAM_MUSIC` (`setAndroidMediaVolume`) y sincroniza `set_volume` al backend (clientes LAN y `rockola_config.json`) | Ajustan `STREAM_MUSIC` y actualizan el slider vía `mediaVolumeChanged` | Fija en `1.0` (`0.0` solo al mutear)        |
| **Android Cliente con _Escuchar acá_ (`listenLocally`)** | Ajusta `STREAM_MUSIC` (`setAndroidMediaVolume`) sin pisar el volumen del servidor remoto                                    | Ajustan `STREAM_MUSIC` y actualizan el slider vía `mediaVolumeChanged` | Fija en `1.0` (`0.0` solo al mutear)        |
| **Android Cliente sin _Escuchar acá_ (control remoto)**  | Envía `set_volume` al servidor remoto                                                                                       | Ajustan `STREAM_MUSIC` local sin alterar el servidor remoto            | N/A (suena en el servidor)                  |
| **Escritorio (`mpv`) / Web LAN**                         | Envía `set_volume` al backend (`mpv`) o ajusta `<audio>.volume` en escucha local                                            | Control de volumen del sistema anfitrión                               | `0–100%` en `mpv` / `<audio>`               |

- **Sin doble atenuación**: `AndroidAudioPlayer` mantiene `ExoPlayer.volume` en `1.0f` (`0.0f` únicamente si `serverMuted` está activo) para que escalar `STREAM_MUSIC` no aplique una segunda reducción sobre la ganancia interna.
- **Rotulado en UI**: _Perillas_ muestra _"Volumen del dispositivo"_ cuando `isNativeAndroidHost() && (isHostMode || listenLocally)` y _"Volumen del reproductor"_ en los demás casos.
- **Botones físicos (`volumeControlStream = AudioManager.STREAM_MUSIC`)**: `MainActivity` fija `STREAM_MUSIC` para que subir/bajar volumen controle la música incluso sin audio sonando.
- **Observador multi-vía de cambios de volumen (`VolumeChangeTracker`)**: `RockolaServerPlugin` combina `BroadcastReceiver` (`android.media.VOLUME_CHANGED_ACTION`), `ContentObserver` sobre `Settings.System.CONTENT_URI`, relectura en `handleOnResume()` y polling liviano cada `1000 ms` **únicamente mientras la Activity está visible** (detenido en `handleOnPause()` y `handleOnDestroy()`), filtrando duplicados mediante `VolumeChangeTracker` para emitir `mediaVolumeChanged` solo ante cambios efectivos de nivel o mute.

### Edge-to-Edge, teclado (IME), PiP, MediaButton y Atajos

- **`enableEdgeToEdge` + `SystemBars`**: `MainActivity` configura barras transparentes oscuras con `enableEdgeToEdge(...)` y delega `--safe-area-inset-*` a `@capacitor/core` (`SystemBars` con `insetsHandling: 'css'` sobre `window.decorView`).
- **IME (`registerImeInsetsObserver`)**: Se adjunta sobre `android.R.id.content` (nunca sobre `window.decorView`) para no pisar el listener de `SystemBars`, exponiendo `--rockola-ime-height` y `html.ime-open` mientras `.floating-player` se oculta automáticamente con el teclado abierto.
- **Atrás predictivo y `BackProgressThrottler`**: `OnBackPressedCallback` inicia deshabilitado (`false`) y se habilita reactivamente con `hasClosableLayer`. `BackProgressThrottler` filtra micro-deltas (`< 0.02` y `< 16 ms`) pero **siempre** emite `0f` y `1f` para evitar que la animación `--rockola-back-progress` quede pegada al cancelar el gesto.
- **PiP y `MediaButtonReceiver`**: El modo Picture-in-Picture (1:1 con auto-enter en Android 12+ cuando el Fogón está activo) usa íconos propios en blanco (`ic_media_previous`, `ic_media_play`, `ic_media_pause`, `ic_media_next`). `androidx.media.session.MediaButtonReceiver` permanece `exported="true"`, mientras que `RockolaForegroundService` es `exported="false"` sin `<intent-filter>` redundante de `MEDIA_BUTTON`.
- **Atajos exclusivamente dinámicos (`ShortcutHelper`)**: Los accesos (`open_library`, `open_queue`, `open_tops`, `open_fogon` y `resume_last` cuando hay último tema) se actualizan en `shortcutExecutor` fuera del hilo principal. En arranque en frío, `ACTION_RESUME_LAST` cambia a la pestaña Ronda y difiere la reanudación (`pause()`) hasta que `localServerState === 'ready'`.

### Diagnóstico local sin telemetría (`LocalCrashDiagnostics`)

- Sin envío de datos a servidores externos:
    - **Último error no capturado**: Captura excepciones Kotlin (`UncaughtExceptionHandler` encadenado), errores fatales Python (`EmbeddedPythonHost.startBlocking`) y errores de JS/Vue (`logWebError`), guardándolos en `filesDir/rockola_last_error.log` acotado a `16 KB`.
    - **Historial de muerte de proceso (`ApplicationExitInfo`, API 30+)**: Al arrancar en hilo de fondo (`RockolaDiagnostics`), consulta `ActivityManager.getHistoricalProcessExitReasons`, traduce códigos (`ANR`, `LOW_MEMORY`, `CRASH`, `EXCESSIVE_RESOURCE_USAGE`, etc.), lo loguea bajo el tag `RockolaDiagnostics` y lo guarda en `filesDir/rockola_last_exit.log`.
    - **Consulta desde plugin**: `RockolaServer.getLastDiagnostics()` expone ambos snapshots bajo demanda.

---

## 🌐 Seguridad de Red (LAN), Precarga TTS y Permisos

- **Network Security Config (`network_security_config.xml`)**: Se reemplazó `usesCleartextTraffic="true"` global por una configuración explícita de `localhost` / `127.0.0.1` junto con `base-config` documentando que el modo Cliente Remoto se conecta por HTTP plano a IPs LAN privadas (`192.168.x.x`, `10.x.x.x`) que no admiten CIDR en `<domain-config>`.
- **Sin `addJavascriptInterface` ni acceso a archivos WebView**: El WebView no registra interfaces JS heredadas y mantiene `allowMixedContent: false` con `androidScheme: 'http'`.
- **Precarga TTS controlada**: En Android, `run_tts_preload` corta por tandas al alcanzar **333 MB** en `tts_cache.db` (podando por `last_used`). _(Nota: en la revisión actual, el arranque en segundo plano sigue activo automáticamente al iniciar en red no medida / Wi-Fi sin flag opt-in dedicado)._

---

## 📁 Almacenamiento SAF Real (Memoria Interna y MicroSD)

La aplicación **no solicita** `MANAGE_EXTERNAL_STORAGE` y **no copia** tu biblioteca musical al almacenamiento privado de la app:

- **Selector nativo (`ACTION_OPEN_DOCUMENT_TREE`)**: Persistimos permisos de lectura sobre el árbol SAF elegido (`takePersistableUriPermission`).
- **Instalación limpia**: En instalaciones nuevas donde ninguna carpeta estándar de Android sea legible, `music_dir` inicia vacío (`""`, `music_dir_configured = false`) y se pide elegir carpeta explícitamente.
- **Acceso directo por file descriptor y escaneo paginado multi-árbol**: `AndroidStorageBridge.kt` enumera pistas en tandas paginadas vía `DocumentsContract` con aislamiento completo entre múltiples raíces/bibliotecas SAF en cachés acotados (`parentCache`, `dirLyricsCache`) y limpieza sincronizada bajo TTL e inactividad sin eliminar sesiones mientras un batch está en vuelo. Entrega descriptores nativos (`detachFd`) a `app/infrastructure/storage/backend.py` (`AndroidSafStorageBackend` + `os.fdopen(fd, "rb")`) para leer tags con Mutagen, calcular `smart_hash` resistente a lecturas parciales (`_read_exact`), calcular `audio_hash` (soportando `.flac`, `.mp3`, `.wav`/`.ogg`/`.opus` y `.m4a` sin tracks `vide`, devolviendo `None` explícitamente en `.mp4` u otros contenedores de video), transmitir con HTTP `206 Partial Content` verificando el tamaño real de descriptores seekables, corte explícito ante EOF prematuro y cierre idempotente vía `BackgroundTask`.
- **Limitaciones conocidas**:
    - Si revocás permisos o expulsás la tarjeta MicroSD, el sistema reporta estados explícitos (`permission_denied`, `storage_unavailable`, `unsupported_provider`) con acción directa para reelegir carpeta.
    - Al ser la biblioteca SAF de solo lectura en Android, la edición de letras se deshabilita en la interfaz y `POST /api/v1/lyrics/save` devuelve HTTP 400 explicando la restricción.

---

## ⚙️ Requisitos, ABIs, Alineamiento 16 KB, Variantes y CI/CD

### Requisitos de compilación

- **Node.js 22+** y **npm**
- **Java JDK 21** (`JAVA_HOME=/usr/lib/jvm/java-21-openjdk` en Linux si tu `java` por defecto no trae `javac`)
- **Android SDK** (`ANDROID_HOME` o `android/local.properties` con `compileSdk 36`, `minSdk 24`)
- **Python 3.14** disponible para `buildPython` de Chaquopy `17.2.0`

### Variantes (`debug`, `release`, `releaseSmoke`) y convivencia

- **`debug`**: Usa `applicationIdSuffix ".debug"` (`ar.carpincho.rockola.debug`), nombre _"La Rockola (Debug)"_, habilita `StrictMode` (detección de disco/red en main thread con `penaltyLog()`) y `WebView.setWebContentsDebuggingEnabled(true)`. Puede convivir instalada junto a la versión `release` (`ar.carpincho.rockola`) sin colisión de preferencias ni autoridades.
- **`release`**: `minifyEnabled true`, `shrinkResources true`, firma obligatoria (`keystore.properties` o variables `ROCKOLA_KEYSTORE_*`), reglas R8 acotadas en `android/app/proguard-rules.pro` (7 clases propias de puente/Android).
- **`releaseSmoke`**: Hereda de `release` con R8 activo para `connected*ReleaseSmokeAndroidTest`, usando `proguard-releasesmoke.pro` y `proguard-androidtest.pro` exclusivamente para el runner de instrumentación (`kotlin.**`, `androidx.tracing.**`, `-dontobfuscate`) sin alterar `proguard-rules.pro` de producción.

### ABIs, verificación 16 KB y Workflow de Release

- **Arquitecturas y versionado monotónico**: `arm64` (`arm64-v8a`) y `x86_64` con `versionCode` monotónico por minuto en UTC multiplicado por ABI (`base * 10 + 1` y `base * 10 + 2`).
- **Verificador automático (`scripts/verify_android_apk.py`)**: Audita cada `.so` dentro de `lib/` validando `PT_LOAD p_align >= 0x4000`, congruencia `p_offset % p_align == p_vaddr % p_align`, ausencia de `RUNPATH/RPATH` apuntando a `com.termux`, `zipalign -c -P 16 -v 4` en APK y `PAGE_ALIGNMENT_16K` vía `bundletool` en AAB (`--strict-aab`).
- **Workflow de Release (`.github/workflows/release.yml`)**: Separado en jobs independientes de compilación (`build-windows`, `build-linux-appimage`, `build-android`) y jobs de publicación desacoplados (`publish-desktop-release` y `publish-android-release`) que adjuntan cada artefacto con verificación SHA-256 previa.

### Comandos principales

```bash
# Compilar frontend + sincronizar assets + APK arm64 Debug + verificar ELFs 16 KB + .sha256
python3 scripts/build_android.py --flavor arm64

# Compilar APK o AAB Release firmado (y verificado 16 KB + .sha256)
python3 scripts/build_android.py --flavor arm64 --release
python3 scripts/build_android.py --flavor arm64 --release --bundle

# Correr pruebas unitarias JVM de Kotlin y smoke test R8 en dispositivo/emulador
JAVA_HOME=/usr/lib/jvm/java-21-openjdk ./android/gradlew -p android testArm64DebugUnitTest
JAVA_HOME=/usr/lib/jvm/java-21-openjdk ./android/gradlew -p android -PROCKOLA_TEST_BUILD_TYPE=releaseSmoke connectedArm64ReleaseSmokeAndroidTest --no-daemon

# E2E en dispositivo real (acepta --package ar.carpincho.rockola.debug)
python3 scripts/test_android_e2e.py --if-available
```

---

## 📊 Matriz de Soporte de Funcionalidades

| Funcionalidad                                                   |   Escritorio (Linux/Win)    |                            Android Host Local                             |         Android Cliente Remoto         |               PWA Navegador               |
| :-------------------------------------------------------------- | :-------------------------: | :-----------------------------------------------------------------------: | :------------------------------------: | :---------------------------------------: |
| Reproducción nativa de servidor                                 |         Sí (`mpv`)          |                             Sí (`ExoPlayer`)                              |       Controla servidor destino        |           Controla / Web Audio            |
| Stream local en navegador (`Escuchar acá`)                      |             Sí              |                         No aplica (usa ExoPlayer)                         |         Sí (`Range` streaming)         |                    Sí                     |
| Acceso a carpetas / MicroSD                                     |        POSIX directo        |                        SAF `content://` sin copia                         |        Biblioteca del servidor         |          Biblioteca del servidor          |
| Controles en notificación / Pantalla bloqueo / PiP              |        MPRIS (Linux)        |                      MediaSession + MediaStyle + PiP                      | MediaSession + PiP hacia origen remoto |           Media Session API web           |
| Locutor radial Carpincho (`edge-tts`)                           |             Sí              |                           Sí (online para TTS)                            |       Controla servidor destino        |         Controla servidor destino         |
| Mezcla de cortina musical radial y análisis BPM/Mood (`ffmpeg`) |             Sí              |        Degrada elegante (oculta Mood; tags BPM ID3 siguen activos)        |   Según capacidades del host remoto    |        Según capacidades del host         |
| Huella acústica (`fpcalc`)                                      |             Sí              |                      No disponible (usa smart-hash)                       |   Según capacidades del host remoto    |                    N/A                    |
| Editor de letras `.ass` / `.lrc`                                | Lectura y guardado en disco | Lectura SAF + consulta online (guardado bloqueado si SAF es solo lectura) | Lectura y guardado en servidor destino |  Lectura y guardado en servidor destino   |
| Desconexión offline (Service Worker)                            |             N/A             |                    Desactivado (assets locales en APK)                    |  Desactivado (assets locales en APK)   | Caché `rockola-shell-v2` + fallback `503` |

---

## 📱 Experiencia Nativa, Métricas Comparables y Resolución de Problemas

### Decisiones técnicas vigentes

- **Splash único sin doble pantalla (`SplashHoldPolicy`)**: `MainActivity` retiene el splash del sistema con `setKeepOnScreenCondition` hasta que Vue dispara `markUiReady()` desde `src/main.ts` apenas pinta el primer frame (tope de seguridad reducido a `1200 ms`, bajado desde `2500 ms`), y dispara `reportFullyDrawn()` al renderizar el primer contenido útil (snapshot hidratado, biblioteca u onboarding). La prioridad del hilo `RockolaPythonWarmup` se bajó a `Thread.MIN_PRIORITY` para evitar contención con el WebView en el arranque en frío.
- **Snapshot local (`useLocalSnapshot.ts`)**: Guarda hasta `80` temas, cola, favoritos y pista actual en `localStorage` para hidratar la interfaz antes de que Python responda `/health`.
- **Versión mínima de WebView (`WebViewVersionPolicy`)**: Piso **Chromium 108**; si es menor, muestra diálogo nativo oscuro con enlace a la tienda (fail-open si el proveedor no informa versión).
- **Tema nativo solo oscuro**: `AppTheme` con `AppCompatDelegate.setDefaultNightMode(MODE_NIGHT_YES)` y `color-scheme: dark`.

### Métricas medidas (Release R8 vs Release R8 — Mediana de 5 corridas en frío)

Dispositivo de prueba: **Samsung Galaxy A72 (`SM-A725M`, Android 14 / SDK 34)**, build `arm64-release` con R8 activo y la misma firma de release (`android/keystore.properties`), `am force-stop ar.carpincho.rockola` antes de cada corrida (25/11/2026).

| Métrica (Release R8, mediana de 5 corridas)            |            Antes (Baseline Release R8)             |                  Después (Candidato 1.0 Release R8)                  | Notas                                                                                                                                         |
| :----------------------------------------------------- | :------------------------------------------------: | :------------------------------------------------------------------: | :-------------------------------------------------------------------------------------------------------------------------------------------- |
| `WaitTime` cold start (`am start -W`)                  | **1283 ms** (1250 / 1283 / 1291 / 1302 / **1277**) |   **1284 ms** (1290 / 1206 / 1338 / **1284** / 1052 — mín 1052 ms)   | La cifra previa de `3020 ms` provenía de un build `arm64-debug` sin R8. En release R8 el arranque se mantiene estable en el piso del WebView. |
| `TotalTime` cold start (`am start -W`)                 | **1271 ms** (1244 / 1258 / 1275 / 1284 / **1271**) |          **1267 ms** (1281 / 1168 / 1317 / **1267** / 1042)          | Dentro de la variación natural (~4 ms); sin regresión frente al baseline release.                                                             |
| Retiro del splash (`RockolaStartup` `splash_released`) |                  No instrumentado                  | **795 ms** (`uiReady=true`, `activityElapsedMs=772 ms` en corrida 5) | Confirmado: el splash sale por `markUiReady()` antes del tope de `1200 ms`, no por timeout.                                                   |
| `Fully drawn` del sistema (`reportFullyDrawn()`)       |                  No instrumentado                  |           **+1049 ms** (`reason=snapshot` a los `784 ms`)            | Medido nativamente por `ActivityTaskManager` al pintar contenido útil.                                                                        |
| Tiempo hasta `Uvicorn running` (`python.stderr`)       | **3671 ms** (3392 / **3671** / 3608 / 3904 / 3713) |          **3888 ms** (3888 / 3866 / 3959 / **3888** / 3307)          | Warmup de Python en `MIN_PRIORITY` prioriza el primer frame del WebView (~1 s) antes de levantar el servidor en paralelo.                     |

_(Desglose completo de corrida 5 en `RockolaStartup`: `app_on_create=0 ms` → `activity_on_create=23 ms` → `index_html_loaded=783 ms` (`jsNowMs=227`) → `vue_mounted=783 ms` (`jsNowMs=480`) → `fully_drawn=784 ms` → `mark_ui_ready_received=784 ms` → `splash_released=795 ms` → `Displayed=+1042 ms` → `Uvicorn=3011 ms`.)_

### Limitaciones conocidas

1. **Android 15/16 (`dataSync` 6 h/24 h)**: En Android 15+, si la app queda en segundo plano sirviendo a clientes remotos sin reproducir música local durante más de 6 horas acumuladas en 24 horas, el sistema invoca `onTimeout` y detiene el servidor embebido (`FGS_TIMEOUT`).
2. **Almacenamiento SAF solo lectura**: La edición/guardado de archivos `.ass`/`.lrc` locales desde Android está bloqueada por diseño; requiere editarlos desde escritorio o servidor remoto.
3. **Sin `ffmpeg` ni `fpcalc` nativos en Android**: El análisis acústico de estado de ánimo (_Más Manija_), la mezcla de cortina radial con `ffmpeg` y las huellas acústicas `fpcalc` se ocultan/degradan elegante (las etiquetas ID3 BPM siguen activas).
4. **Precarga TTS en segundo plano**: Aún no cuenta con toggle opt-in exclusivo en ajustes Android (corre acotada a 333 MB).
5. **Verificación `bundletool` en host sin herramienta**: El script `verify_android_apk.py` audita los 74 `.so` del `.aab` correctamente, pero la auditoría estricta de `BundleConfig.pb` (`PAGE_ALIGNMENT_16K`) requiere `bundletool` instalado en el entorno (disponible en CI / con `bundletool` en PATH).

### Solución de problemas

- **Permiso SAF revocado o tarjeta MicroSD desconectada**: La app muestra `permission_denied` / `storage_unavailable` con acceso directo a reelegir carpeta. Tocá **"Elegir carpeta de música"** en el banner o en _Perillas_ para renovar el `takePersistableUriPermission`.
- **Android detuvo el servidor en segundo plano (`FGS_TIMEOUT` o ahorro de batería)**: En fabricantes agresivos (Samsung One UI, Xiaomi MIUI, Realme/Oppo), si el sistema mata el proceso con pantalla apagada sin música, abrí _Ajustes del sistema → Aplicaciones → La Rockola del Carpincho → Batería → Sin restricciones_ (y verificá que esté reproduciendo música o con clientes conectados si la pantalla está apagada). Al volver a abrir la app, `ensureLocalAndroidServerAlive` reintenta levantar el servidor local automáticamente.
- **Aviso de Android System WebView antiguo**: Si ves el diálogo de versión `< 108`, actualizá _Android System WebView_ (o _Google Chrome_ en Android 7–9) desde Play Store para soportar `100dvh`, `content-visibility` y `:has()`.
- **Botones de volumen no sincronizan en algún dispositivo**: Si un fabricante bloquea `VOLUME_CHANGED_ACTION`, la UI relee el volumen multimedia cada 1 s mientras está visible y al volver a primer plano; en última instancia ajustá desde el slider _"Volumen del dispositivo"_ en _Perillas_ o Modo Fogón.
- **Obtener diagnóstico tras un fallo sin telemetría**: Los últimos errores no capturados (Kotlin, Python y WebView) y la razón de muerte anterior (`ApplicationExitInfo` en Android 11+) quedan guardados localmente en `filesDir/rockola_last_error.log` y `filesDir/rockola_last_exit.log` (visibles vía `RockolaServer.getLastDiagnostics()` o `adb logcat -s RockolaDiagnostics RockolaWebError`).
