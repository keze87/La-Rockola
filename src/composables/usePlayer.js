import { ref, computed, watch, watchEffect } from 'vue';
import { useVibrate, useTitle, useWebSocket } from '@vueuse/core';

const { vibrate } = useVibrate();

// Global state created outside the function so it is shared across all components
let wsSend = null; // Reference to the VueUse websocket send function
const activeTab = ref('library');
const currentTrackPath = ref(null);
const historyState = ref([]);
const isFogonMode = ref(false);
const isPaused = ref(false);
const isScanning = ref(false);
const librarySearchQuery = ref('');
const queueState = ref([]);
const topPlayedState = ref([]);

// Library
const currentTracks = ref([]);
const favorites = ref([]);
const originalTracks = ref([]);
const trackMap = ref({});
const urlMetadata = ref({});

// Auto-DJ Logic
const djCarpinchoEnabled = ref(false);
const djNextTrack = ref(null);
const djSafeModeEnabled = ref(false);

// Pause-after
const pauseAfterPath = ref(null);

// Local Audio Playback & Media Session
const duration = ref(0);
const ignoreServerTimeUntil = ref(0);
const isDraggingSeek = ref(false);
const listenLocally = ref(false);
const localPlayerRef = ref(null); // This will be bound to the <audio> element in App.vue
const localTimePos = ref(0);
const serverMuted = ref(false);
const timePos = ref(0);
const volume = ref(100);

// MPV window visibility
const mpvVisible = ref(true);

// Fogon Mode
const showFogonVolume = ref(false);

// Toasts
const toasts = ref([]);
let toastIdCounter = 0;

const isPlaying = computed(() => !!currentTrackPath.value && !isPaused.value);
const volIcon = computed(() => {
	if (serverMuted.value || volume.value == 0) return 'volume_off';
	if (volume.value <= 40) return 'volume_down';
	if (volume.value <= 100) return 'volume_up';
	return 'surround_sound';
});

export function usePlayer() {
	function normalizeString(s) {
		return s
			? s
					.normalize('NFD')
					.replace(/[\u0300-\u036f]/g, '')
					.toLowerCase()
			: '';
	}

	function connectWebSocket() {
		// Evitamos abrir múltiples conexiones si ya está instanciado
		if (wsSend) return;

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
						const lp = localPlayerRef.value;

						if (lp && lp.src) {
							const newTime = data.mode === 'absolute' ? data.amount : lp.currentTime + data.amount;
							lp.currentTime = Math.max(0, Math.min(newTime, lp.duration || Infinity));
							localTimePos.value = lp.currentTime;
							_sendLocalPlayerUpdate({ time_pos: lp.currentTime });
						}

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

		wsSend = send;
	}

	async function sendCmd(cmd, data = {}) {
		try {
			const res = await fetch('/command', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ cmd, ...data }),
			});

			return await res.json();
		} catch (err) {
			console.error(err);
			showToast('Error mandando comando fiera.', 'error');
		}
	}

	function getTrackInfo(path) {
		if (!path) return { display_title: 'Desconocido', display_artist: 'Vaya uno a saber' };

		if (trackMap.value[path]) return trackMap.value[path];

		if (urlMetadata.value[path]) return urlMetadata.value[path];

		const isUrl = path.startsWith('http');
		return {
			display_title: isUrl ? path : 'Audio Misterioso',
			display_artist: isUrl ? '🌐 De la Internet' : 'Vaya uno a saber',
		};
	}

	function queueIndex(path) {
		return queueState.value.indexOf(path);
	}

	async function loadLibrary(forceScan = false) {
		const endpoint = forceScan ? '/scan' : '/library';

		if (forceScan) isScanning.value = true;

		try {
			const res = await fetch(endpoint);
			const data = await res.json();
			if (data && data.data) {
				originalTracks.value = [...data.data];
				const map = {};
				data.data.forEach((t) => (map[t.path] = t));
				trackMap.value = map;

				const urlParams = new URLSearchParams(window.location.search);

				if (urlParams.has('vibra')) {
					sortLibrary('shuffle', true);
				} else {
					currentTracks.value = [...data.data];
				}
			}
		} catch (err) {
			console.error(err);
			showToast('Uy! Se volcó el mate conectando con la API', 'error');
		} finally {
			if (forceScan) isScanning.value = false;
		}
	}

	function sortLibrary(type, keepSeed = false) {
		if (type === 'time') {
			const url = new URL(window.location);
			url.searchParams.delete('vibra');
			window.history.pushState({}, '', url);
			currentTracks.value = [...originalTracks.value];
		} else if (type === 'artist') {
			const url = new URL(window.location);
			url.searchParams.delete('vibra');
			window.history.pushState({}, '', url);
			currentTracks.value = [...currentTracks.value].sort((a, b) => {
				const cmp = (a.artist || '').localeCompare(b.artist || '');
				return cmp === 0 ? (a.title || '').localeCompare(b.title || '') : cmp;
			});
		} else if (type === 'mood') {
			const url = new URL(window.location);
			url.searchParams.delete('vibra');
			window.history.pushState({}, '', url);
			currentTracks.value = [...currentTracks.value].sort((a, b) => {
				return (b.mood_score || 0) - (a.mood_score || 0);
			});
		} else if (type === 'shuffle') {
			let seed;
			const urlParams = new URLSearchParams(window.location.search);
			const seedParam = urlParams.get('vibra');

			if (keepSeed && seedParam !== null && !isNaN(parseInt(seedParam))) {
				seed = parseInt(seedParam);
			} else {
				seed = Math.floor(Math.random() * 1000000);
				const url = new URL(window.location);
				url.searchParams.set('vibra', seed);
				window.history.pushState({}, '', url);
			}

			// Mulberry32 PRNG for a reproducible shuffle
			let a = seed;
			const randomFunc = () => {
				let t = (a += 0x6d2b79f5);
				t = Math.imul(t ^ (t >>> 15), t | 1);
				t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
				return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
			};

			let array = [...originalTracks.value];
			for (let i = array.length - 1; i > 0; i--) {
				const j = Math.floor(randomFunc() * (i + 1));
				[array[i], array[j]] = [array[j], array[i]];
			}
			currentTracks.value = array;
		}
		activeTab.value = 'library';
	}

	async function toggleFavorite(path) {
		await sendCmd('toggle_favorite', { path });
	}

	async function toggleQueue(path, mostrarToast = true) {
		const wasInQueue = queueState.value.includes(path);
		const title = getTrackInfo(path).display_title;
		const res = await sendCmd('toggle_queue', { path });

		if (res && res.status === 'ok') {
			if (mostrarToast) {
				if (!wasInQueue) showToast(`¡Adentro! <b>${title}</b> a la fila.`, 'success');
				else showToast(`Sacamos <b>${title}</b> de la fila.`, 'warning');
			}
		} else {
			showToast('Uy, no se pudo agregar el tema.', 'error');
		}
	}

	function handleLibraryClick(track) {
		if (currentTrackPath.value === track.path) sendCmd('pause');
		else toggleQueue(track.path, false);
	}

	function switchTab(tabId) {
		activeTab.value = tabId;

		if (tabId === 'queue') {
			setTimeout(() => {
				const el = document.getElementById('current-queue-row');
				if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}, 200);
		}
	}

	async function togglePauseAfterCurrent() {
		if (!currentTrackPath.value) return;

		if (pauseAfterPath.value === currentTrackPath.value) {
			pauseAfterPath.value = null;
			await sendCmd('pause_after', { path: '' });
			showToast(`Cancelamos la pausa al terminar 🦦`, 'info');
		} else {
			pauseAfterPath.value = currentTrackPath.value;
			await sendCmd('pause_after', { path: currentTrackPath.value });
			const title = getTrackInfo(currentTrackPath.value).display_title;
			showToast(`Frenamos la joda después de <b>${title}</b> ⏸`, 'warning');
		}
	}

	async function toggleMpvVisibility() {
		const targetState = !mpvVisible.value;
		const endpoint = targetState ? '/mpv/show' : '/mpv/hide';
		try {
			await fetch(endpoint, { method: 'POST' });
			showToast(targetState ? 'Mostrando ventana de MPV' : 'Ocultando ventana de MPV', 'info');
			haptic();
		} catch (err) {
			console.error(err);
			showToast('Error cambiando visibilidad de MPV', 'error');
		}
	}

	function setVolume() {
		sendCmd('set_volume', { vollevel: parseInt(volume.value) });
	}

	function showToast(msg, type = 'info') {
		const id = toastIdCounter++;
		let icon = 'info',
			colorClasses = 'bg-blue-600';

		if (type === 'success') {
			icon = 'check_circle';
			colorClasses = 'bg-green-600';
		}

		if (type === 'warning') {
			icon = 'warning';
			colorClasses = 'bg-orange-600';
		}
		if (type === 'error') {
			icon = 'error';
			colorClasses = 'bg-red-600';
		}

		toasts.value.push({ id, msg, icon, colorClasses });
		setTimeout(() => {
			toasts.value = toasts.value.filter((t) => t.id !== id);
		}, 3000);
	}

	// --- LOCAL PLAYER METHODS ---
	function _startLocalPlayer(path) {
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

	function _stopLocalPlayer() {
		const lp = localPlayerRef.value;

		if (!lp) return;

		lp.pause();
		lp.removeAttribute('src');
		lp.load();
	}

	function _sendLocalPlayerUpdate(payload) {
		if (wsSend) wsSend(JSON.stringify({ type: 'local_player_update', ...payload }));
	}

	function haptic(heavy = false) {
		if (navigator.vibrate) {
			vibrate(heavy ? [10, 30, 20] : 10);
			return;
		}
		try {
			const ctx = new (window.AudioContext || window.webkitAudioContext)();
			const osc = ctx.createOscillator();
			const gain = ctx.createGain();
			osc.connect(gain);
			gain.connect(ctx.destination);
			gain.gain.setValueAtTime(heavy ? 0.03 : 0.01, ctx.currentTime);
			gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + (heavy ? 0.05 : 0.02));
			osc.frequency.setValueAtTime(heavy ? 200 : 400, ctx.currentTime);
			osc.start(ctx.currentTime);
			osc.stop(ctx.currentTime + (heavy ? 0.05 : 0.02));
			osc.onended = () => ctx.close();
		} catch {
			// Si el navegador no lo soporta, fallamos silenciosamente sin romper nada
		}
	}

	// --- Singleton Watchers and Timer initialization ---
	if (!usePlayer._initialized) {
		usePlayer._initialized = true;

		const title = useTitle('La Rockola del Carpincho 🦦🧉');

		// Sincronización reactiva del Título y MediaSession (reemplaza updateMediaSession y updateDocumentTitle)
		watchEffect(() => {
			if (currentTrackPath.value) {
				const info = getTrackInfo(currentTrackPath.value);

				// 1. Actualiza el título de la pestaña
				if (isPlaying.value) {
					title.value = `${info.display_title} 🦦🧉`;
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
				if (wsSend) wsSend(JSON.stringify({ type: 'local_player_claim' }));
			} else {
				if (wsSend) wsSend(JSON.stringify({ type: 'local_player_release' }));

				sendCmd('set_mute', { state: false });
				_stopLocalPlayer();
			}
		});
	}

	return {
		_sendLocalPlayerUpdate,
		activeTab,
		connectWebSocket,
		currentTrackPath,
		currentTracks,
		djCarpinchoEnabled,
		djNextTrack,
		djSafeModeEnabled,
		duration,
		favorites,
		getTrackInfo,
		handleLibraryClick,
		haptic,
		historyState,
		ignoreServerTimeUntil,
		isDraggingSeek,
		isFogonMode,
		isPaused,
		isPlaying,
		isScanning,
		librarySearchQuery,
		listenLocally,
		loadLibrary,
		localPlayerRef,
		localTimePos,
		mpvVisible,
		normalizeString,
		originalTracks,
		pauseAfterPath,
		queueIndex,
		queueState,
		sendCmd,
		serverMuted,
		setVolume,
		showFogonVolume,
		showToast,
		sortLibrary,
		switchTab,
		timePos,
		toasts,
		toggleFavorite,
		toggleMpvVisibility,
		togglePauseAfterCurrent,
		toggleQueue,
		topPlayedState,
		volIcon,
		volume,
	};
}
