import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
	useLocalPlayback,
	_startLocalPlayer,
	_stopLocalPlayer,
	applyRemoteSeek,
} from '@/composables/player/useLocalPlayback';
import {
	volume,
	listenLocally,
	currentTrackPath,
	localPlayerRef,
	localTimePos,
	setWsSend,
} from '@/composables/player/state';

describe('useLocalPlayback', () => {
	let mockAudioEl: HTMLAudioElement;

	beforeEach(() => {
		volume.value = 80;
		listenLocally.value = false;
		currentTrackPath.value = null;
		localTimePos.value = 0;

		mockAudioEl = document.createElement('audio');
		mockAudioEl.load = vi.fn();
		mockAudioEl.play = vi.fn().mockResolvedValue(undefined);
		mockAudioEl.pause = vi.fn();
		localPlayerRef.value = mockAudioEl;
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

	it('_startLocalPlayer configures audio element and triggers load', () => {
		useLocalPlayback();

		_startLocalPlayer('/music/test_song.flac');

		expect(mockAudioEl.preload).toBe('auto');
		expect(mockAudioEl.src).toContain('/stream?path=');
		expect(mockAudioEl.currentTime).toBe(0);
		expect(mockAudioEl.load).toHaveBeenCalled();
	});

	it('_stopLocalPlayer pauses and cleans up audio element', () => {
		useLocalPlayback();

		mockAudioEl.src = '/stream?path=test';
		_stopLocalPlayer();

		expect(mockAudioEl.pause).toHaveBeenCalled();
		expect(mockAudioEl.hasAttribute('src')).toBe(false);
		expect(mockAudioEl.load).toHaveBeenCalled();
	});

	it('applyRemoteSeek applies absolute and relative seeks to local audio element', () => {
		const wsSendMock = vi.fn();
		setWsSend(wsSendMock);
		useLocalPlayback();

		mockAudioEl.src = 'http://localhost/stream?path=test';
		mockAudioEl.currentTime = 30.0;
		Object.defineProperty(mockAudioEl, 'duration', { value: 180.0, configurable: true });

		// 1. Absolute seek
		applyRemoteSeek({ mode: 'absolute', amount: 75.0 });
		expect(localTimePos.value).toBe(75.0);
		expect(wsSendMock).toHaveBeenCalled();
		const sent1 = JSON.parse(wsSendMock.mock.calls[0][0]);
		expect(sent1.time_pos).toBe(75.0);

		// 2. Relative seek
		mockAudioEl.currentTime = 75.0;
		wsSendMock.mockClear();
		applyRemoteSeek({ mode: 'relative', amount: 15.0 });
		expect(localTimePos.value).toBe(90.0);
		const sent2 = JSON.parse(wsSendMock.mock.calls[0][0]);
		expect(sent2.time_pos).toBe(90.0);
	});
});
