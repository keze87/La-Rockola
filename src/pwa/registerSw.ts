// Registro de Service Worker solo en web/PWA y migración acotada a recursos propios dentro del WebView nativo Android.

import { Capacitor } from '@capacitor/core';

export const ROCKOLA_CACHE_PREFIX = 'rockola-shell-';
export const NATIVE_SW_CLEANUP_STORAGE_KEY = 'rockola_native_sw_cleanup_v1';

export interface SwSetupOptions {
	isProd?: boolean;
	isNative?: boolean;
}

function isOwnServiceWorkerRegistration(reg: ServiceWorkerRegistration): boolean {
	const scriptUrl = reg.active?.scriptURL || reg.waiting?.scriptURL || reg.installing?.scriptURL || '';
	if (!scriptUrl) return false;
	try {
		const pathname = new URL(scriptUrl, typeof location !== 'undefined' ? location.href : 'https://localhost/')
			.pathname;
		return /(?:^|\/)sw\.js$/i.test(pathname);
	} catch {
		return /(?:^|\/)sw\.js(?:[?#].*)?$/i.test(scriptUrl);
	}
}

function hasCompletedNativeCleanup(): boolean {
	try {
		return typeof localStorage !== 'undefined' && localStorage.getItem(NATIVE_SW_CLEANUP_STORAGE_KEY) === '1';
	} catch {
		return false;
	}
}

function markNativeCleanupCompleted(): void {
	try {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(NATIVE_SW_CLEANUP_STORAGE_KEY, '1');
		}
	} catch {
		// Sin acceso a localStorage en contextos restringidos
	}
}

export async function setupServiceWorker(options?: SwSetupOptions): Promise<void> {
	if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;

	const isNative = options?.isNative ?? Capacitor.isNativePlatform();
	const isProd = options?.isProd ?? import.meta.env.PROD;

	if (isNative) {
		try {
			const regs = await navigator.serviceWorker.getRegistrations();
			const ownRegs = regs.filter(isOwnServiceWorkerRegistration);
			if (ownRegs.length > 0) {
				await Promise.all(ownRegs.map((reg) => reg.unregister().catch(() => false)));
			}

			const alreadyCleaned = hasCompletedNativeCleanup();
			if ((!alreadyCleaned || ownRegs.length > 0) && typeof caches !== 'undefined') {
				const keys = await caches.keys();
				const ownCaches = keys.filter((k) => k.startsWith(ROCKOLA_CACHE_PREFIX));
				await Promise.all(ownCaches.map((k) => caches.delete(k).catch(() => false)));
			}
			if (!alreadyCleaned) {
				markNativeCleanupCompleted();
			}
		} catch {
			// Ignoramos si el WebView restringe el almacenamiento de Service Workers
		}
		return;
	}

	if (!isProd) return;
	try {
		await navigator.serviceWorker.register('./sw.js');
	} catch {
		// Registro opcional en navegación privada o contextos sin HTTPS/localhost
	}
}
