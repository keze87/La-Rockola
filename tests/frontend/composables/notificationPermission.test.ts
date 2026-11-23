import { beforeEach, describe, expect, it, vi } from 'vitest';

const { startServerSpy, getNotificationStatusSpy, requestNotificationSpy, openNotificationSettingsSpy } = vi.hoisted(
	() => ({
		startServerSpy: vi.fn(async () => ({
			running: true,
			hostState: 'ready',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/music',
		})),
		getNotificationStatusSpy: vi.fn(async () => ({ status: 'prompt', granted: false })),
		requestNotificationSpy: vi.fn(async () => ({ status: 'granted', granted: true })),
		openNotificationSettingsSpy: vi.fn(async () => ({ opened: true })),
	})
);

vi.mock('@capacitor/core', () => ({
	Capacitor: {
		isNativePlatform: () => true,
		getPlatform: () => 'android',
	},
	SystemBars: { hide: vi.fn(), show: vi.fn() },
	registerPlugin: () => ({
		startServer: startServerSpy,
		getStatus: vi.fn(async () => ({
			running: true,
			hostState: 'ready',
			port: 1729,
			localIp: '127.0.0.1',
			serverUrl: 'http://127.0.0.1:1729',
			musicDir: '/music',
		})),
		getNotificationPermissionStatus: getNotificationStatusSpy,
		requestNotificationPermission: requestNotificationSpy,
		openNotificationSettings: openNotificationSettingsSpy,
	}),
}));

import {
	androidNotificationPermission,
	dismissNotificationPermissionPrompt,
	openAndroidNotificationSettings,
	prepareContextualNotificationPrompt,
	requestAndroidNotificationPermission,
	showNotificationPermissionRationale,
} from '../../../src/composables/useAndroidHost';

describe('Permiso de notificaciones contextual', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		androidNotificationPermission.value = 'unknown';
		showNotificationPermissionRationale.value = false;
	});

	it('muestra explicacion contextual solo cuando esta en prompt y permite aceptar o denegar sin bloquear', async () => {
		getNotificationStatusSpy.mockResolvedValueOnce({ status: 'prompt', granted: false });
		await prepareContextualNotificationPrompt();

		expect(requestNotificationSpy).not.toHaveBeenCalled();
		expect(showNotificationPermissionRationale.value).toBe(true);

		const granted = await requestAndroidNotificationPermission();
		expect(granted).toBe(true);
		expect(androidNotificationPermission.value).toBe('granted');
		expect(showNotificationPermissionRationale.value).toBe(false);
	});

	it('si el usuario descarta o deniega, guarda estado y permite abrir ajustes de notificaciones', async () => {
		getNotificationStatusSpy.mockResolvedValueOnce({ status: 'prompt', granted: false });
		await prepareContextualNotificationPrompt();
		dismissNotificationPermissionPrompt();
		expect(showNotificationPermissionRationale.value).toBe(false);

		// No vuelve a molestar inmediatamente en la misma sesion
		getNotificationStatusSpy.mockResolvedValueOnce({ status: 'prompt', granted: false });
		await prepareContextualNotificationPrompt();
		expect(showNotificationPermissionRationale.value).toBe(false);

		requestNotificationSpy.mockResolvedValueOnce({ status: 'denied', granted: false });
		const granted = await requestAndroidNotificationPermission();
		expect(granted).toBe(false);
		expect(androidNotificationPermission.value).toBe('denied');

		await openAndroidNotificationSettings();
		expect(openNotificationSettingsSpy).toHaveBeenCalledTimes(1);
	});
});
