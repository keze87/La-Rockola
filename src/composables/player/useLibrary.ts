import { watch } from 'vue';
import { useApi } from '../useApi';
import { useToasts } from './useToasts';
import {
	activeSort,
	currentTracks,
	defaultSort,
	djMode,
	filteredTracks,
	isScanning,
	originalTracks,
	queueState,
	trackMap,
	urlMetadata,
	urlParams,
} from './state';
import type { Track } from '../../types';

// Sincronización singleton a nivel de módulo: se registra exactamente una vez en toda la app
let syncTimeout: ReturnType<typeof setTimeout> | null = null;
function syncLibraryWithDj() {
	if (djMode.value !== 'library') return;
	if (syncTimeout) clearTimeout(syncTimeout);
	syncTimeout = setTimeout(() => {
		const api = useApi();
		const paths = filteredTracks.value.map((t) => t.path);
		api.command('sync_dj_library', { paths }).catch((e) => {
			console.error('Error sincronizando biblioteca con DJ Bara:', e);
		});
	}, 250);
}

watch([filteredTracks, djMode], () => {
	syncLibraryWithDj();
});

export function useLibrary() {
	const api = useApi();
	const { showToast } = useToasts();

	function getTrackInfo(path: string | null | undefined): Track {
		if (!path) return { display_title: 'Desconocido', display_artist: 'Vaya uno a saber', path: '' };

		if (trackMap.value[path]) return trackMap.value[path];

		if (urlMetadata.value[path]) return urlMetadata.value[path];

		if (path.includes('radio_announcement')) {
			return {
				path,
				display_title: 'Transmisión de Cabina',
				display_artist: 'Transmisión de Cabina 🎙️',
			};
		}

		const isUrl = path.startsWith('http');
		return {
			path,
			display_title: isUrl ? path : 'Audio Misterioso',
			display_artist: isUrl ? '🌐 De la Internet' : 'Vaya uno a saber',
		};
	}

	function queueIndex(path: string): number {
		return queueState.value.indexOf(path);
	}

	async function loadLibrary(forceScan: boolean = false) {
		if (forceScan) isScanning.value = true;

		try {
			const data = forceScan ? await api.scanLibrary() : await api.getLibrary();

			if (data && data.data) {
				originalTracks.value = [...data.data];
				const map: Record<string, Track> = {};
				data.data.forEach((t: Track) => (map[t.path] = t));
				trackMap.value = map;

				if (data.default_sort) {
					defaultSort.value = data.default_sort as 'time' | 'artist' | 'mood' | 'shuffle';
				}

				if (urlParams.vibra !== undefined) {
					sortLibrary('shuffle', true);
				} else {
					const targetSort = activeSort.value || defaultSort.value || 'time';
					sortLibrary(targetSort, false);
				}
			}
		} catch (err) {
			console.error(err);
			showToast('Uy! Se volcó el mate conectando con la API', 'error');
		} finally {
			if (forceScan) isScanning.value = false;
		}
	}

	async function saveDefaultSort(sort: 'time' | 'artist' | 'mood' | 'shuffle') {
		await api.command('set_default_sort', { sort });
		defaultSort.value = sort;
	}

	function sortLibrary(type: 'time' | 'artist' | 'mood' | 'shuffle', keepSeed: boolean = false) {
		activeSort.value = type;
		const source = originalTracks.value.length > 0 ? originalTracks.value : currentTracks.value;

		if (type === 'time') {
			delete urlParams.vibra;
			currentTracks.value = [...source];
		} else if (type === 'artist') {
			delete urlParams.vibra;
			currentTracks.value = [...source].sort((a, b) => {
				const cmp = (a.artist || '').localeCompare(b.artist || '');
				return cmp === 0 ? (a.title || '').localeCompare(b.title || '') : cmp;
			});
		} else if (type === 'mood') {
			delete urlParams.vibra;
			currentTracks.value = [...source].sort((a, b) => {
				const scoreB = b.mood_score !== undefined ? b.mood_score : (b.bpm ?? 0);
				const scoreA = a.mood_score !== undefined ? a.mood_score : (a.bpm ?? 0);
				return scoreB - scoreA;
			});
		} else if (type === 'shuffle') {
			let seed: number;
			const seedParam = urlParams.vibra;

			if (keepSeed && seedParam !== undefined && !isNaN(parseInt(seedParam))) {
				seed = parseInt(seedParam);
			} else {
				seed = Math.floor(Math.random() * 1000000);
				urlParams.vibra = seed.toString();
			}

			// Generador pseudoaleatorio Mulberry32 para un orden aleatorio reproducible
			let a = seed;
			const randomFunc = () => {
				let t = (a += 0x6d2b79f5);
				t = Math.imul(t ^ (t >>> 15), t | 1);
				t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
				return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
			};

			const array = [...source];
			for (let i = array.length - 1; i > 0; i--) {
				const j = Math.floor(randomFunc() * (i + 1));
				[array[i], array[j]] = [array[j], array[i]];
			}
			currentTracks.value = array;
		}
	}

	if (typeof window !== 'undefined') {
		window.addEventListener('rockola:vibra', () => {
			sortLibrary('shuffle', true);
		});
	}

	return { filteredTracks, getTrackInfo, loadLibrary, queueIndex, saveDefaultSort, sortLibrary };
}
