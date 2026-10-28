# 🦫 La Rockola del Carpincho

> **Un reproductor de música sin vueltas, pensado para escuchar en grupo, reproducir local sin consumir recursos y controlar todo en tiempo real desde el celu.**

## 📋 ¿Por qué nació?

Los reproductores de escritorio tradicionales y las apps de streaming actuales suelen tener varias fricciones molestas:

1. **Control local pesado:** Los reproductores clásicos suelen ser pesados, comen recursos a lo loco y son incómodos para manejar mientras laburás o hacés otra cosa.
2. **Falta de control compartido:** En un asado, previa, juntada o en la oficina, si alguien quiere poner un tema tiene que pedir prestado el teléfono, desbloquear pantallas ajenas o joder todo el tiempo al que puso la música.
3. **Manejo remoto engorroso:** Manejar la música desde el sillón o la cocina suele requerir bajarse apps pesadas, levantar servidores multimedia complejos o renegar con emparejamientos y configuraciones de red.

## 💡 La Solución

**La Rockola del Carpincho** resuelve todo esto combinando una interfaz de escritorio súper ágil con un control remoto web instantáneo:

- **Control remoto instantáneo por WebSockets:** Manejá la reproducción, organizá la cola y explorá tu biblioteca desde cualquier dispositivo conectado a la misma red local, sin instalar absolutamente nada.
- **Modo Fogón (Cola Colaborativa):** Tus amigos e invitados pueden mandar temas a la cola directamente desde sus teléfonos con una interfaz limpia, rápida y mobile-friendly.
- **Rendimiento liviano y al pie:** Construido sobre Vue 3, Vite y el motor MPV para garantizar un consumo mínimo de CPU y RAM, con búsqueda instantánea, letras sincronizadas (LRC), menús contextuales y respuesta háptica en el celular.

## ✨ Características Principales

- **Gestión completa de temas:** Explorá, buscá, filtrá y administrá tu biblioteca local y tus listas de reproducción sin despeinarte.
- **Modo Fogón:** Que cualquiera en la juntada sume canciones a la cola sin sacarte el control de la máquina principal.
- **Letras Sincronizadas (LRC):** Visualización de letras en tiempo real para cantar los temas a coro.
- **Controles de reproducción precisos:** Ajuste fino de volumen, barra de progreso interactiva y atajos de teclado configurables.
- **Interfaz móvil táctil:** Diseñada para pantallas táctiles, con controles cómodos y respuesta háptica por vibración.
- **Motor de audio nativo con MPV:** Usa MPV bajo el capó para decodificación de audio sólida como una roca y soporte de ventana flotante.
- **Modo Radio con Locución:** Comentarios radiales automatizados en español rioplatense (con Edge-TTS), clima en vivo (wttr.in) y masterización con ducking en FFmpeg.

## 🛠️ Stack Tecnológico

- **Arquitectura Backend:** Arquitectura Hexagonal (Puertos y Adaptadores) con separación estricta del dominio.
- **Framework Backend:** [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) (Python 3.10+).
- **Motor de Audio:** `mpv` controlado de forma asíncrona mediante sockets/pipes JSON IPC (`AsyncMpvController`).
- **Integración con el Sistema:** Controles multimedia globales por D-Bus MPRIS v2 (`dbus-next`).
- **Locución y Radio:** Síntesis con Edge-TTS, masterización dinámica mediante grafos de audio en FFmpeg y reporte meteorológico con wttr.in.
- **Base de Datos:** SQLite con Write-Ahead Logging (`WAL`), migraciones versionadas y patrón Repository.
- **Etiquetado y Huellas de Audio:** `mutagen` para tags ID3/Vorbis y `fpcalc` (Chromaprint) para reconciliación y detección de duplicados.
- **Frontend SPA:** [Vue 3](https://vuejs.org/) (Composition API con TypeScript y Vite).
- **Estilos:** Tailwind CSS con diseño glassmorphic moderno.
- **Sincronización en Tiempo Real:** WebSockets nativos con difusión incremental de diffs de estado.

## 📁 Estructura del Proyecto

Para ver el detalle completo de capas, contratos y secuencias de comunicación, consultá [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```text
La Rockola del Carpincho/
├── app/                     # Backend en Python (Arquitectura Hexagonal)
│   ├── api/                 # Adaptadores de entrada: endpoints REST, despachador de comandos, WebSockets
│   ├── cli/                 # Presentación CLI: punto de entrada y asistente interactivo
│   ├── core/                # Contenedor de inyección de dependencias, configuración, logging y red
│   ├── domain/              # Lógica pura de negocio: orquestador de reproducción, cola, DJ Bara, radio, biblioteca
│   └── infrastructure/      # Adaptadores de salida: mpv IPC, mpris, repositorios SQLite, mezclador FFmpeg
├── docs/                    # Documentación y guías arquitectónicas
│   └── ARCHITECTURE.md      # Especificación técnica detallada y diagramas
├── src/                     # Frontend SPA moderno en Vue 3 + TypeScript
│   ├── audio/               # Drivers de audio para navegador (media session, keepalive)
│   ├── components/          # Pestañas y vistas (ControlsTab, QueueTab, LibraryTab, FogonMode, modales)
│   ├── composables/         # Lógica reactiva de presentación (sockets, drag & drop, atajos)
│   ├── stores/              # Stores reactivas de dominio (playback, queue, library, radio, ui)
│   └── types/               # Definiciones de tipos TypeScript compartidas
├── tests/                   # Batería de pruebas automatizadas (pytest + vitest)
│   ├── frontend/            # Pruebas de Vitest para componentes y composables
│   └── test_*.py            # Etapas de pruebas de Python (infraestructura, dominio, API, radio, auditoría)
├── server.py                # Punto de entrada principal del servidor
├── package.json             # Dependencias y scripts del frontend
└── vite.config.ts           # Configuración del empaquetador Vite
```

## 🚀 Puesta en Marcha

El servidor en Python coordina la biblioteca musical, la base de datos y el control de MPV, sirviendo al mismo tiempo la interfaz web en Vue.

> **💡 Versiones Portátiles y Releases Autónomos (AppImage / ZIP Portable):**
> Las versiones oficiales de lanzamiento vienen listas para usar, con las dependencias esenciales ya incluidas. Si falta algún binario opcional como `ffmpeg`, `yt-dlp` o `fpcalc`, La Rockola intenta descargarlo y configurarlo automáticamente en tu carpeta de usuario (`~/.carpincho` o `%APPDATA%\Carpincho`) sin romper la reproducción en caso de estar sin internet.

### 1. Dependencias del Sistema (Ejecución desde Código Fuente)

Al correr desde el código fuente, La Rockola usa exactamente el mismo motor de resolución y auto-descarga de binarios. Busca en carpetas locales, entornos virtuales, la carpeta de Carpincho y el `PATH` del sistema. Si falta algo, intentará descargarlo por vos.

Si preferís instalarlos manualmente con el gestor de paquetes de tu sistema operativo:

- **MPV** (Requerido): Motor de reproducción de audio (se auto-descarga en Windows y Linux si no está instalado).
- **FFmpeg y FFprobe** (Recomendado): Necesario para las locuciones radiales, masterización y análisis de BPM/mood.
- **Chromaprint (`fpcalc`)** (Opcional): Permite generar huellas acústicas para detectar duplicados y reconciliar archivos movidos.
- **yt-dlp** (Opcional): Permite reproducir enlaces de YouTube y extraer metadatos de la web.

**Instalación manual por sistema operativo:**

- **Windows**: `winget install mpv yt-dlp Gyan.FFmpeg Chromaprint.fpcalc Python.Python.3 OpenJS.NodeJS`
- **macOS**: `brew install mpv ffmpeg chromaprint yt-dlp python node`
- **Linux**: `sudo apt update && sudo apt install mpv ffmpeg libchromaprint-tools yt-dlp python3 python3-pip nodejs npm` (o el equivalente en tu distribución)

### 2. Dependencias de Python

Instalá los paquetes necesarios mediante `pip`:

```bash
pip install fastapi uvicorn mutagen pydantic
```

**Paquetes opcionales de Python:**

- `edge-tts`: Habilita la locución automática del Carpincho (`pip install edge-tts`).
- `dbus-next`: Habilita el control por teclas multimedia en Linux vía MPRIS (`pip install dbus-next`).

### 3. Iniciar el Servidor

Una vez listas las dependencias, arrancá la aplicación:

```bash
python server.py
```

El servidor compila automáticamente el frontend con Vite en el primer inicio si no existe `dist/index.html`.

**Opciones principales de la línea de comandos (CLI):**

- `--host`: Dirección de escucha (por defecto `0.0.0.0` para acceso en red local).
- `--port`: Puerto web del servidor (por defecto `1729`).
- `--dir`: Directorio principal de música (por defecto `~/Music`).
- `--dir2`: Directorio secundario opcional de música.
- `--weather-location`: Ciudad/ubicación para el reporte del clima en la radio (ej: `"Rosario, Argentina"`).
- `--setup`: Lanza el asistente interactivo de configuración en la terminal.
- `--no-interactive`: Omite el asistente interactivo en entornos desatendidos.
- `--rebuild-frontend`: Fuerza la recompilación del frontend con Vite antes de iniciar.
- `--open-browser` / `--no-browser`: Activa o desactiva la apertura automática del navegador.
- `--debug`: Habilita logs detallados en nivel DEBUG.

_Ejemplo de uso:_

```bash
python server.py --port 8080 --dir "/home/usuario/Música"
```

> **Aviso sobre el Puerto 80:** Si elegís usar `--port 80` (el puerto estándar HTTP) para no tener que tipear el número de puerto en el navegador, tu sistema operativo va a requerir permisos de administrador o root para enlazarlo.
>
> - **Windows:** Ejecutá la consola o terminal como Administrador.
> - **macOS / Linux:** Ejecutá con `sudo` (ej: `sudo python server.py --port 80`) o configurá `authbind` para tu usuario.

Cuando el servidor arranca, abre automáticamente el reproductor en tu navegador predeterminado apuntando a la IP local (ej: `http://192.168.X.Y:1729`). Para controlar la música desde el celular o con amigos, conectate a la misma red Wi-Fi y entrá a la IP que figura en la consola o escaneá el código QR en la pestaña **Controles**. Para ver todas las opciones disponibles, ejecutá `python server.py --help`.
