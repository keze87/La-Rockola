import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useTrack } from '@/composables/useTrack';
import { trackMap, urlMetadata, favorites, queueState, currentTrackPath, isPaused } from '@/composables/player/state';
import type { Track } from '@/types';

describe('useTrack', () => {
	beforeEach(() => {
		trackMap.value = {};
		urlMetadata.value = {};
		favorites.value = [];
		queueState.value = [];
		currentTrackPath.value = null;
		isPaused.value = false;
	});

	it('returns metadata from trackMap when available', () => {
		const track: Track = {
			path: '/music/rock.flac',
			display_title: 'Seminare',
			display_artist: 'Serú Girán',
			album: 'Serú Girán',
			duration_str: '3:27',
		};
		trackMap.value['/music/rock.flac'] = track;

		const { displayTitle, displayArtist, durationStr, isPlaying, isFavorite, isNext } = useTrack(track);

		expect(displayTitle.value).toBe('Seminare');
		expect(displayArtist.value).toBe('Serú Girán');
		expect(durationStr.value).toBe('3:27');
		expect(isPlaying.value).toBe(false);
		expect(isFavorite.value).toBe(false);
		expect(isNext.value).toBe(false);
	});

	it('reflects dynamic playing, favorite, and queue status', () => {
		const path = '/music/cancion.mp3';
		trackMap.value[path] = {
			path,
			display_title: 'Canción para mi muerte',
			display_artist: 'Sui Generis',
		};

		const { isPlaying, isFavorite, isNext, queueIndex, toggleFavorite } = useTrack(path);

		expect(isPlaying.value).toBe(false);
		expect(isFavorite.value).toBe(false);
		expect(isNext.value).toBe(false);
		expect(queueIndex.value).toBe(-1);

		currentTrackPath.value = path;
		expect(isPlaying.value).toBe(true);

		queueState.value = [path, '/other/song.mp3'];
		expect(isNext.value).toBe(true);
		expect(queueIndex.value).toBe(0);

		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		toggleFavorite();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'toggle_favorite', path }),
			})
		);

		favorites.value = [path];
		expect(isFavorite.value).toBe(true);
	});

	it('handles web stream URLs and unknown fallbacks', () => {
		const url = 'https://youtube.com/watch?v=live';
		urlMetadata.value[url] = {
			path: url,
			display_title: 'Charly Live',
			display_artist: 'Canal Rock',
		};

		const { displayTitle, displayArtist } = useTrack(url);
		expect(displayTitle.value).toBe('Charly Live');
		expect(displayArtist.value).toBe('Canal Rock');

		const unknownUrl = 'https://stream.radio/rock';
		const unknown = useTrack(unknownUrl);
		expect(unknown.displayTitle.value).toBe(unknownUrl);
		expect(unknown.displayArtist.value).toBe('🌐 De la Internet');
	});
});
