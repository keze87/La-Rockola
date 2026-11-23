// Store de dominio para pestañas activas, Modo Fogón, red y puntero de transporte WebSocket.

import { computed, ref } from 'vue';
import type { Track } from '../types';

export const activeTab = ref<string>('library');
export const isTabsBarHidden = ref<boolean>(false);
export const isFogonMode = ref<boolean>(false);
export const isLyricsEditorOpen = ref<boolean>(false);
export const lyricsEditorTrack = ref<Track | null>(null);
export const showFogonVolume = ref<boolean>(false);
export const serverUrl = ref<string | null>(null);
export const localIp = ref<string | null>(null);

interface OpenModalEntry {
	id: string;
	close: () => void;
}

export const activeModalStack = ref<OpenModalEntry[]>([]);
export const hasOpenModal = computed(() => activeModalStack.value.length > 0);

export function registerOpenModal(id: string, close: () => void): void {
	const filtered = activeModalStack.value.filter((item) => item.id !== id);
	filtered.push({ id, close });
	activeModalStack.value = filtered;
}

export function unregisterOpenModal(id: string): void {
	if (activeModalStack.value.some((item) => item.id === id)) {
		activeModalStack.value = activeModalStack.value.filter((item) => item.id !== id);
	}
}

export function closeTopModal(): boolean {
	const top = activeModalStack.value[activeModalStack.value.length - 1];
	if (!top) return false;
	unregisterOpenModal(top.id);
	top.close();
	return true;
}

let wsSend: ((data: string) => void) | null = null;
let wsClose: (() => void) | null = null;

export function setWsSend(sendFn: ((data: string) => void) | null, closeFn: (() => void) | null = null) {
	wsSend = sendFn;
	wsClose = closeFn;
}

export function closeSocketHandle(): void {
	const closeFn = wsClose;
	wsSend = null;
	wsClose = null;
	if (closeFn) {
		try {
			closeFn();
		} catch {
			// Ignoramos errores al cerrar un socket ya cerrado
		}
	}
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
		closeSocketHandle,
		isSocketConnected,
		sendRaw,
	};
}
