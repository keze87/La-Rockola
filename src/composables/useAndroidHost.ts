// Puente tipado hacia el plugin nativo Kotlin RockolaServer en Capacitor Android.
// Permite arrancar/detener el servidor embebido (Chaquopy + ForegroundService),
// alternar explícitamente entre modo host local y cliente remoto, y elegir carpetas de música.

import { Capacitor, SystemBars, registerPlugin } from '@capacitor/core';
import { ref, watch } from 'vue';
import { listenLocally, volume } from '../stores/usePlaybackStore';
import {
	type LibraryFolderStatus,
	STORAGE_KEY_REMOTE_SERVER,
	activeMediaTarget,
	activeRemoteServerUrl,
	clearServerError,
	isHostMode,
	lastRemoteServerUrl,
	libraryFolderError,
	libraryFolderStatus,
	localMusicDir,
	localMusicDisplayName,
	localServerIp,
	localServerLanUrl,
	localServerPort,
	localServerState,
	resetPlaybackAndLibraryState,
	setHostMode,
	setRemoteMode,
	setServerError,
} from '../stores/useServerConnectionStore';
import { requestSocketReconnect } from './player/connectionActions';
import { setApiOrigin, useApi } from './useApi';

export interface AndroidServerInfo {
	running: boolean;
	hostState?: string;
	lastError?: string | null;
	port: number;
	localIp: string;
	serverUrl: string;
	musicDir: string | null;
	bootStage?: string;
	extractProgress?: number;
}

export interface AndroidServerStatus extends AndroidServerInfo {
	needsFolder: boolean;
}

export interface PickMusicFolderResult {
	path: string | null;
	uri?: string | null;
	displayName?: string | null;
	status?: string | null;
	error?: string | null;
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

export interface MediaTargetPayload {
	mode: 'host' | 'remote';
	origin: string;
	authHeader?: string | null;
	generation: number;
}

export interface RockolaServerPlugin {
	markUiReady?(): Promise<{ ready: boolean }>;
	setBackHandlerEnabled?(options: { enabled: boolean }): Promise<{ enabled: boolean }>;
	startServer(options?: { port?: number; musicDir?: string }): Promise<AndroidServerInfo>;
	stopServer(): Promise<{ stopped: boolean }>;
	getStatus(): Promise<AndroidServerInfo>;
	pickMusicFolder(): Promise<PickMusicFolderResult>;
	validateMusicFolder?(options?: { uri?: string }): Promise<{
		valid: boolean;
		status: LibraryFolderStatus;
		uri: string;
		displayName?: string | null;
		error?: string | null;
	}>;
	updateMediaNotification(options: MediaNotificationPayload): Promise<{ updated: boolean }>;
	updateMediaPosition(options: MediaPositionPayload): Promise<{ updated: boolean }>;
	setMediaTarget?(options: MediaTargetPayload): Promise<{ updated: boolean }>;
	hapticFeedback(options?: { heavy?: boolean }): Promise<{ performed: boolean }>;
	setKeepScreenOn(options: { enabled: boolean }): Promise<{ enabled: boolean }>;
	shareUrl(options: { url: string; title?: string; text?: string }): Promise<{ shared: boolean }>;
	consumePendingShortcut(): Promise<{ action: string | null }>;
	setFogonState(options: { active: boolean }): Promise<{ active: boolean }>;
	enterPipMode(): Promise<{ entered: boolean; reason?: string | null }>;
	getMediaVolume(): Promise<{ level: number; muted: boolean }>;
	setMediaVolume(options: { level: number }): Promise<{ level: number; muted: boolean }>;
}

const RockolaServer = registerPlugin<RockolaServerPlugin>('RockolaServer');

export { activeRemoteServerUrl, lastRemoteServerUrl };

export const androidServerStatus = ref<AndroidServerStatus>({
	running: false,
	port: 1729,
	localIp: '127.0.0.1',
	serverUrl: 'http://127.0.0.1:1729',
	musicDir: null,
	needsFolder: false,
});

// Sincroniza androidServerStatus desde el store único de verdad para mantener compatibilidad con vistas y tests
watch(
	[localServerState, localServerPort, localServerIp, localServerLanUrl, localMusicDir, libraryFolderStatus],
	([srvState, port, ip, lanUrl, musicDir, folderStatus]) => {
		const normalizedDir = musicDir ? musicDir.trim() || null : null;
		androidServerStatus.value = {
			running: srvState === 'ready',
			port,
			localIp: ip,
			serverUrl: lanUrl,
			musicDir: normalizedDir,
			needsFolder: !normalizedDir || folderStatus !== 'ok',
		};
	},
	{ flush: 'sync' }
);

export const isAndroidFullscreen = ref<boolean>(false);
export const isAndroidPipMode = ref<boolean>(false);
export const androidBootStage = ref<string>('idle');
export const androidExtractProgress = ref<number>(0);

export function isNativeAndroidHost(): boolean {
	return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android';
}

export function markAndroidUiReady(): void {
	if (!isNativeAndroidHost() || typeof RockolaServer.markUiReady !== 'function') return;
	void RockolaServer.markUiReady().catch(() => {
		// El splash nativo tiene tope de seguridad si el plugin todavía no está listo
	});
}

export function setAndroidBackHandlerEnabled(enabled: boolean): void {
	if (!isNativeAndroidHost() || typeof RockolaServer.setBackHandlerEnabled !== 'function') return;
	void Promise.resolve(RockolaServer.setBackHandlerEnabled({ enabled })).catch(() => {
		// Ignoramos errores transitorios si el puente nativo todavía no está listo
	});
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

export async function enterAndroidPipModeDetailed(): Promise<{ entered: boolean; reason: string | null }> {
	if (!isNativeAndroidHost()) return { entered: false, reason: 'NOT_ANDROID' };
	try {
		const res = await RockolaServer.enterPipMode();
		return { entered: Boolean(res?.entered), reason: res?.reason ?? null };
	} catch (err) {
		return {
			entered: false,
			reason: err instanceof Error ? err.message : 'PIP_FAILED',
		};
	}
}

export async function enterAndroidPipMode(): Promise<boolean> {
	const res = await enterAndroidPipModeDetailed();
	return res.entered;
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

export async function syncAndroidMediaTarget(): Promise<void> {
	if (!isNativeAndroidHost()) return;
	if (typeof RockolaServer.setMediaTarget !== 'function') return;
	try {
		const target = activeMediaTarget.value;
		await RockolaServer.setMediaTarget({
			mode: target.mode,
			origin: target.origin,
			authHeader: target.authHeader,
			generation: target.generation,
		});
	} catch {
		// Ignoramos si la versión del plugin nativo no expone setMediaTarget durante tests aislados
	}
}

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

interface HealthProbeResult {
	ok: boolean;
	code: 'OK' | 'AUTH_FAILED' | 'HTTP_ERROR' | 'INVALID_RESPONSE' | 'TIMEOUT' | 'NETWORK_ERROR';
	status?: number;
	message?: string;
}

async function probeServerHealth(origin: string, timeoutMs = 2000): Promise<HealthProbeResult> {
	const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
	const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
	try {
		const res = await fetch(`${origin}/health`, controller ? { signal: controller.signal } : undefined);
		if (res.status === 401 || res.status === 403) {
			return {
				ok: false,
				code: 'AUTH_FAILED',
				status: res.status,
				message: `Error de autenticación en el servidor (${res.status})`,
			};
		}
		if (!res.ok) {
			return {
				ok: false,
				code: 'HTTP_ERROR',
				status: res.status,
				message: `El servidor respondió con estado ${res.status}`,
			};
		}
		if (typeof res.json === 'function') {
			const payload = (await res.json()) as { status?: string } | null;
			if (!payload || payload.status !== 'ok') {
				return {
					ok: false,
					code: 'INVALID_RESPONSE',
					message: 'El endpoint /health respondió sin estado válido',
				};
			}
		}
		return { ok: true, code: 'OK' };
	} catch (err) {
		const isAbort = err instanceof Error && err.name === 'AbortError';
		return {
			ok: false,
			code: isAbort ? 'TIMEOUT' : 'NETWORK_ERROR',
			message: isAbort
				? 'Tiempo de espera agotado al verificar salud del servidor'
				: err instanceof Error
					? err.message
					: 'Error de conectividad HTTP',
		};
	} finally {
		if (timer) clearTimeout(timer);
	}
}

export async function connectToRemoteServer(
	rawUrl: string,
	opts?: { timeoutMs?: number; onServerChanged?: () => void }
): Promise<string> {
	const normalized = normalizeServerOrigin(rawUrl);
	if (!normalized) {
		throw new Error('Dirección de servidor inválida (ej: 192.168.0.55 o http://192.168.0.55:1729)');
	}

	const probe = await probeServerHealth(normalized, opts?.timeoutMs ?? 4000);
	if (!probe.ok) {
		throw new Error(probe.message || 'No se pudo conectar al servidor remoto');
	}

	try {
		localStorage.setItem(STORAGE_KEY_REMOTE_SERVER, normalized);
	} catch {
		// Sin acceso a localStorage en modo restringido
	}

	lastRemoteServerUrl.value = normalized;
	setRemoteMode(normalized);
	clearServerError();
	resetPlaybackAndLibraryState();
	setApiOrigin(normalized);
	await syncAndroidMediaTarget();

	if (opts?.onServerChanged) {
		opts.onServerChanged();
	} else {
		requestSocketReconnect({ onlyIfActive: true });
	}
	return normalized;
}

export function disconnectFromRemoteServer(opts?: { onServerChanged?: () => void }): void {
	setHostMode();
	clearServerError();
	resetPlaybackAndLibraryState();
	setApiOrigin(`http://127.0.0.1:${localServerPort.value || 1729}`);
	void syncAndroidMediaTarget();

	if (opts?.onServerChanged) {
		opts.onServerChanged();
	} else {
		requestSocketReconnect({ onlyIfActive: true });
	}
}

export const resetToLocalServer = disconnectFromRemoteServer;

let initInFlight: Promise<boolean> | null = null;
let stopInFlight: Promise<void> | null = null;
let recoveryInFlight: Promise<boolean> | null = null;
let lastRecoveryAttemptAt = 0;

function applyLocalServerInfo(info: AndroidServerInfo): number {
	const port = info.port || 1729;
	const musicDir = info.musicDir ? info.musicDir.trim() : '';
	localServerPort.value = port;
	localServerIp.value = info.localIp || '127.0.0.1';
	localServerLanUrl.value = info.serverUrl || `http://127.0.0.1:${port}`;
	localMusicDir.value = musicDir || null;
	if (!musicDir) {
		libraryFolderStatus.value = 'unconfigured';
	} else if (libraryFolderStatus.value === 'unconfigured') {
		libraryFolderStatus.value = 'ok';
	}
	if (info.hostState === 'failed') {
		localServerState.value = 'unavailable';
		setServerError('SERVER_START_FAILED', info.lastError || 'El servidor embebido falló al arrancar');
	} else if (info.hostState === 'stopping') {
		localServerState.value = 'stopping';
	} else if (info.hostState === 'stopped' && !info.running) {
		localServerState.value = 'stopped';
	}
	if (typeof info.bootStage === 'string') {
		androidBootStage.value = info.bootStage;
	}
	if (typeof info.extractProgress === 'number') {
		androidExtractProgress.value = info.extractProgress;
	}
	return port;
}

export async function refreshAndroidHostStatus(): Promise<AndroidServerInfo | null> {
	if (!isNativeAndroidHost()) return null;
	try {
		const info = await RockolaServer.getStatus();
		applyLocalServerInfo(info);
		if (info.hostState === 'ready' || (info.running && !info.hostState)) {
			localServerState.value = 'ready';
			clearServerError();
		} else if (info.hostState === 'starting') {
			localServerState.value = 'starting';
		}
		return info;
	} catch {
		return null;
	}
}

export function initAndroidServer(opts?: { pollIntervalMs?: number; timeoutMs?: number }): Promise<boolean> {
	if (!isNativeAndroidHost()) return Promise.resolve(false);
	if (initInFlight) return initInFlight;

	initInFlight = (async () => {
		if (stopInFlight) {
			await stopInFlight;
		}

		setHostMode();
		clearServerError();
		localServerState.value = 'starting';

		// En Android el backend nativo (ExoPlayer) reproduce el audio fuera del WebView
		listenLocally.value = false;
		void getAndroidMediaVolume().then((mediaVol) => {
			if (mediaVol) {
				volume.value = mediaVol.level;
			}
		});

		const pollIntervalMs = opts?.pollIntervalMs ?? 250;
		const timeoutMs = opts?.timeoutMs ?? 15000;

		let info: AndroidServerInfo;
		try {
			info = await RockolaServer.startServer();
		} catch (err) {
			const msg = err instanceof Error ? err.message : 'No se pudo iniciar el servicio nativo';
			localServerState.value = 'unavailable';
			setServerError('SERVER_START_FAILED', msg);
			return false;
		}

		const port = applyLocalServerInfo(info);
		if (info.hostState === 'failed') {
			return false;
		}
		if (isHostMode.value) {
			setApiOrigin(`http://127.0.0.1:${port}`);
			await syncAndroidMediaTarget();
		}

		const localOrigin = `http://127.0.0.1:${port}`;
		const deadline = Date.now() + timeoutMs;
		let lastFailure = 'El servidor embebido no respondió a tiempo';

		while (Date.now() <= deadline) {
			if (!isHostMode.value) {
				// El usuario cambió explícitamente a servidor remoto durante el arranque
				return false;
			}
			const probe = await probeServerHealth(localOrigin, 1500);
			if (probe.ok) {
				localServerState.value = 'ready';
				clearServerError();
				return true;
			}
			if (probe.message) {
				lastFailure = probe.message;
			}
			if (typeof RockolaServer.getStatus === 'function') {
				try {
					const status = await RockolaServer.getStatus();
					applyLocalServerInfo(status);
					if (status?.hostState === 'failed') {
						return false;
					}
				} catch {
					// Continuamos esperando /health mientras el plugin responde
				}
			}
			await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
		}

		localServerState.value = 'unavailable';
		setServerError('HEALTH_CHECK_TIMEOUT', lastFailure);
		return false;
	})().finally(() => {
		initInFlight = null;
	});

	return initInFlight;
}

/**
 * Verifica si el servidor local embebido en Android murió y lo reinicia solo tras confirmar
 * (servicio detenido por el SO o dos chequeos /health consecutivos fallidos).
 * Nunca se ejecuta en web ni cuando está en modo cliente remoto.
 */
export function ensureLocalAndroidServerAlive(opts?: {
	retryDelayMs?: number;
	cooldownMs?: number;
	initTimeoutMs?: number;
}): Promise<boolean> {
	if (!isNativeAndroidHost() || !isHostMode.value) return Promise.resolve(false);
	if (recoveryInFlight) return recoveryInFlight;
	if (initInFlight) return initInFlight;

	const cooldownMs = opts?.cooldownMs ?? 10000;
	const now = Date.now();
	if (cooldownMs > 0 && now - lastRecoveryAttemptAt < cooldownMs) {
		return Promise.resolve(false);
	}

	recoveryInFlight = (async () => {
		try {
			const status = await RockolaServer.getStatus();
			const port = status.port || localServerPort.value || 1729;
			const localOrigin = `http://127.0.0.1:${port}`;

			if (!status.running) {
				lastRecoveryAttemptAt = Date.now();
				localServerState.value = 'recovering';
				const restarted = await initAndroidServer({
					pollIntervalMs: 100,
					timeoutMs: opts?.initTimeoutMs ?? 15000,
				});
				return restarted;
			}

			if ((await probeServerHealth(localOrigin, 2000)).ok) {
				localServerState.value = 'ready';
				return false;
			}

			// Una sola falla puede ser transitoria: reintentamos antes de concluir que murió
			const retryDelayMs = opts?.retryDelayMs ?? 1200;
			await new Promise((resolve) => setTimeout(resolve, retryDelayMs));

			if ((await probeServerHealth(localOrigin, 2000)).ok) {
				localServerState.value = 'ready';
				return false;
			}

			lastRecoveryAttemptAt = Date.now();
			localServerState.value = 'recovering';
			try {
				await RockolaServer.stopServer();
			} catch {
				// Ignoramos error si el proceso Python ya estaba caído
			}
			const restarted = await initAndroidServer({
				pollIntervalMs: 100,
				timeoutMs: opts?.initTimeoutMs ?? 15000,
			});
			return restarted;
		} catch (err) {
			localServerState.value = 'unavailable';
			setServerError(
				'RECOVERY_FAILED',
				err instanceof Error ? err.message : 'Fallo verificando salud del servidor local'
			);
			return false;
		} finally {
			recoveryInFlight = null;
		}
	})();

	return recoveryInFlight;
}

export async function validateAndroidMusicFolder(uri?: string): Promise<LibraryFolderStatus> {
	if (!isNativeAndroidHost() || typeof RockolaServer.validateMusicFolder !== 'function') {
		return libraryFolderStatus.value;
	}
	try {
		const res = await RockolaServer.validateMusicFolder(uri ? { uri } : undefined);
		libraryFolderStatus.value = res.status;
		localMusicDisplayName.value = res.displayName ?? null;
		libraryFolderError.value = res.error ?? null;
		return res.status;
	} catch {
		return libraryFolderStatus.value;
	}
}

export async function pickAndApplyMusicFolder(): Promise<string | null> {
	if (!isNativeAndroidHost()) return null;

	const res = await RockolaServer.pickMusicFolder();
	if (res?.status && res.status !== 'ok') {
		libraryFolderStatus.value = res.status as LibraryFolderStatus;
		localMusicDisplayName.value = res.displayName ?? null;
		libraryFolderError.value = res.error ?? 'No se pudo acceder a la carpeta seleccionada';
		return null;
	}

	const selectedPath = res?.path?.trim() || res?.uri?.trim();
	if (!selectedPath) return null;

	await useApi().setMusicDir(selectedPath);
	localMusicDir.value = selectedPath;
	localMusicDisplayName.value = res?.displayName ?? null;
	libraryFolderStatus.value = 'ok';
	libraryFolderError.value = null;
	return selectedPath;
}

export function stopAndroidServer(): Promise<void> {
	if (!isNativeAndroidHost()) return Promise.resolve();
	if (stopInFlight) return stopInFlight;

	stopInFlight = (async () => {
		localServerState.value = 'stopping';
		try {
			await RockolaServer.stopServer();
			localServerState.value = 'stopped';
		} catch (err) {
			localServerState.value = 'unavailable';
			setServerError(
				'SERVER_STOP_FAILED',
				err instanceof Error ? err.message : 'No se pudo detener el servidor local'
			);
			throw err;
		} finally {
			stopInFlight = null;
		}
	})();

	return stopInFlight;
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
