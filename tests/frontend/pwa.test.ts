import { beforeEach, describe, expect, it, vi } from 'vitest';

const capState = vi.hoisted(() => ({ isNative: false, platform: 'web' }));

vi.mock('@capacitor/core', () => ({
	Capacitor: {
		isNativePlatform: () => capState.isNative,
		getPlatform: () => capState.platform,
	},
	SystemBars: { hide: vi.fn(), show: vi.fn() },
	registerPlugin: () => ({}),
}));

describe('PWA service worker registration & native cleanup', () => {
	beforeEach(() => {
		capState.isNative = false;
		capState.platform = 'web';
		if (typeof localStorage !== 'undefined') {
			localStorage.clear();
		}
		vi.restoreAllMocks();
	});

	it('unregisters own service workers on native Android without registering sw.js, leaving foreign SW/caches intact', async () => {
		capState.isNative = true;
		capState.platform = 'android';

		const unregisterOwn = vi.fn().mockResolvedValue(true);
		const unregisterForeign = vi.fn().mockResolvedValue(true);
		const registerMock = vi.fn().mockResolvedValue({});
		Object.defineProperty(navigator, 'serviceWorker', {
			configurable: true,
			value: {
				getRegistrations: vi.fn().mockResolvedValue([
					{ active: { scriptURL: 'https://localhost/sw.js' }, unregister: unregisterOwn },
					{ active: { scriptURL: 'https://localhost/other-sw.js' }, unregister: unregisterForeign },
				]),
				register: registerMock,
			},
		});

		const cacheStore = new Set(['rockola-shell-v1', 'rockola-shell-v3', 'external-cache', 'other-app-v1']);
		const deleteMock = vi.fn(async (key: string) => cacheStore.delete(key));
		const keysMock = vi.fn(async () => [...cacheStore]);
		Object.defineProperty(globalThis, 'caches', {
			configurable: true,
			value: {
				keys: keysMock,
				delete: deleteMock,
			},
		});

		const { setupServiceWorker, NATIVE_SW_CLEANUP_STORAGE_KEY } = await import('@/pwa/registerSw');
		await setupServiceWorker({ isProd: true });

		expect(unregisterOwn).toHaveBeenCalledTimes(1);
		expect(unregisterForeign).not.toHaveBeenCalled();
		expect(registerMock).not.toHaveBeenCalled();
		expect(deleteMock).toHaveBeenCalledWith('rockola-shell-v1');
		expect(deleteMock).toHaveBeenCalledWith('rockola-shell-v3');
		expect(deleteMock).not.toHaveBeenCalledWith('external-cache');
		expect(deleteMock).not.toHaveBeenCalledWith('other-app-v1');
		expect(localStorage.getItem(NATIVE_SW_CLEANUP_STORAGE_KEY)).toBe('1');

		// Segundo arranque tras migración ya completada: no repite limpieza de caches
		deleteMock.mockClear();
		keysMock.mockClear();
		(navigator.serviceWorker.getRegistrations as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
		await setupServiceWorker({ isProd: true });
		expect(keysMock).not.toHaveBeenCalled();
		expect(deleteMock).not.toHaveBeenCalled();
	});

	it('registers ./sw.js on web production builds', async () => {
		capState.isNative = false;
		capState.platform = 'web';

		const registerMock = vi.fn().mockResolvedValue({});
		Object.defineProperty(navigator, 'serviceWorker', {
			configurable: true,
			value: {
				getRegistrations: vi.fn().mockResolvedValue([]),
				register: registerMock,
			},
		});

		const { setupServiceWorker } = await import('@/pwa/registerSw');
		await setupServiceWorker({ isProd: true });

		expect(registerMock).toHaveBeenCalledWith('./sw.js');
	});
});
