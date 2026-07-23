import { watch, watchEffect } from 'vue';
import { useEventListener, useMediaControls, useTitle } from '@vueuse/core';
import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
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

// A tiny, valid silent file to keep the OS MediaSession alive
let silentBlobUrl = '/silent';

const { pause, setMute, skip, prev, seek, seekAbsolute } = usePlaybackControls();
const { getTrackInfo } = useLibrary();

// --- Internals shared with useSocket ---
export function _sendLocalPlayerUpdate(payload: Record<string, unknown>) {
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
			const { showToast } = useToasts();
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
	const { pause, setMute, skip, prev, seek, seekAbsolute } = usePlaybackControls();
	const { getTrackInfo } = useLibrary();

	function setVolume() {
		sendCmd('set_volume', { vollevel: parseInt(volume.value.toString()) });
	}

	if (!initialized) {
		initialized = true;

		// Fetch the silent audio into RAM to bypass the 206 Partial Content looping bug
		fetch('/silent')
			.then((res) => res.blob())
			.then((blob) => {
				silentBlobUrl = URL.createObjectURL(blob);
				// If already acting as a remote, hot-swap the src to the in-memory blob
				const lp = localPlayerRef.value;
				if (!listenLocally.value && lp && lp.src.includes('/silent')) {
					lp.src = silentBlobUrl;
					if (!isPaused.value) lp.play().catch(() => {});
				}
			})
			.catch((e) => console.error('Pifió cargando el silencio en RAM:', e));

		mediaControls = useMediaControls(localPlayerRef);
		const { currentTime, duration: elementDuration, ended } = mediaControls;

		// 1. Report duration (ONLY if listening locally so we don't broadcast the silent track's duration)
		watch(elementDuration, (d) => {
			if (listenLocally.value && d > 0) {
				duration.value = d;
				_sendLocalPlayerUpdate({ duration: d });
			}
		});

		// 2. Throttle time updates back to server (ONLY if listening locally)
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

		// 3. Notify server when track ends (ONLY if listening locally)
		watch(ended, (isEnded) => {
			if (listenLocally.value && isEnded) _sendLocalPlayerUpdate({ song_ended: true });
		});

		// 4. Handle OS Audio Focus Loss (e.g. another app starts playing or incoming call)
		useEventListener(localPlayerRef, 'pause', () => {
			if (!isPaused.value) {
				// Browser paused HTML5 audio due to lost focus -> sync state with server
				pause();
			}
		});

		// 5. Document Title Management
		const title = useTitle('La Rockola del Carpincho 🪗');

		watchEffect(() => {
			if (currentTrackPath.value && isPlaying.value) {
				const info = getTrackInfo(currentTrackPath.value);
				title.value = `▶ ${info.display_title} 🦦🧉`;
			} else {
				title.value = 'La Rockola del Carpincho 🦦🧉';
			}
		});

		// 6. MediaSession Metadata & Active Playback State (ALWAYS ACTIVE)
		watchEffect(() => {
			if (!('mediaSession' in navigator)) return;

			if (currentTrackPath.value) {
				const info = getTrackInfo(currentTrackPath.value);
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
			} else {
				navigator.mediaSession.metadata = null;
				navigator.mediaSession.playbackState = 'none';
			}
		});

		// 7. MediaSession Position State (Lockscreen Seekbar Sync) (ALWAYS ACTIVE)
		watch([localTimePos, duration, isPaused], () => {
			if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;

			if (duration.value > 0 && currentTrackPath.value) {
				try {
					navigator.mediaSession.setPositionState({
						duration: duration.value,
						playbackRate: 1.0,
						position: Math.min(Math.max(0, localTimePos.value), duration.value),
					});
				} catch {
					// Ignore transient state errors during track switching
				}
			}
		});

		// 8. MediaSession Action Handlers (Setup & Clean Teardown) (ALWAYS ACTIVE)
		watchEffect(() => {
			if (!('mediaSession' in navigator)) return;

			if (currentTrackPath.value) {
				// EXPLICIT ACTION HANDLERS: Do not toggle blindly!
				navigator.mediaSession.setActionHandler('play', () => {
					if (isPaused.value) pause();
				});
				navigator.mediaSession.setActionHandler('pause', () => {
					if (!isPaused.value) pause();
				});
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
				try {
					navigator.mediaSession.setActionHandler('seekto', (details) => {
						if (details.seekTime !== undefined && details.seekTime !== null) {
							localTimePos.value = details.seekTime;
							ignoreServerTimeUntil.value = Date.now() + 2000;
							seekAbsolute(details.seekTime);
						}
					});
				} catch {
					// seekto not supported in all browsers
				}
			} else {
				// RELEASE MEDIA CONTROLS TO OS WHEN LOCAL PLAYBACK IS OFF / STOPPED
				navigator.mediaSession.setActionHandler('play', null);
				navigator.mediaSession.setActionHandler('pause', null);
				navigator.mediaSession.setActionHandler('previoustrack', null);
				navigator.mediaSession.setActionHandler('nexttrack', null);
				navigator.mediaSession.setActionHandler('seekbackward', null);
				navigator.mediaSession.setActionHandler('seekforward', null);
				try {
					navigator.mediaSession.setActionHandler('seekto', null);
				} catch {
					// seekto not supported in all browsers
				}
			}
		});

		// 9. Smooth Local Time Progression Timer
		setInterval(() => {
			if (isPlaying.value && !isPaused.value && !isDraggingSeek.value && duration.value > 0) {
				localTimePos.value = Math.min(localTimePos.value + 0.25, duration.value);
			}
		}, 250);

		// 10. Playback & Track Change Reactive Watchers
		watch(currentTrackPath, (newPath, oldPath) => {
			if (oldPath && oldPath === pauseAfterPath.value) pauseAfterPath.value = null;

			const lp = localPlayerRef.value;
			if (!lp) return;

			if (listenLocally.value) {
				lp.loop = false;
				if (newPath && !newPath.startsWith('http')) _startLocalPlayer(newPath);
				else _stopLocalPlayer();
			} else {
				// Remote Mode: Play silent audio loop from RAM
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

			if (val) {
				sendRaw({ type: 'local_player_claim' });
				lp.loop = false;
				if (currentTrackPath.value && !currentTrackPath.value.startsWith('http')) {
					_startLocalPlayer(currentTrackPath.value);
				}
			} else {
				sendRaw({ type: 'local_player_release' });
				setMute(false);
				if (currentTrackPath.value) {
					lp.src = silentBlobUrl;
					lp.loop = true;
					if (!isPaused.value) lp.play().catch(() => {});
				} else {
					_stopLocalPlayer();
				}
			}
		});

		// 11. Audio Autoplay Unlocker (The Synchronous Resumer)
		let audioUnlocked = false;
		const unlockAudio = () => {
			if (listenLocally.value) return;

			const lp = localPlayerRef.value;
			if (!lp) return;

			// CRUCIAL: Mobile browsers require playsinline to maintain background audio context
			lp.setAttribute('playsinline', '');
			lp.setAttribute('webkit-playsinline', '');

			// Ensure we use the Blob URL
			if (!lp.src || (!lp.src.startsWith('blob:') && silentBlobUrl.startsWith('blob:'))) {
				lp.src = silentBlobUrl;
				lp.loop = true;
			}

			// If the server says we should be playing, enforce it synchronously on tap
			if (!isPaused.value && currentTrackPath.value) {
				if (lp.paused) {
					lp.play().catch(() => {});
				}
				audioUnlocked = true;
			}
			// If it's the very first tap and we are paused, "bless" the audio tag
			else if (!audioUnlocked) {
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

		useEventListener(document, 'pointerdown', unlockAudio, { capture: true });
		useEventListener(document, 'touchend', unlockAudio, { capture: true });
	}

	return { _sendLocalPlayerUpdate, setVolume };
}
