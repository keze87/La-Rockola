import { watch, watchEffect } from 'vue';
import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
import { useMediaControls, useTitle } from '@vueuse/core';
import { usePlaybackControls } from '../usePlaybackControls';
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

const { pause, setMute, skip, prev, seek } = usePlaybackControls();
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

// Set once, inside useLocalPlayback()'s singleton setup below — reactive
// currentTime/duration/ended wired to the <audio> element, replacing the old
// manual onloadedmetadata/ontimeupdate/onended assignment in _startLocalPlayer.
// Play/pause stay imperative (lp.play()/lp.pause()) rather than going through
// mediaControls.playing: that ref only calls play() when its *value* flips,
// so setting it to `true` again while already `true` (the common case when
// advancing to the next track mid-playback) would silently no-op.
let mediaControls: ReturnType<typeof useMediaControls> | undefined;

export function _startLocalPlayer(path: string) {
	const lp = localPlayerRef.value;

	if (!lp) return;

	lp.src = '/stream?path=' + encodeURIComponent(path);
	lp.currentTime = 0;

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

	if (lp && lp.src && mediaControls) {
		const newTime = data.mode === 'absolute' ? data.amount : lp.currentTime + data.amount;
		mediaControls.currentTime.value = Math.max(0, Math.min(newTime, lp.duration || Infinity));
		localTimePos.value = mediaControls.currentTime.value;
		_sendLocalPlayerUpdate({ time_pos: mediaControls.currentTime.value });
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

		mediaControls = useMediaControls(localPlayerRef);
		const { currentTime, duration: elementDuration, ended } = mediaControls;

		// Reportamos la duración ni bien el navegador la tiene
		watch(elementDuration, (d) => {
			if (d > 0) {
				duration.value = d;
				_sendLocalPlayerUpdate({ duration: d });
			}
		});

		// Reportar time_pos mientras avanza (throttleado a ~1s para no inundar el WS)
		let lastSent = 0;
		watch(currentTime, (t) => {
			localTimePos.value = t;
			const now = Date.now();

			if (now - lastSent >= 5000) {
				lastSent = now;
				_sendLocalPlayerUpdate({ time_pos: t });
			}
		});

		// Avisar al servidor cuando termina la canción
		watch(ended, (isEnded) => {
			if (isEnded) _sendLocalPlayerUpdate({ song_ended: true });
		});

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
			navigator.mediaSession.setActionHandler('play', () => pause());
			navigator.mediaSession.setActionHandler('pause', () => pause());
			navigator.mediaSession.setActionHandler('previoustrack', () => prev());
			navigator.mediaSession.setActionHandler('nexttrack', () => skip());

			navigator.mediaSession.setActionHandler('seekbackward', (details) => {
				const amount = -(details.seekOffset ?? 10);
				localTimePos.value = Math.max(0, localTimePos.value + amount);
				ignoreServerTimeUntil.value = Date.now() + 2000;
				seek(amount);
			});

			navigator.mediaSession.setActionHandler('seekforward', (details) => {
				const amount = details.seekOffset ?? 10;
				localTimePos.value = Math.min(duration.value, localTimePos.value + amount);
				ignoreServerTimeUntil.value = Date.now() + 2000;
				seek(amount);
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

				setMute(false);
				_stopLocalPlayer();
			}
		});
	}

	return { _sendLocalPlayerUpdate, setVolume };
}
