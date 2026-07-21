import { useWebSocket } from '@vueuse/core';
import { useCommands } from './useCommands';
import { useToasts } from './useToasts';
import { _startLocalPlayer, applyRemoteSeek } from './useLocalPlayback';
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
	isSocketConnected,
	isScanning,
	listenLocally,
	localTimePos,
	mpvVisible,
	originalTracks,
	pauseAfterPath,
	isPaused,
	queueState,
	serverMuted,
	setWsSend,
	timePos,
	topPlayedState,
	trackMap,
	urlMetadata,
	volume,
} from './state';

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
						if (data.current_track !== undefined) currentTrackPath.value = data.current_track;
						if (data.dj_carpincho_enabled !== undefined)
							djCarpinchoEnabled.value = data.dj_carpincho_enabled;
						if (data.dj_next_track !== undefined) djNextTrack.value = data.dj_next_track;
						if (data.dj_safe_mode !== undefined) djSafeModeEnabled.value = data.dj_safe_mode;
						if (data.duration !== undefined) duration.value = data.duration;
						if (data.favorites !== undefined) favorites.value = data.favorites;
						if (data.history) historyState.value = data.history;
						if (data.is_scanning !== undefined) isScanning.value = data.is_scanning;
						if (data.mpv_visible !== undefined) mpvVisible.value = data.mpv_visible;
						if (data.pause_after_path !== undefined) pauseAfterPath.value = data.pause_after_path;
						if (data.paused !== undefined) isPaused.value = data.paused;
						if (data.queue !== undefined) queueState.value = data.queue;
						if (data.server_muted !== undefined) serverMuted.value = data.server_muted;
						if (data.top_played) topPlayedState.value = data.top_played;
						if (data.url_metadata) urlMetadata.value = data.url_metadata;
						if (data.volume !== undefined) volume.value = data.volume;

						if (data.time_pos !== undefined) {
							timePos.value = data.time_pos;
							if (!listenLocally.value && Date.now() > ignoreServerTimeUntil.value) {
								if (!isDraggingSeek.value && Math.abs(localTimePos.value - timePos.value) > 1.5) {
									localTimePos.value = timePos.value;
								}
							}
						}
						if (data.library) {
							originalTracks.value = [...data.library];
							currentTracks.value = [...data.library];
							const map = {};
							data.library.forEach((t) => (map[t.path] = t));
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
