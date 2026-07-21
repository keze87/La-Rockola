import { useApi } from '../useApi';
import { useToasts } from './useToasts';
import { activeTab, currentTracks, isScanning, originalTracks, queueState, trackMap, urlMetadata } from './state';
import type { Track } from '../../types';

export function useLibrary() {
	const api = useApi();
	const { showToast } = useToasts();

	function normalizeString(s: string) {
		return s
			? s
					.normalize('NFD')
					.replace(/[\u0300-\u036f]/g, '')
					.toLowerCase()
			: '';
	}

	function getTrackInfo(path: string | null | undefined): Track {
		if (!path) return { display_title: 'Desconocido', display_artist: 'Vaya uno a saber', path: '' };

		if (trackMap.value[path]) return trackMap.value[path];

		if (urlMetadata.value[path]) return urlMetadata.value[path];

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

				const urlParams = new URLSearchParams(window.location.search);

				if (urlParams.has('vibra')) {
					sortLibrary('shuffle', true);
				} else {
					currentTracks.value = [...data.data];
				}
			}
		} catch (err) {
			console.error(err);
			showToast('Uy! Se volcó el mate conectando con la API', 'error');
		} finally {
			if (forceScan) isScanning.value = false;
		}
	}

	function sortLibrary(type: 'time' | 'artist' | 'mood' | 'shuffle', keepSeed: boolean = false) {
		if (type === 'time') {
			const url = new URL(window.location.href);
			url.searchParams.delete('vibra');
			window.history.pushState({}, '', url.toString());
			currentTracks.value = [...originalTracks.value];
		} else if (type === 'artist') {
			const url = new URL(window.location.href);
			url.searchParams.delete('vibra');
			window.history.pushState({}, '', url.toString());
			currentTracks.value = [...currentTracks.value].sort((a, b) => {
				const cmp = (a.artist || '').localeCompare(b.artist || '');
				return cmp === 0 ? (a.title || '').localeCompare(b.title || '') : cmp;
			});
		} else if (type === 'mood') {
			const url = new URL(window.location.href);
			url.searchParams.delete('vibra');
			window.history.pushState({}, '', url.toString());
			currentTracks.value = [...currentTracks.value].sort((a, b) => {
				return (b.mood_score || 0) - (a.mood_score || 0);
			});
		} else if (type === 'shuffle') {
			let seed: number;
			const urlParams = new URLSearchParams(window.location.search);
			const seedParam = urlParams.get('vibra');

			if (keepSeed && seedParam !== null && !isNaN(parseInt(seedParam))) {
				seed = parseInt(seedParam);
			} else {
				seed = Math.floor(Math.random() * 1000000);
				const url = new URL(window.location.href);
				url.searchParams.set('vibra', seed.toString());
				window.history.pushState({}, '', url.toString());
			}

			// Mulberry32 PRNG for a reproducible shuffle
			let a = seed;
			const randomFunc = () => {
				let t = (a += 0x6d2b79f5);
				t = Math.imul(t ^ (t >>> 15), t | 1);
				t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
				return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
			};

			const array = [...originalTracks.value];
			for (let i = array.length - 1; i > 0; i--) {
				const j = Math.floor(randomFunc() * (i + 1));
				[array[i], array[j]] = [array[j], array[i]];
			}
			currentTracks.value = array;
		}
		activeTab.value = 'library';
	}

	return { getTrackInfo, loadLibrary, normalizeString, queueIndex, sortLibrary };
}
