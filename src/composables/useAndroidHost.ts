// Puente tipado hacia el plugin nativo Kotlin RockolaServer en Capacitor Android.
// Permite arrancar/detener el servidor embebido (Chaquopy + ForegroundService)
// y elegir carpetas de la MicroSD resolviendo su ruta real en Android 11+.

import { Capacitor, SystemBars, registerPlugin } from '@capacitor/core';
import { ref } from 'vue';
import { listenLocally, volume } from '../stores/usePlaybackStore';
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
	trackPath?: string | null;
	duration?: number;
	position?: number;
	isFavorite?: boolean;
	isPauseAfter?: boolean;
}

export interface MediaPositionPayload {
	duration: number;
	position: number;
	paused: boolean;
}

export interface RockolaServerPlugin {
	startServer(options?: { port?: number; musicDir?: string }): Promise<AndroidServerInfo>;
	stopServer(): Promise<{ stopped: boolean }>;
	getStatus(): Promise<AndroidServerInfo>;
	pickMusicFolder(): Promise<PickMusicFolderResult>;
	hasStoragePermission(): Promise<{ granted: boolean }>;
	requestStoragePermission(): Promise<{ granted: boolean }>;
	updateMediaNotification(options: MediaNotificationPayload): Promise<{ updated: boolean }>;
	updateMediaPosition(options: MediaPositionPayload): Promise<{ updated: boolean }>;
	hapticFeedback(options?: { heavy?: boolean }): Promise<{ performed: boolean }>;
	setKeepScreenOn(options: { enabled: boolean }): Promise<{ enabled: boolean }>;
	shareUrl(options: { url: string; title?: string; text?: string }): Promise<{ shared: boolean }>;
	consumePendingShortcut(): Promise<{ action: string | null }>;
	setFogonState(options: { active: boolean }): Promise<{ active: boolean }>;
	enterPipMode(): Promise<{ entered: boolean }>;
	getMediaVolume(): Promise<{ level: number; muted: boolean }>;
	setMediaVolume(options: { level: number }): Promise<{ level: number; muted: boolean }>;
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

export const isAndroidFullscreen = ref<boolean>(false);
export const isAndroidPipMode = ref<boolean>(false);

export function isNativeAndroidHost(): boolean {
	return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android';
}

export function triggerAndroidHaptic(heavy = false): void {
	if (!isNativeAndroidHost()) return;
	void RockolaServer.hapticFeedback({ heavy }).catch(() => {
		// Fallamos silenciosamente si el puente nativo todavía no está listo
	});
}

export async function setAndroidKeepScreenOn(enabled: boolean): Promise<void> {
	if (!isNativeAndroidHost()) return;
	try {
		await RockolaServer.setKeepScreenOn({ enabled });
	} catch {
		// Ignoramos errores transitorios si la ventana todavía no está adjunta
	}
}

export async function shareAndroidUrl(options: { url: string; title?: string; text?: string }): Promise<boolean> {
	if (!isNativeAndroidHost()) return false;
	try {
		const res = await RockolaServer.shareUrl(options);
		return Boolean(res?.shared);
	} catch {
		return false;
	}
}

export async function consumeAndroidPendingShortcut(): Promise<string | null> {
	if (!isNativeAndroidHost()) return null;
	try {
		const res = await RockolaServer.consumePendingShortcut();
		return res?.action?.trim() || null;
	} catch {
		return null;
	}
}

export async function setAndroidFogonState(active: boolean): Promise<void> {
	if (!isNativeAndroidHost()) return;
	try {
		await RockolaServer.setFogonState({ active });
	} catch {
		// Ignoramos errores transitorios durante el montaje o cierre
	}
}

export async function enterAndroidPipMode(): Promise<boolean> {
	if (!isNativeAndroidHost()) return false;
	try {
		const res = await RockolaServer.enterPipMode();
		return Boolean(res?.entered);
	} catch {
		return false;
	}
}

export async function getAndroidMediaVolume(): Promise<{ level: number; muted: boolean } | null> {
	if (!isNativeAndroidHost()) return null;
	try {
		const res = await RockolaServer.getMediaVolume();
		if (res && typeof res.level === 'number') {
			return { level: Math.max(0, Math.min(100, res.level)), muted: Boolean(res.muted) };
		}
		return null;
	} catch {
		return null;
	}
}

export async function setAndroidMediaVolume(level: number): Promise<number | null> {
	if (!isNativeAndroidHost()) return null;
	const clamped = Math.max(0, Math.min(100, Math.round(level)));
	try {
		const res = await RockolaServer.setMediaVolume({ level: clamped });
		return typeof res?.level === 'number' ? res.level : clamped;
	} catch {
		return null;
	}
}

export async function toggleAndroidFullscreen(): Promise<boolean> {
	if (!isNativeAndroidHost()) return false;
	const next = !isAndroidFullscreen.value;
	if (next) {
		await SystemBars.hide();
	} else {
		await SystemBars.show();
	}
	isAndroidFullscreen.value = next;
	return next;
}

const STORAGE_KEY_REMOTE_SERVER = 'rockola_remote_server_url';

function readSavedRemoteServer(): string | null {
	try {
		if (typeof localStorage === 'undefined') return null;
		const saved = localStorage.getItem(STORAGE_KEY_REMOTE_SERVER);
		return saved ? saved.trim() || null : null;
	} catch {
		return null;
	}
}

export const activeRemoteServerUrl = ref<string | null>(readSavedRemoteServer());

export function normalizeServerOrigin(raw: string | null | undefined): string | null {
	const cleaned = (raw ?? '').trim().replace(/\/+$/, '');
	if (!cleaned) return null;
	const withProtocol = /^https?:\/\//i.test(cleaned) ? cleaned : `http://${cleaned}`;
	try {
		const parsed = new URL(withProtocol);
		if (!parsed.port && !/:\d+$/.test(parsed.host) && parsed.protocol === 'http:') {
			parsed.port = '1729';
		}
		return parsed.origin;
	} catch {
		return null;
	}
}

export async function connectToRemoteServer(rawUrl: string): Promise<string> {
	const normalized = normalizeServerOrigin(rawUrl);
	if (!normalized) {
		throw new Error('Dirección de servidor inválida (ej: 192.168.0.55 o http://192.168.0.55:1729)');
	}

	const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
	const timer = controller ? setTimeout(() => controller.abort(), 4000) : null;
	try {
		const res = await fetch(`${normalized}/health`, controller ? { signal: controller.signal } : undefined);
		if (!res.ok) {
			throw new Error(`El servidor respondió con estado ${res.status}`);
		}
	} finally {
		if (timer) clearTimeout(timer);
	}

	try {
		localStorage.setItem(STORAGE_KEY_REMOTE_SERVER, normalized);
	} catch {
		// Sin acceso a localStorage en modo restringido
	}
	activeRemoteServerUrl.value = normalized;
	setApiOrigin(normalized);
	return normalized;
}

export function resetToLocalServer(): void {
	try {
		localStorage.removeItem(STORAGE_KEY_REMOTE_SERVER);
	} catch {
		// Ignorado
	}
	activeRemoteServerUrl.value = null;
}

let recoveryInFlight: Promise<boolean> | null = null;
let lastRecoveryAttemptAt = 0;

async function probeLocalHealth(port: number, timeoutMs = 2000): Promise<boolean> {
	const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
	const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
	try {
		const res = await fetch(
			`http://127.0.0.1:${port}/health`,
			controller ? { signal: controller.signal } : undefined
		);
		return res.ok;
	} catch {
		return false;
	} finally {
		if (timer) clearTimeout(timer);
	}
}

/**
 * Verifica si el servidor local embebido en Android murió y lo reinicia solo tras confirmar
 * (servicio detenido por el SO o dos chequeos /health consecutivos fallidos).
 * Nunca se ejecuta en web ni cuando está conectado a un servidor remoto.
 */
export async function ensureLocalAndroidServerAlive(opts?: {
	retryDelayMs?: number;
	cooldownMs?: number;
}): Promise<boolean> {
	if (!isNativeAndroidHost() || activeRemoteServerUrl.value) return false;
	if (recoveryInFlight) return recoveryInFlight;

	const cooldownMs = opts?.cooldownMs ?? 10000;
	const now = Date.now();
	if (cooldownMs > 0 && now - lastRecoveryAttemptAt < cooldownMs) {
		return false;
	}

	recoveryInFlight = (async () => {
		try {
			const status = await RockolaServer.getStatus();
			const port = status.port || 1729;

			if (!status.running) {
				lastRecoveryAttemptAt = Date.now();
				await initAndroidServer();
				return true;
			}

			if (await probeLocalHealth(port)) {
				return false;
			}

			// Una sola falla puede ser transitoria: reintentamos antes de concluir que murió
			const retryDelayMs = opts?.retryDelayMs ?? 1200;
			await new Promise((resolve) => setTimeout(resolve, retryDelayMs));

			if (await probeLocalHealth(port)) {
				return false;
			}

			lastRecoveryAttemptAt = Date.now();
			try {
				await RockolaServer.stopServer();
			} catch {
				// Ignoramos error si el proceso Python ya estaba caído
			}
			await initAndroidServer();
			return true;
		} catch {
			return false;
		} finally {
			recoveryInFlight = null;
		}
	})();

	return recoveryInFlight;
}

export async function initAndroidServer(opts?: { pollIntervalMs?: number; timeoutMs?: number }): Promise<boolean> {
	if (!isNativeAndroidHost()) return false;

	// En Android el teléfono es su propio parlante por defecto ("Escuchar acá")
	listenLocally.value = true;
	void getAndroidMediaVolume().then((mediaVol) => {
		if (mediaVol) {
			volume.value = mediaVol.level;
		}
	});

	const savedRemote = activeRemoteServerUrl.value ?? readSavedRemoteServer();
	if (savedRemote) {
		activeRemoteServerUrl.value = savedRemote;
		setApiOrigin(savedRemote);
		androidServerStatus.value = {
			running: true,
			port: 1729,
			localIp: 'remoto',
			serverUrl: savedRemote,
			musicDir: null,
			needsFolder: false,
		};
		return true;
	}

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

let lastPosSentAt = 0;
let lastPosValue = -1;
let lastDurationValue = -1;
let lastPausedValue: boolean | null = null;

export function resetAndroidMediaPositionThrottle(): void {
	lastPosSentAt = 0;
	lastPosValue = -1;
	lastDurationValue = -1;
	lastPausedValue = null;
}

export async function syncAndroidMediaNotification(payload: MediaNotificationPayload): Promise<void> {
	if (!isNativeAndroidHost()) return;
	const duration = payload.duration ?? 0;
	const position = payload.position ?? 0;
	lastPosSentAt = Date.now();
	lastPosValue = position;
	lastDurationValue = duration;
	lastPausedValue = payload.paused;
	try {
		await RockolaServer.updateMediaNotification({
			title: payload.title,
			artist: payload.artist,
			paused: payload.paused,
			coverUrl: payload.coverUrl ?? null,
			trackPath: payload.trackPath ?? null,
			duration,
			position,
			isFavorite: Boolean(payload.isFavorite),
			isPauseAfter: Boolean(payload.isPauseAfter),
		});
	} catch {
		// Ignoramos errores transitorios si el servicio todavía está levantando
	}
}

export async function syncAndroidMediaPosition(payload: MediaPositionPayload): Promise<void> {
	if (!isNativeAndroidHost()) return;

	const now = Date.now();
	const isFirst = lastPausedValue === null;
	const pausedChanged = payload.paused !== lastPausedValue;
	const durationChanged = Math.abs(payload.duration - lastDurationValue) > 0.5;
	const jumped = Math.abs(payload.position - lastPosValue) > 1.5;
	const elapsed = now - lastPosSentAt >= 3000;

	if (!isFirst && !pausedChanged && !durationChanged && !jumped && !elapsed) {
		return;
	}

	lastPosSentAt = now;
	lastPosValue = payload.position;
	lastDurationValue = payload.duration;
	lastPausedValue = payload.paused;

	try {
		await RockolaServer.updateMediaPosition({
			duration: payload.duration,
			position: payload.position,
			paused: payload.paused,
		});
	} catch {
		// Ignoramos errores transitorios si el servicio todavía está levantando
	}
}
