// Registro de Service Worker solo en web/PWA y limpieza explícita dentro del WebView nativo Android.

import { Capacitor } from '@capacitor/core';

export interface SwSetupOptions {
	isProd?: boolean;
	isNative?: boolean;
}

export async function setupServiceWorker(options?: SwSetupOptions): Promise<void> {
	if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;

	const isNative = options?.isNative ?? Capacitor.isNativePlatform();
	const isProd = options?.isProd ?? import.meta.env.PROD;

	if (isNative) {
		try {
			const regs = await navigator.serviceWorker.getRegistrations();
			await Promise.all(regs.map((reg) => reg.unregister().catch(() => false)));
			if (typeof caches !== 'undefined') {
				const keys = await caches.keys();
				await Promise.all(keys.map((k) => caches.delete(k).catch(() => false)));
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
