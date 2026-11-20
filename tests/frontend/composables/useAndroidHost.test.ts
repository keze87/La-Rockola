import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { pluginMock, state } = vi.hoisted(() => ({
	pluginMock: {
		startServer: vi.fn(),
		stopServer: vi.fn(),
		getStatus: vi.fn(),
		pickMusicFolder: vi.fn(),
		hasStoragePermission: vi.fn(),
		requestStoragePermission: vi.fn(),
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
import {
	androidServerStatus,
	initAndroidServer,
	isNativeAndroidHost,
	pickAndApplyMusicFolder,
} from '@/composables/useAndroidHost';

describe('useAndroidHost.ts', () => {
	beforeEach(() => {
		state.isNative = false;
		state.platform = 'web';
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
});
