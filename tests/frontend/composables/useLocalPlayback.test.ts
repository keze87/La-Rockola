import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useLocalPlayback } from '@/composables/player/useLocalPlayback';
import { volume, listenLocally, currentTrackPath, setWsSend } from '@/composables/player/state';

describe('useLocalPlayback', () => {
	beforeEach(() => {
		volume.value = 80;
		listenLocally.value = false;
		currentTrackPath.value = null;
	});

	it('setVolume sends set_volume command with current volume.value', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { setVolume } = useLocalPlayback();

		volume.value = 45;
		await setVolume();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'set_volume', vollevel: 45 }),
			})
		);
	});

	it('_sendLocalPlayerUpdate sends local_player_update payload over websocket', () => {
		const wsSendMock = vi.fn();
		setWsSend(wsSendMock);

		const { _sendLocalPlayerUpdate } = useLocalPlayback();

		_sendLocalPlayerUpdate({ time_pos: 15.2, duration: 180, paused: false });

		expect(wsSendMock).toHaveBeenCalled();
		const sent = JSON.parse(wsSendMock.mock.calls[0][0]);
		expect(sent.type).toBe('local_player_update');
		expect(sent.time_pos).toBe(15.2);
	});
});
