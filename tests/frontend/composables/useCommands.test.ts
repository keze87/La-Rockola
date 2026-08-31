import { describe, it, expect, vi } from 'vitest';
import { useCommands } from '@/composables/player/useCommands';

describe('useCommands', () => {
	it('sends POST request to /command with specified payload', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { sendCmd } = useCommands();

		const res = await sendCmd('play', { path: '/music/song.mp3' });
		expect(res).toEqual({ status: 'ok' });
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ cmd: 'play', path: '/music/song.mp3' }),
			})
		);
	});

	it('handles network failure without unhandled rejection', async () => {
		global.fetch = vi.fn().mockRejectedValue(new Error('Network offline'));

		const { sendCmd } = useCommands();
		const res = await sendCmd('pause');
		expect(res).toBeUndefined();
	});
});
