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
- **Apagado acotado y `onDestroy`**: `stop_embedded_server()` señala `should_exit = True` en Uvicorn de inmediato (y `force_exit = True` en un segundo intento) y ejecuta `flush_pending_volume_persist()` + `save_playback_session(force=True)` en un executor serializado sin bloquear el timeout de `HostLifecycleCoordinator` (4 s totales sobre hook + hilo). Si el worker sigue vivo tras el timeout, el estado pasa a `STOP_TIMED_OUT` con `hasActiveWorker = true`, bloqueando reinicios hasta la terminación real; `onDestroy()` no falsea `isRunning = false` ni pisa `STOP_TIMED_OUT` si el worker sigue vivo.
- **Cierre desde Recientes (`onTaskRemoved`) y hosting remoto**: Si no hay reproducción local ni clientes remotos activos (WebSockets no-loopback o streams HTTP `/stream` activos / dentro de 30 s de gracia), el servicio detiene el servidor y se cierra limpio. Si hay clientes remotos sin audio local, promueve temporalmente con tipo `dataSync` (no `mediaPlayback`) y monitorea cada 15 s para apagar el servidor apenas se cierre el último cliente y venza la gracia.
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
- **Acceso directo por file descriptor y escaneo paginado**: `AndroidStorageBridge.kt` enumera pistas en tandas paginadas vía `DocumentsContract` con caché acotada de padres/letras y limpieza automática al cancelar o expirar, tolerando `mtime`/`size` opcionales (`None` sin validar falsos hits de caché) y diferenciando cursor `null` como error de proveedor. Entrega descriptores nativos (`detachFd`) a `app/infrastructure/storage/backend.py` (`AndroidSafStorageBackend` + `os.fdopen(fd, "rb")`) para leer tags ID3/FLAC/MP4 con Mutagen, calcular hashes, transmitir con soporte HTTP `206 Partial Content` en seekables (o `200` secuencial `Accept-Ranges: none` cuando el tamaño es desconocido), extraer portadas (`/cover`) y leer letras hermanas `.ass` / `.lrc` (`/lrc`, `/api/v1/lyrics/content`).
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
