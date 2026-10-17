// Coordinador de reproducción local y sincronización con el servidor.
// Delega la síntesis de keepalive Morse a src/audio/morseKeepalive.ts,
// la integración con MediaSession a src/audio/mediaSession.ts y
// el manejo de búfer HTML5 a src/audio/localAudioEngine.ts.

import { watch, watchEffect } from 'vue';
import { useEventListener, useMediaControls, useTitle } from '@vueuse/core';
import { apiUrl } from '../useApi';
import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
import { usePlaybackControls } from '../usePlaybackControls';
import {
	cleanupBufferWait,
	clearTrackChanging,
	getBufferedAhead,
	isChangingTrack,
	markTrackChanging,
	playWhenBuffered as enginePlayWhenBuffered,
	prefetchNextTrack,
} from '../../audio/localAudioEngine';
import { bindMediaSessionHandlers, syncMediaSessionMetadata, syncMediaSessionPosition } from '../../audio/mediaSession';
import { getSilentBlobUrl } from '../../audio/morseKeepalive';
import {
	currentTrackPath,
	djCarpinchoEnabled,
	djNextTrack,
	duration,
	isDraggingSeek,
	isPaused,
	isPlaying,
	listenLocally,
	localPlayerRef,
	localTimePos,
	pauseAfterPath,
	pendingSeekTime,
	queueState,
	sendRaw,
	serverMuted,
	volume,
} from './state';

export { clearTrackChanging, getBufferedAhead, isChangingTrack, markTrackChanging };

let silentBlobUrl = '';
let mediaControls: ReturnType<typeof useMediaControls> | undefined;

export function _sendLocalPlayerUpdate(payload: Record<string, unknown>) {
	sendRaw({ type: 'local_player_update', ...payload });
}

export function playWhenBuffered(lp: HTMLAudioElement, minBufferSeconds = 6, maxWaitMs = 2500) {
	enginePlayWhenBuffered(lp, minBufferSeconds, maxWaitMs, () => isPaused.value);
}

export function _startLocalPlayer(path: string) {
	const lp = localPlayerRef.value;
	if (!lp) return;

	markTrackChanging();
	lp.preload = 'auto';
	lp.src = apiUrl('/stream?path=' + encodeURIComponent(path));
	lp.currentTime = 0;
	lp.volume = Number.isFinite(volume.value) ? Math.max(0, Math.min(1, volume.value / 100)) : 1;
	lp.muted = Boolean(serverMuted.value);
	lp.load();

	if (!isPaused.value) {
		playWhenBuffered(lp, 6, 2500);
	}
}

export function _stopLocalPlayer() {
	const lp = localPlayerRef.value;
	if (!lp) return;

	cleanupBufferWait();
	markTrackChanging();
	lp.pause();
	lp.removeAttribute('src');
	lp.load();
}

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
	const { pause, skip, prev, seek, seekAbsolute } = usePlaybackControls();
	const { getTrackInfo } = useLibrary();

	function setVolume(vollevel?: number) {
		const targetVol = vollevel !== undefined ? vollevel : parseInt(volume.value.toString());
		sendCmd('set_volume', { vollevel: targetVol });
	}

	if (!initialized) {
		initialized = true;
		silentBlobUrl = getSilentBlobUrl();

		mediaControls = useMediaControls(localPlayerRef);
		const { currentTime, duration: elementDuration, ended } = mediaControls;

		watch(
			[localPlayerRef, volume, serverMuted],
			([lp, newVol, newMuted]) => {
				if (!lp) return;
				lp.volume = Number.isFinite(newVol) ? Math.max(0, Math.min(1, newVol / 100)) : 1;
				lp.muted = Boolean(newMuted);
			},
			{ immediate: true }
		);

		watch(elementDuration, (d) => {
			if (listenLocally.value && d > 0) {
				duration.value = d;
				_sendLocalPlayerUpdate({ duration: d });
			}
		});

		let lastSent = 0;
		watch(currentTime, (t) => {
			if (listenLocally.value) {
				localTimePos.value = t;
				const now = Date.now();
				if (now - lastSent >= 5000) {
					lastSent = now;
					_sendLocalPlayerUpdate({ time_pos: t });
				}
			}
		});

		watch(ended, (isEnded) => {
			if (listenLocally.value && isEnded && !isChangingTrack.value) {
				_sendLocalPlayerUpdate({ song_ended: true });
			}
		});

		useEventListener(localPlayerRef, 'playing', () => clearTrackChanging());
		useEventListener(localPlayerRef, 'error', () => clearTrackChanging());

		useEventListener(localPlayerRef, 'pause', () => {
			const lp = localPlayerRef.value;
			if (
				listenLocally.value &&
				!isChangingTrack.value &&
				!isPaused.value &&
				lp &&
				!lp.ended &&
				(lp.duration ? lp.currentTime < lp.duration - 0.5 : true)
			) {
				_sendLocalPlayerUpdate({ paused: true });
			}
		});

		const title = useTitle('La Rockola del Carpincho 🪗');
		watchEffect(() => {
			if (currentTrackPath.value && isPlaying.value) {
				const info = getTrackInfo(currentTrackPath.value);
				title.value = `${info.display_title} 🦦🧉`;
			} else {
				title.value = 'La Rockola del Carpincho 🦦🧉';
			}
		});

		watchEffect(() => {
			syncMediaSessionMetadata(currentTrackPath.value, isPaused.value, getTrackInfo);
		});

		watch([localTimePos, duration, isPaused], () => {
			syncMediaSessionPosition(currentTrackPath.value, duration.value, localTimePos.value);
		});

		watchEffect(() => {
			bindMediaSessionHandlers(
				currentTrackPath.value,
				() => isPaused.value,
				{
					pause,
					prev,
					skip,
					seek,
					seekAbsolute,
					onOptimisticSeek: (nextPos) => {
						localTimePos.value = nextPos;
						pendingSeekTime.value = nextPos;
					},
				},
				() => localTimePos.value,
				() => duration.value
			);
		});

		setInterval(() => {
			if (isPlaying.value && !isPaused.value && !isDraggingSeek.value && duration.value > 0) {
				localTimePos.value = Math.min(localTimePos.value + 0.25, duration.value);
			}
		}, 250);

		watch(currentTrackPath, (newPath, oldPath) => {
			if (oldPath && oldPath === pauseAfterPath.value) pauseAfterPath.value = null;

			const lp = localPlayerRef.value;
			if (!lp) return;

			markTrackChanging();
			if (listenLocally.value) {
				lp.loop = false;
				if (newPath && !newPath.startsWith('http')) _startLocalPlayer(newPath);
				else _stopLocalPlayer();
			} else {
				if (newPath) {
					if (!lp.src.startsWith('blob:')) lp.src = silentBlobUrl;
					lp.loop = true;
					if (!isPaused.value) lp.play().catch(() => {});
				} else {
					_stopLocalPlayer();
				}
			}
		});

		watch(isPaused, (val) => {
			const lp = localPlayerRef.value;
			if (lp && lp.src) {
				if (val) lp.pause();
				else lp.play().catch(() => {});

				if (listenLocally.value) _sendLocalPlayerUpdate({ paused: val });
			}
		});

		watch(listenLocally, (val) => {
			const lp = localPlayerRef.value;
			if (!lp) return;

			markTrackChanging();
			if (val) {
				sendRaw({ type: 'local_player_claim' });
				lp.loop = false;
				if (currentTrackPath.value && !currentTrackPath.value.startsWith('http')) {
					_startLocalPlayer(currentTrackPath.value);
				}
			} else {
				sendRaw({ type: 'local_player_release' });
				if (currentTrackPath.value) {
					lp.src = silentBlobUrl;
					lp.loop = true;
					if (!isPaused.value) lp.play().catch(() => {});
				} else {
					_stopLocalPlayer();
				}
			}
		});

		let audioUnlocked = false;
		const unlockAudio = () => {
			if (listenLocally.value) return;

			const lp = localPlayerRef.value;
			if (!lp) return;

			lp.setAttribute('playsinline', '');
			lp.setAttribute('webkit-playsinline', '');

			if (!lp.src || (!lp.src.startsWith('blob:') && silentBlobUrl.startsWith('blob:'))) {
				markTrackChanging();
				lp.src = silentBlobUrl;
				lp.loop = true;
			}

			if (!isPaused.value && currentTrackPath.value) {
				if (lp.paused) {
					lp.play().catch(() => {});
				}
				audioUnlocked = true;
			} else if (!audioUnlocked) {
				const playPromise = lp.play();
				if (playPromise !== undefined) {
					playPromise
						.then(() => {
							audioUnlocked = true;
							lp.pause();
						})
						.catch(() => {});
				}
			}
		};

		useEventListener(document, 'click', unlockAudio, { capture: true });
		useEventListener(document, 'touchend', unlockAudio, { capture: true });

		watch(
			[queueState, djNextTrack, listenLocally, currentTrackPath],
			() => {
				if (!listenLocally.value) return;

				let nextPath: string | null = null;
				if (queueState.value.length > 0) {
					nextPath = queueState.value[0];
				} else if (djCarpinchoEnabled.value && djNextTrack.value) {
					nextPath = djNextTrack.value.path;
				}

				if (nextPath && nextPath !== currentTrackPath.value) {
					prefetchNextTrack(nextPath);
				}
			},
			{ deep: true }
		);

		useEventListener(localPlayerRef, 'waiting', () => {
			const lp = localPlayerRef.value;
			if (listenLocally.value && !isPaused.value && !isChangingTrack.value && lp && !lp.ended) {
				playWhenBuffered(lp, 4, 3000);
			}
		});
	}

	return { _sendLocalPlayerUpdate, setVolume, returnToServerSpeakers };
}

export function returnToServerSpeakers() {
	sendRaw({ type: 'local_player_reset' });
}
