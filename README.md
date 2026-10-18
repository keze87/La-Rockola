# 🦫 La Rockola del Carpincho

> **A seamless, low-friction music player built for shared listening, lightweight local playback, and real-time remote control.**

## 📋 Why?

Traditional desktop media players and modern streaming apps suffer from several recurring friction points:

1. **Cumbersome Local Control:** Standard media players often feel bloated, resource-heavy, and clunky to navigate while multitasking.
2. **Lack of Shared/Social Controls:** In social settings—like a gathering, party, or office—letting guests queue songs usually means passing a phone around, sharing unlocked screens, or constantly interrupting the host.
3. **Complex Remote Management:** Managing music playback from across the room often requires installing bulky mobile apps, setting up complex media servers, or dealing with network pairing headaches.

## 💡 The Solution

**La Rockola del Carpincho** solves these challenges by combining a sleek desktop player interface with an instant remote control web interface:

- **Instant Socket-Based Remote Control:** Control playback, manage queues, and browse music remotely from any device on the same local network without installing extra software.
- **Social Queueing:** Allows friends and guests to easily add tracks to a shared queue from their phones using a simple, mobile-friendly interface.
- **Lightweight & Fast Performance:** Built with Vue 3, Vite, and MPV integration to ensure minimal CPU/RAM usage while offering rich features like track searching, synchronized lyrics, context menus, and haptic feedback on mobile.

## ✨ Key Features

- **Full Track Management:** Browse, search, filter, and manage your local library and queues effortlessly.
- **Campfire Mode:** Social queuing made easy—let anyone queue songs without giving up control of your master device.
- **Synchronized Lyrics:** Integrated lyrics display for an immersive listening or sing-along experience.
- **Precision Playback Controls:** Advanced playback adjustments, sliders, volume controls, and configurable keyboard shortcuts.
- **Mobile-Optimized Remote UI:** Responsive control interface built with tactile controls and haptic feedback.
- **MPV Native Player Integration:** Leverages MPV for rock-solid audio decoding and smooth window management.

## 🛠️ Tech Stack

- **Backend Architecture:** Hexagonal Architecture (Ports and Adapters) with pure domain separation
- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) (Python 3.10+)
- **Audio Engine:** `mpv` via asynchronous JSON IPC sockets/pipes (`AsyncMpvController`)
- **Desktop Integration:** D-Bus MPRIS v2 media controls (`dbus-next`)
- **Radio & Speech:** Edge-TTS synthesis, FFmpeg dynamic audio graph mastering, and wttr.in weather forecast integration
- **Database:** SQLite with Write-Ahead Logging (`WAL`), versioned migrations, and repository pattern
- **Audio Tagging & Fingerprinting:** `mutagen` for ID3/Vorbis tags and `fpcalc` (Chromaprint) for audio reconciliation
- **Frontend Framework:** [Vue 3](https://vuejs.org/) (Composition API with TypeScript & Vite)
- **Styling:** Tailwind CSS + custom glassmorphic theme
- **Real-time Networking:** Native WebSockets with incremental state diff broadcasting

## 📁 Project Structure

For an in-depth breakdown of layers, contracts, and communication sequences, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

```text
La Rockola del Carpincho/
├── app/                     # Clean Python backend (Hexagonal Architecture)
│   ├── api/                 # Inbound adapters: REST endpoints, command router, WebSockets
│   ├── cli/                 # Presentation: CLI entrypoint & interactive setup wizard
│   ├── core/                # Dependency injection container, config, logging, network
│   ├── domain/              # Pure business logic: playback orchestrator, queue, DJ, radio, library
│   └── infrastructure/      # Outbound adapters: mpv IPC, mpris, sqlite repositories, ffmpeg mixer
├── docs/                    # Project documentation & architectural designs
├── src/                     # Modern Vue 3 + TypeScript SPA frontend
│   ├── audio/               # Browser audio drivers (media session, keepalive)
│   ├── components/          # UI tabs (ControlsTab, QueueTab, LibraryTab, FogonMode, modals)
│   ├── composables/         # Reactive presentation composables (sockets, drag & drop, shortcuts)
│   ├── stores/              # Reactive domain stores (playback, queue, library, radio, ui)
│   └── types/               # Shared TypeScript type definitions
├── tests/                   # Comprehensive automated test suites (pytest + vitest)
│   ├── frontend/            # Vitest suites for Vue components and composables
│   └── test_*.py            # Python test stages (infrastructure, domain, api, radio, audit)
├── server.py                # Server entrypoint
├── package.json             # Frontend dependencies and scripts
└── vite.config.ts           # Vite configuration
```

## 🚀 Getting Started

The application coordinates the music library, database, and MPV player control while serving the Vue frontend.

> **💡 Zero-Friction Standalone Releases (AppImage / Portable ZIP):**
> Official release builds are completely self-contained. They come pre-bundled with core dependencies. If optional binaries like `ffmpeg`, `yt-dlp`, or `fpcalc` are missing, La Rockola automatically attempts to download and configure them in your user directory with graceful degradation if offline—no manual installation needed.

### 1. System Dependencies (Running from Source)

When running from source, La Rockola uses the exact same automated binary detection and auto-download engine. It searches local project directories, virtualenv scripts, the Carpincho data folder, and system `PATH`. If missing, it will automatically attempt to fetch them for you.

Alternatively, you can manually install them via your package manager:

- **MPV** (Required): Core audio playback engine (auto-downloaded on Windows/Linux if missing).
- **FFmpeg & FFprobe** (Recommended): Required for radio announcements, mastering, and mood/BPM audio feature analysis.
- **Chromaprint (`fpcalc`)** (Optional): Enables audio fingerprinting and duplicate/reconciliation detection.
- **yt-dlp** (Optional): Enables streaming tracks and metadata extraction from YouTube and remote URLs.

**Manual Installation by OS:**

- **Windows**: Run `winget install mpv yt-dlp Gyan.FFmpeg Chromaprint.fpcalc Python.Python.3 OpenJS.NodeJS`.
- **macOS**: Run `brew install mpv ffmpeg chromaprint yt-dlp python node`.
- **Linux**: Run `sudo apt update && sudo apt install mpv ffmpeg libchromaprint-tools yt-dlp python3 python3-pip nodejs npm` (or your distribution's equivalent).

### 2. Python Dependencies

Install the Python packages via `pip`:

```bash
pip install fastapi uvicorn mutagen pydantic
```

**Optional Python Packages:**

- `edge-tts`: Enables automated Argentine radio speaker commentary (`pip install edge-tts`).
- `dbus-next`: Enables Linux system multimedia key control via MPRIS (`pip install dbus-next`).

### 3. Running the Server

Once your dependencies are installed, start the server:

```bash
python server.py
```

The server automatically compiles the frontend with Vite on first launch if `dist/index.html` is missing.

**Available CLI Options:**

- `--host`: Listen address (defaults to `0.0.0.0` for local network access).
- `--port`: Server web port (defaults to `1729`).
- `--dir`: Primary music library directory (defaults to `~/Music`).
- `--dir2`: Optional secondary music library directory.
- `--weather-location`: City/location for radio weather reports (e.g. `"Rosario, Argentina"`).
- `--setup`: Force the interactive terminal configuration wizard.
- `--no-interactive`: Skip the interactive wizard in automated environments.
- `--rebuild-frontend`: Force recompilation of the frontend with Vite before starting.
- `--open-browser` / `--no-browser`: Toggle automatic opening of the web player in your browser.
- `--debug`: Enable verbose DEBUG level logging.

_Example:_

```bash
python server.py --port 8080 --dir "C:\Users\UserName\Music"
```

> **Note on using Port 80:** If you choose to set `--port 80` (the standard HTTP port) so you don't have to type a port number in your browser, your operating system will likely require administrator or root privileges to bind to it.
>
> - **Windows:** Run your command prompt or terminal as Administrator.
> - **macOS/Linux:** Run the command with `sudo` (e.g., `sudo python server.py --port 80`). Alternatively, on Linux, to avoid running the entire server as root, you can use `authbind` (e.g., `authbind python server.py --port 80`) after configuring it for your user account.

4. Once the server is running, La Rockola automatically opens the player in your default browser using your local network IP (e.g., `http://192.168.X.Y:1729`). You can also start without opening the browser by passing `--no-browser`. To control the music from your phone or with friends, connect to the same Wi-Fi network and navigate to the local IP displayed in the console or scan the QR code located in the **Controles** tab. Run `python server.py --help` to see all available CLI options.
