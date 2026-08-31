import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useQueue } from '@/composables/player/useQueue';
import { currentTrackPath, pauseAfterPath, queueState, trackMap } from '@/composables/player/state';

describe('useQueue', () => {
	beforeEach(() => {
		currentTrackPath.value = null;
		pauseAfterPath.value = null;
		queueState.value = [];
		trackMap.value = {
			'/m/1.mp3': { path: '/m/1.mp3', display_title: 'Track One', display_artist: 'Artist' },
			'/m/2.mp3': { path: '/m/2.mp3', display_title: 'Track Two', display_artist: 'Artist' },
		};
	});

	it('toggleQueue sends toggle_queue command', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { toggleQueue } = useQueue();
		await toggleQueue('/m/1.mp3', false);

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'toggle_queue', path: '/m/1.mp3' }),
			})
		);
	});

	it('handleLibraryClick pauses if clicking currently playing track, otherwise toggles queue', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { handleLibraryClick } = useQueue();

		currentTrackPath.value = '/m/1.mp3';
		handleLibraryClick(trackMap.value['/m/1.mp3']);

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'pause' }),
			})
		);

		handleLibraryClick(trackMap.value['/m/2.mp3']);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'toggle_queue', path: '/m/2.mp3' }),
			})
		);
	});

	it('togglePauseAfterCurrent sets and clears pause_after_path', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { togglePauseAfterCurrent } = useQueue();

		currentTrackPath.value = '/m/1.mp3';

		await togglePauseAfterCurrent();
		expect(pauseAfterPath.value).toBe('/m/1.mp3');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'pause_after', path: '/m/1.mp3' }),
			})
		);

		await togglePauseAfterCurrent();
		expect(pauseAfterPath.value).toBeNull();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'pause_after', path: '' }),
			})
		);
	});
});
