# 🦫 La Rockola del Carpincho

> **A seamless, low-friction music player built for shared listening, lightweight local playback, and real-time remote control.**

---

## 📋 Why?

Traditional desktop media players and modern streaming apps suffer from several recurring friction points:

1. **Cumbersome Local Control:** Standard media players often feel bloated, resource-heavy, and clunky to navigate while multitasking.
2. **Lack of Shared/Social Controls:** In social settings—like a gathering, party, or office—letting guests queue songs usually means passing a phone around, sharing unlocked screens, or constantly interrupting the host.
3. **Complex Remote Management:** Managing music playback from across the room often requires installing bulky mobile apps, setting up complex media servers, or dealing with network pairing headaches.

---

## 💡 The Solution

**La Rockola del Carpincho** solves these challenges by combining a sleek desktop player interface with an instant remote control web interface:

* **Instant Socket-Based Remote Control:** Control playback, manage queues, and browse music remotely from any device on the same local network without installing extra software.
* **Social Queueing:** Allows friends and guests to easily add tracks to a shared queue from their phones using a simple, mobile-friendly interface.
* **Lightweight & Fast Performance:** Built with Vue 3, Vite, and MPV integration to ensure minimal CPU/RAM usage while offering rich features like track searching, synchronized lyrics, context menus, and haptic feedback on mobile.

---

## ✨ Key Features

* 🎵 **Full Track Management:** Browse, search, filter, and manage your local library and queues effortlessly.
* 🔥 **Campfire Mode:** Social queuing made easy—let anyone queue songs without giving up control of your master device.
* 🎙️ **Synchronized Lyrics:** Integrated lyrics display for an immersive listening or sing-along experience.
* 🎛️ **Precision Playback Controls:** Advanced playback adjustments, sliders, volume controls, and configurable keyboard shortcuts.
* 📱 **Mobile-Optimized Remote UI:** Responsive control interface built with tactile controls and haptic feedback.
* 🪟 **MPV Native Player Integration:** Leverages MPV for rock-solid audio decoding and smooth window management.

---

## 🛠️ Tech Stack

* **Frontend Framework:** [Vue 3](https://vuejs.org/) (Composition API with TypeScript)
* **Build Tool:** [Vite](https://vitejs.dev/)
* **Styling:** CSS3 / tailwindcss
* **State & Logic:** Vue Composables Architecture
* **Real-time Networking:** WebSockets (Real-time remote syncing)
* **Audio Engine:** `mpv` integration
* **Notifications:** `vue-sonner` toast notifications

---

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
├── vite.config.ts           # Vite configuration
└── package.json             # Dependencies and scripts
```
