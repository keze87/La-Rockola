// Store de dominio para la biblioteca musical, estado de escaneo, favoritos y búsqueda.

import { useUrlSearchParams } from '@vueuse/core';
import { computed, ref } from 'vue';
import Fuse from 'fuse.js';
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
export const activeSort = ref<'time' | 'artist' | 'mood' | 'shuffle'>('time');
export const defaultSort = ref<'time' | 'artist' | 'mood' | 'shuffle'>('time');
export const showFavoritesOnly = ref<boolean>(false);

export const fuse = computed(() => {
	return new Fuse(currentTracks.value, {
		keys: ['title', 'artist', 'display_title', 'display_artist'],
		threshold: 0.3,
		ignoreLocation: true,
	});
});

export const filteredTracks = computed(() => {
	let tracks = currentTracks.value;

	if (showFavoritesOnly.value) {
		tracks = tracks.filter((t) => favorites.value.includes(t.path));
	}

	const query = librarySearchQuery.value.trim();
	if (!query) return tracks;

	return fuse.value.search(query).map((result) => result.item);
});

export function useLibraryStore() {
	return {
		activeSort,
		currentTracks,
		defaultSort,
		favorites,
		filteredTracks,
		isScanning,
		scanStatus,
		showFavoritesOnly,
		librarySearchQuery,
		originalTracks,
		trackMap,
		urlMetadata,
		urlParams,
	};
}
