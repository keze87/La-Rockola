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
		setMediaTarget: vi.fn(),
		hapticFeedback: vi.fn(),
		setKeepScreenOn: vi.fn(),
		shareUrl: vi.fn(),
		consumePendingShortcut: vi.fn(),
		setFogonState: vi.fn(),
		enterPipMode: vi.fn(),
		getMediaVolume: vi.fn(),
		setMediaVolume: vi.fn(),
		addListener: vi.fn().mockResolvedValue({ remove: vi.fn().mockResolvedValue(undefined) }),
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
		expect(listenLocally.value).toBe(false);
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
		const triggerAndroidHaptic = (mod as any).triggerAndroidHaptic as (
			kindOrHeavy?: boolean | 'tap' | 'confirm' | 'long_press' | 'reject'
		) => Promise<void> | void;

		expect(typeof triggerAndroidHaptic).toBe('function');

		// En web no hace nada
		await triggerAndroidHaptic(false);
		expect(pluginMock.hapticFeedback).not.toHaveBeenCalled();

		// En Android nativo traduce booleanos legacy o tipos semánticos al contrato nativo
		state.isNative = true;
		state.platform = 'android';
		pluginMock.hapticFeedback.mockResolvedValue({ performed: true });

		await triggerAndroidHaptic(false);
		await triggerAndroidHaptic(true);
		await triggerAndroidHaptic('confirm');

		expect(pluginMock.hapticFeedback).toHaveBeenNthCalledWith(1, { kind: 'tap' });
		expect(pluginMock.hapticFeedback).toHaveBeenNthCalledWith(2, { kind: 'long_press' });
		expect(pluginMock.hapticFeedback).toHaveBeenNthCalledWith(3, { kind: 'confirm' });
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

	it('normalizes remote server URLs, remembers last server, and always starts local on boot', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const normalizeServerOrigin = (mod as any).normalizeServerOrigin as (raw: string) => string | null;
		const connectToRemoteServer = (mod as any).connectToRemoteServer as (raw: string) => Promise<string>;
		const resetToLocalServer = (mod as any).resetToLocalServer as () => void;
		const activeRemoteServerUrl = (mod as any).activeRemoteServerUrl;
		const lastRemoteServerUrl = (mod as any).lastRemoteServerUrl;

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
		expect(lastRemoteServerUrl.value).toBe('http://192.168.0.55:1729');
		expect(localStorage.getItem('rockola_remote_server_url')).toBe('http://192.168.0.55:1729');

		// Al volver al teléfono, activeRemoteServerUrl se apaga pero lastRemoteServerUrl se conserva
		resetToLocalServer();
		expect(activeRemoteServerUrl.value).toBeNull();
		expect(lastRemoteServerUrl.value).toBe('http://192.168.0.55:1729');
		expect(localStorage.getItem('rockola_remote_server_url')).toBe('http://192.168.0.55:1729');

		// Al iniciar la app siempre arranca en el servidor local aunque haya último servidor guardado
		const ready = await initAndroidServer({ pollIntervalMs: 5, timeoutMs: 200 });
		expect(ready).toBe(true);
		expect(pluginMock.startServer).toHaveBeenCalledTimes(1);
		expect(activeRemoteServerUrl.value).toBeNull();
		expect(getApiOrigin()).toBe('http://127.0.0.1:1729');
	});

	it('ensureLocalAndroidServerAlive ignores remote mode, ignores transient failures, and restarts only when confirmed dead', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const ensureLocalAndroidServerAlive = (mod as any).ensureLocalAndroidServerAlive as (opts?: {
			retryDelayMs?: number;
			cooldownMs?: number;
		}) => Promise<boolean>;
		const activeRemoteServerUrl = (mod as any).activeRemoteServerUrl;

		// 1. No corre en web ni en modo servidor remoto
		state.isNative = false;
		await expect(ensureLocalAndroidServerAlive()).resolves.toBe(false);

		state.isNative = true;
		state.platform = 'android';
		activeRemoteServerUrl.value = 'http://192.168.0.55:1729';
		await expect(ensureLocalAndroidServerAlive()).resolves.toBe(false);
		activeRemoteServerUrl.value = null;

		// 2. Si el servicio corre y /health responde en el primer o segundo intento, NO reinicia
		pluginMock.getStatus.mockResolvedValue({
			running: true,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
		});
		let healthCalls = 0;
		global.fetch = vi.fn().mockImplementation(() => {
			healthCalls += 1;
			if (healthCalls === 1) {
				return Promise.reject(new Error('transient timeout'));
			}
			return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
		});

		await expect(ensureLocalAndroidServerAlive({ retryDelayMs: 5, cooldownMs: 0 })).resolves.toBe(false);
		expect(pluginMock.startServer).not.toHaveBeenCalled();

		// 3. Si getStatus().running es false (Android mató el servicio), reinicia de una
		pluginMock.getStatus.mockResolvedValue({
			running: false,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
		});
		pluginMock.startServer.mockResolvedValue({
			running: true,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
		});
		global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });

		await expect(ensureLocalAndroidServerAlive({ retryDelayMs: 5, cooldownMs: 0 })).resolves.toBe(true);
		expect(pluginMock.startServer).toHaveBeenCalledTimes(1);

		// 4. Si getStatus().running es true pero fallan 2 /health consecutivos, detiene y reinicia
		pluginMock.startServer.mockClear();
		pluginMock.getStatus.mockResolvedValue({
			running: true,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
		});
		let phase4Calls = 0;
		global.fetch = vi.fn().mockImplementation(() => {
			phase4Calls += 1;
			if (phase4Calls <= 2) {
				return Promise.reject(new Error('dead'));
			}
			return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
		});

		await expect(ensureLocalAndroidServerAlive({ retryDelayMs: 5, cooldownMs: 0 })).resolves.toBe(true);
		expect(pluginMock.stopServer).toHaveBeenCalledTimes(1);
		expect(pluginMock.startServer).toHaveBeenCalledTimes(1);
	});

	it('initAndroidServer returns false and sets localServerState=unavailable when /health fails or returns invalid body', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');
		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();

		pluginMock.startServer.mockResolvedValue({
			running: true,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/storage/emulated/0/Music',
		});

		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'broken' }),
		});

		const ready = await mod.initAndroidServer({ pollIntervalMs: 5, timeoutMs: 30 });
		expect(ready).toBe(false);
		expect(store.localServerState.value).toBe('unavailable');
		expect(store.lastServerError.value?.code).toBe('HEALTH_CHECK_TIMEOUT');
		expect(mod.androidServerStatus.value.running).toBe(false);
	});

	it('ensureLocalAndroidServerAlive returns false when restart fails and deduplicates concurrent calls', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');
		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();

		pluginMock.getStatus.mockResolvedValue({
			running: false,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
		});
		pluginMock.startServer.mockResolvedValue({
			running: true,
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: null,
		});
		global.fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'));

		const p1 = mod.ensureLocalAndroidServerAlive({ retryDelayMs: 5, cooldownMs: 0, initTimeoutMs: 25 });
		const p2 = mod.ensureLocalAndroidServerAlive({ retryDelayMs: 5, cooldownMs: 0, initTimeoutMs: 25 });
		expect(p1).toBe(p2);

		const res = await p1;
		expect(res).toBe(false);
		expect(store.localServerState.value).toBe('unavailable');
		expect(pluginMock.startServer).toHaveBeenCalledTimes(1);
	});

	it('connectToRemoteServer and disconnectFromRemoteServer clear stale state and update mode explicitly', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');
		const playback = await import('@/stores/usePlaybackStore');
		const queue = await import('@/stores/useQueueStore');

		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();
		playback.currentTrackPath.value = '/local/track.mp3';
		queue.queueState.value = ['/local/next.mp3'];

		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		});

		const onModeSwitch = vi.fn();
		const target = await mod.connectToRemoteServer('192.168.0.88', { onServerChanged: onModeSwitch });
		expect(target).toBe('http://192.168.0.88:1729');
		expect(store.serverMode.value).toBe('remote');
		expect(playback.currentTrackPath.value).toBeNull();
		expect(queue.queueState.value).toEqual([]);
		expect(onModeSwitch).toHaveBeenCalledTimes(1);

		// Error 401/403 preserva mensaje accionable sin cambiar modo
		global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 });
		await expect(mod.connectToRemoteServer('192.168.0.99')).rejects.toThrow(/autenticación|401/i);
		expect(store.serverMode.value).toBe('remote');
		expect(store.activeRemoteServerUrl.value).toBe('http://192.168.0.88:1729');

		await mod.syncAndroidMediaTarget();
		expect(pluginMock.setMediaTarget).toHaveBeenCalledWith(
			expect.objectContaining({
				mode: 'remote',
				origin: 'http://192.168.0.88:1729',
			})
		);

		playback.currentTrackPath.value = '/remote/track.mp3';
		const disconnectRes = await mod.disconnectFromRemoteServer({ onServerChanged: onModeSwitch });
		expect(disconnectRes.ok).toBe(true);
		expect(disconnectRes.synced).toBe(true);
		expect(store.serverMode.value).toBe('host');
		expect(playback.currentTrackPath.value).toBeNull();
		expect(onModeSwitch).toHaveBeenCalledTimes(2);
	});

	it('enterAndroidPipMode returns structured failure reason when Android denies PiP', async () => {
		const mod = await import('@/composables/useAndroidHost');
		state.isNative = true;
		state.platform = 'android';

		pluginMock.enterPipMode.mockResolvedValue({ entered: false, reason: 'PIP_DENIED' });
		const res = await mod.enterAndroidPipModeDetailed();
		expect(res).toEqual({ entered: false, reason: 'PIP_DENIED' });
		expect(mod.isAndroidPipMode.value).toBe(false);
	});

	it('initAndroidServer aborts quickly and exposes lastError when native hostState is failed', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');

		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();

		pluginMock.startServer.mockResolvedValue({
			running: true,
			hostState: 'starting',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '',
		});
		pluginMock.getStatus.mockResolvedValue({
			running: false,
			hostState: 'failed',
			lastError: 'Puerto ocupado en Uvicorn',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '',
		});
		global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

		const ok = await mod.initAndroidServer({ pollIntervalMs: 10, timeoutMs: 5000 });
		expect(ok).toBe(false);
		expect(store.localServerState.value).toBe('unavailable');
		expect(store.lastServerError.value?.message).toContain('Puerto ocupado en Uvicorn');
	});

	it('pickAndApplyMusicFolder handles SAF permission_denied without calling /system/music-dir', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');

		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();

		pluginMock.pickMusicFolder.mockResolvedValue({
			path: null,
			uri: 'content://com.android.externalstorage.documents/tree/ABCD-1234%3AMusic',
			status: 'permission_denied',
			error: 'El permiso sobre la carpeta fue revocado',
		});
		const fetchMock = vi.fn();
		global.fetch = fetchMock;

		const selected = await mod.pickAndApplyMusicFolder();
		expect(selected).toBeNull();
		expect(fetchMock).not.toHaveBeenCalled();
		expect(store.libraryFolderStatus.value).toBe('permission_denied');
		expect(store.libraryFolderError.value).toContain('revocado');
	});

	it('initAndroidServer exposes actionable error when startServer rejects with SERVICE_START_NOT_ALLOWED', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');

		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();

		pluginMock.startServer.mockRejectedValueOnce(
			Object.assign(new Error('Android bloqueó el inicio del servicio en segundo plano.'), {
				code: 'SERVICE_START_NOT_ALLOWED',
			})
		);

		const ok = await mod.initAndroidServer();
		expect(ok).toBe(false);
		expect(store.localServerState.value).toBe('unavailable');
		expect(store.lastServerError.value?.message).toContain('segundo plano');
	});

	it('subscribeAndroidNativeEvents registers Capacitor listeners on Android and removes handles on cleanup', async () => {
		const mod = await import('@/composables/useAndroidHost');
		state.isNative = true;
		state.platform = 'android';

		const listeners: Record<string, (data: Record<string, unknown>) => void> = {};
		const removeFn = vi.fn().mockResolvedValue(undefined);
		pluginMock.addListener.mockImplementation(
			async (eventName: string, cb: (d: Record<string, unknown>) => void) => {
				listeners[eventName] = cb;
				return { remove: removeFn };
			}
		);

		const onVol = vi.fn();
		const onErr = vi.fn();
		const onPip = vi.fn();
		const onIme = vi.fn();
		const onBack = vi.fn();
		const onShortcut = vi.fn();

		const cleanup = mod.subscribeAndroidNativeEvents({
			onMediaVolumeChanged: onVol,
			onNativeCommandError: onErr,
			onPipModeChanged: onPip,
			onImeInsetsChanged: onIme,
			onBackProgress: onBack,
			onShortcutAction: onShortcut,
		});

		await new Promise((r) => setTimeout(r, 0));

		listeners.mediaVolumeChanged?.({ level: 42, muted: false });
		listeners.nativeCommandError?.({ cmd: 'skip', code: 'TIMEOUT', message: 'Sin respuesta' });
		listeners.pipModeChanged?.({ active: true });
		listeners.imeInsetsChanged?.({ bottomCssPx: 280 });
		listeners.backProgress?.({ progress: 0.45 });
		listeners.shortcutAction?.({ action: 'ar.carpincho.rockola.ACTION_OPEN_QUEUE' });

		expect(onVol).toHaveBeenCalledWith(42, false);
		expect(onErr).toHaveBeenCalledWith('skip', 'TIMEOUT', 'Sin respuesta');
		expect(onPip).toHaveBeenCalledWith(true);
		expect(onIme).toHaveBeenCalledWith(280);
		expect(onBack).toHaveBeenCalledWith(0.45);
		expect(onShortcut).toHaveBeenCalledWith('ar.carpincho.rockola.ACTION_OPEN_QUEUE');

		cleanup();
		expect(removeFn).toHaveBeenCalledTimes(6);
	});

	it('serializes MediaTarget sync, discards stale A->B responses, blocks commands until synced, and supports retries', async () => {
		const mod = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');

		state.isNative = true;
		state.platform = 'android';
		store.resetServerConnectionStore();
		mod.resetMediaTargetSyncStateForTests();

		// 1. Plugin nativo no disponible -> mediaTargetSynced=false y error accionable
		const origSetTarget = pluginMock.setMediaTarget;
		(pluginMock as unknown as Record<string, unknown>).setMediaTarget = undefined;
		store.setRemoteMode('http://192.168.0.10:1729');
		const unavailRes = await mod.syncAndroidMediaTarget();
		expect(unavailRes.ok).toBe(false);
		expect(unavailRes.synced).toBe(false);
		expect(mod.mediaTargetSynced.value).toBe(false);
		expect(mod.mediaTargetSyncError.value).toBeTruthy();

		// Mientras mediaTargetSynced=false, bloquea envíos al destino nativo anterior
		await mod.syncAndroidMediaNotification({
			title: 'Tema',
			artist: 'Artista',
			paused: false,
		});
		await mod.syncAndroidMediaPosition({ duration: 120, position: 10, paused: false });
		expect(pluginMock.updateMediaNotification).not.toHaveBeenCalled();
		expect(pluginMock.updateMediaPosition).not.toHaveBeenCalled();

		// 2. Sincronización fallida y reintento exitoso
		pluginMock.setMediaTarget = origSetTarget;
		pluginMock.setMediaTarget.mockRejectedValueOnce(new Error('IPC caído'));
		const failRes = await mod.syncAndroidMediaTarget();
		expect(failRes.ok).toBe(false);
		expect(mod.mediaTargetSynced.value).toBe(false);
		expect(mod.mediaTargetSyncError.value).toContain('IPC caído');

		pluginMock.setMediaTarget.mockResolvedValueOnce({ updated: true });
		const retryRes = await mod.retrySyncAndroidMediaTarget();
		expect(retryRes.ok).toBe(true);
		expect(retryRes.synced).toBe(true);
		expect(mod.mediaTargetSynced.value).toBe(true);
		expect(mod.mediaTargetSyncError.value).toBeNull();

		// Una vez sincronizado, permite enviar notificaciones/posición
		await mod.syncAndroidMediaNotification({
			title: 'Tema OK',
			artist: 'Artista OK',
			paused: false,
		});
		expect(pluginMock.updateMediaNotification).toHaveBeenCalledTimes(1);

		// 3. Cambio A -> B mientras A responde tarde: descarta A como obsoleta por generación
		let resolveA!: (val: { updated: boolean }) => void;
		const promiseA = new Promise<{ updated: boolean }>((resolve) => {
			resolveA = resolve;
		});
		pluginMock.setMediaTarget.mockImplementationOnce(() => promiseA).mockResolvedValueOnce({ updated: true });

		store.setRemoteMode('http://192.168.0.20:1729');
		const genA = store.mediaTargetGeneration.value;
		const syncA = mod.syncAndroidMediaTarget();
		expect(mod.mediaTargetSynced.value).toBe(false);

		// Durante la transición hacia A, los comandos nativos NO deben dispararse al destino anterior
		await mod.syncAndroidMediaNotification({
			title: 'Durante transición',
			artist: 'Nadie',
			paused: false,
		});
		expect(pluginMock.updateMediaNotification).toHaveBeenCalledTimes(1);

		store.setRemoteMode('http://192.168.0.30:1729');
		const genB = store.mediaTargetGeneration.value;
		const syncB = mod.syncAndroidMediaTarget();

		resolveA({ updated: true });
		const [resA, resB] = await Promise.all([syncA, syncB]);
		expect(resA.generation).toBe(genA);
		expect(resA.stale).toBe(true);
		expect(resA.synced).toBe(false);
		expect(resB.generation).toBe(genB);
		expect(resB.ok).toBe(true);
		expect(resB.synced).toBe(true);
		expect(mod.mediaTargetSynced.value).toBe(true);

		// 4. Desconexión hacia host local devuelve promesa verificable
		pluginMock.setMediaTarget.mockResolvedValueOnce({ updated: true });
		const hostRes = await mod.disconnectFromRemoteServer();
		expect(hostRes.ok).toBe(true);
		expect(hostRes.synced).toBe(true);
		expect(store.serverMode.value).toBe('host');
	});
});
