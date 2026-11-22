import { _startLocalPlayer, _stopLocalPlayer, applyRemoteSeek } from './useLocalPlayback';
import { applyLibrarySort } from './useLibrary';
import { useToasts } from './useToasts';
import { ensureLocalAndroidServerAlive, isNativeAndroidHost } from '../useAndroidHost';
import { getWsUrl } from '../useApi';
import {
	type LibraryFolderStatus,
	connectionState,
	isHostMode,
	libraryFolderError,
	libraryFolderStatus,
	localMusicDir,
	localMusicDisplayName,
} from '../../stores/useServerConnectionStore';
import { useWebSocket } from '@vueuse/core';
import {
	activeSort,
	closeSocketHandle,
	currentTrackPath,
	defaultSort,
	djBaraEnabled,
	djMode,
	djNextTrack,
	djSafeModeEnabled,
	duration,
	favorites,
	hasEdgeTts,
	hasFfmpeg,
	hasLocalPlayer,
	hasMpv,
	hasUserSelectedSort,
	historyState,
	isDraggingSeek,
	isPaused,
	isPlayingRadioAnnouncement,
	isScanning,
	isSocketConnected,
	isSynthesizingRadio,
	listenLocally,
	localIp,
	localTimePos,
	mpvVisible,
	originalTracks,
	pauseAfterPath,
	pendingSeekTime,
	queueState,
	radioModeEnabled,
	scanStatus,
	serverMuted,
	serverUrl,
	setWsSend,
	timePos,
	topPlayedState,
	trackMap,
	urlMetadata,
	urlParams,
	volume,
	weatherLocation,
} from './state';
import type { PlayerState, Track } from '../../types';

let socketGeneration = 0;
let socketRequested = false;
let activeCloseHandle: (() => void) | null = null;

export function useSocket() {
	const { showToast } = useToasts();

	function disconnectWebSocket(): void {
		socketRequested = false;
		socketGeneration += 1;
		const closeFn = activeCloseHandle;
		activeCloseHandle = null;
		closeFn?.();
		closeSocketHandle();
		connectionState.value = 'disconnected';
	}

	function reconnectWebSocket(opts?: { onlyIfActive?: boolean }): void {
		const shouldReconnect = !opts?.onlyIfActive || socketRequested;
		// Siempre invalidamos la generación y cerramos el handle previo aunque estuviera reconnecting
		disconnectWebSocket();
		if (shouldReconnect) {
			connectWebSocket();
		}
	}

	function connectWebSocket(): void {
		socketRequested = true;
		// Evitamos abrir múltiples conexiones si ya está instanciado
		if (isSocketConnected()) return;

		const gen = ++socketGeneration;
		let intentionallyClosed = false;
		let consecutiveDisconnects = 0;
		const wsUrl = getWsUrl('/ws');
		connectionState.value = 'connecting';

		// VueUse se encarga del auto-reconnect, backoff exponencial y limpieza
		const { send, close } = useWebSocket(wsUrl, {
			autoReconnect: {
				retries: () => !intentionallyClosed && gen === socketGeneration,
				delay: (retryCount) => Math.min(1000 * Math.pow(2, retryCount), 30000),
			},

			onConnected() {
				if (intentionallyClosed || gen !== socketGeneration) return;
				consecutiveDisconnects = 0;
				connectionState.value = 'connected';
				if (listenLocally.value) {
					send(JSON.stringify({ type: 'local_player_claim' }));
				}
			},

			onDisconnected() {
				if (intentionallyClosed || gen !== socketGeneration) return;
				consecutiveDisconnects += 1;
				connectionState.value = 'reconnecting';
				showToast('Se cortó la señal. Reconectando...', 'warning');
				if (isNativeAndroidHost() && isHostMode.value && consecutiveDisconnects >= 2) {
					void ensureLocalAndroidServerAlive();
				}
			},

			onMessage(_ws, event) {
				if (intentionallyClosed || gen !== socketGeneration) return;
				try {
					const data = JSON.parse(event.data);

					// Eventos de lógica del reproductor local
					if (data.type === 'local_player_seek') {
						// Otro cliente mandó un seek — lo aplicamos al <audio> local
						applyRemoteSeek(data);
						return;
					}

					if (data.type === 'local_player_claim_result') {
						if (data.ok) {
							// El servidor aceptó nuestro rol — arrancar el reproductor local (el servidor silencia MPV directamente)
							if (currentTrackPath.value) {
								_startLocalPlayer(currentTrackPath.value);
							}
						} else {
							// Otro cliente ya está reproduciendo — revertir el toggle
							listenLocally.value = false;
							showToast('Otro cliente ya está reproduciendo localmente.', 'warning');
						}
						return;
					}

					if (data.type === 'local_player_evicted') {
						// El servidor nos desalojó porque otro cliente tomó el control o se pidió volver a los parlantes
						listenLocally.value = false;
						_stopLocalPlayer();
						const msg =
							data.reason === 'replaced'
								? 'La reproducción local pasó a otro dispositivo.'
								: 'La música volvió a los parlantes del servidor.';
						showToast(msg, 'warning');
						return;
					}

					if (data.type === 'state_update') {
						const state: PlayerState = data;
						const trackChanged =
							state.current_track !== undefined && state.current_track !== currentTrackPath.value;
						if (state.current_track !== undefined) currentTrackPath.value = state.current_track;
						if (trackChanged) {
							const nextPos = state.time_pos ?? 0;
							localTimePos.value = nextPos;
							timePos.value = nextPos;
							pendingSeekTime.value = null;
						}
						if (state.has_local_player !== undefined)
							hasLocalPlayer.value = Boolean(state.has_local_player);
						if (state.has_mpv !== undefined) hasMpv.value = Boolean(state.has_mpv);
						if (state.dj_carpincho_enabled !== undefined) djBaraEnabled.value = state.dj_carpincho_enabled;
						if (state.dj_mode !== undefined) djMode.value = state.dj_mode;
						if (state.dj_next_track !== undefined) djNextTrack.value = state.dj_next_track;
						if (state.dj_safe_mode !== undefined) djSafeModeEnabled.value = state.dj_safe_mode;
						if (state.duration !== undefined) duration.value = state.duration;
						if (state.favorites !== undefined) favorites.value = state.favorites;
						if (state.has_edge_tts !== undefined) hasEdgeTts.value = state.has_edge_tts;
						if (state.has_ffmpeg !== undefined) hasFfmpeg.value = state.has_ffmpeg;
						if (state.history) historyState.value = state.history;
						if (state.scan_status !== undefined) scanStatus.value = state.scan_status;
						if (state.is_scanning !== undefined) isScanning.value = state.is_scanning;
						if (state.is_synthesizing_radio !== undefined)
							isSynthesizingRadio.value = state.is_synthesizing_radio;
						if (state.is_playing_radio_announcement !== undefined)
							isPlayingRadioAnnouncement.value = state.is_playing_radio_announcement;
						if (state.mpv_visible !== undefined) mpvVisible.value = state.mpv_visible;
						if (state.pause_after_path !== undefined) pauseAfterPath.value = state.pause_after_path;
						if (state.paused !== undefined) isPaused.value = state.paused;
						if (state.queue !== undefined) queueState.value = state.queue;
						if (state.radio_mode_enabled !== undefined) radioModeEnabled.value = state.radio_mode_enabled;
						if (state.server_muted !== undefined) serverMuted.value = state.server_muted;
						if (state.server_url !== undefined) serverUrl.value = state.server_url;
						if (state.local_ip !== undefined) localIp.value = state.local_ip;
						if (isHostMode.value && state.folder_status !== undefined) {
							libraryFolderStatus.value = state.folder_status as LibraryFolderStatus;
							if (state.music_dir !== undefined) {
								localMusicDir.value = state.music_dir ? state.music_dir.trim() || null : null;
							}
							if (state.folder_display_name !== undefined) {
								localMusicDisplayName.value = state.folder_display_name;
							}
							if (state.folder_error !== undefined) {
								libraryFolderError.value = state.folder_error;
							}
						}
						if (state.top_played) topPlayedState.value = state.top_played;
						if (state.url_metadata) urlMetadata.value = state.url_metadata;
						if (state.volume !== undefined && !(isNativeAndroidHost() && listenLocally.value)) {
							volume.value = state.volume;
						}
						if (state.weather_location !== undefined) weatherLocation.value = state.weather_location;
						if (state.default_sort !== undefined) {
							defaultSort.value = state.default_sort;
							if (
								!hasUserSelectedSort.value &&
								urlParams.vibra === undefined &&
								activeSort.value !== state.default_sort &&
								!state.library
							) {
								applyLibrarySort(state.default_sort, false);
							}
						}

						if (state.time_pos !== undefined) {
							timePos.value = state.time_pos;
							if (!listenLocally.value) {
								if (pendingSeekTime.value !== null) {
									// Hay un salto (seek) en curso: ignoramos ticks del server hasta que
									// el tiempo emitido se alinee con lo que pedimos.
									const drift = Math.abs(state.time_pos - pendingSeekTime.value);
									if (drift <= 0.5) {
										pendingSeekTime.value = null;
										localTimePos.value = state.time_pos;
									}
								} else if (
									!isDraggingSeek.value &&
									Math.abs(localTimePos.value - timePos.value) > 1.5
								) {
									localTimePos.value = timePos.value;
								}
							}
						}

						if (state.library) {
							originalTracks.value = [...state.library];
							const map: Record<string, Track> = {};
							state.library.forEach((t) => (map[t.path] = t));
							trackMap.value = map;
							if (urlParams.vibra !== undefined) {
								applyLibrarySort('shuffle', true);
							} else {
								const targetSort = hasUserSelectedSort.value
									? activeSort.value
									: defaultSort.value || 'time';
								applyLibrarySort(targetSort, true);
							}
						}
					}
				} catch (e) {
					console.error('¡Se rompió el JSON que mandó el server, fiera!', e);
				}
			},
		});

		const closeThisSocket = () => {
			intentionallyClosed = true;
			close(1000, 'server_switch');
		};
		activeCloseHandle = closeThisSocket;
		setWsSend(send, closeThisSocket);
	}

	return { connectWebSocket, disconnectWebSocket, reconnectWebSocket };
}
