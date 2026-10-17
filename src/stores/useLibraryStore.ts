// Store de dominio para la biblioteca musical, estado de escaneo, favoritos y búsqueda.

import { useUrlSearchParams } from '@vueuse/core';
import { ref } from 'vue';
import type { ScanStatus, Track } from '../types';

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
export const urlParams = useUrlSearchParams<{ vibra?: string }>('history');

export function useLibraryStore() {
	return {
		currentTracks,
		favorites,
		isScanning,
		scanStatus,
		librarySearchQuery,
		originalTracks,
		trackMap,
		urlMetadata,
		urlParams,
	};
}
