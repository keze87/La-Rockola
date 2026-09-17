# Development Guidelines for La Rockola del Carpincho

## 🎯 Target Platforms & Distribution

- **First-Class Targets**: Linux (`x86_64` AppImage) and Windows (`x86_64` Portable ZIP / `.exe`).
- **User-Friendly Releases**:
    - Releases must be standalone and zero-friction for the end user (click and run).
    - External binaries (such as `mpv` or `yt-dlp`) should be auto-detected, auto-downloaded, or updated smoothly when missing on portable platforms.
    - Optional heavy dependencies (like `librosa` for BPM/mood analysis) must degrade gracefully: utilize system Python if installed on the host, or hide advanced mood features in the UI without crashing or preventing core playback.

---

## 🏗️ Architecture & Code Organization

### Backend (`server.py`)

- **Core Stack**: FastAPI + WebSockets for instant state sync and real-time remote controls.
- **Player Engine**: Asynchronous MPV controller (`AsyncMpvController`) communicating over JSON IPC sockets.
- **Database & Library**: SQLite (`rockola.db`) with smart file-hash caching, fingerprint reconciliation (`fpcalc`), and non-blocking background scanning.

### Frontend (`src/`)

- **Core Stack**: Vue + TypeScript + Vite + Tailwind CSS.
- **State Management**:
    - Do NOT create duplicate local state in components for shared playback, volume, queue, or server capability flags.

---

## 🧉 Identity & Tone

- User-facing logs, CLI setup wizards, and UI copy embrace an authentic, friendly Argentine tone (_"ojo al piojo"_, _"joyita"_, _"cortala de una"_, _"más manija"_).
- Internal code remains clean, modular, and strongly typed.

---

## ✅ Mandatory Verification & Quality Standards

Whenever changes are made to the Python backend or frontend code, **always** execute the complete quality suite before finalizing:

1. **Formatting**:
    - Python: `ruff format .`
    - Frontend: `npm run format`

2. **Linting**:
    - Python: `ruff check .`
    - Frontend: `npm run lint`

3. **Compilation & Build**:
    - Python: `python -m compileall server.py scripts/ tests/`
    - Frontend: `npm run build`

4. **Testing**:
    - Python: `pytest`
    - Frontend: `npm test`
