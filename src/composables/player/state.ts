import { useUrlSearchParams } from '@vueuse/core';
import { ref, computed } from 'vue';
import type { Track } from '../../types';

// Central reactive state for the player, shared across every composable in
// this folder. This file holds no business logic — just the raw refs and
// the handful of values purely derived from them (isPlaying, volIcon). Each
// sibling composable owns the *behavior* for one slice of this state; this
// keeps that behavior easy to find instead of buried in one giant file.

// Navigation
export const activeTab = ref<string>('library');

// Now playing / transport
export const currentTrackPath = ref<string | null>(null);
export const historyState = ref<string[]>([]);
export const isPaused = ref<boolean>(false);
export const pauseAfterPath = ref<string | null>(null);
export const topPlayedState = ref<Track[]>([]);

// Library
export const currentTracks = ref<Track[]>([]);
export const favorites = ref<string[]>([]);
export const isScanning = ref<boolean>(false);
export const librarySearchQuery = ref<string>('');
export const originalTracks = ref<Track[]>([]);
export const trackMap = ref<Record<string, Track>>({});
export const urlMetadata = ref<Record<string, Track>>({});

// Queue
export const queueState = ref<string[]>([]);

// Reactive URL search params (history mode), synced automatically both ways —
// used by useLibrary's sortLibrary for the `vibra` shuffle-seed param instead
// of each caller building its own URLSearchParams + history.pushState. Called
// once here, at module scope, rather than per-component.
export const urlParams = useUrlSearchParams<{ vibra?: string }>('history');

// Auto-DJ (mirrored from the server — no client-side logic lives here)
export const djCarpinchoEnabled = ref<boolean>(false);
export const djNextTrack = ref<Track | null>(null);
export const djSafeModeEnabled = ref<boolean>(false);

// Local audio playback & Media Session
export const duration = ref<number>(0);
export const pendingSeekTime = ref<number | null>(null);
export const isDraggingSeek = ref<boolean>(false);
export const listenLocally = ref<boolean>(false);
export const localPlayerRef = ref<HTMLAudioElement | null>(null); // bound to the <audio> element in App.vue
export const localTimePos = ref<number>(0);
export const serverMuted = ref<boolean>(false);
export const timePos = ref<number>(0);
export const volume = ref<number>(100);

// MPV window visibility
export const mpvVisible = ref<boolean>(true);

// Modo Fogón
export const isFogonMode = ref<boolean>(false);
export const showFogonVolume = ref<boolean>(false);

export const isPlaying = computed(() => !!currentTrackPath.value && !isPaused.value);
export const volIcon = computed(() => {
	if (serverMuted.value || volume.value == 0) return 'volume_off';
	if (volume.value <= 40) return 'volume_down';
	if (volume.value <= 100) return 'volume_up';
	return 'surround_sound';
});

// --- Raw WebSocket transport pointer ---
// A couple of composables (useSocket, useLocalPlayback) need to push
// messages straight over the socket, outside of the request/response
// `sendCmd` (HTTP) flow. Kept here rather than inside useSocket.js so
// useLocalPlayback doesn't need to import useSocket just to send a
// `local_player_update` message — which would risk a circular import,
// since useSocket needs to import useLocalPlayback the other way for
// `local_player_seek` / `local_player_claim_result` handling.
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
