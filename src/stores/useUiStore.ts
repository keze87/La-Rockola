// Store de dominio para pestañas activas, Modo Fogón, red y puntero de transporte WebSocket.

import { ref } from 'vue';
import type { Track } from '../types';

export const activeTab = ref<string>('library');
export const isTabsBarHidden = ref<boolean>(false);
export const isFogonMode = ref<boolean>(false);
export const isLyricsEditorOpen = ref<boolean>(false);
export const lyricsEditorTrack = ref<Track | null>(null);
export const showFogonVolume = ref<boolean>(false);
export const serverUrl = ref<string | null>(null);
export const localIp = ref<string | null>(null);

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

export function useUiStore() {
	return {
		activeTab,
		isTabsBarHidden,
		isFogonMode,
		isLyricsEditorOpen,
		lyricsEditorTrack,
		showFogonVolume,
		serverUrl,
		localIp,
		setWsSend,
		isSocketConnected,
		sendRaw,
	};
}
