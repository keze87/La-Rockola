# Pautas de Desarrollo para La Rockola del Carpincho

## 🎯 Plataformas Objetivo y Distribución

- **Objetivos Principales**: Linux (`x86_64` AppImage) y Windows (`x86_64` ZIP Portable / `.exe`).
- **Versiones Fáciles de Usar**:
    - Los lanzamientos deben ser autónomos y sin fricción para el usuario final (hacer clic y ejecutar).
    - Los binarios externos (como `mpv`, `ffmpeg` o `yt-dlp`) deben ser detectados, descargados o actualizados automáticamente y sin problemas cuando falten en plataformas portables.
    - El análisis de estado de ánimo/BPM utiliza `ffmpeg` y etiquetas de metadatos de audio con degradación elegante (ocultando funciones avanzadas de estado de ánimo en la interfaz cuando no estén disponibles, sin fallar ni impedir la reproducción básica).

---

## 🏗️ Arquitectura y Organización del Código

### Backend (`server.py`)

- **Stack Principal**: FastAPI + WebSockets para sincronización de estado instantánea y controles remotos en tiempo real.
- **Motor de Reproducción**: Controlador asíncrono de MPV (`AsyncMpvController`) comunicándose mediante sockets JSON IPC.
- **Base de Datos y Biblioteca**: SQLite (`rockola.db`) con caché inteligente de hashes de archivos, reconciliación de huellas acústicas (`fpcalc`) y escaneo en segundo plano no bloqueante.

### Frontend (`src/`)

- **Stack Principal**: Vue + TypeScript + Vite + Tailwind CSS.
- **Gestión de Estado**:
    - NO crear estado local duplicado en los componentes para la reproducción compartida, el volumen, la cola o los indicadores de capacidad del servidor.

### TDD Obligatorio

Siempre que se vayan a realizar cambios, primero crear las pruebas, asegurarse de que fallen y luego comenzar a implementar los cambios.

### Compatibilidad Hacia Atrás

- La compatibilidad hacia atrás NO es necesaria ni crítica: priorizar arquitecturas limpias y modernas, eliminando código muerto, flags heredados y fallbacks obsoletos en lugar de mantener shims redundantes.

---

## 🧉 Identidad y Tono

- Los logs de cara al usuario, los asistentes de configuración de la CLI y los textos de la interfaz adoptan un tono argentino auténtico y amigable (_"ojo al piojo"_, _"joyita"_, _"cortala de una"_, _"más manija"_).
- El código interno se mantiene limpio, modular y fuertemente tipado.
- Los comentarios en el código deben estar en español argentino.
- La documentación, guías y archivos README deben estar en español.

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

## ✅ Estándares de Calidad y Verificación Obligatoria

Siempre que se realicen cambios en el backend de Python o en el código del frontend, ejecutar **siempre** la suite completa de calidad antes de finalizar:

1. **Formateo**:
    - Python: `ruff format .`
    - Frontend: `npm run format`

2. **Linting**:
    - Python: `ruff check .`
    - Frontend: `npm run lint`

3. **Compilación y Construcción**:
    - Python: `python -m compileall server.py scripts/ tests/`
    - Frontend: `npm run build`

4. **Testing**:
    - Python: `pytest`
    - Frontend: `npm test`

5. **Commit**:
    - Antes de finalizar, crear un nombre de commit con tono profesional argentino.
