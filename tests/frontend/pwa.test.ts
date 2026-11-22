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
		vi.restoreAllMocks();
	});

	it('unregisters existing service workers on native Android instead of registering sw.js', async () => {
		capState.isNative = true;
		capState.platform = 'android';

		const unregisterMock = vi.fn().mockResolvedValue(true);
		const registerMock = vi.fn().mockResolvedValue({});
		Object.defineProperty(navigator, 'serviceWorker', {
			configurable: true,
			value: {
				getRegistrations: vi.fn().mockResolvedValue([{ unregister: unregisterMock }]),
				register: registerMock,
			},
		});

		const { setupServiceWorker } = await import('@/pwa/registerSw');
		await setupServiceWorker({ isProd: true });

		expect(unregisterMock).toHaveBeenCalledTimes(1);
		expect(registerMock).not.toHaveBeenCalled();
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
