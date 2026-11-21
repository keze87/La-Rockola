import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { pluginMock, systemBarsMock, state } = vi.hoisted(() => ({
	pluginMock: {
		startServer: vi.fn(),
		stopServer: vi.fn(),
		getStatus: vi.fn(),
		pickMusicFolder: vi.fn(),
		hasStoragePermission: vi.fn(),
		requestStoragePermission: vi.fn(),
		updateMediaNotification: vi.fn(),
		updateMediaPosition: vi.fn(),
		hapticFeedback: vi.fn(),
		setKeepScreenOn: vi.fn(),
		shareUrl: vi.fn(),
		consumePendingShortcut: vi.fn(),
		setFogonState: vi.fn(),
		enterPipMode: vi.fn(),
		getMediaVolume: vi.fn(),
		setMediaVolume: vi.fn(),
	},
	systemBarsMock: {
		hide: vi.fn().mockResolvedValue(undefined),
		show: vi.fn().mockResolvedValue(undefined),
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
	SystemBars: systemBarsMock,
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

	it('toggleAndroidFullscreen hides and shows SystemBars only on native Android host', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const toggleAndroidFullscreen = (mod as any).toggleAndroidFullscreen as () => Promise<boolean>;
		const isAndroidFullscreen = (mod as any).isAndroidFullscreen as { value: boolean };

		expect(typeof toggleAndroidFullscreen).toBe('function');

		// En web no hace nada
		await expect(toggleAndroidFullscreen()).resolves.toBe(false);
		expect(systemBarsMock.hide).not.toHaveBeenCalled();

		// En Android nativo alterna barras del sistema
		state.isNative = true;
		state.platform = 'android';

		await expect(toggleAndroidFullscreen()).resolves.toBe(true);
		expect(systemBarsMock.hide).toHaveBeenCalledTimes(1);
		expect(isAndroidFullscreen.value).toBe(true);

		await expect(toggleAndroidFullscreen()).resolves.toBe(false);
		expect(systemBarsMock.show).toHaveBeenCalledTimes(1);
		expect(isAndroidFullscreen.value).toBe(false);
	});

	it('triggerAndroidHaptic calls native RockolaServer.hapticFeedback only on Android', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const triggerAndroidHaptic = (mod as any).triggerAndroidHaptic as (heavy?: boolean) => Promise<void> | void;

		expect(typeof triggerAndroidHaptic).toBe('function');

		// En web no hace nada
		await triggerAndroidHaptic(false);
		expect(pluginMock.hapticFeedback).not.toHaveBeenCalled();

		// En Android nativo invoca feedback nativo liviano o pesado
		state.isNative = true;
		state.platform = 'android';
		pluginMock.hapticFeedback.mockResolvedValue({ performed: true });

		await triggerAndroidHaptic(false);
		await triggerAndroidHaptic(true);

		expect(pluginMock.hapticFeedback).toHaveBeenNthCalledWith(1, { heavy: false });
		expect(pluginMock.hapticFeedback).toHaveBeenNthCalledWith(2, { heavy: true });
	});

	it('setAndroidKeepScreenOn, shareAndroidUrl, and consumeAndroidPendingShortcut work only on Android', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const setAndroidKeepScreenOn = (mod as any).setAndroidKeepScreenOn as (enabled: boolean) => Promise<void>;
		const shareAndroidUrl = (mod as any).shareAndroidUrl as (opts: {
			url: string;
			title?: string;
			text?: string;
		}) => Promise<boolean>;
		const consumeAndroidPendingShortcut = (mod as any).consumeAndroidPendingShortcut as () => Promise<
			string | null
		>;

		expect(typeof setAndroidKeepScreenOn).toBe('function');
		expect(typeof shareAndroidUrl).toBe('function');
		expect(typeof consumeAndroidPendingShortcut).toBe('function');

		// En web no llaman al plugin nativo
		await setAndroidKeepScreenOn(true);
		await expect(shareAndroidUrl({ url: 'http://192.168.0.10:1729' })).resolves.toBe(false);
		await expect(consumeAndroidPendingShortcut()).resolves.toBeNull();
		expect(pluginMock.setKeepScreenOn).not.toHaveBeenCalled();
		expect(pluginMock.shareUrl).not.toHaveBeenCalled();
		expect(pluginMock.consumePendingShortcut).not.toHaveBeenCalled();

		// En Android delegan al plugin
		state.isNative = true;
		state.platform = 'android';
		pluginMock.setKeepScreenOn.mockResolvedValue({ enabled: true });
		pluginMock.shareUrl.mockResolvedValue({ shared: true });
		pluginMock.consumePendingShortcut.mockResolvedValue({ action: 'ar.carpincho.rockola.ACTION_OPEN_FOGON' });

		await setAndroidKeepScreenOn(true);
		await setAndroidKeepScreenOn(false);
		expect(pluginMock.setKeepScreenOn).toHaveBeenNthCalledWith(1, { enabled: true });
		expect(pluginMock.setKeepScreenOn).toHaveBeenNthCalledWith(2, { enabled: false });

		await expect(
			shareAndroidUrl({ url: 'http://192.168.0.10:1729', title: 'Rockola', text: 'Sumate' })
		).resolves.toBe(true);
		expect(pluginMock.shareUrl).toHaveBeenCalledWith({
			url: 'http://192.168.0.10:1729',
			title: 'Rockola',
			text: 'Sumate',
		});

		await expect(consumeAndroidPendingShortcut()).resolves.toBe('ar.carpincho.rockola.ACTION_OPEN_FOGON');
		expect(pluginMock.consumePendingShortcut).toHaveBeenCalledTimes(1);
	});

	it('setAndroidFogonState and enterAndroidPipMode invoke native plugin only on Android', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const setAndroidFogonState = (mod as any).setAndroidFogonState as (active: boolean) => Promise<void>;
		const enterAndroidPipMode = (mod as any).enterAndroidPipMode as () => Promise<boolean>;

		expect(typeof setAndroidFogonState).toBe('function');
		expect(typeof enterAndroidPipMode).toBe('function');

		// En web no hacen nada
		await setAndroidFogonState(true);
		await expect(enterAndroidPipMode()).resolves.toBe(false);
		expect(pluginMock.setFogonState).not.toHaveBeenCalled();
		expect(pluginMock.enterPipMode).not.toHaveBeenCalled();

		// En Android delegan al plugin
		state.isNative = true;
		state.platform = 'android';
		pluginMock.setFogonState.mockResolvedValue({ active: true });
		pluginMock.enterPipMode.mockResolvedValue({ entered: true });

		await setAndroidFogonState(true);
		await setAndroidFogonState(false);
		expect(pluginMock.setFogonState).toHaveBeenNthCalledWith(1, { active: true });
		expect(pluginMock.setFogonState).toHaveBeenNthCalledWith(2, { active: false });

		await expect(enterAndroidPipMode()).resolves.toBe(true);
		expect(pluginMock.enterPipMode).toHaveBeenCalledTimes(1);
	});

	it('getAndroidMediaVolume and setAndroidMediaVolume delegate to native STREAM_MUSIC plugin only on Android', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const getAndroidMediaVolume = (mod as any).getAndroidMediaVolume as () => Promise<{
			level: number;
			muted: boolean;
		} | null>;
		const setAndroidMediaVolume = (mod as any).setAndroidMediaVolume as (level: number) => Promise<number | null>;

		expect(typeof getAndroidMediaVolume).toBe('function');
		expect(typeof setAndroidMediaVolume).toBe('function');

		// En web no llaman al plugin nativo
		await expect(getAndroidMediaVolume()).resolves.toBeNull();
		await expect(setAndroidMediaVolume(65)).resolves.toBeNull();
		expect(pluginMock.getMediaVolume).not.toHaveBeenCalled();
		expect(pluginMock.setMediaVolume).not.toHaveBeenCalled();

		// En Android delegan al plugin
		state.isNative = true;
		state.platform = 'android';
		pluginMock.getMediaVolume.mockResolvedValue({ level: 55, muted: false });
		pluginMock.setMediaVolume.mockResolvedValue({ level: 80, muted: false });

		await expect(getAndroidMediaVolume()).resolves.toEqual({ level: 55, muted: false });
		await expect(setAndroidMediaVolume(80)).resolves.toBe(80);
		expect(pluginMock.setMediaVolume).toHaveBeenCalledWith({ level: 80 });

		// Clampa valores fuera de 0..100
		pluginMock.setMediaVolume.mockResolvedValue({ level: 100, muted: false });
		await setAndroidMediaVolume(110);
		expect(pluginMock.setMediaVolume).toHaveBeenLastCalledWith({ level: 100 });
	});

	it('normalizes remote server URLs and connects to a remote PC server on Android', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const normalizeServerOrigin = (mod as any).normalizeServerOrigin as (raw: string) => string | null;
		const connectToRemoteServer = (mod as any).connectToRemoteServer as (raw: string) => Promise<string>;
		const resetToLocalServer = (mod as any).resetToLocalServer as () => void;
		const activeRemoteServerUrl = (mod as any).activeRemoteServerUrl;

		expect(normalizeServerOrigin('')).toBeNull();
		expect(normalizeServerOrigin('   ')).toBeNull();
		expect(normalizeServerOrigin('192.168.0.55')).toBe('http://192.168.0.55:1729');
		expect(normalizeServerOrigin('192.168.0.55:8080/')).toBe('http://192.168.0.55:8080');
		expect(normalizeServerOrigin('https://rockola.local/')).toBe('https://rockola.local');

		state.isNative = true;
		state.platform = 'android';
		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		});

		const url = await connectToRemoteServer('192.168.0.55');
		expect(url).toBe('http://192.168.0.55:1729');
		expect(getApiOrigin()).toBe('http://192.168.0.55:1729');
		expect(activeRemoteServerUrl.value).toBe('http://192.168.0.55:1729');
		expect(localStorage.getItem('rockola_remote_server_url')).toBe('http://192.168.0.55:1729');

		// Al reiniciar con servidor remoto guardado, no arranca el servidor embebido local
		const ready = await initAndroidServer({ pollIntervalMs: 5, timeoutMs: 200 });
		expect(ready).toBe(true);
		expect(pluginMock.startServer).not.toHaveBeenCalled();

		resetToLocalServer();
		expect(activeRemoteServerUrl.value).toBeNull();
		expect(localStorage.getItem('rockola_remote_server_url')).toBeNull();
	});
});
