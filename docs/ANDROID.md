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

El servidor HTTP embebido y el servicio en primer plano **no** abusan de `FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK` cuando no hay música sonando:

- **Reproducción activa**: El servicio se promueve a foreground (`mediaPlayback`) junto con la notificación MediaStyle, carátula, barra de progreso y `PARTIAL_WAKE_LOCK` (tope 4 h renovables). El `WifiLock` (`WIFI_MODE_FULL_LOW_LATENCY` o `WIFI_MODE_FULL_HIGH_PERF` en API < 29) solo se adquiere en modo Cliente Remoto o cuando hay clientes remotos conectados.
- **En pausa**: Soltamos `WakeLock`/`WifiLock` para ahorrar batería, manteniendo el servicio en foreground mientras el servidor local siga activo (`isRunning`) para evitar que Android 12+ revoque `mAllowStartForeground` con la pantalla apagada.
- **Detenido / cambio de destino**: Desmontamos el modo foreground con `STOP_FOREGROUND_REMOVE` al apagar el servidor (`forceStop = true`) antes de cancelar la notificación.
- **Apagado acotado y `onDestroy`**: `stop_embedded_server()` señala `should_exit = True` en Uvicorn de inmediato (y `force_exit = True` en un segundo intento) y ejecuta `flush_pending_volume_persist()` + `save_playback_session(force=True)` coalesciendo snapshots y aislando generaciones (`_server_generation`) sin bloquear `HostLifecycleCoordinator`. El coordinador usa un `reaperExecutor` dedicado que ejecuta `Thread.join()` antes de limpiar `activeThread`/`activeStopHook` y diferencia explícitamente `StopHookOutcome` (`COMPLETED`, `FAILED`, `TIMED_OUT`, `REJECTED`, `NONE`); si el worker sigue vivo tras el presupuesto único de 4 s, pasa a `STOP_TIMED_OUT` con `hasActiveWorker = true` impidiendo arranques concurrentes hasta su terminación física. `DistAssetExtractor` extrae los assets web a un directorio temporal, valida `index.html`, JS, CSS y `manifest.webmanifest`, sella `.dist_stamp` después de validar y realiza reemplazo atómico con backup/rollback para no dejar una carpeta `dist/` truncada.
- **Cierre desde Recientes (`onTaskRemoved`) y hosting remoto**: Si no hay reproducción local ni clientes remotos activos (WebSockets no-loopback o streams HTTP `/stream` activos / dentro de 30 s de gracia), el servicio detiene el servidor y se cierra limpio. Si hay clientes remotos sin audio local, promueve temporalmente con tipo `dataSync` (no `mediaPlayback`) y monitorea cada 15 s para apagar el servidor apenas se cierre el último cliente y venza la gracia.
- **Servidor embebido sin reproducción y límite `dataSync` en Android 15 (`onTimeout`)**:
    - Cuando no hay música sonando ni clientes remotos conectados y el usuario cierra la app desde Recientes, el servidor embebido se apaga de inmediato. Si la app sigue en primer plano (o en pausa con el servidor corriendo), no se mantiene un lock de CPU activo.
    - Solo se utiliza `foregroundServiceType="dataSync"` cuando la app fue quitada de Recientes pero quedan clientes remotos conectados sin reproducción local. En **Android 15+ (API 35+)**, `dataSync` tiene un cupo acumulado de 6 horas cada 24 horas en segundo plano; `RockolaForegroundService` implementa `onTimeout(startId, fgsType)` (y `onTimeout(startId)`): si justo está sonando música local (`isMediaPlaying == true`), migra inmediatamente el tipo foreground a `mediaPlayback`; si no hay reproducción local, notifica a la UI (`FGS_TIMEOUT`), detiene el servidor embebido limpiamente y llama a `stopSelf(startId)` para evitar `ForegroundServiceDidNotStopInTimeException`.
- **Permisos mínimos y contextuales**: Se eliminaron `READ_MEDIA_AUDIO`, `READ_EXTERNAL_STORAGE` y `FileProvider` (acceso 100% SAF), se desactivó `allowBackup` (`false`), se habilitó gesto atrás predictivo (`enableOnBackInvokedCallback="true"`), y `POST_NOTIFICATIONS` se solicita de forma contextual al iniciar el servidor local (no en el arranque en frío).

---

## 🌐 Seguridad de Red (LAN), Precarga TTS y Permisos

- **Network Security Config (`network_security_config.xml`)**: Se reemplazó `usesCleartextTraffic="true"` global por una configuración explícita de `localhost` / `127.0.0.1` junto con `base-config` documentando que el modo Cliente Remoto se conecta por HTTP plano a IPs LAN privadas (`192.168.x.x`, `10.x.x.x`) que no admiten CIDR en `<domain-config>`.
- **Permisos mínimos y backup**: Se eliminaron `READ_MEDIA_AUDIO`, `READ_EXTERNAL_STORAGE` y `FileProvider` (acceso 100% SAF), y se desactivó `allowBackup` (`false`) con gesto atrás predictivo (`enableOnBackInvokedCallback="true"`).
- **Precarga TTS controlada**: En Android, `run_tts_preload` arranca automáticamente en segundo plano **solo en Wi-Fi / Ethernet no medida** (`ConnectivityManager` + `NET_CAPABILITY_NOT_METERED`) y corta por tandas al alcanzar **333 MB** en `tts_cache.db` (podando por `last_used`).
- **Volumen del reproductor (`ExoPlayer.volume`)**: El control de volumen de La Rockola ajusta la ganancia propia de `ExoPlayer` (`0.0`–`1.0`, conservando el nivel al mutear/desmutear) sin alterar el volumen multimedia global del dispositivo, manteniendo consistencia con escritorio (`mpv`) y modo remoto.

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

## ⚙️ Requisitos, ABIs, Alineamiento 16 KB y Firma Release

### Requisitos de compilación

- **Node.js 22+** y **npm**
- **Java JDK 21** (`JAVA_HOME=/usr/lib/jvm/java-21-openjdk` en Linux si tu `java` por defecto no trae `javac`)
- **Android SDK** (`ANDROID_HOME` o `android/local.properties` con `compileSdk 36`, `minSdk 24`)
- **Python 3.14** disponible para `buildPython` de Chaquopy `17.2.0`

### ABIs y verificación binaria de 16 KB (`0x4000`)

- **Arquitecturas y versionado monotónico**: `arm64` (`arm64-v8a`) y `x86_64` con `versionCode` monotónico por minuto en UTC (`(año - 2020) * 1000000 + día_año * 1440 + min_día`, o `ROCKOLA_VERSION_CODE`) multiplicado por ABI (`base * 10 + 1` y `base * 10 + 2`). Se removió `armv7` (32 bits) ya que el stack `cp314` (Python 3.14) de Play exige 64-bit y 16 KB.
- **Decisión Python 3.14 + wheels nativos sin reetiquetado Linux**: Se adoptó **Python 3.14** sobre **Chaquopy 17.2.0** para contar con wheels `cp314` compilados nativamente con alineamiento 16 KB (`pydantic==2.14.3`, `pydantic-core==2.50.4`, `aiohttp==3.14.5`, `frozenlist==1.8.0`, `multidict==7.2.1`, `yarl==1.25.1`) desde `https://pypi.flet.dev` / PyPI sin reetiquetado manual, eliminando `pillow`/`libfreetype.so` mediante `AndroidImageResizer.kt` (`BitmapFactory`).
- **Pines estrictos sin `--require-hashes` en Chaquopy**: Todas las dependencias Python en `android/app/build.gradle` están fijadas con `==`. No se habilita `--require-hashes` porque `chaquopy-pip` resuelve wheels específicos por ABI (`arm64-v8a` / `x86_64`) entre PyPI y `--extra-index-url https://pypi.flet.dev` con dependencias transitivas cuyo conjunto de hashes difiere por arquitectura/plataforma.
- **Verificador automático (`scripts/verify_android_apk.py`)**: Audita cada `.so` dentro de `lib/` y archivos comprimidos `.imy`/`.zip` (rechazando ZIPs corruptos), validando `PT_LOAD p_align >= 0x4000`, potencia de 2, congruencia `p_offset % p_align == p_vaddr % p_align`, límites de archivo y ausencia de `RUNPATH/RPATH` apuntando a `com.termux`. En APKs valida también `zipalign -c -P 16 -v 4` cuando está disponible en el SDK; en AABs verifica `BundleConfig.pb` y `PAGE_ALIGNMENT_16K` vía `bundletool dump config` (`--strict-aab`).

### Firma obligatoria en Release

Los builds **Release fallan explícitamente** si falta firma (nunca caen silenciosamente en `signingConfigs.debug`). Podés configurarla de dos formas:

1. Archivo local `android/keystore.properties` (ignorado por Git):
    ```properties
    storeFile=/ruta/absoluta/a/tu-keystore.jks
    storePassword=...
    keyAlias=rockola
    keyPassword=...
    ```
2. Variables de entorno (CI/CD):
   `ROCKOLA_KEYSTORE_PATH`, `ROCKOLA_KEYSTORE_PASSWORD`, `ROCKOLA_KEY_ALIAS`, `ROCKOLA_KEY_PASSWORD`.

### Comandos principales

```bash
# Compilar frontend + sincronizar assets + APK arm64 Debug + verificar ELFs 16 KB + .sha256
python3 scripts/build_android.py --flavor arm64

# Compilar APK o AAB Release firmado (y verificado 16 KB + .sha256)
python3 scripts/build_android.py --flavor arm64 --release
python3 scripts/build_android.py --flavor arm64 --release --bundle

# Correr pruebas unitarias JVM de Kotlin y compilación de test instrumentado
./android/gradlew -p android testArm64DebugUnitTest compileArm64DebugAndroidTestKotlin
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

## 📱 Experiencia Nativa (Decisiones, Métricas y Checklist)

### Decisiones técnicas

- **Splash único sin doble pantalla (`SplashHoldPolicy`)**: `MainActivity` retiene el splash del sistema con `setKeepOnScreenCondition` hasta que Vue dispara `markUiReady()` (tope de seguridad de `2500 ms`), usando un ícono vectorial dedicado (`ic_splash_carpincho.xml` sobre `288 dp` en zona segura de 2/3) y el color `@color/rockola_bg` unificado. El placeholder HTML `#web-boot-splash` de `index.html` se oculta automáticamente en Capacitor y queda solo para PWA/web.
- **Snapshot local, precalentamiento Python e imports diferidos**:
    - `useLocalSnapshot.ts` guarda hasta `80` temas, cola, favoritos y pista actual en `localStorage` para hidratar la interfaz antes de que Python responda `/health`, mostrando `"Actualizando lista..."`.
    - `RockolaApplication` precalienta `Python.start(AndroidPlatform(...))` en segundo plano al crear el proceso (`onCreate`), y `EmbeddedPythonHost` expone progreso real de extracción (`extractStage` / `extractProgress`).
    - `tts_cache.py` y `radio/service.py` difieren la importación de `edge_tts` (y su árbol `aiohttp`) hasta la primera síntesis TTS (`importlib.util.find_spec` para `HAS_EDGE_TTS`).
- **Versión mínima de WebView (`WebViewVersionPolicy`)**: El frontend usa `100dvh`, `content-visibility` y `:has()`, cuyo piso real es **Chromium 108**. Si `WebViewCompat.getCurrentWebViewPackage` reporta una versión mayor `< 108`, `MainActivity` muestra un diálogo nativo oscuro con enlace directo a Play Store; si el proveedor no informa versión, aplica política fail-open.
- **Atrás predictivo real (`BackNavigationPolicy`)**: El `OnBackPressedCallback` nativo inicia deshabilitado (`false`) y Vue empuja `setBackHandlerEnabled(hasClosableLayer)` reactivamente según haya foco en un input (lo desenfoca), modales/`<dialog>` abiertos, menú contextual, editor de letras, Modo Fogón o pestaña distinta de Biblioteca. Cuando no hay capas cerrables, el callback queda deshabilitado para que Android ejecute su animación predictiva nativa de volver al inicio. Además `handleOnBackProgressed` expone `--rockola-back-progress` a JS.
- **Teclado (IME) con edge-to-edge**: `MainActivity` declara `android:windowSoftInputMode="adjustResize"` y escucha `WindowInsetsCompat.Type.ime()` vía `ViewCompat.setOnApplyWindowInsetsListener` para empujar `--rockola-ime-height` y `html.ime-open` al CSS (una única vía explícita). Cuando el teclado está abierto se oculta `.floating-player` y se suma `--rockola-ime-height` al padding inferior de listados y modales.
- **Evaluación de Media3 `MediaSession` (decisión: mantener `MediaSessionCompat` endurecido)**: Como el origen activo de reproducción puede alternar en caliente entre Host local (`ExoPlayer`) y Cliente Remoto (`HTTP/WS` hacia otro dispositivo), exponer un `Player` fachada (`SimpleBasePlayer`) que emule toda la máquina de estados remota duplicaría lógica ya resuelta en Python/JS sin beneficio inmediato para Android Auto/Wear. Se mantuvo `MediaSessionCompat` endurecido con `setSessionActivity` hacia `MainActivity`, `MediaSessionPolicy.computePlaybackActions` (habilitando `ACTION_SEEK_TO` solo con duración positiva) y `HeadsetDoubleTapDetector` (1 toque = play/pausa, doble toque <= 350 ms = siguiente).
- **Permiso de notificaciones contextual**: Se quitó `requestNotificationPermissionIfNeeded()` de `startServer()`. El permiso se solicita con explicación previa al terminar de elegir la carpeta SAF o al iniciar la primera reproducción; si se deniega, la app sigue operando normal y `ControlsTab` ofrece acceso directo a `Settings.ACTION_APP_NOTIFICATION_SETTINGS`.
- **Háptica semántica (`HapticPolicy`)**: Se eliminó `Vibrator` y el permiso `VIBRATE` del manifest. `RockolaServerPlugin.hapticFeedback` invoca `webView.performHapticFeedback(constant)` **sin** `FLAG_IGNORE_VIEW_SETTING`/`FLAG_IGNORE_GLOBAL_SETTING`, mapeando acciones semánticas (`tap`, `long_press`, `confirm`, `reject`, `gesture_start`, `gesture_end`, `toggle_on`, `toggle_off`, `tick`) al nivel de API correspondiente (24 / 30 / 34).
- **Accesos directos dinámicos e intents externos**: `ShortcutHelper` usa `ShortcutManagerCompat` para publicar dinámicamente los 4 accesos base (`open_library`, `open_queue`, `open_tops`, `open_fogon`) y suma `resume_last` (`ACTION_RESUME_LAST`) al haber último tema conocido. Se **descarta** soportar `ACTION_VIEW`/`ACTION_SEND` de audio/URLs externas porque la biblioteca Android opera exclusivamente sobre árbol SAF de solo lectura y la jukebox colaborativa en red local centraliza la cola en el servidor.
- **Tema nativo solo oscuro**: `AppTheme` hereda de `Theme.AppCompat.DayNight.NoActionBar` con `AppCompatDelegate.setDefaultNightMode(MODE_NIGHT_YES)` y `color-scheme: dark` en CSS. Se decidió soportar **solo modo oscuro** (sin modo claro ni color dinámico Material You) para preservar la estética cálida nocturna de La Rockola y el contraste de portadas/letras.
- **Navegación adaptativa y pantallas grandes**: En teléfonos (`< 768 px`) las pestañas pasan a una barra inferior estilo Material 3 con etiquetas siempre visibles y `FloatingPlayer` encima; desde `768 px` (`md`) pasan a un riel lateral izquierdo; y desde `1024 px` (`lg`) se activa vista de dos paneles cuando está abierta Biblioteca o Clásicos (panel principal + `QueueTab` lateral). Targets táctiles elevados a `48 px` en `pointer: coarse`, `:focus-visible` de alto contraste y atajos de teclado (`/` para buscar, `MediaPlayPause`, `MediaTrackNext`, `MediaTrackPrevious`).
- **Higiene de release**: `capacitor.config.ts` fija `allowMixedContent: false` manteniendo `androidScheme: 'http'` para que los servidores remotos LAN (`http://192.168.x.x`) sigan siendo HTTP→HTTP sin bloqueo de contenido mixto. `WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)` queda restringido a builds debug; producción elimina `console.log`/`console.debug`/`debugger` y errores no capturados del WebView se registran en logcat bajo el tag `RockolaWebError`.

### Métricas medidas (Antes / Después)

Dispositivo de prueba: **Samsung Galaxy A72 (`SM-A725M`, Android 14 / SDK 34)** con `adb shell am start -W` (3 corridas cold start con `am force-stop`, tomando mediana) y perfilado Python en host Linux x86_64 (`python3 -X importtime -c "import app.main"`).

| Métrica                                                            |           Antes (Baseline)            |                Después (Post-cambios)                | Notas                                                                                                                                                         |
| :----------------------------------------------------------------- | :-----------------------------------: | :--------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `WaitTime` cold start (`am start -W`, mediana 3 corridas)          |     **974 ms** (970 / 878 / 986)      |           **3020 ms** (3036 / 3019 / 3020)           | Subida esperada: `setKeepOnScreenCondition` retiene el splash nativo (~2,5 s) hasta el primer frame útil de Vue en lugar de soltarlo vacío antes del montaje. |
| Primer contenido útil visible (sin pantalla HTML "Prendiendo...")  | > 5226 ms (tras Uvicorn + `/library`) | **~3020 ms** (al caer el splash, con snapshot local) | Eliminado el salto visual del splash web; la lista/cola del snapshot aparece inmediata marcada como `"Actualizando lista..."`.                                |
| Tiempo hasta `Uvicorn running` en dispositivo (mediana 3 corridas) |   **5226 ms** (5412 / 5093 / 5226)    |           **6429 ms** (7457 / 6429 / 6375)           | Baseline medido sobre el APK previo instalado (otra firma) vs build `arm64-debug` sin R8 y con contención inicial de hilos entre warmup Python y WebView.     |
| `python3 -X importtime -c "import app.main"` (host Linux)          |             **337.1 ms**              |                 **283.3 ms** (-16%)                  | `edge_tts` y `aiohttp` diferidos fuera del arranque inicial.                                                                                                  |

### Falsos positivos verificados

1. **Ítem 2 (Precarga TTS por tandas y `--max-mb`)**: Ya estaba implementado y cubierto por tests (`app/domain/radio/preload.py` corta por tandas en `_get_cache_size_bytes >= max_bytes`, `scripts/preload_tts_cache.py` expone `--max-mb`, verificado con `pytest tests/test_tts_preload.py` — 9 passed).
2. **Ítem 15 (Íconos y fuentes sin red)**: `src/assets/fonts/fonts.css` ya empaqueta localmente `material-icons.woff2` con `font-display: block`, `Nunito` y `Noto Color Emoji` sin peticiones a Google Fonts (`grep` sobre `fonts.googleapis`/`fonts.gstatic` dio 0 coincidencias).
3. **Ítem 14 (parcial — Tailwind `hover:` en táctil)**: Tailwind CSS v4 (`4.3.3`) ya envuelve `hover:` dentro de `@media (hover: hover)` en el bundle CSS compilado.
4. **Ítem 13 (parcial — `<meta name="color-scheme">`)**: `index.html` ya declaraba `<meta name="color-scheme" content="dark" />`; faltaba `color-scheme: dark` en CSS y migrar `AppTheme` desde `Theme.AppCompat.Light.DarkActionBar`.

### Checklist manual en dispositivo real (Android 14, 15 y 16)

- [ ] Arranque en frío y en caliente: una sola transición continua desde el ícono sin parpadeo blanco ni pantalla HTML web.
- [ ] Gesto/botón atrás desde cada pestaña, menú contextual, modales (`WeatherLocationModal`, servidor remoto), editor de letras y Modo Fogón; verificar animación predictiva "volver a inicio" al estar en Biblioteca (Android 14+/15/16 con navegación por gestos y botones).
- [ ] Teclado (IME) en buscador de biblioteca y modales: ningún campo tapado y `.floating-player` oculto mientras el teclado está abierto.
- [ ] Háptica con "Vibración al tocar" activada y desactivada en Ajustes del sistema.
- [ ] Controles multimedia en pantalla de bloqueo, notificación, auriculares (toque simple = play/pausa, doble toque = siguiente), Bluetooth y reanudación tras matar la app.
- [ ] Permiso de notificaciones: aceptar tras elegir carpeta/primera reproducción, denegar y comprobar botón "Ajustes" en Las Perillas.
- [ ] Rotación, multiventana, teléfono, plegable desplegado y tablet (riel lateral + dos paneles + atajos de teclado `/` y flechas/espacio).
- [ ] Servicio `dataSync` > 6 h en Android 15 (o simulación con `adb shell cmd activity` / `onTimeout`) verificando apagado limpio sin `ForegroundServiceDidNotStopInTimeException`.
