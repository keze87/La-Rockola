import { ref, computed } from 'vue';

// Central reactive state for the player, shared across every composable in
// this folder. This file holds no business logic — just the raw refs and
// the handful of values purely derived from them (isPlaying, volIcon). Each
// sibling composable owns the *behavior* for one slice of this state; this
// keeps that behavior easy to find instead of buried in one giant file.

// Navigation
export const activeTab = ref('library');

// Now playing / transport
export const currentTrackPath = ref(null);
export const historyState = ref([]);
export const isPaused = ref(false);
export const pauseAfterPath = ref(null);
export const topPlayedState = ref([]);

// Library
export const currentTracks = ref([]);
export const favorites = ref([]);
export const isScanning = ref(false);
export const librarySearchQuery = ref('');
export const originalTracks = ref([]);
export const trackMap = ref({});
export const urlMetadata = ref({});

// Queue
export const queueState = ref([]);

// Auto-DJ (mirrored from the server — no client-side logic lives here)
export const djCarpinchoEnabled = ref(false);
export const djNextTrack = ref(null);
export const djSafeModeEnabled = ref(false);

// Local audio playback & Media Session
export const duration = ref(0);
export const ignoreServerTimeUntil = ref(0);
export const isDraggingSeek = ref(false);
export const listenLocally = ref(false);
export const localPlayerRef = ref(null); // bound to the <audio> element in App.vue
export const localTimePos = ref(0);
export const serverMuted = ref(false);
export const timePos = ref(0);
export const volume = ref(100);

// MPV window visibility
export const mpvVisible = ref(true);

// Modo Fogón
export const isFogonMode = ref(false);
export const showFogonVolume = ref(false);

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
let wsSend = null;

export function setWsSend(sendFn) {
	wsSend = sendFn;
}

export function isSocketConnected() {
	return !!wsSend;
}

export function sendRaw(payload) {
	if (wsSend) wsSend(JSON.stringify(payload));
}
