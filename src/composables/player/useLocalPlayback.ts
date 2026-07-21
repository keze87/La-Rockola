import { watch, watchEffect } from 'vue';
import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
import { useTitle } from '@vueuse/core';
import { useToasts } from './useToasts';
import {
	currentTrackPath,
	duration,
	ignoreServerTimeUntil,
	isDraggingSeek,
	isPaused,
	isPlaying,
	listenLocally,
	localPlayerRef,
	localTimePos,
	pauseAfterPath,
	sendRaw,
	volume,
} from './state';

const { showToast } = useToasts();
const { getTrackInfo } = useLibrary();

// --- Internals shared with useSocket.js ---
// These aren't wrapped in the useLocalPlayback() factory below because
// useSocket needs to call them directly from its onMessage handler
// (for `local_player_claim_result` and `local_player_seek`), without
// having to invoke the composable first.

function _sendLocalPlayerUpdate(payload: Record<string, unknown>) {
	sendRaw({ type: 'local_player_update', ...payload });
}

export function _startLocalPlayer(path: string) {
	const lp = localPlayerRef.value;

	if (!lp) return;

	lp.src = '/stream?path=' + encodeURIComponent(path);
	lp.currentTime = 0;

	// Arrancamos el audio y reportamos la duración cuando el browser la tenga
	lp.onloadedmetadata = () => {
		duration.value = lp.duration;
		_sendLocalPlayerUpdate({ duration: lp.duration });
	};

	// Reportar time_pos mientras avanza (throttleado a ~1s para no inundar el WS)
	let lastSent = 0;
	lp.ontimeupdate = () => {
		localTimePos.value = lp.currentTime;
		const now = Date.now();

		if (now - lastSent >= 5000) {
			lastSent = now;
			_sendLocalPlayerUpdate({ time_pos: lp.currentTime });
		}
	};

	// Avisar al servidor cuando termina la canción
	lp.onended = () => {
		_sendLocalPlayerUpdate({ song_ended: true });
	};

	if (!isPaused.value) {
		lp.play().catch(() => {
			showToast('Tocá la pantalla para arrancar el audio local', 'warning');
		});
	}
}

export function _stopLocalPlayer() {
	const lp = localPlayerRef.value;

	if (!lp) return;

	lp.pause();
	lp.removeAttribute('src');
	lp.load();
}

// Applies a seek that another connected client requested, to our own
// local <audio> element — used by useSocket's `local_player_seek` handler.
export function applyRemoteSeek(data: { mode: string; amount: number }) {
	const lp = localPlayerRef.value;

	if (lp && lp.src) {
		const newTime = data.mode === 'absolute' ? data.amount : lp.currentTime + data.amount;
		lp.currentTime = Math.max(0, Math.min(newTime, lp.duration || Infinity));
		localTimePos.value = lp.currentTime;
		_sendLocalPlayerUpdate({ time_pos: lp.currentTime });
	}
}

let initialized = false;

export function useLocalPlayback() {
	const { sendCmd } = useCommands();

	function setVolume() {
		sendCmd('set_volume', { vollevel: parseInt(volume.value.toString()) });
	}

	// --- Singleton watchers and timers, set up once no matter how many
	// components call useLocalPlayback() (or usePlayer(), which composes it) ---
	if (!initialized) {
		initialized = true;

		const title = useTitle('La Rockola del Carpincho 🦦🧉');

		// Sincronización reactiva del Título y MediaSession (reemplaza updateMediaSession y updateDocumentTitle)
		watchEffect(() => {
			if (currentTrackPath.value) {
				const info = getTrackInfo(currentTrackPath.value);

				// 1. Actualiza el título de la pestaña
				if (isPlaying.value) {
					title.value = `▶ ${info.display_title} 🦦🧉`;
				} else {
					title.value = 'La Rockola del Carpincho 🦦🧉';
				}

				// 2. Actualiza la metadata del dispositivo nativo (API Nativa)
				if ('mediaSession' in navigator) {
					const artworkSrc = !currentTrackPath.value.startsWith('http')
						? `${window.location.origin}/cover?path=${encodeURIComponent(currentTrackPath.value)}`
						: null;

					navigator.mediaSession.metadata = new MediaMetadata({
						title: info.display_title || 'Desconocido',
						artist: info.display_artist || 'Desconocido',
						album: 'La Rockola del Carpincho',
						artwork: artworkSrc ? [{ src: artworkSrc, sizes: '512x512', type: 'image/jpeg' }] : [],
					});
					navigator.mediaSession.playbackState = isPaused.value ? 'paused' : 'playing';
				}
			} else {
				title.value = 'La Rockola del Carpincho 🦦🧉';

				if ('mediaSession' in navigator) navigator.mediaSession.metadata = null;
			}
		});

		// Smooth Local Progression Timer (Fires every 250ms)
		setInterval(() => {
			if (isPlaying.value && !isPaused.value && !isDraggingSeek.value && duration.value > 0) {
				localTimePos.value = Math.min(localTimePos.value + 0.25, duration.value);
			}
		}, 250);

		// Hardware Media Session Action Handlers setup
		if ('mediaSession' in navigator) {
			navigator.mediaSession.setActionHandler('play', () => sendCmd('pause'));
			navigator.mediaSession.setActionHandler('pause', () => sendCmd('pause'));
			navigator.mediaSession.setActionHandler('previoustrack', () => sendCmd('prev'));
			navigator.mediaSession.setActionHandler('nexttrack', () => sendCmd('skip'));

			navigator.mediaSession.setActionHandler('seekbackward', (details) => {
				const amount = -(details.seekOffset ?? 10);
				localTimePos.value = Math.max(0, localTimePos.value + amount);
				ignoreServerTimeUntil.value = Date.now() + 2000;
				sendCmd('seek', { amount });
			});

			navigator.mediaSession.setActionHandler('seekforward', (details) => {
				const amount = details.seekOffset ?? 10;
				localTimePos.value = Math.min(duration.value, localTimePos.value + amount);
				ignoreServerTimeUntil.value = Date.now() + 2000;
				sendCmd('seek', { amount });
			});
		}

		watch(currentTrackPath, (newPath, oldPath) => {
			if (oldPath && oldPath === pauseAfterPath.value) pauseAfterPath.value = null;

			if (listenLocally.value && localPlayerRef.value) {
				if (newPath && !newPath.startsWith('http')) _startLocalPlayer(newPath);
				else _stopLocalPlayer();
			}
		});

		watch(isPaused, (val) => {
			if (listenLocally.value && localPlayerRef.value && localPlayerRef.value.src) {
				if (val) localPlayerRef.value.pause();
				else localPlayerRef.value.play().catch(() => {});

				_sendLocalPlayerUpdate({ paused: val });
			}
		});

		watch(listenLocally, (val) => {
			if (val) {
				sendRaw({ type: 'local_player_claim' });
			} else {
				sendRaw({ type: 'local_player_release' });

				sendCmd('set_mute', { state: false });
				_stopLocalPlayer();
			}
		});
	}

	return { _sendLocalPlayerUpdate, setVolume };
}
