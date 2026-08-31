import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSocket } from '@/composables/player/useSocket';
import {
	currentTrackPath,
	currentTracks,
	djCarpinchoEnabled,
	djNextTrack,
	djSafeModeEnabled,
	duration,
	favorites,
	historyState,
	isDraggingSeek,
	isPaused,
	isScanning,
	listenLocally,
	localTimePos,
	mpvVisible,
	originalTracks,
	pauseAfterPath,
	pendingSeekTime,
	queueState,
	serverMuted,
	setWsSend,
	timePos,
	topPlayedState,
	trackMap,
	urlMetadata,
	volume,
} from '@/composables/player/state';
import * as localPlayback from '@/composables/player/useLocalPlayback';

let capturedOptions: any = null;
let mockWsSend = vi.fn();

vi.mock('@vueuse/core', async (importOriginal) => {
	const actual = await importOriginal<typeof import('@vueuse/core')>();
	return {
		...actual,
		useWebSocket: (url: string, options: any) => {
			capturedOptions = options;
			mockWsSend = vi.fn();
			return {
				send: mockWsSend,
				close: vi.fn(),
				open: vi.fn(),
			};
		},
	};
});

describe('useSocket.ts', () => {
	beforeEach(() => {
		setWsSend(null);
		capturedOptions = null;
		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);

		currentTrackPath.value = null;
		currentTracks.value = [];
		originalTracks.value = [];
		djCarpinchoEnabled.value = false;
		djNextTrack.value = null;
		djSafeModeEnabled.value = false;
		duration.value = 0;
		favorites.value = [];
		historyState.value = [];
		isDraggingSeek.value = false;
		isPaused.value = false;
		isScanning.value = false;
		listenLocally.value = false;
		localTimePos.value = 0;
		mpvVisible.value = true;
		pauseAfterPath.value = null;
		pendingSeekTime.value = null;
		queueState.value = [];
		serverMuted.value = false;
		timePos.value = 0;
		topPlayedState.value = [];
		trackMap.value = {};
		urlMetadata.value = {};
		volume.value = 80;
	});

	it('connects to websocket and sets wsSend', () => {
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		expect(capturedOptions).not.toBeNull();
		expect(capturedOptions.autoReconnect).toBeDefined();

		// Calling again does nothing because isSocketConnected() is now true
		capturedOptions = null;
		connectWebSocket();
		expect(capturedOptions).toBeNull();
	});

	it('claims local player on connection when listenLocally is true', () => {
		listenLocally.value = true;
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		capturedOptions.onConnected();
		expect(mockWsSend).toHaveBeenCalledWith(JSON.stringify({ type: 'local_player_claim' }));
	});

	it('handles onDisconnected without crashing', () => {
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		expect(() => capturedOptions.onDisconnected()).not.toThrow();
	});

	it('handles local_player_seek message', () => {
		const applySeekSpy = vi.spyOn(localPlayback, 'applyRemoteSeek').mockImplementation(() => {});
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		capturedOptions.onMessage(null, {
			data: JSON.stringify({ type: 'local_player_seek', mode: 'relative', amount: 10 }),
		});

		expect(applySeekSpy).toHaveBeenCalledWith(
			expect.objectContaining({ type: 'local_player_seek', amount: 10 })
		);
	});

	it('handles local_player_claim_result accepted vs rejected', () => {
		const startLpSpy = vi.spyOn(localPlayback, '_startLocalPlayer').mockImplementation(() => {});
		currentTrackPath.value = '/music/song.mp3';
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		// 1. Accepted
		capturedOptions.onMessage(null, {
			data: JSON.stringify({ type: 'local_player_claim_result', ok: true }),
		});
		expect(startLpSpy).toHaveBeenCalledWith('/music/song.mp3');

		// 2. Rejected
		listenLocally.value = true;
		capturedOptions.onMessage(null, {
			data: JSON.stringify({ type: 'local_player_claim_result', ok: false }),
		});
		expect(listenLocally.value).toBe(false);
	});

	it('processes state_update payload and updates all player states', () => {
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		const payload = {
			type: 'state_update',
			current_track: '/music/spinetta.mp3',
			dj_carpincho_enabled: true,
			dj_next_track: { path: '/music/dj.mp3', title: 'DJ Tune' },
			dj_safe_mode: true,
			duration: 210,
			favorites: ['/music/spinetta.mp3'],
			history: ['/music/prev.mp3'],
			is_scanning: true,
			mpv_visible: false,
			pause_after_path: '/music/spinetta.mp3',
			paused: true,
			queue: ['/music/q1.mp3'],
			server_muted: true,
			top_played: [{ path: '/music/spinetta.mp3', count: 10 }],
			url_metadata: { 'https://youtube.com/watch?v=1': { display_title: 'Web Song' } },
			volume: 95,
			time_pos: 45.0,
			library: [
				{ path: '/music/spinetta.mp3', display_title: 'Barro Tal Vez', artist: 'Spinetta' },
			],
		};

		capturedOptions.onMessage(null, { data: JSON.stringify(payload) });

		expect(currentTrackPath.value).toBe('/music/spinetta.mp3');
		expect(djCarpinchoEnabled.value).toBe(true);
		expect(djNextTrack.value?.title).toBe('DJ Tune');
		expect(djSafeModeEnabled.value).toBe(true);
		expect(duration.value).toBe(210);
		expect(favorites.value).toEqual(['/music/spinetta.mp3']);
		expect(historyState.value).toEqual(['/music/prev.mp3']);
		expect(isScanning.value).toBe(true);
		expect(mpvVisible.value).toBe(false);
		expect(pauseAfterPath.value).toBe('/music/spinetta.mp3');
		expect(isPaused.value).toBe(true);
		expect(queueState.value).toEqual(['/music/q1.mp3']);
		expect(serverMuted.value).toBe(true);
		expect(topPlayedState.value).toHaveLength(1);
		expect(volume.value).toBe(95);
		expect(timePos.value).toBe(45.0);
		expect(currentTracks.value).toHaveLength(1);
		expect(trackMap.value['/music/spinetta.mp3']).toBeDefined();
	});

	it('reconciles time drift and pendingSeekTime in state_update', () => {
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		// 1. Pending seek waiting for broadcast confirmation
		pendingSeekTime.value = 50.0;
		localTimePos.value = 50.0;

		// Server reports 10.0 (drift 40.0 > 0.5) -> ignore
		capturedOptions.onMessage(null, {
			data: JSON.stringify({ type: 'state_update', time_pos: 10.0 }),
		});
		expect(pendingSeekTime.value).toBe(50.0);
		expect(localTimePos.value).toBe(50.0);

		// Server caught up to 50.2 (drift 0.2 <= 0.5) -> confirmed
		capturedOptions.onMessage(null, {
			data: JSON.stringify({ type: 'state_update', time_pos: 50.2 }),
		});
		expect(pendingSeekTime.value).toBeNull();
		expect(localTimePos.value).toBe(50.2);

		// 2. Normal drift reconciliation (> 1.5s difference)
		localTimePos.value = 10.0;
		capturedOptions.onMessage(null, {
			data: JSON.stringify({ type: 'state_update', time_pos: 18.0 }),
		});
		expect(localTimePos.value).toBe(18.0);
	});

	it('ignores invalid non-JSON messages without crashing', () => {
		const { connectWebSocket } = useSocket();
		connectWebSocket();

		expect(() => {
			capturedOptions.onMessage(null, { data: 'invalid json string <<<' });
		}).not.toThrow();
	});
});
