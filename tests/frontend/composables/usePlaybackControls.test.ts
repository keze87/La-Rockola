import { describe, it, expect, beforeEach, vi } from 'vitest';
import { usePlaybackControls } from '@/composables/usePlaybackControls';

describe('usePlaybackControls.ts', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;
	});

	it('executes all playback commands with expected payloads', async () => {
		const controls = usePlaybackControls();

		await controls.play('/m/song.mp3');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'play', path: '/m/song.mp3' }) })
		);

		await controls.pause();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'pause' }) })
		);

		await controls.skip();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'skip' }) })
		);

		await controls.prev();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'prev' }) })
		);

		await controls.stop();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'stop' }) })
		);

		await controls.fullscreen();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'fullscreen' }) })
		);

		await controls.clearQueue();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'clear_queue' }) })
		);

		await controls.addUrl('https://yt.com/watch?v=1');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'add_url', path: 'https://yt.com/watch?v=1' }) })
		);

		await controls.jumpToHistory(2);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'jump', type: 'history', index: 2 }) })
		);

		await controls.jumpToQueue(1);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'jump', type: 'queue', index: 1 }) })
		);

		await controls.moveQueueItem(0, 3);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_queue_item', index: 0, new_index: 3 }) })
		);

		await controls.removeQueueItem(4);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'remove_queue_item', index: 4 }) })
		);

		await controls.removeHistoryItem(5);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'remove_history_item', index: 5 }) })
		);

		await controls.seek(15);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'seek', amount: 15 }) })
		);

		await controls.seekAbsolute(42);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'seek_absolute', amount: 42 }) })
		);

		await controls.setMute(true);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'set_mute', state: true }) })
		);

		await controls.setVolume(70);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'set_volume', vollevel: 70 }) })
		);

		await controls.toggleDjCarpincho(true);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_dj_carpincho', state: true }) })
		);

		await controls.toggleDjSafeMode(false);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_dj_safe_mode', state: false }) })
		);

		await controls.toggleFavorite('/m/fav.mp3');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_favorite', path: '/m/fav.mp3' }) })
		);

		await controls.toggleQueue('/m/q.mp3', 'Song Title');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_queue', path: '/m/q.mp3' }) })
		);

		await controls.pauseAfter('/m/pause.mp3');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'pause_after', path: '/m/pause.mp3' }) })
		);
	});

	it('handles network errors gracefully and returns null', async () => {
		global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
		const controls = usePlaybackControls();

		const res = await controls.play('/m/fail.mp3');
		expect(res).toBeNull();
	});
});
