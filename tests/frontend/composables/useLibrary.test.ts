import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useLibrary } from '@/composables/player/useLibrary';
import {
	activeSort,
	currentTracks,
	defaultSort,
	originalTracks,
	trackMap,
	urlParams,
} from '@/composables/player/state';
import type { Track } from '@/types';

describe('useLibrary', () => {
	const sampleTracks: Track[] = [
		{ path: '/m/1.mp3', artist: 'Charly García', title: 'Nos siguen pegando abajo', mood_score: 0.8 },
		{ path: '/m/2.mp3', artist: 'Fito Páez', title: '11 y 6', mood_score: 0.5 },
		{ path: '/m/3.mp3', artist: 'Charly García', title: 'Demoliendo hoteles', mood_score: 0.95 },
	];

	beforeEach(() => {
		originalTracks.value = [...sampleTracks];
		currentTracks.value = [...sampleTracks];
		trackMap.value = {};
		activeSort.value = 'time';
		defaultSort.value = 'time';
		delete urlParams.vibra;
	});

	it('getTrackInfo returns track or friendly fallbacks', () => {
		const { getTrackInfo } = useLibrary();

		trackMap.value['/m/1.mp3'] = sampleTracks[0];
		expect(getTrackInfo('/m/1.mp3')).toEqual(sampleTracks[0]);

		const unknown = getTrackInfo('/m/unknown.mp3');
		expect(unknown.display_title).toBe('Audio Misterioso');

		const web = getTrackInfo('https://stream.radio/live');
		expect(web.display_title).toBe('https://stream.radio/live');
		expect(web.display_artist).toBe('🌐 De la Internet');
	});

	it('sortLibrary sorts by artist and title alphabetically and updates activeSort', () => {
		const { sortLibrary } = useLibrary();

		sortLibrary('artist');
		expect(activeSort.value).toBe('artist');
		expect(currentTracks.value.map((t) => t.title)).toEqual([
			'Demoliendo hoteles',
			'Nos siguen pegando abajo',
			'11 y 6',
		]);
	});

	it('sortLibrary sorts by mood_score descending and updates activeSort', () => {
		const { sortLibrary } = useLibrary();

		sortLibrary('mood');
		expect(activeSort.value).toBe('mood');
		expect(currentTracks.value.map((t) => t.title)).toEqual([
			'Demoliendo hoteles',
			'Nos siguen pegando abajo',
			'11 y 6',
		]);
	});

	it('sortLibrary with shuffle generates reproducible seed and updates activeSort', () => {
		const { sortLibrary } = useLibrary();

		sortLibrary('shuffle');
		expect(activeSort.value).toBe('shuffle');
		const generatedSeed = urlParams.vibra;
		expect(generatedSeed).toBeDefined();

		const firstShuffleOrder = currentTracks.value.map((t) => t.path);

		sortLibrary('shuffle', true);
		expect(currentTracks.value.map((t) => t.path)).toEqual(firstShuffleOrder);
	});

	it('loadLibrary respects defaultSort when loading tracks without vibra parameter', async () => {
		defaultSort.value = 'artist';
		activeSort.value = 'artist';
		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [...sampleTracks] }),
		} as unknown as Response);

		const { loadLibrary } = useLibrary();
		await loadLibrary(false);

		expect(currentTracks.value.map((t) => t.title)).toEqual([
			'Demoliendo hoteles',
			'Nos siguen pegando abajo',
			'11 y 6',
		]);
	});

	it('saveDefaultSort dispatches command and updates defaultSort', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { saveDefaultSort } = useLibrary();
		await saveDefaultSort('mood');

		expect(defaultSort.value).toBe('mood');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_default_sort', sort: 'mood' }),
			})
		);
	});
});
