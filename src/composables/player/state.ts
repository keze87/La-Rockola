import { useUrlSearchParams } from '@vueuse/core';
import { ref, computed } from 'vue';
import type { ScanStatus, Track } from '../../types';

// Estado reactivo central del reproductor, compartido entre todos los composables
// de esta carpeta. Este archivo no tiene lógica de negocio: solo las refs crudas y
// los valores directamente derivados (isPlaying, volIcon). Cada composable hermano
// maneja el *comportamiento* de una parte de este estado para mantener la lógica
// modular en vez de sepultada en un archivo gigante.

// Navegación
export const activeTab = ref<string>('library');

// Reproducción actual / transporte
export const currentTrackPath = ref<string | null>(null);
export const historyState = ref<string[]>([]);
export const isPaused = ref<boolean>(false);
export const pauseAfterPath = ref<string | null>(null);
export const topPlayedState = ref<Track[]>([]);

// Biblioteca
export const currentTracks = ref<Track[]>([]);
export const favorites = ref<string[]>([]);
export const isScanning = ref<boolean>(false);
export const scanStatus = ref<ScanStatus>({
	is_scanning: false,
	is_analyzing_mood: false,
	phase: 'idle',
	current: 0,
	total: 0,
	message: '',
});
export const librarySearchQuery = ref<string>('');
export const originalTracks = ref<Track[]>([]);
export const trackMap = ref<Record<string, Track>>({});
export const urlMetadata = ref<Record<string, Track>>({});

// Fila de reproducción
export const queueState = ref<string[]>([]);

// Parámetros de búsqueda reactivos en la URL (modo history), sincronizados en ambas direcciones.
// Los usa `sortLibrary` en useLibrary para el parámetro `vibra` (semilla de mezcla) en lugar
// de armar URLSearchParams + history.pushState en cada llamada. Se ejecuta acá a nivel de módulo.
export const urlParams = useUrlSearchParams<{ vibra?: string }>('history');

// Auto-DJ (espejado desde el servidor; acá no hay lógica de cliente)
export const djCarpinchoEnabled = ref<boolean>(false);
export const djNextTrack = ref<Track | null>(null);
export const djSafeModeEnabled = ref<boolean>(false);

// Modo Radio (locutor con hora y fortunas entre temas)
export const radioModeEnabled = ref<boolean>(false);
export const isSynthesizingRadio = ref<boolean>(false);
export const isPlayingRadioAnnouncement = ref<boolean>(false);
export const weatherLocation = ref<string>('San Miguel de Tucumán');

// Reproducción de audio local y Media Session
export const duration = ref<number>(0);
export const pendingSeekTime = ref<number | null>(null);
export const isDraggingSeek = ref<boolean>(false);
export const listenLocally = ref<boolean>(false);
export const localPlayerRef = ref<HTMLAudioElement | null>(null); // vinculado al elemento <audio> en App.vue
export const localTimePos = ref<number>(0);
export const serverMuted = ref<boolean>(false);
export const timePos = ref<number>(0);
export const volume = ref<number>(100);

// Visibilidad de la ventana de MPV
export const mpvVisible = ref<boolean>(true);

// Modo Fogón
export const isFogonMode = ref<boolean>(false);
export const showFogonVolume = ref<boolean>(false);

// Red y URLs del servidor
export const serverUrl = ref<string | null>(null);
export const localIp = ref<string | null>(null);

// Capacidades del servidor
export const hasEdgeTts = ref<boolean>(false);
export const hasFfmpeg = ref<boolean>(false);

export const isPlaying = computed(() => !!currentTrackPath.value && !isPaused.value);
export const volIcon = computed(() => {
	if (serverMuted.value || volume.value == 0) return 'volume_off';
	if (volume.value <= 40) return 'volume_down';
	if (volume.value <= 100) return 'volume_up';
	return 'surround_sound';
});

// --- Puntero de transporte WebSocket crudo ---
// Un par de composables (useSocket, useLocalPlayback) necesitan mandar
// mensajes directos por el socket, por fuera del flujo petición/respuesta
// `sendCmd` (HTTP). Se guarda acá en vez de adentro de useSocket para que
// useLocalPlayback no tenga que importar useSocket solo para mandar
// `local_player_update` (evitando dependencias circulares).
let wsSend: ((data: string) => void) | null = null;

export function setWsSend(sendFn: (data: string) => void) {
	wsSend = sendFn;
}

export function isSocketConnected(): boolean {
	return !!wsSend;
}

export function sendRaw(payload: Record<string, unknown>) {
	if (wsSend) wsSend(JSON.stringify(payload));
}
