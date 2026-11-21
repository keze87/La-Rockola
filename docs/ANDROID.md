# 📱 La Rockola del Carpincho en Android

Esta guía explica cómo funciona **La Rockola del Carpincho** tanto como **servidor** (llevando tu biblioteca musical en el teléfono o en la tarjeta **MicroSD**) como **cliente** (app APK nativa o PWA instalable desde Chrome).

---

## 🏗️ Arquitectura en Android

La versión de Android reutiliza el 100% del backend en Python y del frontend en Vue 3:

1. **Cliente Nativo (Capacitor + Vue 3):** Empaqueta la interfaz web compilada (`dist/`) dentro de un WebView configurado con `androidScheme: "http"` y `usesCleartextTraffic="true"` para comunicarse sin bloqueos con `http://127.0.0.1:1729` o con otro servidor en la red Wi-Fi.
2. **Servidor Embebido (Chaquopy + FastAPI/Uvicorn):** Corre en segundo plano dentro de `RockolaForegroundService` (`foregroundServiceType="mediaPlayback"`) con `PARTIAL_WAKE_LOCK` y `WifiLock`, arrancando automáticamente al abrir la app en modo `--no-mpv` (`NullMpvController`).
3. **Acceso Real a la MicroSD (`RockolaServerPlugin`):**
    - Solicita `READ_MEDIA_AUDIO` (Android 13+) o `MANAGE_EXTERNAL_STORAGE` (_Acceso a todos los archivos_) para que Python y `mutagen` puedan leer carpetas arbitrarias de la tarjeta MicroSD (`/storage/XXXX-XXXX/...`) sin las trabas de _Scoped Storage_.
    - La base de datos `rockola.db`, `rockola_config.json` y los audios temporales de radio se guardan siempre en el almacenamiento interno privado de la app (`ROCKOLA_DATA_DIR`), nunca en la MicroSD.
4. **Cliente Web / PWA para Invitados:** Cualquier otro teléfono conectado al mismo Wi-Fi puede entrar a la IP mostrada en la notificación o escanear el QR en **Las Perillas**, e instalar la web como PWA (_"Agregar a pantalla principal"_) gracias a `/manifest.webmanifest` y `/sw.js`.

---

## 🛠️ Cómo Compilar el APK

### Requisitos previos

- **Node.js** y dependencias instaladas (`npm install`).
- **Android Studio** o **Android SDK + NDK** (`ANDROID_HOME` configurado) y JDK 21.
- **Python 3.11** disponible en el `PATH` del equipo de compilación para que Chaquopy resuelva las ruedas nativas (`pip` / `buildPython`).

> [!NOTE]
> El backend usa Pydantic v2 (`pydantic-core`), que incluye código nativo en Rust. El script `scripts/build_android.py` descarga y reetiqueta automáticamente las ruedas `android_24_*` faltantes en `android/app/wheels/`, y `android/app/build.gradle` define sabores (`arm64`, `armv7`, `x86_64`) para generar APKs livianos separados por arquitectura.

### Pasos de compilación

1. **Sincronizar frontend, backend Python y Capacitor:**

    ```bash
    npm run android:sync
    ```

    _(Esto ejecuta `npm run build`, copia únicamente `app/` a `android/app/src/main/python/app/`, limpia cualquier `assets/dist/` obsoleto y corre `npx cap sync android` para dejar el frontend en `android/app/src/main/assets/public/`)._

2. **Generar los APKs por arquitectura (`arm64`, `armv7`, `x86_64`):**
    - Por consola (con `ANDROID_HOME` configurado):
        ```bash
        npm run android:build
        ```
        Los binarios se generan en `android/app/build/outputs/apk/<sabor>/debug/` (por ejemplo `arm64/debug/app-arm64-debug.apk`).
    - O abriendo la carpeta `android/` directamente desde **Android Studio** y ejecutando **Build > Build Bundle(s) / APK(s) > Build APK(s)**.

---

## 📲 Configuración Inicial en el Teléfono

1. Instalá el APK generado y abrí **La Rockola del Carpincho** (el servidor arranca solo en segundo plano).
2. En el primer arranque, tocá el aviso **"Elegir carpeta de música en tu MicroSD"** (o entrá en **Las Perillas → Elegir carpeta de música (MicroSD)**).
3. Concedé el permiso de acceso a archivos cuando Android lo solicite y seleccioná la carpeta donde tenés tus MP3/FLAC en la tarjeta SD.
4. Tocá **"Escuchar en este dispositivo"** (o activá **Escuchar acá** en **Las Perillas**) para reproducir por el teléfono o parlante Bluetooth conectado.
5. **Recomendado para sesiones largas:** en _Ajustes → Aplicaciones → La Rockola del Carpincho → Batería_, seleccioná **"Sin restricciones"** para evitar que la capa del fabricante cierre el servicio tras varias horas con la pantalla apagada.

---

## 💻 Modo Headless en Linux/PC (`--no-mpv`)

Si querés correr La Rockola en una Raspberry Pi, servidor casero o PC sin parlantes ni MPV instalado para escuchar únicamente desde celulares o navegadores:

```bash
python server.py --no-mpv --no-browser
```
