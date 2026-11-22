// Store único de verdad para el modo activo (host local vs cliente remoto),
// estado del servidor embebido, estado de conexión WebSocket, errores y destino multimedia.

import { computed, ref } from 'vue';
import {
	currentTracks,
	favorites,
	isScanning,
	originalTracks,
	scanStatus,
	trackMap,
	urlMetadata,
} from './useLibraryStore';
import {
	currentTrackPath,
	duration,
	hasLocalPlayer,
	historyState,
	isPaused,
	listenLocally,
	localTimePos,
	pauseAfterPath,
	pendingSeekTime,
	timePos,
	topPlayedState,
} from './usePlaybackStore';
import { queueState } from './useQueueStore';
import { djNextTrack, isPlayingRadioAnnouncement, isSynthesizingRadio } from './useRadioStore';
import { localIp, serverUrl } from './useUiStore';

export type ServerMode = 'host' | 'remote';
export type LocalServerState = 'stopped' | 'starting' | 'ready' | 'recovering' | 'unavailable' | 'stopping';
export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';
export type LibraryFolderStatus =
	'ok' | 'unconfigured' | 'missing' | 'permission_denied' | 'storage_unavailable' | 'unsupported_provider';

export interface ServerErrorInfo {
	code: string;
	message: string;
	timestamp: number;
}

export interface MediaControlTarget {
	mode: ServerMode;
	origin: string;
	authHeader: string | null;
	generation: number;
}

export const STORAGE_KEY_REMOTE_SERVER = 'rockola_remote_server_url';

function readSavedRemoteServer(): string | null {
	try {
		if (typeof localStorage === 'undefined') return null;
		const saved = localStorage.getItem(STORAGE_KEY_REMOTE_SERVER);
		return saved ? saved.trim() || null : null;
	} catch {
		return null;
	}
}

export const serverMode = ref<ServerMode>('host');
export const localServerState = ref<LocalServerState>('stopped');
export const connectionState = ref<ConnectionState>('disconnected');
export const localServerPort = ref<number>(1729);
export const localServerIp = ref<string>('127.0.0.1');
export const localServerLanUrl = ref<string>('http://127.0.0.1:1729');
export const localMusicDir = ref<string | null>(null);
export const libraryFolderStatus = ref<LibraryFolderStatus>('ok');
export const libraryFolderError = ref<string | null>(null);
export const lastServerError = ref<ServerErrorInfo | null>(null);
export const mediaTargetGeneration = ref<number>(0);

export const lastRemoteServerUrl = ref<string | null>(readSavedRemoteServer());
const _remoteServerUrl = ref<string | null>(null);
const _remoteAuthHeader = ref<string | null>(null);

// Ref escribible derivada que mantiene sincronía bidireccional entre serverMode y callers legados
export const activeRemoteServerUrl = computed<string | null>({
	get: () => (serverMode.value === 'remote' ? _remoteServerUrl.value : null),
	set: (val) => {
		const cleaned = val ? val.trim() || null : null;
		if (cleaned) {
			if (_remoteServerUrl.value !== cleaned || serverMode.value !== 'remote') {
				_remoteServerUrl.value = cleaned;
				serverMode.value = 'remote';
				mediaTargetGeneration.value += 1;
			}
		} else if (serverMode.value !== 'host' || _remoteServerUrl.value !== null) {
			_remoteServerUrl.value = null;
			_remoteAuthHeader.value = null;
			serverMode.value = 'host';
			mediaTargetGeneration.value += 1;
		}
	},
});

export const isHostMode = computed<boolean>(() => serverMode.value === 'host');
export const isRemoteMode = computed<boolean>(() => serverMode.value === 'remote' && Boolean(_remoteServerUrl.value));

export const activeServerOrigin = computed<string>(() => {
	if (serverMode.value === 'remote' && _remoteServerUrl.value) {
		return _remoteServerUrl.value;
	}
	return `http://127.0.0.1:${localServerPort.value || 1729}`;
});

export const activeMediaTarget = computed<MediaControlTarget>(() => ({
	mode: isRemoteMode.value ? 'remote' : 'host',
	origin: activeServerOrigin.value,
	authHeader: isRemoteMode.value ? _remoteAuthHeader.value : null,
	generation: mediaTargetGeneration.value,
}));

export const needsMusicFolder = computed<boolean>(
	() => isHostMode.value && (!localMusicDir.value || libraryFolderStatus.value !== 'ok')
);

export function setRemoteMode(origin: string, authHeader: string | null = null): void {
	const cleaned = origin.trim().replace(/\/+$/, '');
	_remoteServerUrl.value = cleaned;
	_remoteAuthHeader.value = authHeader;
	serverMode.value = 'remote';
	mediaTargetGeneration.value += 1;
}

export function setHostMode(): void {
	_remoteServerUrl.value = null;
	_remoteAuthHeader.value = null;
	serverMode.value = 'host';
	mediaTargetGeneration.value += 1;
}

export function setServerError(code: string, message: string): void {
	lastServerError.value = { code, message, timestamp: Date.now() };
}

export function clearServerError(): void {
	lastServerError.value = null;
}

export function resetPlaybackAndLibraryState(): void {
	currentTrackPath.value = null;
	queueState.value = [];
	historyState.value = [];
	isPaused.value = false;
	duration.value = 0;
	timePos.value = 0;
	localTimePos.value = 0;
	pendingSeekTime.value = null;
	pauseAfterPath.value = null;
	favorites.value = [];
	originalTracks.value = [];
	currentTracks.value = [];
	trackMap.value = {};
	topPlayedState.value = [];
	djNextTrack.value = null;
	urlMetadata.value = {};
	serverUrl.value = null;
	localIp.value = null;
	isScanning.value = false;
	scanStatus.value = {
		is_scanning: false,
		is_analyzing_mood: false,
		phase: 'idle',
		current: 0,
		total: 0,
		message: '',
	};
	isPlayingRadioAnnouncement.value = false;
	isSynthesizingRadio.value = false;
	hasLocalPlayer.value = false;
	listenLocally.value = false;
}

export function resetServerConnectionStore(): void {
	serverMode.value = 'host';
	_remoteServerUrl.value = null;
	_remoteAuthHeader.value = null;
	localServerState.value = 'stopped';
	connectionState.value = 'disconnected';
	localServerPort.value = 1729;
	localServerIp.value = '127.0.0.1';
	localServerLanUrl.value = 'http://127.0.0.1:1729';
	localMusicDir.value = null;
	libraryFolderStatus.value = 'ok';
	libraryFolderError.value = null;
	lastServerError.value = null;
	mediaTargetGeneration.value = 0;
}

export function useServerConnectionStore() {
	return {
		serverMode,
		localServerState,
		connectionState,
		localServerPort,
		localServerIp,
		localServerLanUrl,
		localMusicDir,
		libraryFolderStatus,
		libraryFolderError,
		lastServerError,
		mediaTargetGeneration,
		lastRemoteServerUrl,
		activeRemoteServerUrl,
		isHostMode,
		isRemoteMode,
		activeServerOrigin,
		activeMediaTarget,
		needsMusicFolder,
		setRemoteMode,
		setHostMode,
		setServerError,
		clearServerError,
		resetPlaybackAndLibraryState,
		resetServerConnectionStore,
	};
}
