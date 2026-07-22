# 🦫 La Rockola del Carpincho

> **A seamless, low-friction music player built for shared listening, lightweight local playback, and real-time remote control.**

## 📋 Why?

Traditional desktop media players and modern streaming apps suffer from several recurring friction points:

1. **Cumbersome Local Control:** Standard media players often feel bloated, resource-heavy, and clunky to navigate while multitasking.
2. **Lack of Shared/Social Controls:** In social settings—like a gathering, party, or office—letting guests queue songs usually means passing a phone around, sharing unlocked screens, or constantly interrupting the host.
3. **Complex Remote Management:** Managing music playback from across the room often requires installing bulky mobile apps, setting up complex media servers, or dealing with network pairing headaches.

## 💡 The Solution

**La Rockola del Carpincho** solves these challenges by combining a sleek desktop player interface with an instant remote control web interface:

* **Instant Socket-Based Remote Control:** Control playback, manage queues, and browse music remotely from any device on the same local network without installing extra software.
* **Social Queueing:** Allows friends and guests to easily add tracks to a shared queue from their phones using a simple, mobile-friendly interface.
* **Lightweight & Fast Performance:** Built with Vue 3, Vite, and MPV integration to ensure minimal CPU/RAM usage while offering rich features like track searching, synchronized lyrics, context menus, and haptic feedback on mobile.

## ✨ Key Features

* 🎵 **Full Track Management:** Browse, search, filter, and manage your local library and queues effortlessly.
* 🔥 **Campfire Mode:** Social queuing made easy—let anyone queue songs without giving up control of your master device.
* 🎙️ **Synchronized Lyrics:** Integrated lyrics display for an immersive listening or sing-along experience.
* 🎛️ **Precision Playback Controls:** Advanced playback adjustments, sliders, volume controls, and configurable keyboard shortcuts.
* 📱 **Mobile-Optimized Remote UI:** Responsive control interface built with tactile controls and haptic feedback.
* 🪟 **MPV Native Player Integration:** Leverages MPV for rock-solid audio decoding and smooth window management.

## 🛠️ Tech Stack

* **Frontend Framework:** [Vue 3](https://vuejs.org/) (Composition API with TypeScript)
* **Build Tool:** [Vite](https://vitejs.dev/)
* **Styling:** CSS3 / tailwindcss
* **State & Logic:** Vue Composables Architecture
* **Real-time Networking:** WebSockets (Real-time remote syncing)
* **Audio Engine:** `mpv` integration
* **Notifications:** `vue-sonner` toast notifications
* **Backend Server:** Python 3 with FastAPI and Uvicorn
* **Database:** SQLite (for history, favorites, and mood tracking)

## 📁 Project Structure

```text
La Rockola del Carpincho/
├── src/
│   ├── assets/              # Static media assets
│   ├── components/          # UI components and main player tabs
│   │   └── ui/              # Reusable UI controls (sliders, buttons, track rows)
│   ├── composables/         # Application logic & state management
│   │   └── player/          # Specialized player, queue, socket & playback logic
│   ├── types/               # TypeScript declarations and global types
│   ├── App.vue              # Main App entry view
│   ├── main.ts              # Vue app initialization
│   └── style.css            # Global application styles
├── public/                  # Public assets
├── server.py                # Server / backend
├── vite.config.ts           # Vite configuration
└── package.json             # Dependencies and scripts
```

## 🚀 Getting Started

The application relies on a Python backend server that handles the music library, database, and MPV player control, while simultaneously serving the Vue frontend. The server script includes a helpful checker that will alert you if any dependencies are missing before starting.

### 1. System Dependencies

You must install the MPV media player on your system for the audio engine to work. And optionally, yt-dlp, if you want the ability to play tracks directly from YouTube or the internet.

* **Windows**: Run `winget install mpv yt-dlp Python.Python.3 OpenJS.NodeJS`.
* **macOS**: Run `brew install mpv yt-dlp python node`.
* **Linux**: Run `sudo apt update && sudo apt install mpv yt-dlp python3 python3-pip nodejs npm` (or your distribution's equivalent).

### 2. Python Dependencies

Ensure you have Python 3 installed. You can install the required Python packages using `pip`.

**Required Packages:**

* `fastapi`: `pip install fastapi`.
* `uvicorn`: `pip install uvicorn`.
* `mutagen`: `pip install mutagen`.
* `pydantic`: `pip install pydantic`.

**Optional Packages (Highly Recommended):**

* `librosa`: `pip install librosa` (Enables mood and BPM analysis for your tracks).
* `dbus-next`: `pip install dbus-next` (Required only on Linux to enable control via multimedia keys).

### 3. Running the Server

Once your dependencies are installed, you can start the server. The script will automatically trigger the frontend build (`npm run build`) before launching.

1. Open your terminal and navigate to the project directory.
2. Run the server script (assuming it is named `server.py`):

```bash
python server.py
```

3. **Customizing the run command:** The server accepts several arguments to customize your experience:

* `--host`: Sets the host address (defaults to `0.0.0.0` to be accessible on your local network).
* `--port`: Sets the server port (defaults to `9696`).
* `--dir`: Defines your primary music directory (defaults to `~/Music`).
* `--dir2`: Defines an optional secondary music directory.

*Example with arguments:*

```bash
python server.py --port 8080 --dir "C:\Users\Name\Music"
```

4. Once the server is running, open your web browser and navigate to `http://localhost:9696` (or your custom port) to access the player. To control it remotely from your phone, connect to the same Wi-Fi network and navigate to your computer's local IP address (e.g., `http://192.168.X.Y:9696`).