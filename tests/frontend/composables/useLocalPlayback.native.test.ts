import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { nextTick } from 'vue';
import {
	useLocalPlayback,
	_startLocalPlayer,
	_stopLocalPlayer,
	applyRemoteSeek,
} from '@/composables/player/useLocalPlayback';
import {
	currentTrackPath,
	duration,
	isPaused,
	listenLocally,
	localPlayerRef,
	localTimePos,
	setWsSend,
} from '@/composables/player/state';
import * as androidHost from '@/composables/useAndroidHost';

describe('useLocalPlayback en Android nativo (ExoPlayer remoto)', () => {
	let mockAudioEl: HTMLAudioElement;
	let remotePlaySpy: ReturnType<typeof vi.spyOn>;
	let remoteStopSpy: ReturnType<typeof vi.spyOn>;
	let remoteSeekSpy: ReturnType<typeof vi.spyOn>;
	let remotePauseSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		listenLocally.value = true;
		isPaused.value = false;
		currentTrackPath.value = null;
		localTimePos.value = 0;
		duration.value = 180;

		mockAudioEl = document.createElement('audio');
		mockAudioEl.load = vi.fn();
		mockAudioEl.play = vi.fn().mockResolvedValue(undefined);
		mockAudioEl.pause = vi.fn();
		localPlayerRef.value = mockAudioEl;

		vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		remotePlaySpy = vi.spyOn(androidHost as any, 'remotePlayAudio').mockResolvedValue(true);
		remoteStopSpy = vi.spyOn(androidHost as any, 'remoteStopAudio').mockResolvedValue(true);
		remoteSeekSpy = vi.spyOn(androidHost as any, 'remoteSeekAudio').mockResolvedValue(true);
		remotePauseSpy = vi.spyOn(androidHost as any, 'remoteSetPausedAudio').mockResolvedValue(true);
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('delega _startLocalPlayer a ExoPlayer nativo sin usar HTMLAudioElement.load', () => {
		useLocalPlayback();
		_startLocalPlayer('/music/chacarera.mp3');

		expect(remotePlaySpy).toHaveBeenCalledWith(
			expect.objectContaining({
				url: expect.stringContaining('/stream?path=%2Fmusic%2Fchacarera.mp3'),
				paused: false,
			})
		);
		expect(mockAudioEl.load).not.toHaveBeenCalled();
	});

	it('delega _stopLocalPlayer a remoteStopAudio en Android nativo', () => {
		useLocalPlayback();
		_stopLocalPlayer();

		expect(remoteStopSpy).toHaveBeenCalled();
	});

	it('delega applyRemoteSeek a remoteSeekAudio y notifica local_player_update', () => {
		const wsSendMock = vi.fn();
		setWsSend(wsSendMock);
		useLocalPlayback();
		currentTrackPath.value = '/music/chacarera.mp3';

		applyRemoteSeek({ mode: 'absolute', amount: 42 });

		expect(remoteSeekSpy).toHaveBeenCalledWith(42);
		expect(localTimePos.value).toBe(42);
		const sent = JSON.parse(wsSendMock.mock.calls.at(-1)![0]);
		expect(sent.type).toBe('local_player_update');
		expect(sent.time_pos).toBe(42);
	});

	it('delega cambios de isPaused a remoteSetPausedAudio cuando escucha localmente', async () => {
		useLocalPlayback();
		currentTrackPath.value = '/music/chacarera.mp3';
		await nextTick();

		isPaused.value = true;
		await nextTick();
		expect(remotePauseSpy).toHaveBeenCalledWith(true);

		isPaused.value = false;
		await nextTick();
		expect(remotePauseSpy).toHaveBeenCalledWith(false);
	});

	it('en modo servidor Android sincroniza STREAM_MUSIC y tambien notifica set_volume al backend', async () => {
		const { setHostMode } = await import('@/stores/useServerConnectionStore');
		setHostMode();
		listenLocally.value = false;
		const setMediaVolSpy = vi.spyOn(androidHost, 'setAndroidMediaVolume').mockResolvedValue(70);
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const { setVolume } = useLocalPlayback();
		await setVolume(70);

		expect(setMediaVolSpy).toHaveBeenCalledWith(70);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'set_volume', vollevel: 70 }),
			})
		);
	});
});
