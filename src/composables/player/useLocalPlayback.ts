import { ref, watch, watchEffect } from 'vue';
import { useEventListener, useMediaControls, useTitle } from '@vueuse/core';
import { apiUrl } from '../useApi';
import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
import { usePlaybackControls } from '../usePlaybackControls';
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

// Genera un blob de audio en código morse que suena "CARPINCHO" muy bajito de fondo. Se usa como marcador de posición cuando el usuario escucha de forma remota, para que el elemento <audio> quede activo y pueda ser controlado por la Media Session del sistema operativo sin reproducir la música real acá.
function createFaintNoiseBlob(): Blob {
	const sampleRate = 44100; // Calidad de CD
	const unit = 0.2; // 200 ms por unidad
	const amplitude = 10; // Amplitud máxima para PCM de 16 bits
	const message = 'CARPINCHO'; // Mensaje en código morse a codificar
	const frequency = 440; // Tono La 4 (440Hz)

	// Diccionario morse
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

	// Pasamos el mensaje a morse
	const sequence = message
		.toUpperCase()
		.split('')
		.map((ch) => morse[ch] || '')
		.join(' ');

	// Construimos las muestras de audio
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

	// Cabecera WAV
	const buffer = new ArrayBuffer(44 + samples.length * 2);
	const view = new DataView(buffer);
	const writeString = (offset: number, str: string) => {
		for (let i = 0; i < str.length; i++) {
			view.setUint8(offset + i, str.charCodeAt(i));
		}
	};

	// Cabecera WAV
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

	// Escribimos las muestras
	samples.forEach((s, i) => view.setInt16(44 + i * 2, s, true));

	return new Blob([view], { type: 'audio/wav' });
}

let silentBlobUrl = '';

// --- Métodos internos compartidos con useSocket ---
export function _sendLocalPlayerUpdate(payload: Record<string, unknown>) {
	sendRaw({ type: 'local_player_update', ...payload });
}

// Se define una sola vez en la inicialización singleton de useLocalPlayback():
// vincula currentTime/duration/ended de forma reactiva al elemento <audio>,
// reemplazando las asignaciones manuales en _startLocalPlayer. Play/pause se
// mantienen imperativos (lp.play()/lp.pause()) porque la ref de vueuse solo llama
// a play() si su valor cambia, fallando silenciosamente si ya estaba en `true`.
let mediaControls: ReturnType<typeof useMediaControls> | undefined;

export const isChangingTrack = ref<boolean>(false);
let changeTrackTimer: ReturnType<typeof setTimeout> | null = null;

export function markTrackChanging() {
	isChangingTrack.value = true;
	if (changeTrackTimer) clearTimeout(changeTrackTimer);
	changeTrackTimer = setTimeout(() => {
		isChangingTrack.value = false;
	}, 2000);
}

export function clearTrackChanging() {
	isChangingTrack.value = false;
	if (changeTrackTimer) {
		clearTimeout(changeTrackTimer);
		changeTrackTimer = null;
	}
}

export function getBufferedAhead(lp: HTMLAudioElement): number {
	const current = lp.currentTime || 0;
	for (let i = 0; i < lp.buffered.length; i++) {
		if (lp.buffered.start(i) <= current && current <= lp.buffered.end(i)) {
			return lp.buffered.end(i) - current;
		}
	}
	return 0;
}

let bufferWaitCleanup: (() => void) | null = null;

export function playWhenBuffered(lp: HTMLAudioElement, minBufferSeconds = 6, maxWaitMs = 2500) {
	if (bufferWaitCleanup) {
		bufferWaitCleanup();
		bufferWaitCleanup = null;
	}

	if (isPaused.value) return;

	let started = false;

	const doPlay = () => {
		if (started || isPaused.value) return;
		started = true;
		if (bufferWaitCleanup) {
			bufferWaitCleanup();
			bufferWaitCleanup = null;
		}
		lp.play().catch(() => {});
	};

	const checkBuffer = () => {
		if (started || isPaused.value) return;
		const dur = lp.duration || 0;
		const ahead = getBufferedAhead(lp);
		const target = dur > 0 ? Math.min(minBufferSeconds, dur) : minBufferSeconds;

		if (ahead >= target) {
			doPlay();
		}
	};

	const onCanPlayThrough = () => {
		doPlay();
	};

	const onProgress = () => {
		checkBuffer();
	};

	const onLoadedMetadata = () => {
		checkBuffer();
	};

	// Timeout de seguridad: nunca congelarse indefinidamente si la conexión es lenta
	const timeout = setTimeout(() => {
		doPlay();
	}, maxWaitMs);

	bufferWaitCleanup = () => {
		clearTimeout(timeout);
		lp.removeEventListener('progress', onProgress);
		lp.removeEventListener('canplaythrough', onCanPlayThrough);
		lp.removeEventListener('loadedmetadata', onLoadedMetadata);
	};

	lp.addEventListener('progress', onProgress);
	lp.addEventListener('canplaythrough', onCanPlayThrough);
	lp.addEventListener('loadedmetadata', onLoadedMetadata);

	// Verificamos al toque si ya está en buffer desde la caché
	checkBuffer();
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

	if (bufferWaitCleanup) {
		bufferWaitCleanup();
		bufferWaitCleanup = null;
	}

	markTrackChanging();
	lp.pause();
	lp.removeAttribute('src');
	lp.load();
}

// Aplica un seek solicitado por otro cliente conectado sobre nuestro propio
// elemento <audio> local; utilizado por el manejador `local_player_seek` de useSocket.
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

		// Instanciamos de inmediato la URL del blob con el audio bajito de 100s
		silentBlobUrl = URL.createObjectURL(createFaintNoiseBlob());

		mediaControls = useMediaControls(localPlayerRef);
		const { currentTime, duration: elementDuration, ended } = mediaControls;

		// Sincronizamos volumen y muteo con el elemento <audio> local
		watch(
			[localPlayerRef, volume, serverMuted],
			([lp, newVol, newMuted]) => {
				if (!lp) return;
				lp.volume = Number.isFinite(newVol) ? Math.max(0, Math.min(1, newVol / 100)) : 1;
				lp.muted = Boolean(newMuted);
			},
			{ immediate: true }
		);

		// 1. Notificar duración (SOLO si escuchamos localmente, para no transmitir los 100s del blob)
		watch(elementDuration, (d) => {
			if (listenLocally.value && d > 0) {
				duration.value = d;
				_sendLocalPlayerUpdate({ duration: d });
			}
		});

		// 2. Controlar la frecuencia (throttle) de actualización de tiempo al servidor (SOLO si escuchamos localmente)
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

		// 3. Avisar al servidor cuando termina la canción (SOLO si escuchamos localmente)
		watch(ended, (isEnded) => {
			if (listenLocally.value && isEnded && !isChangingTrack.value) {
				_sendLocalPlayerUpdate({ song_ended: true });
			}
		});

		// Limpiar flag de transición cuando el audio arranca o da error
		useEventListener(localPlayerRef, 'playing', () => {
			clearTrackChanging();
		});
		useEventListener(localPlayerRef, 'error', () => {
			clearTrackChanging();
		});

		// 4. Manejar pérdida de foco de audio del SO (ej. llamada entrante u otra app)
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
				// El navegador pausó el audio por pérdida de foco -> sincronizamos estado con el server
				_sendLocalPlayerUpdate({ paused: true });
			}
		});

		// 5. Gestión del título del documento
		const title = useTitle('La Rockola del Carpincho 🪗');

		watchEffect(() => {
			if (currentTrackPath.value && isPlaying.value) {
				const info = getTrackInfo(currentTrackPath.value);
				title.value = `${info.display_title} 🦦🧉`;
			} else {
				title.value = 'La Rockola del Carpincho 🦦🧉';
			}
		});

		// 6. Metadatos de MediaSession y estado de reproducción activo (SIEMPRE ACTIVO)
		watchEffect(() => {
			if (!('mediaSession' in navigator)) return;

			if (currentTrackPath.value) {
				const info = getTrackInfo(currentTrackPath.value);
				const artworkSrc = !currentTrackPath.value.startsWith('http')
					? `${window.location.origin}${apiUrl(`/cover?path=${encodeURIComponent(currentTrackPath.value)}&size=512`)}`
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

		// 7. Posición en MediaSession (Sincronización con barra de pantalla de bloqueo) (SIEMPRE ACTIVO)
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
					// Ignoramos errores transitorios al cambiar de tema
				}
			}
		});

		// 8. Manejadores de acciones de MediaSession (Configuración y limpieza) (SIEMPRE ACTIVO)
		watchEffect(() => {
			if (!('mediaSession' in navigator)) return;

			if (currentTrackPath.value) {
				// MANEJADORES EXPLÍCITOS: ¡No alternar a ciegas!
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
					// seekto no está soportado en todos los navegadores
				}
			} else {
				// LIBERAR CONTROLES MULTIMEDIA AL SO CUANDO NO HAY TEMA CARGADO
				navigator.mediaSession.setActionHandler('play', null);
				navigator.mediaSession.setActionHandler('pause', null);
				navigator.mediaSession.setActionHandler('previoustrack', null);
				navigator.mediaSession.setActionHandler('nexttrack', null);
				navigator.mediaSession.setActionHandler('seekbackward', null);
				navigator.mediaSession.setActionHandler('seekforward', null);
				try {
					navigator.mediaSession.setActionHandler('seekto', null);
				} catch {
					// seekto no está soportado en todos los navegadores
				}
			}
		});

		// 9. Temporizador para progresión suave del tiempo local
		setInterval(() => {
			if (isPlaying.value && !isPaused.value && !isDraggingSeek.value && duration.value > 0) {
				localTimePos.value = Math.min(localTimePos.value + 0.25, duration.value);
			}
		}, 250);

		// 10. Watchers reactivos para cambio de tema y reproducción
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
				// Modo Remoto: Reproducir el loop de audio bajito desde memoria RAM
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

		// 11. Desbloqueador de reproducción automática (activación sincrónica)
		let audioUnlocked = false;
		const unlockAudio = () => {
			if (listenLocally.value) return;

			const lp = localPlayerRef.value;
			if (!lp) return;

			// FUNDAMENTAL: Los navegadores móviles requieren playsinline para mantener el audio en segundo plano
			lp.setAttribute('playsinline', '');
			lp.setAttribute('webkit-playsinline', '');

			// Nos aseguramos de usar la URL del Blob si estamos en modo remoto
			if (!lp.src || (!lp.src.startsWith('blob:') && silentBlobUrl.startsWith('blob:'))) {
				markTrackChanging();
				lp.src = silentBlobUrl;
				lp.loop = true;
			}

			// Si el server dice que debe sonar, lo forzamos de forma sincrónica con el toque
			if (!isPaused.value && currentTrackPath.value) {
				if (lp.paused) {
					lp.play().catch(() => {});
				}
				audioUnlocked = true;
			}
			// Si es el primer toque y estamos en pausa, "bendecimos" la etiqueta de audio para habilitarla
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

		// 12. Precaché inteligente del próximo tema en la caché del navegador
		function prefetchNextTrack(path: string | null | undefined) {
			if (!path || path.startsWith('http')) return;
			const url = apiUrl('/stream?path=' + encodeURIComponent(path));
			// Precarga los primeros 4MB del tema que se viene para que esté listo en caché
			fetch(url, { headers: { Range: 'bytes=0-4194303' } }).catch(() => {});
		}

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

		// 13. Re-búfer anti-cortes (si hay bajón de red en medio del tema)
		useEventListener(localPlayerRef, 'waiting', () => {
			const lp = localPlayerRef.value;
			if (listenLocally.value && !isPaused.value && !isChangingTrack.value && lp && !lp.ended) {
				playWhenBuffered(lp, 4, 3000);
			}
		});
	}

	return { _sendLocalPlayerUpdate, setVolume };
}
