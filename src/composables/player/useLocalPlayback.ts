import { watch, watchEffect } from 'vue';
import { useEventListener, useMediaControls, useTitle } from '@vueuse/core';
import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
import { usePlaybackControls } from '../usePlaybackControls';
import {
	currentTrackPath,
	duration,
	isDraggingSeek,
	isPaused,
	isPlaying,
	listenLocally,
	localPlayerRef,
	localTimePos,
	pauseAfterPath,
	pendingSeekTime,
	sendRaw,
	volume,
} from './state';

// Generates a morse code audio blob that plays "CARPINCHO" faintly in the background. This is used as a placeholder when the user is listening remotely, so that the <audio> element is active and can be controlled by the OS media session, but no actual music is played.
function createFaintNoiseBlob(): Blob {
	const sampleRate = 44100; // CD quality
	const unit = 0.2; // 200 ms per unit
	const amplitude = 10; // Max amplitude for 16-bit PCM
	const message = 'CARPINCHO'; // Morse code message to encode
	const frequency = 440; // A4 tone

	// Morse dictionary
	const morse: Record<string, string> = {
		A: '.-',
		B: '-...',
		C: '-.-.',
		D: '-..',
		E: '.',
		F: '..-.',
		G: '--.',
		H: '....',
		I: '..',
		J: '.---',
		K: '-.-',
		L: '.-..',
		M: '--',
		N: '-.',
		O: '---',
		P: '.--.',
		Q: '--.-',
		R: '.-.',
		S: '...',
		T: '-',
		U: '..-',
		V: '...-',
		W: '.--',
		X: '-..-',
		Y: '-.--',
		Z: '--..',
	};

	// Convert message to Morse
	const sequence = message
		.toUpperCase()
		.split('')
		.map((ch) => morse[ch] || '')
		.join(' ');

	// Build audio samples
	const samples: number[] = [];
	const addTone = (units: number) => {
		for (let i = 0; i < units * unit * sampleRate; i++) {
			const t = i / sampleRate;
			samples.push(Math.sin(2 * Math.PI * frequency * t) * amplitude);
		}
	};
	const addSilence = (units: number) => {
		for (let i = 0; i < units * unit * sampleRate; i++) {
			samples.push(0);
		}
	};

	for (const symbol of sequence) {
		if (symbol === '.') {
			addTone(1);
			addSilence(1);
		} else if (symbol === '-') {
			addTone(3);
			addSilence(1);
		} else if (symbol === ' ') {
			addSilence(3);
		}
	}

	// WAV header
	const buffer = new ArrayBuffer(44 + samples.length * 2);
	const view = new DataView(buffer);
	const writeString = (offset: number, str: string) => {
		for (let i = 0; i < str.length; i++) {
			view.setUint8(offset + i, str.charCodeAt(i));
		}
	};

	// WAV header
	writeString(0, 'RIFF');
	view.setUint32(4, 36 + samples.length * 2, true);
	writeString(8, 'WAVE');
	writeString(12, 'fmt ');
	view.setUint32(16, 16, true); // PCM chunk size
	view.setUint16(20, 1, true); // PCM format
	view.setUint16(22, 1, true); // mono
	view.setUint32(24, sampleRate, true);
	view.setUint32(28, sampleRate * 2, true); // byte rate
	view.setUint16(32, 2, true); // block align
	view.setUint16(34, 16, true); // bits per sample
	writeString(36, 'data');
	view.setUint32(40, samples.length * 2, true);

	// Write samples
	samples.forEach((s, i) => view.setInt16(44 + i * 2, s, true));

	return new Blob([view], { type: 'audio/wav' });
}

let silentBlobUrl = '';

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
			// const { showToast } = useToasts();
			// showToast('Tocá la pantalla para arrancar el audio local', 'warning');
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

		// Instantiate the 100s faint noise blob URL immediately
		silentBlobUrl = URL.createObjectURL(createFaintNoiseBlob());

		mediaControls = useMediaControls(localPlayerRef);
		const { currentTime, duration: elementDuration, ended } = mediaControls;

		// 1. Report duration (ONLY if listening locally so we don't broadcast the blob's 100s duration)
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
				title.value = `${info.display_title} 🦦🧉`;
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
					pendingSeekTime.value = localTimePos.value;
					seek(amount);
				});
				navigator.mediaSession.setActionHandler('seekforward', (details) => {
					const amount = details.seekOffset ?? 10;
					localTimePos.value = Math.min(duration.value, localTimePos.value + amount);
					pendingSeekTime.value = localTimePos.value;
					seek(amount);
				});
				try {
					navigator.mediaSession.setActionHandler('seekto', (details) => {
						if (details.seekTime !== undefined && details.seekTime !== null) {
							localTimePos.value = details.seekTime;
							pendingSeekTime.value = details.seekTime;
							seekAbsolute(details.seekTime);
						}
					});
				} catch {
					// seekto not supported in all browsers
				}
			} else {
				// RELEASE MEDIA CONTROLS TO OS WHEN NO TRACK IS LOADED
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
				// Remote Mode: Play the faint noise loop from RAM
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

			// Ensure we use the Blob URL if remote
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

		useEventListener(document, 'click', unlockAudio, { capture: true });
		useEventListener(document, 'touchend', unlockAudio, { capture: true });
	}

	return { _sendLocalPlayerUpdate, setVolume };
}
