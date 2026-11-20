// Puente tipado hacia el plugin nativo Kotlin RockolaServer en Capacitor Android.
// Permite arrancar/detener el servidor embebido (Chaquopy + ForegroundService)
// y elegir carpetas de la MicroSD resolviendo su ruta real en Android 11+.

import { Capacitor, registerPlugin } from '@capacitor/core';
import { ref } from 'vue';
import { listenLocally } from '../stores/usePlaybackStore';
import { setApiOrigin, useApi } from './useApi';

export interface AndroidServerInfo {
	running: boolean;
	port: number;
	localIp: string;
	serverUrl: string;
	musicDir: string | null;
}

export interface AndroidServerStatus extends AndroidServerInfo {
	needsFolder: boolean;
}

export interface PickMusicFolderResult {
	path: string | null;
	uri?: string | null;
}

export interface MediaNotificationPayload {
	title: string;
	artist: string;
	paused: boolean;
	coverUrl?: string | null;
}

export interface RockolaServerPlugin {
	startServer(options?: { port?: number; musicDir?: string }): Promise<AndroidServerInfo>;
	stopServer(): Promise<{ stopped: boolean }>;
	getStatus(): Promise<AndroidServerInfo>;
	pickMusicFolder(): Promise<PickMusicFolderResult>;
	hasStoragePermission(): Promise<{ granted: boolean }>;
	requestStoragePermission(): Promise<{ granted: boolean }>;
	updateMediaNotification(options: MediaNotificationPayload): Promise<{ updated: boolean }>;
}

const RockolaServer = registerPlugin<RockolaServerPlugin>('RockolaServer');

export const androidServerStatus = ref<AndroidServerStatus>({
	running: false,
	port: 1729,
	localIp: '127.0.0.1',
	serverUrl: 'http://127.0.0.1:1729',
	musicDir: null,
	needsFolder: false,
});

export function isNativeAndroidHost(): boolean {
	return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android';
}

export async function initAndroidServer(opts?: { pollIntervalMs?: number; timeoutMs?: number }): Promise<boolean> {
	if (!isNativeAndroidHost()) return false;

	// En Android el teléfono es su propio parlante por defecto ("Escuchar acá")
	listenLocally.value = true;

	const pollIntervalMs = opts?.pollIntervalMs ?? 250;
	const timeoutMs = opts?.timeoutMs ?? 15000;

	const info = await RockolaServer.startServer();
	const port = info.port || 1729;
	setApiOrigin(`http://127.0.0.1:${port}`);

	const musicDir = info.musicDir ? info.musicDir.trim() : '';
	androidServerStatus.value = {
		running: Boolean(info.running),
		port,
		localIp: info.localIp || '127.0.0.1',
		serverUrl: info.serverUrl || `http://127.0.0.1:${port}`,
		musicDir: musicDir || null,
		needsFolder: !musicDir,
	};

	const healthUrl = `http://127.0.0.1:${port}/health`;
	const deadline = Date.now() + timeoutMs;
	while (Date.now() <= deadline) {
		try {
			const res = await fetch(healthUrl);
			if (res.ok) {
				androidServerStatus.value.running = true;
				return true;
			}
		} catch {
			// El hilo Python de Uvicorn todavía está levantando
		}
		await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
	}
	return false;
}

export async function pickAndApplyMusicFolder(): Promise<string | null> {
	if (!isNativeAndroidHost()) return null;

	const res = await RockolaServer.pickMusicFolder();
	const selectedPath = res?.path?.trim();
	if (!selectedPath) return null;

	await useApi().setMusicDir(selectedPath);
	androidServerStatus.value = {
		...androidServerStatus.value,
		musicDir: selectedPath,
		needsFolder: false,
	};
	return selectedPath;
}

export async function stopAndroidServer(): Promise<void> {
	if (!isNativeAndroidHost()) return;
	await RockolaServer.stopServer();
	androidServerStatus.value.running = false;
}

export async function syncAndroidMediaNotification(payload: MediaNotificationPayload): Promise<void> {
	if (!isNativeAndroidHost()) return;
	try {
		await RockolaServer.updateMediaNotification({
			title: payload.title,
			artist: payload.artist,
			paused: payload.paused,
			coverUrl: payload.coverUrl ?? null,
		});
	} catch {
		// Ignoramos errores transitorios si el servicio todavía está levantando
	}
}
