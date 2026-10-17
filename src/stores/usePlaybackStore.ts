// Store de dominio para el transporte de reproducción, volumen, tiempo y estado del reproductor local/remoto.

import { computed, ref } from 'vue';
import type { Track } from '../types';

export const currentTrackPath = ref<string | null>(null);
export const historyState = ref<string[]>([]);
export const isPaused = ref<boolean>(false);
export const pauseAfterPath = ref<string | null>(null);
export const topPlayedState = ref<Track[]>([]);

export const duration = ref<number>(0);
export const pendingSeekTime = ref<number | null>(null);
export const isDraggingSeek = ref<boolean>(false);
export const listenLocally = ref<boolean>(false);
export const hasLocalPlayer = ref<boolean>(false);
export const localPlayerRef = ref<HTMLAudioElement | null>(null);
export const localTimePos = ref<number>(0);
export const serverMuted = ref<boolean>(false);
export const timePos = ref<number>(0);
export const volume = ref<number>(100);
export const mpvVisible = ref<boolean>(false);

export const isPlaying = computed(() => !!currentTrackPath.value && !isPaused.value);
export const volIcon = computed(() => {
	if (serverMuted.value || volume.value === 0) return 'volume_off';
	if (volume.value <= 40) return 'volume_down';
	if (volume.value <= 100) return 'volume_up';
	return 'surround_sound';
});

export function usePlaybackStore() {
	return {
		currentTrackPath,
		historyState,
		isPaused,
		pauseAfterPath,
		topPlayedState,
		duration,
		pendingSeekTime,
		isDraggingSeek,
		listenLocally,
		hasLocalPlayer,
		localPlayerRef,
		localTimePos,
		serverMuted,
		timePos,
		volume,
		mpvVisible,
		isPlaying,
		volIcon,
	};
}
