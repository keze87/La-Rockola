import { beforeEach, describe, expect, it } from 'vitest';
import {
	activeMediaTarget,
	activeRemoteServerUrl,
	activeServerOrigin,
	connectionState,
	isHostMode,
	isRemoteMode,
	lastServerError,
	libraryFolderError,
	libraryFolderStatus,
	localMusicDir,
	localServerIp,
	localServerLanUrl,
	localServerPort,
	localServerState,
	mediaTargetGeneration,
	needsMusicFolder,
	resetPlaybackAndLibraryState,
	resetServerConnectionStore,
	serverMode,
	setHostMode,
	setRemoteMode,
} from '@/stores/useServerConnectionStore';
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
} from '@/stores/usePlaybackStore';
import { queueState } from '@/stores/useQueueStore';
import { currentTracks, favorites, isScanning, originalTracks, trackMap, urlMetadata } from '@/stores/useLibraryStore';
import { djNextTrack, isPlayingRadioAnnouncement, isSynthesizingRadio } from '@/stores/useRadioStore';
import { localIp, serverUrl } from '@/stores/useUiStore';

describe('useServerConnectionStore', () => {
	beforeEach(() => {
		resetServerConnectionStore();
	});

	it('maintains explicit host vs remote mode and active media target as single source of truth', () => {
		localServerPort.value = 1829;
		expect(serverMode.value).toBe('host');
		expect(isHostMode.value).toBe(true);
		expect(isRemoteMode.value).toBe(false);
		expect(activeServerOrigin.value).toBe('http://127.0.0.1:1829');
		expect(activeMediaTarget.value).toEqual({
			mode: 'host',
			origin: 'http://127.0.0.1:1829',
			authHeader: null,
			generation: 0,
		});

		setRemoteMode('http://192.168.1.50:1729');
		expect(serverMode.value).toBe('remote');
		expect(isHostMode.value).toBe(false);
		expect(isRemoteMode.value).toBe(true);
		expect(activeRemoteServerUrl.value).toBe('http://192.168.1.50:1729');
		expect(activeServerOrigin.value).toBe('http://192.168.1.50:1729');
		expect(mediaTargetGeneration.value).toBe(1);
		expect(activeMediaTarget.value).toEqual({
			mode: 'remote',
			origin: 'http://192.168.1.50:1729',
			authHeader: null,
			generation: 1,
		});

		setHostMode();
		expect(serverMode.value).toBe('host');
		expect(activeRemoteServerUrl.value).toBeNull();
		expect(activeServerOrigin.value).toBe('http://127.0.0.1:1829');
		expect(mediaTargetGeneration.value).toBe(2);
	});

	it('keeps serverMode synchronized when legacy activeRemoteServerUrl ref is mutated directly', () => {
		activeRemoteServerUrl.value = 'http://10.0.0.8:1729';
		expect(serverMode.value).toBe('remote');
		expect(isRemoteMode.value).toBe(true);
		expect(activeServerOrigin.value).toBe('http://10.0.0.8:1729');

		activeRemoteServerUrl.value = null;
		expect(serverMode.value).toBe('host');
		expect(isHostMode.value).toBe(true);
	});

	it('tracks explicit server lifecycle, connection state, folder status, and last error', () => {
		localServerState.value = 'starting';
		connectionState.value = 'connecting';
		localServerIp.value = '192.168.0.10';
		localServerLanUrl.value = 'http://192.168.0.10:1729';
		localMusicDir.value = null;
		libraryFolderStatus.value = 'unconfigured';
		libraryFolderError.value = 'Elegí una carpeta';
		lastServerError.value = { code: 'TEST', message: 'Fallo de prueba', timestamp: 1234 };

		expect(needsMusicFolder.value).toBe(true);
		expect(lastServerError.value?.code).toBe('TEST');

		localMusicDir.value = 'content://tree/123';
		libraryFolderStatus.value = 'ok';
		libraryFolderError.value = null;
		expect(needsMusicFolder.value).toBe(false);
	});

	it('resets stale playback, queue, library, and radio state cleanly on server switch', () => {
		currentTrackPath.value = '/music/viejo.mp3';
		queueState.value = ['/music/cola.mp3'];
		historyState.value = ['/music/historial.mp3'];
		isPaused.value = true;
		duration.value = 180;
		timePos.value = 42;
		localTimePos.value = 42;
		pendingSeekTime.value = 55;
		pauseAfterPath.value = '/music/viejo.mp3';
		favorites.value = ['/music/viejo.mp3'];
		originalTracks.value = [{ path: '/music/viejo.mp3', display_title: 'Viejo', display_artist: 'X' }];
		currentTracks.value = [...originalTracks.value];
		trackMap.value = { '/music/viejo.mp3': originalTracks.value[0] };
		topPlayedState.value = [...originalTracks.value];
		djNextTrack.value = originalTracks.value[0];
		urlMetadata.value = { 'https://x': { display_title: 'Y', display_artist: 'Z', path: 'https://x' } };
		serverUrl.value = 'http://192.168.0.99:1729';
		localIp.value = '192.168.0.99';
		isScanning.value = true;
		isPlayingRadioAnnouncement.value = true;
		isSynthesizingRadio.value = true;
		hasLocalPlayer.value = true;
		listenLocally.value = true;

		resetPlaybackAndLibraryState();

		expect(currentTrackPath.value).toBeNull();
		expect(queueState.value).toEqual([]);
		expect(historyState.value).toEqual([]);
		expect(isPaused.value).toBe(false);
		expect(duration.value).toBe(0);
		expect(timePos.value).toBe(0);
		expect(localTimePos.value).toBe(0);
		expect(pendingSeekTime.value).toBeNull();
		expect(pauseAfterPath.value).toBeNull();
		expect(favorites.value).toEqual([]);
		expect(originalTracks.value).toEqual([]);
		expect(currentTracks.value).toEqual([]);
		expect(trackMap.value).toEqual({});
		expect(topPlayedState.value).toEqual([]);
		expect(djNextTrack.value).toBeNull();
		expect(urlMetadata.value).toEqual({});
		expect(serverUrl.value).toBeNull();
		expect(localIp.value).toBeNull();
		expect(isScanning.value).toBe(false);
		expect(isPlayingRadioAnnouncement.value).toBe(false);
		expect(isSynthesizingRadio.value).toBe(false);
		expect(hasLocalPlayer.value).toBe(false);
		expect(listenLocally.value).toBe(false);
	});
});
