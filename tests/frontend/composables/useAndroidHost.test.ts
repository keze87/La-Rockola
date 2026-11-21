import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { pluginMock, state } = vi.hoisted(() => ({
	pluginMock: {
		startServer: vi.fn(),
		stopServer: vi.fn(),
		getStatus: vi.fn(),
		pickMusicFolder: vi.fn(),
		hasStoragePermission: vi.fn(),
		requestStoragePermission: vi.fn(),
		updateMediaNotification: vi.fn(),
		updateMediaPosition: vi.fn(),
	},
	state: {
		isNative: false,
		platform: 'web',
	},
}));

vi.mock('@capacitor/core', () => ({
	Capacitor: {
		isNativePlatform: () => state.isNative,
		getPlatform: () => state.platform,
	},
	registerPlugin: () => pluginMock,
}));

import { clearApiOrigin, getApiOrigin } from '@/composables/useApi';
import { listenLocally } from '@/stores/usePlaybackStore';
import {
	androidServerStatus,
	initAndroidServer,
	isNativeAndroidHost,
	pickAndApplyMusicFolder,
	resetAndroidMediaPositionThrottle,
	syncAndroidMediaNotification,
	syncAndroidMediaPosition,
} from '@/composables/useAndroidHost';

describe('useAndroidHost.ts', () => {
	beforeEach(() => {
		state.isNative = false;
		state.platform = 'web';
		listenLocally.value = false;
		resetAndroidMediaPositionThrottle();
		clearApiOrigin();
		vi.clearAllMocks();
		androidServerStatus.value = {
			running: false,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
			needsFolder: false,
		};
	});

	afterEach(() => {
		clearApiOrigin();
	});

	it('detects native Android host only on Capacitor Android', () => {
		expect(isNativeAndroidHost()).toBe(false);

		state.isNative = true;
		state.platform = 'ios';
		expect(isNativeAndroidHost()).toBe(false);

		state.platform = 'android';
		expect(isNativeAndroidHost()).toBe(true);
	});

	it('initAndroidServer starts ForegroundService, sets API origin, and polls /health', async () => {
		state.isNative = true;
		state.platform = 'android';

		pluginMock.startServer.mockResolvedValue({
			running: true,
			port: 1729,
			localIp: '192.168.0.44',
			serverUrl: 'http://192.168.0.44:1729',
			musicDir: '',
		});

		let calls = 0;
		global.fetch = vi.fn().mockImplementation((url: string) => {
			calls += 1;
			expect(url).toBe('http://127.0.0.1:1729/health');
			if (calls === 1) {
				return Promise.reject(new Error('Connection refused'));
			}
			return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
		});

		const ready = await initAndroidServer({ pollIntervalMs: 5, timeoutMs: 2000 });
		expect(ready).toBe(true);
		expect(listenLocally.value).toBe(true);
		expect(pluginMock.startServer).toHaveBeenCalledTimes(1);
		expect(getApiOrigin()).toBe('http://127.0.0.1:1729');
		expect(androidServerStatus.value.running).toBe(true);
		expect(androidServerStatus.value.needsFolder).toBe(true);
		expect(androidServerStatus.value.localIp).toBe('192.168.0.44');
	});

	it('pickAndApplyMusicFolder selects MicroSD path and notifies /system/music-dir', async () => {
		state.isNative = true;
		state.platform = 'android';
		pluginMock.pickMusicFolder.mockResolvedValue({
			path: '/storage/ABCD-1234/Musica',
			uri: 'content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusica',
		});

		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', music_dir: '/storage/ABCD-1234/Musica' }),
		});
		global.fetch = fetchMock;

		const selected = await pickAndApplyMusicFolder();
		expect(selected).toBe('/storage/ABCD-1234/Musica');
		expect(pluginMock.pickMusicFolder).toHaveBeenCalledTimes(1);
		expect(fetchMock).toHaveBeenCalledWith(
			'/system/music-dir',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ dir: '/storage/ABCD-1234/Musica' }),
			})
		);
		expect(androidServerStatus.value.musicDir).toBe('/storage/ABCD-1234/Musica');
		expect(androidServerStatus.value.needsFolder).toBe(false);
	});

	it('syncAndroidMediaNotification forwards metadata to native plugin only on Android', async () => {
		await syncAndroidMediaNotification({
			title: 'Barro Tal Vez',
			artist: 'Spinetta',
			paused: false,
			coverUrl: 'http://127.0.0.1:1729/cover?path=a.mp3',
		});
		expect(pluginMock.updateMediaNotification).not.toHaveBeenCalled();

		state.isNative = true;
		state.platform = 'android';
		pluginMock.updateMediaNotification.mockResolvedValue({ updated: true });

		await syncAndroidMediaNotification({
			title: 'Barro Tal Vez',
			artist: 'Spinetta',
			paused: false,
			coverUrl: 'http://127.0.0.1:1729/cover?path=a.mp3',
			trackPath: '/music/a.mp3',
			duration: 210,
			position: 12,
			isFavorite: true,
			isPauseAfter: true,
		});
		expect(pluginMock.updateMediaNotification).toHaveBeenCalledWith({
			title: 'Barro Tal Vez',
			artist: 'Spinetta',
			paused: false,
			coverUrl: 'http://127.0.0.1:1729/cover?path=a.mp3',
			trackPath: '/music/a.mp3',
			duration: 210,
			position: 12,
			isFavorite: true,
			isPauseAfter: true,
		});
	});

	it('syncAndroidMediaPosition forwards throttled progress and immediate seek/pause updates', async () => {
		pluginMock.updateMediaPosition.mockResolvedValue({ updated: true });

		await syncAndroidMediaPosition({ duration: 200, position: 10, paused: false });
		expect(pluginMock.updateMediaPosition).not.toHaveBeenCalled();

		state.isNative = true;
		state.platform = 'android';

		// Primer envío: siempre pasa
		await syncAndroidMediaPosition({ duration: 200, position: 10, paused: false });
		expect(pluginMock.updateMediaPosition).toHaveBeenCalledTimes(1);
		expect(pluginMock.updateMediaPosition).toHaveBeenLastCalledWith({
			duration: 200,
			position: 10,
			paused: false,
		});

		// Tick normal (< 1.5s y < 3s): se filtra (throttle)
		await syncAndroidMediaPosition({ duration: 200, position: 10.25, paused: false });
		expect(pluginMock.updateMediaPosition).toHaveBeenCalledTimes(1);

		// Seek (> 1.5s): se envía de inmediato
		await syncAndroidMediaPosition({ duration: 200, position: 45, paused: false });
		expect(pluginMock.updateMediaPosition).toHaveBeenCalledTimes(2);

		// Cambio de pausa: se envía de inmediato
		await syncAndroidMediaPosition({ duration: 200, position: 45, paused: true });
		expect(pluginMock.updateMediaPosition).toHaveBeenCalledTimes(3);
	});
});
