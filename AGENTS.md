# Development Guidelines for La Rockola del Carpincho

## 🎯 Target Platforms & Distribution

- **First-Class Targets**: Linux (`x86_64` AppImage) and Windows (`x86_64` Portable ZIP / `.exe`).
- **User-Friendly Releases**:
    - Releases must be standalone and zero-friction for the end user (click and run).
    - External binaries (such as `mpv`, `ffmpeg` or `yt-dlp`) should be auto-detected, auto-downloaded, or updated smoothly when missing on portable platforms.
    - Mood/BPM analysis utilizes `ffmpeg` and audio metadata tags with clean graceful degradation (hiding advanced mood features in the UI when unavailable without crashing or preventing core playback).

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

### Force TDD

Whenever changes are about to be made, first create the tests, make sure they fail, and then start implementing the changes.

### Backward Compatibility

- Backward compatibility is NOT needed or critical: prioritize clean, modern architectures, removing dead code, legacy flags, and obsolete fallbacks rather than keeping redundant shims.

---

## 🧉 Identity & Tone

- User-facing logs, CLI setup wizards, and UI copy embrace an authentic, friendly Argentine tone (_"ojo al piojo"_, _"joyita"_, _"cortala de una"_, _"más manija"_).
- Internal code remains clean, modular, and strongly typed.
- Code comments must be in Argentine spanish
- Documentation, guides, and README files must be in Spanish

### 📻 Línea Editorial Radial y Variedad de Humor

El humor de la radio funciona cuando suena como un lugar coherente, con identidad ribereña y personajes vivos. Para no desgastar el dial:

- **Evitar la fórmula fija**: No abusar del chiste recurrente de "mate + carpincho en el agua + fiaca/no hacer nada". La variedad temática mantiene viva la sorpresa.
- **Diversificación de mecanismos cómicos**:
    - **Anuncios secos y solemnes (Deadpan)**: Informaciones leídas con seriedad absoluta que contrastan con lo absurdo de la situación.
    - **Avisos burocráticos absurdos**: Notificaciones oficiales del pueblo, edictos municipales, resoluciones comunales, expedientes de catastro y actas del concejo deliberante.
    - **Dedicatorias de oyentes genuinas**: Mensajes verosímiles de la vida real en el delta y el conurbano (trabajadores de peaje, frigoríficos, talleres mecánicos, cooperativas eléctricas).
    - **Radiopasillo y radioteatro con personajes recurrentes**: Continuidad narrativa con vecinos conocidos (Don Anselmo, Doña Gladys, Cacho de la gomería, Pocho el botero, Romualdo, el comisario jubilado).
    - **Interrupciones surrealistas y transiciones secas**: Interferencias crípticas breves, avisos de cabina y pases directos al hueso sin vueltas entre canciones.
- **No monopolizar con carpinchos**: Darle aire al pueblo, a los vecinos y al ecosistema completo de la cuenca.
- **Añadir variedad**: Priorizar enriquecer y diversificar el repertorio antes que podar contenido. Todas las frases en los bancos deben ser alcanzables y auditadas contra código muerto.
- **Precarga**: Revisar que las frases nuevas se puedan precargar.

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

5. **Commit**:
    - Before finalizing create commit name with professional Argentine tone.
