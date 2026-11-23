import { beforeEach, describe, expect, it } from 'vitest';
import {
	BOOT_SNAPSHOT_STORAGE_KEY,
	MAX_SNAPSHOT_TRACKS,
	clearSnapshotHydrationFlag,
	hydrateFromBootSnapshot,
	isHydratedFromSnapshot,
	saveBootSnapshot,
} from '../../../src/composables/player/useLocalSnapshot';
import { currentTracks, favorites, originalTracks, trackMap } from '../../../src/stores/useLibraryStore';
import { currentTrackPath, duration } from '../../../src/stores/usePlaybackStore';
import { queueState } from '../../../src/stores/useQueueStore';
import type { Track } from '../../../src/types';

function makeTrack(i: number): Track {
	return {
		path: `/music/track-${i}.mp3`,
		title: `Tema ${i}`,
		artist: `Artista ${i}`,
		display_title: `Tema ${i}`,
		display_artist: `Artista ${i}`,
		duration: 180,
	};
}

describe('useLocalSnapshot', () => {
	beforeEach(() => {
		localStorage.clear();
		currentTracks.value = [];
		originalTracks.value = [];
		trackMap.value = {};
		queueState.value = [];
		currentTrackPath.value = null;
		duration.value = 0;
		favorites.value = [];
		clearSnapshotHydrationFlag();
	});

	it('guarda hasta MAX_SNAPSHOT_TRACKS e hidrata los stores inmediatamente', () => {
		const manyTracks = Array.from({ length: 120 }, (_, i) => makeTrack(i));
		originalTracks.value = manyTracks;
		currentTracks.value = manyTracks;
		queueState.value = ['/music/track-1.mp3', '/music/track-2.mp3'];
		currentTrackPath.value = '/music/track-0.mp3';
		duration.value = 185;
		favorites.value = ['/music/track-0.mp3'];

		saveBootSnapshot('host');

		// Limpiamos estado en memoria simulando arranque en frío
		currentTracks.value = [];
		originalTracks.value = [];
		trackMap.value = {};
		queueState.value = [];
		currentTrackPath.value = null;
		duration.value = 0;
		favorites.value = [];

		const hydrated = hydrateFromBootSnapshot('host');
		expect(hydrated).toBe(true);
		expect(isHydratedFromSnapshot.value).toBe(true);
		expect(currentTracks.value.length).toBe(MAX_SNAPSHOT_TRACKS);
		expect(originalTracks.value.length).toBe(MAX_SNAPSHOT_TRACKS);
		expect(queueState.value).toEqual(['/music/track-1.mp3', '/music/track-2.mp3']);
		expect(currentTrackPath.value).toBe('/music/track-0.mp3');
		expect(duration.value).toBe(185);
		expect(favorites.value).toEqual(['/music/track-0.mp3']);
		expect(trackMap.value['/music/track-0.mp3']?.display_title).toBe('Tema 0');

		clearSnapshotHydrationFlag();
		expect(isHydratedFromSnapshot.value).toBe(false);
	});

	it('tolera JSON corrupto y no hidrata si cambia el modo', () => {
		localStorage.setItem(BOOT_SNAPSHOT_STORAGE_KEY, '{corrupto');
		expect(hydrateFromBootSnapshot('host')).toBe(false);
		expect(isHydratedFromSnapshot.value).toBe(false);

		originalTracks.value = [makeTrack(1)];
		saveBootSnapshot('host');
		currentTracks.value = [];
		originalTracks.value = [];
		expect(hydrateFromBootSnapshot('remote:http://192.168.1.10:1729')).toBe(false);
	});
});
