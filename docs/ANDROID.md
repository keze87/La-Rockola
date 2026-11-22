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

- **Reproducción activa**: El servicio se promueve a foreground (`mediaPlayback`) junto con la notificación MediaStyle, carátula, barra de progreso y candados `PARTIAL_WAKE_LOCK` + `WifiManager.WIFI_MODE_FULL_LOW_LATENCY` (o `WIFI_MODE_FULL_HIGH_PERF` en API < 29).
- **En pausa**: Soltamos inmediatamente `WakeLock`/`WifiLock` y ejecutamos `STOP_FOREGROUND_DETACH`, dejando la notificación descartable para poder reanudar sin consumir batería en primer plano.
- **Detenido / cambio de destino**: Desmontamos el modo foreground con `STOP_FOREGROUND_REMOVE` antes de cancelar la notificación para evitar inconsistencias de ciclo de vida.
- **Cierre desde Recientes (`onTaskRemoved`) y apagado**: Si no hay reproducción activa, el servicio detiene Uvicorn de forma ordenada (`should_exit = True` + join acotado de hasta 4 segundos en `HostLifecycleCoordinator`) y se cierra limpio sin hilos Python huérfanos. Si cerrás la app desde Recientes mientras está en reposo, Android también detendrá el servidor embebido.
- **Limitaciones en segundo plano (Android 12+)**: Si no hay audio reproduciéndose, el SO puede frenar el proceso en segundo plano o bloquear `startService` desde el plugin (`SERVICE_START_NOT_ALLOWED`); la app captura estas excepciones sin crashear y muestra un aviso accionable para reabrir/reiniciar desde primer plano.

---

## 🌐 Seguridad de Red (LAN), Precarga TTS y Permisos

- **Network Security Config (`network_security_config.xml`)**: Se reemplazó `usesCleartextTraffic="true"` global por una configuración explícita de `localhost` / `127.0.0.1` junto con `base-config` documentando que el modo Cliente Remoto se conecta por HTTP plano a IPs LAN privadas (`192.168.x.x`, `10.x.x.x`) que no admiten CIDR en `<domain-config>`.
- **Permisos mínimos y backup**: Se eliminaron `READ_MEDIA_AUDIO`, `READ_EXTERNAL_STORAGE` y `FileProvider` (acceso 100% SAF), y se desactivó `allowBackup` (`false`) con gesto atrás predictivo (`enableOnBackInvokedCallback="true"`).
- **Precarga TTS controlada**: En Android, `run_tts_preload` arranca automáticamente en segundo plano **solo en Wi-Fi / Ethernet no medida** (`ConnectivityManager` + `NET_CAPABILITY_NOT_METERED`) y corta por tandas al alcanzar **333 MB** en `tts_cache.db` (podando por `last_used`).
- **Botones físicos de volumen (`ContentObserver`)**: Observar `Settings.System.CONTENT_URI` es un mecanismo best-effort que puede no emitir eventos en todos los fabricantes o versiones de Android 14–16; como respaldo, `RockolaServerPlugin.handleOnResume()` re-lee el volumen multimedia cada vez que la app vuelve a primer plano.

---

## 📁 Almacenamiento SAF Real (Memoria Interna y MicroSD)

La aplicación **no solicita** `MANAGE_EXTERNAL_STORAGE` y **no copia** tu biblioteca musical al almacenamiento privado de la app:

- **Selector nativo (`ACTION_OPEN_DOCUMENT_TREE`)**: Persistimos permisos de lectura sobre el árbol SAF elegido (`takePersistableUriPermission`).
- **Instalación limpia**: En instalaciones nuevas donde ninguna carpeta estándar de Android sea legible, `music_dir` inicia vacío (`""`, `music_dir_configured = false`) y se pide elegir carpeta explícitamente.
- **Acceso directo por file descriptor**: `AndroidStorageBridge.kt` enumera pistas recursivamente vía `DocumentsContract` y entrega descriptores nativos (`detachFd`) a `app/infrastructure/storage/backend.py` (`AndroidSafStorageBackend` + `os.fdopen(fd, "rb")`) para leer tags ID3/FLAC/MP4 con Mutagen, calcular hashes, transmitir con soporte HTTP `206 Partial Content` (`Range` en `/api/v1/stream`), extraer portadas (`/cover`) y leer letras hermanas `.ass` / `.lrc` (`/lrc`, `/api/v1/lyrics/content`).
- **Limitaciones conocidas**:
    - Si revocás permisos o expulsás la tarjeta MicroSD, el sistema reporta estados explícitos (`permission_denied`, `storage_unavailable`, `unsupported_provider`) con acción directa para reelegir carpeta.
    - Al montarse árboles SAF de solo lectura desde Android, guardar letras nuevas (`POST /api/v1/lyrics/save`) devuelve HTTP 400 explicando la restricción.

---

## ⚙️ Requisitos, ABIs, Alineamiento 16 KB y Firma Release

### Requisitos de compilación

- **Node.js 22+** y **npm**
- **Java JDK 21** (`JAVA_HOME=/usr/lib/jvm/java-21-openjdk` en Linux si tu `java` por defecto no trae `javac`)
- **Android SDK** (`ANDROID_HOME` o `android/local.properties` con `compileSdk 36`, `minSdk 24`)
- **Python 3.14** disponible para `buildPython` de Chaquopy `17.2.0`

### ABIs y verificación binaria de 16 KB (`0x4000`)

- **Arquitecturas soportadas**: `arm64` (`arm64-v8a`) y `x86_64` con `versionCode` diferenciado (`base * 10 + 1` y `base * 10 + 2`). Se removió `armv7` (32 bits) ya que el stack `cp314` (Python 3.14) de Play exige 64-bit y 16 KB.
- **Decisión Python 3.14 + wheels nativos sin reetiquetado Linux**: Se adoptó **Python 3.14** sobre **Chaquopy 17.2.0** para contar con wheels `cp314` compilados nativamente con alineamiento 16 KB (`pydantic==2.14.3`, `pydantic-core==2.50.4`, `aiohttp==3.14.5`, `frozenlist==1.8.0`, `multidict==7.2.1`, `yarl==1.25.1`) desde `https://pypi.flet.dev` / PyPI sin reetiquetado manual, eliminando `pillow`/`libfreetype.so` mediante `AndroidImageResizer.kt` (`BitmapFactory`).
- **Pines estrictos sin `--require-hashes` en Chaquopy**: Todas las dependencias Python en `android/app/build.gradle` están fijadas con `==`. No se habilita `--require-hashes` porque `chaquopy-pip` resuelve wheels específicos por ABI (`arm64-v8a` / `x86_64`) entre PyPI y `--extra-index-url https://pypi.flet.dev` con dependencias transitivas cuyo conjunto de hashes difiere por arquitectura/plataforma.
- **Verificador automático**: `scripts/verify_android_apk.py` audita cada `.so` dentro de `lib/` **y dentro de archivos comprimidos `.imy` de Chaquopy**, exigiendo `PT_LOAD p_align >= 0x4000` y ausencia de `RUNPATH/RPATH` apuntando a `com.termux`.

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
