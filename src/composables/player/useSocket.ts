import { _startLocalPlayer, applyRemoteSeek } from './useLocalPlayback';
import { useCommands } from './useCommands';
import { useToasts } from './useToasts';
import { useWebSocket } from '@vueuse/core';
import {
	currentTrackPath,
	currentTracks,
	djCarpinchoEnabled,
	djNextTrack,
	djSafeModeEnabled,
	duration,
	favorites,
	historyState,
	ignoreServerTimeUntil,
	isDraggingSeek,
	isPaused,
	isScanning,
	isSocketConnected,
	listenLocally,
	localTimePos,
	mpvVisible,
	originalTracks,
	pauseAfterPath,
	queueState,
	serverMuted,
	setWsSend,
	timePos,
	topPlayedState,
	trackMap,
	urlMetadata,
	volume,
} from './state';
import type { PlayerState, Track } from '../../types';

export function useSocket() {
	const { sendCmd } = useCommands();
	const { showToast } = useToasts();

	function connectWebSocket() {
		// Evitamos abrir múltiples conexiones si ya está instanciado
		if (isSocketConnected()) return;

		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const wsUrl = `${protocol}//${window.location.host}/ws`;

		// VueUse se encarga del auto-reconnect, backoff exponencial y limpieza
		const { send } = useWebSocket(wsUrl, {
			autoReconnect: {
				retries: () => true, // Infinitos reintentos
				delay: (retryCount) => Math.min(1000 * Math.pow(2, retryCount), 30000), // Backoff exponencial hasta 30s
			},

			onConnected() {
				if (listenLocally.value) {
					send(JSON.stringify({ type: 'local_player_claim' }));
				}
			},

			onDisconnected() {
				showToast('Se cortó la señal. Reconectando...', 'warning');
			},

			onMessage(ws, event) {
				try {
					const data = JSON.parse(event.data);

					// Local player logic events
					if (data.type === 'local_player_seek') {
						// Otro cliente mandó un seek — lo aplicamos al <audio> local
						applyRemoteSeek(data);
						return;
					}

					if (data.type === 'local_player_claim_result') {
						if (data.ok) {
							// El servidor aceptó nuestro rol — mutear MPV y arrancar el reproductor local
							sendCmd('set_mute', { state: true });

							if (currentTrackPath.value && !currentTrackPath.value.startsWith('http')) {
								_startLocalPlayer(currentTrackPath.value);
							}
						} else {
							// Otro cliente ya está reproduciendo — revertir el toggle
							listenLocally.value = false;
							showToast('Otro cliente ya está reproduciendo localmente.', 'warning');
						}
						return;
					}

					if (data.type === 'state_update') {
						const state: PlayerState = data;
						if (state.current_track !== undefined) currentTrackPath.value = state.current_track;
						if (state.dj_carpincho_enabled !== undefined)
							djCarpinchoEnabled.value = state.dj_carpincho_enabled;
						if (state.dj_next_track !== undefined) djNextTrack.value = state.dj_next_track;
						if (state.dj_safe_mode !== undefined) djSafeModeEnabled.value = state.dj_safe_mode;
						if (state.duration !== undefined) duration.value = state.duration;
						if (state.favorites !== undefined) favorites.value = state.favorites;
						if (state.history) historyState.value = state.history;
						if (state.is_scanning !== undefined) isScanning.value = state.is_scanning;
						if (state.mpv_visible !== undefined) mpvVisible.value = state.mpv_visible;
						if (state.pause_after_path !== undefined) pauseAfterPath.value = state.pause_after_path;
						if (state.paused !== undefined) isPaused.value = state.paused;
						if (state.queue !== undefined) queueState.value = state.queue;
						if (state.server_muted !== undefined) serverMuted.value = state.server_muted;
						if (state.top_played) topPlayedState.value = state.top_played;
						if (state.url_metadata) urlMetadata.value = state.url_metadata;
						if (state.volume !== undefined) volume.value = state.volume;

						if (state.time_pos !== undefined) {
							timePos.value = state.time_pos;
							if (!listenLocally.value && Date.now() > ignoreServerTimeUntil.value) {
								if (!isDraggingSeek.value && Math.abs(localTimePos.value - timePos.value) > 1.5) {
									localTimePos.value = timePos.value;
								}
							}
						}

						if (state.library) {
							originalTracks.value = [...state.library];
							currentTracks.value = [...state.library];
							const map: Record<string, Track> = {};
							state.library.forEach((t) => (map[t.path] = t));
							trackMap.value = map;
						}
					}
				} catch (e) {
					console.error('¡Se rompió el JSON que mandó el server, fiera!', e);
				}
			},
		});

		setWsSend(send);
	}

	return { connectWebSocket };
}
