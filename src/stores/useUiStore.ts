// Store de dominio para pestañas activas, Modo Fogón, red y puntero de transporte WebSocket.

import { ref } from 'vue';

export const activeTab = ref<string>('library');
export const isFogonMode = ref<boolean>(false);
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
		isFogonMode,
		showFogonVolume,
		serverUrl,
		localIp,
		setWsSend,
		isSocketConnected,
		sendRaw,
	};
}
