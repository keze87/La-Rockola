// Store de dominio para DJ Carpincho, Modo Radio, ubicación climática y capacidades del servidor.

import { ref } from 'vue';
import type { Track } from '../types';

export const djCarpinchoEnabled = ref<boolean>(false);
export const djNextTrack = ref<Track | null>(null);
export const djSafeModeEnabled = ref<boolean>(false);

export const radioModeEnabled = ref<boolean>(false);
export const isSynthesizingRadio = ref<boolean>(false);
export const isPlayingRadioAnnouncement = ref<boolean>(false);
export const weatherLocation = ref<string>('San Miguel de Tucumán');

export const hasEdgeTts = ref<boolean>(false);
export const hasFfmpeg = ref<boolean>(false);

export function useRadioStore() {
	return {
		djCarpinchoEnabled,
		djNextTrack,
		djSafeModeEnabled,
		radioModeEnabled,
		isSynthesizingRadio,
		isPlayingRadioAnnouncement,
		weatherLocation,
		hasEdgeTts,
		hasFfmpeg,
	};
}
