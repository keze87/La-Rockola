<script setup lang="ts">
	import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
	import { useLyrics, type LyricSyllable, type LyricLine } from '../composables/useLyrics';
	import { useCover } from '../composables/useCover';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import {
		enterAndroidPipModeDetailed,
		isAndroidPipMode,
		isNativeAndroidHost,
		setAndroidFogonState,
		setAndroidKeepScreenOn,
	} from '../composables/useAndroidHost';
	import { useToasts } from '../composables/player/useToasts';
	import { useSliderFactory } from '../composables/useSliderFactory';
	import { useContextMenuBindings } from '../composables/useContextMenu';
	import { useMarquee } from '../composables/useMarquee';
	import DragSlider from './ui/DragSlider.vue';
	import FavoritableCover from './ui/FavoritableCover.vue';
	import UpNextCard from './ui/UpNextCard.vue';

	const { pause, skip, prev, seekAbsolute, setMute } = usePlaybackControls();
	const player = usePlayer();
	const {
		currentTrackPath,
		djBaraEnabled,
		djNextTrack,
		duration,
		haptic,
		pendingSeekTime,
		isDraggingSeek,
		isFogonMode,
		isPaused,
		isPlaying,
		isPlayingRadioAnnouncement,
		isSynthesizingRadio,
		listenLocally,
		localPlayerRef,
		localTimePos,
		pauseAfterPath,
		serverMuted,
		showFogonVolume,
		togglePauseAfterCurrent,
		volIcon,
		volume,
		setVolume,
	} = player;

	const { createSlider } = useSliderFactory();

	const isLocalTrackPlayingOrPaused = computed(() => {
		const path = currentTrackPath.value;
		if (!path) return false;
		// Solo debe responder si hay un tema reproduciéndose o pausado
		if (!isPlaying.value && !isPaused.value) return false;
		// No debe dispararse para anuncios de radio ni transmisiones de cabina
		if (isPlayingRadioAnnouncement.value || path.includes('radio_announcement')) return false;
		// Debe ser una canción local (no URL web o streaming)
		if (path.startsWith('http://') || path.startsWith('https://')) return false;
		return true;
	});

	const rawContextMenuBindings = useContextMenuBindings(
		() => player.getTrackInfo(currentTrackPath.value || ''),
		'current'
	);

	const fogonContextBindings = {
		contextmenu: (e: MouseEvent) => {
			if (!isLocalTrackPlayingOrPaused.value) return;
			rawContextMenuBindings.contextmenu(e);
		},
		touchstart: (e: TouchEvent) => {
			if (!isLocalTrackPlayingOrPaused.value) return;
			rawContextMenuBindings.touchstart?.(e);
		},
		touchend: (e: TouchEvent) => rawContextMenuBindings.touchend?.(e),
		touchcancel: (e: TouchEvent) => rawContextMenuBindings.touchcancel?.(e),
		touchmove: (e: TouchEvent) => rawContextMenuBindings.touchmove?.(e),
	};

	// 1. Barra de progreso (Seek)
	const {
		displayValue: dragTimePos,
		progressPercent,
		startDrag: startSeek,
		moveDrag: moveSeek,
		endDrag: endSeek,
	} = createSlider(
		localTimePos,
		duration,
		() => (isDraggingSeek.value = true),
		(val) => {
			isDraggingSeek.value = false;
			localTimePos.value = val;
			pendingSeekTime.value = val;

			if (listenLocally.value && localPlayerRef.value) {
				localPlayerRef.value.currentTime = val;
				player._sendLocalPlayerUpdate?.({ time_pos: val });
			} else {
				seekAbsolute(val);
			}
		}
	);

	const formattedTimePos = computed(() => formatTime(dragTimePos.value));
	const formattedDuration = computed(() => formatTime(duration.value));

	let lastVolSent = 0;
	let volThrottleTimer: ReturnType<typeof setTimeout> | null = null;

	function throttledSetVolume() {
		const now = Date.now();
		if (now - lastVolSent >= 150) {
			lastVolSent = now;
			setVolume();
		} else if (!volThrottleTimer) {
			volThrottleTimer = setTimeout(() => {
				volThrottleTimer = null;
				lastVolSent = Date.now();
				setVolume();
			}, 150);
		}
	}

	function handleVolumeUpdate(val: number) {
		volume.value = Math.round(val);

		if (serverMuted.value && volume.value > 0) {
			setMute(false);
		}
		throttledSetVolume();
	}

	function handleVolumeCommit(val: number) {
		if (volThrottleTimer) {
			clearTimeout(volThrottleTimer);
			volThrottleTimer = null;
		}
		volume.value = Math.round(val);
		setVolume();
	}

	// Le pasamos la instancia global del reproductor al composable de letras para sincronizar localTimePos
	const { activeLyricLines, loadLyrics, lyrics } = useLyrics(player);

	// Estado para la vista expandida tipo Apple Music / blyrics
	const lyricsContainerRef = ref<HTMLElement | null>(null);
	const lineRefs = ref<(HTMLElement | null)[]>([]);
	const userIsScrolling = ref(false);
	let userScrollTimer: ReturnType<typeof setTimeout> | null = null;

	const hasLyrics = computed(() => lyrics.value && lyrics.value.length > 0);

	function isLineActive(line: LyricLine): boolean {
		return activeLyricLines.value.some((a) => a.time === line.time);
	}

	const activeLineIndex = computed(() => {
		if (!lyrics.value.length || !activeLyricLines.value.length) return -1;
		const firstActive = activeLyricLines.value[0];
		return lyrics.value.findIndex((l) => l.time === firstActive.time);
	});

	// Para el modo vertical en pantallas chicas o celulares: mostramos hasta 4 líneas (1 previa + 1 activa + 2 siguientes)
	const portraitLyricLines = computed(() => {
		if (!lyrics.value.length) return [];
		if (activeLineIndex.value < 0) {
			const pos = player.localTimePos.value;
			if (pos < lyrics.value[0].time) {
				// Antes de que arranque el tema: mostramos los primeros 3 versos
				return lyrics.value.slice(0, 3);
			}
			// En silencios intermedios: mostramos en torno al próximo verso o el último
			const upcomingIdx = lyrics.value.findIndex((l) => l.time > pos);
			if (upcomingIdx !== -1) {
				const start = Math.max(0, upcomingIdx - 1);
				const end = Math.min(lyrics.value.length, upcomingIdx + 3);
				return lyrics.value.slice(start, end);
			}
			return lyrics.value.slice(-3);
		}
		const activeIdx = activeLineIndex.value;
		const activeCount = activeLyricLines.value.length;

		// Si hay varias líneas activas a la vez (dueto/coros), mostramos las activas más las siguientes
		if (activeCount > 1) {
			const start = Math.max(0, activeIdx);
			const end = Math.min(lyrics.value.length, activeIdx + activeCount + 2);
			return lyrics.value.slice(start, end);
		}

		// Si hay una sola línea activa: anterior (si hay), actual y siguientes (hasta 4 líneas)
		const start = Math.max(0, activeIdx - 1);
		const end = Math.min(lyrics.value.length, activeIdx + 3);
		return lyrics.value.slice(start, end);
	});

	function scrollToActiveLine(smooth = true) {
		if (userIsScrolling.value || !lyrics.value.length) return;
		const container = lyricsContainerRef.value;
		if (!container) return;

		let targetIdx = activeLineIndex.value;
		if (targetIdx < 0) {
			const pos = player.localTimePos.value;
			if (pos < lyrics.value[0].time) {
				targetIdx = 0;
			} else {
				const upcomingIdx = lyrics.value.findIndex((l) => l.time > pos);
				targetIdx = upcomingIdx !== -1 ? Math.max(0, upcomingIdx - 1) : lyrics.value.length - 1;
			}
		}

		const activeEl = lineRefs.value[targetIdx];
		if (activeEl) {
			const targetTop =
				targetIdx === 0 && activeLineIndex.value < 0
					? 0
					: Math.max(0, activeEl.offsetTop - container.clientHeight / 2 + activeEl.clientHeight / 2);
			if (typeof container.scrollTo === 'function') {
				container.scrollTo({
					top: targetTop,
					behavior: smooth ? 'smooth' : 'auto',
				});
			} else {
				container.scrollTop = targetTop;
			}
		}
	}

	function handleUserScroll() {
		userIsScrolling.value = true;
		if (userScrollTimer) clearTimeout(userScrollTimer);
		userScrollTimer = setTimeout(() => {
			userIsScrolling.value = false;
			scrollToActiveLine(true);
		}, 3500);
	}

	function handleLineClick(time: number) {
		seekAbsolute(time);
		userIsScrolling.value = false;
		haptic();
	}

	watch(activeLineIndex, (newIdx) => {
		if (newIdx >= 0) {
			nextTick(() => {
				scrollToActiveLine(true);
			});
		}
	});

	watch([lyrics, isFogonMode], () => {
		userIsScrolling.value = false;
		nextTick(() => {
			scrollToActiveLine(false);
		});
	});

	// Estilo para cada sílaba en el modo karaoke según el momento de la canción (cohesivo con la impronta carpincha)
	function getSyllableClass(syl: LyricSyllable): string {
		const pos = localTimePos.value;
		if (pos >= syl.end) {
			// Ya sonó: dorado mate dulce
			return 'text-carpincho-warning font-black transition-colors duration-150 inline';
		} else if (pos >= syl.start && pos < syl.end) {
			// Cantándose justo ahora: blanco destacado con halo cálido moderado y sin subrayado tosco
			return 'text-white font-black scale-105 drop-shadow-[0_0_10px_rgba(233,196,106,0.75)] transition-transform duration-100 inline-block';
		}
		// Futura: tono crema carpincho atenuado para lectura anticipada
		return 'text-carpincho-text/40 font-bold transition-colors duration-150 inline';
	}

	// --- Propiedades computadas para simplificar el template ---
	const coverSource = computed(() => {
		if (isSynthesizingRadio.value || isPlayingRadioAnnouncement.value) {
			return currentTrackPath.value || 'radio_announcement.mp3';
		}
		if (currentTrackPath.value) return currentTrackPath.value;
		if (djBaraEnabled.value && djNextTrack.value?.path) return djNextTrack.value.path;
		return null;
	});

	const { coverUrl: currentCoverUrl } = useCover(coverSource, { size: 256 });

	const currentTrackInfo = computed(() => {
		if (isSynthesizingRadio.value || (isPlayingRadioAnnouncement.value && !currentTrackPath.value)) {
			return {
				title: 'Transmisión de Cabina',
				artist: 'Acomodando los micrófonos... 🎙️',
				isComing: true,
			};
		}

		if (isPlayingRadioAnnouncement.value) {
			const info = currentTrackPath.value ? player.getTrackInfo(currentTrackPath.value) : null;
			return {
				title: 'Transmisión de Cabina',
				artist: info?.display_artist || 'Transmisión de Cabina 🎙️',
				isComing: false,
			};
		}

		if (currentTrackPath.value) {
			const info = player.getTrackInfo(currentTrackPath.value);
			return {
				title: info.display_title || 'Silencio estampa',
				artist: info.display_artist || 'Nadie',
				isComing: false,
			};
		}

		if (djBaraEnabled.value && djNextTrack.value) {
			return {
				title: djNextTrack.value.display_title || djNextTrack.value.title,
				artist: djNextTrack.value.display_artist || djNextTrack.value.artist,
				isComing: true,
			};
		}

		return { title: 'Silencio estampa', artist: 'Nadie', isComing: false };
	});

	const playPauseIcon = computed(() => (isPlaying.value ? 'pause' : 'play_arrow'));
	const muteIcon = computed(() => (serverMuted.value || volume.value == 0 ? 'volume_off' : 'volume_down'));

	const currentTrackKey = computed(() => {
		if (isSynthesizingRadio.value) return 'radio-synthesizing';
		if (isPlayingRadioAnnouncement.value) return `radio-announcement-${currentTrackPath.value || ''}`;
		if (currentTrackPath.value) return currentTrackPath.value;
		if (djBaraEnabled.value && djNextTrack.value?.path) return `dj-${djNextTrack.value.path}`;
		return 'empty';
	});

	// Lógica del botón de temporizador / pausa programada
	const isTimerActive = computed(() => pauseAfterPath.value === currentTrackPath.value && currentTrackPath.value);
	const timerClass = computed(() => [
		'fogon-timer-btn tap-feedback flex h-10 w-10 items-center justify-center rounded-full transition-colors z-20',
		isTimerActive.value
			? 'bg-[var(--accent-primary-soft)] text-[var(--accent-primary)]'
			: 'text-[var(--text-primary)]/88 hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]',
	]);
	const timerTitle = computed(() => (isTimerActive.value ? 'Cancelar pausa al terminar' : 'Frenar tras este tema'));

	watch(
		currentTrackPath,
		(newPath) => {
			loadLyrics(newPath); // Traer y parsear letras al cambiar de tema
		},
		{ immediate: true }
	);

	function formatTime(sec: number) {
		if (!sec || isNaN(sec)) return '0:00';

		const m = Math.floor(sec / 60);
		const s = Math.floor(sec % 60)
			.toString()
			.padStart(2, '0');
		return `${m}:${s}`;
	}

	// --- Manejadores de acciones ---
	function closeFogon() {
		isFogonMode.value = false;
		haptic();
	}

	// Gestos sobre la tapa: deslizar hacia abajo cierra Fogón; deslizar horizontal pasa de tema
	const COVER_SWIPE_CLOSE_THRESHOLD = 72;
	const COVER_SWIPE_SKIP_THRESHOLD = 64;
	const coverSwipeX = ref(0);
	const coverSwipeY = ref(0);
	const isCoverSwiping = ref(false);
	let coverTouchStartX = 0;
	let coverTouchStartY = 0;
	let coverSwipeAxis: 'vertical' | 'horizontal' | null = null;

	const coverSwipeStyle = computed(() => {
		if (coverSwipeX.value !== 0) {
			const opacity = Math.max(0.55, 1 - Math.abs(coverSwipeX.value) / 240);
			return {
				transform: `translateX(${Math.round(coverSwipeX.value)}px)`,
				opacity: opacity.toFixed(2),
				transition: isCoverSwiping.value ? 'none' : undefined,
			};
		}
		if (coverSwipeY.value <= 0) return undefined;
		const opacity = Math.max(0.45, 1 - coverSwipeY.value / 280);
		return {
			transform: `translateY(${Math.round(coverSwipeY.value)}px)`,
			opacity: opacity.toFixed(2),
			transition: isCoverSwiping.value ? 'none' : undefined,
		};
	});

	function resetCoverSwipe() {
		coverSwipeX.value = 0;
		coverSwipeY.value = 0;
		isCoverSwiping.value = false;
		coverSwipeAxis = null;
	}

	function onCoverTouchStart(e: TouchEvent) {
		const touch = e.touches[0];
		if (!touch) return;
		coverTouchStartX = touch.clientX;
		coverTouchStartY = touch.clientY;
		isCoverSwiping.value = true;
		coverSwipeAxis = null;
		coverSwipeX.value = 0;
		coverSwipeY.value = 0;
	}

	function onCoverTouchMove(e: TouchEvent) {
		if (!isCoverSwiping.value) return;
		const touch = e.touches[0];
		if (!touch) return;
		const dx = touch.clientX - coverTouchStartX;
		const dy = touch.clientY - coverTouchStartY;

		if (!coverSwipeAxis && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
			coverSwipeAxis = Math.abs(dy) > Math.abs(dx) && dy > 0 ? 'vertical' : 'horizontal';
		}

		if (coverSwipeAxis === 'vertical') {
			coverSwipeY.value = Math.max(0, Math.min(240, dy));
			coverSwipeX.value = 0;
			if (e.cancelable) e.preventDefault();
		} else if (coverSwipeAxis === 'horizontal') {
			coverSwipeX.value = Math.max(-120, Math.min(120, dx));
			coverSwipeY.value = 0;
			if (e.cancelable) e.preventDefault();
		} else {
			coverSwipeX.value = 0;
			coverSwipeY.value = 0;
		}
	}

	function onCoverTouchEnd() {
		if (!isCoverSwiping.value) return;
		const axis = coverSwipeAxis;
		const dx = coverSwipeX.value;
		const dy = coverSwipeY.value;
		resetCoverSwipe();

		if (axis === 'vertical' && dy >= COVER_SWIPE_CLOSE_THRESHOLD) {
			closeFogon();
		} else if (axis === 'horizontal' && dx <= -COVER_SWIPE_SKIP_THRESHOLD) {
			skipNext();
		} else if (axis === 'horizontal' && dx >= COVER_SWIPE_SKIP_THRESHOLD) {
			skipPrev();
		}
	}

	function goToQueueFromFogon() {
		closeFogon();
		player.switchTab('queue');
		haptic();
	}

	function toggleVolumePopup() {
		showFogonVolume.value = !showFogonVolume.value;
		haptic();
	}

	function togglePlay() {
		pause();
		haptic(true);
	}

	function skipPrev() {
		prev();
		haptic();
	}

	function skipNext() {
		skip();
		haptic();
	}

	function toggleMute() {
		setMute(!serverMuted.value);
		haptic();
	}

	function handleTimerToggle() {
		togglePauseAfterCurrent();
		haptic();
	}

	// Ocultar el cursor únicamente cuando no haya actividad del mouse por 3 segundos
	const isCursorInactive = ref(false);
	let cursorTimer: ReturnType<typeof setTimeout> | null = null;
	const INACTIVITY_DELAY_MS = 3000;

	// Detección de desborde y marquesina estilo radio vieja para título y artista
	const titleContainerRef = ref<HTMLElement | null>(null);
	const titleTextRef = ref<HTMLElement | null>(null);
	const artistContainerRef = ref<HTMLElement | null>(null);
	const artistTextRef = ref<HTMLElement | null>(null);

	const {
		isOverflowing: isTitleOverflowing,
		marqueeStyle: titleMarqueeStyle,
		checkOverflow: checkTitleOverflow,
		resetOverflow: resetTitleOverflow,
	} = useMarquee(titleContainerRef, titleTextRef, {
		minDuration: 6,
		baseDuration: 4,
		speedFactor: 0.035,
		extraPadding: 12,
	});

	const {
		isOverflowing: isArtistOverflowing,
		marqueeStyle: artistMarqueeStyle,
		checkOverflow: checkArtistOverflow,
		resetOverflow: resetArtistOverflow,
	} = useMarquee(artistContainerRef, artistTextRef, {
		minDuration: 5,
		baseDuration: 3.5,
		speedFactor: 0.035,
		extraPadding: 12,
	});

	function checkOverflow() {
		checkTitleOverflow();
		checkArtistOverflow();
	}

	watch(currentTrackInfo, () => {
		resetTitleOverflow();
		resetArtistOverflow();
		nextTick(() => {
			checkOverflow();
		});
	});

	function resetCursorTimer() {
		isCursorInactive.value = false;
		if (cursorTimer) {
			clearTimeout(cursorTimer);
		}
		if (isFogonMode.value) {
			cursorTimer = setTimeout(() => {
				isCursorInactive.value = true;
			}, INACTIVITY_DELAY_MS);
		}
	}

	function handleMouseMove() {
		resetCursorTimer();
	}

	const canEnterAndroidPip = computed(() => isNativeAndroidHost() && !isAndroidPipMode.value);
	const { showToast } = useToasts();

	async function openAndroidPip() {
		haptic();
		const res = await enterAndroidPipModeDetailed();
		if (!res.entered) {
			showToast('Este teléfono no permitió abrir la ventana flotante (PiP).', 'warning');
		}
	}

	watch(
		isFogonMode,
		(active) => {
			void setAndroidKeepScreenOn(active);
			void setAndroidFogonState(active);
			if (active) {
				window.addEventListener('mousemove', handleMouseMove);
				resetCursorTimer();
				nextTick(() => {
					checkOverflow();
				});
			} else {
				window.removeEventListener('mousemove', handleMouseMove);
				if (cursorTimer) {
					clearTimeout(cursorTimer);
					cursorTimer = null;
				}
				isCursorInactive.value = false;
				resetCoverSwipe();
			}
		},
		{ immediate: true }
	);

	onUnmounted(() => {
		void setAndroidKeepScreenOn(false);
		void setAndroidFogonState(false);
		window.removeEventListener('mousemove', handleMouseMove);
		if (cursorTimer) {
			clearTimeout(cursorTimer);
			cursorTimer = null;
		}
		if (volThrottleTimer) {
			clearTimeout(volThrottleTimer);
			volThrottleTimer = null;
		}
		if (userScrollTimer) {
			clearTimeout(userScrollTimer);
			userScrollTimer = null;
		}
	});
</script>

<template>
	<transition name="fogon">
		<div
			v-if="isFogonMode"
			class="fogon-container fixed inset-0 z-[10000] flex items-center justify-center overflow-hidden overscroll-contain bg-[var(--bg-canvas)] px-4 pt-[calc(2.5rem+var(--rockola-safe-top))] pb-[calc(1rem+var(--rockola-safe-bottom))] text-[var(--text-primary)] sm:p-6 sm:pt-[calc(2.5rem+var(--rockola-safe-top))] sm:pb-[calc(1.5rem+var(--rockola-safe-bottom))] md:p-10 md:pt-[calc(3rem+var(--rockola-safe-top))] md:pb-[calc(2.5rem+var(--rockola-safe-bottom))]"
			:class="[{ 'cursor-none [&_*]:cursor-none': isCursorInactive }, { 'is-android-pip': isAndroidPipMode }]"
		>
			<!-- Fondo ambiental dinámico estilo Apple Music -->
			<div class="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
				<div
					v-if="currentCoverUrl"
					class="absolute inset-0 scale-[1.4] bg-cover bg-center opacity-[0.34] blur-[64px] saturate-150 transition-all duration-700"
					:style="{ backgroundImage: `url('${currentCoverUrl}')` }"
				/>
				<div
					class="absolute inset-0 bg-[linear-gradient(180deg,rgba(18,14,11,0.55)_0%,rgba(18,14,11,0.82)_55%,rgba(18,14,11,0.96)_100%)]"
				/>
			</div>

			<!-- Grabber pill centrado estilo iOS Sheet para cerrar el fogón -->
			<button
				type="button"
				aria-label="Cerrar vista de fogón"
				class="fogon-close-btn tap-feedback absolute top-[calc(0.5rem+var(--rockola-safe-top))] left-1/2 z-40 flex min-h-[36px] min-w-[72px] -translate-x-1/2 cursor-pointer items-center justify-center rounded-full"
				@click="closeFogon"
			>
				<span class="h-[5px] w-[36px] rounded-full bg-[rgba(255,240,220,0.28)]" aria-hidden="true" />
			</button>

			<!-- Botón nativo de Picture-in-Picture en Android -->
			<button
				v-if="canEnterAndroidPip"
				type="button"
				aria-label="Abrir en ventana flotante"
				title="Ventana flotante (PiP)"
				class="touch-target tap-feedback absolute top-[calc(0.75rem+var(--rockola-safe-top))] right-4 z-40 flex h-9 w-9 items-center justify-center rounded-full border border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-primary)]/88 hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]"
				@click="openAndroidPip"
			>
				<i class="material-icons !text-[20px]" aria-hidden="true">picture_in_picture_alt</i>
			</button>

			<!-- Capa para cerrar el popup de volumen al tocar afuera -->
			<div
				v-if="showFogonVolume"
				class="fogon-volume-backdrop fixed inset-0 z-30"
				@click="showFogonVolume = false"
			/>

			<!-- Contenedor principal expandido (estilo Apple Music / blyrics) -->
			<div
				class="fogon-main-layout relative flex h-full w-full max-w-7xl items-center justify-center transition-all duration-500"
				:class="[
					hasLyrics
						? 'has-lyrics flex-col justify-center md:flex-row md:items-center md:gap-12 lg:gap-16'
						: 'mx-auto flex-col justify-center text-center',
				]"
			>
				<!-- COLUMNA IZQUIERDA: Carátula, info y controles del reproductor (centrado simétrico impecable) -->
				<div
					class="fogon-player-column flex w-full shrink-0 flex-col items-center justify-center text-center transition-all duration-500"
					:class="[
						hasLyrics
							? 'h-full py-2 sm:py-4 md:h-auto md:w-88 md:py-0 lg:w-[380px] xl:w-[420px]'
							: 'my-auto max-w-md',
					]"
				>
					<div class="fogon-song-info contents" v-on="fogonContextBindings">
						<!-- Bloque superior: Carátula del álbum bajada hacia el título central en móviles -->
						<div
							class="fogon-cover-section flex w-full flex-col items-center text-center"
							:class="[
								hasLyrics
									? 'min-h-0 flex-[6] justify-end pb-1 sm:pb-2 md:h-auto md:flex-none md:shrink-0 md:justify-center md:pb-0'
									: 'shrink-0 justify-center',
							]"
						>
							<!-- Tapa del disco con escala Apple Music al pausar -->
							<div
								class="fogon-cover-wrapper flex shrink-0 touch-none items-center justify-center overflow-hidden rounded-[16px] border border-[var(--hairline)] bg-[var(--bg-elevated)] shadow-[0_20px_50px_rgba(0,0,0,0.55)] transition-transform duration-[450ms] ease-[var(--ease-spring)]"
								:class="[
									hasLyrics
										? 'aspect-square h-[90vw] max-h-[380px] w-[90vw] max-w-[380px] md:mb-5 md:h-auto md:max-h-none md:w-full md:max-w-none'
										: 'mb-4 aspect-square h-56 max-h-[38vh] w-56 max-w-[38vh] sm:h-64 sm:w-64 md:mb-6 md:h-80 md:w-80 lg:h-88 lg:w-88',
									!isPlaying ? 'scale-[0.92]' : 'scale-100',
								]"
								:style="coverSwipeStyle"
								@touchstart.passive="onCoverTouchStart"
								@touchmove="onCoverTouchMove"
								@touchend="onCoverTouchEnd"
								@touchcancel="resetCoverSwipe"
							>
								<transition name="fogon-cover" mode="out-in">
									<FavoritableCover
										v-if="coverSource"
										:key="coverSource"
										:track="coverSource"
										size="h-full w-full"
										rounded="rounded-2xl md:rounded-3xl"
										:size-px="512"
										:unload-when-hidden="false"
										button-size="h-10 w-10 md:h-12 md:w-12"
										button-icon-size="text-xl md:text-2xl"
										button-position="right-3 bottom-3 md:right-4 md:bottom-4"
										:show-favorite="!isSynthesizingRadio && !isPlayingRadioAnnouncement"
									/>
									<i
										v-else
										key="empty-cover"
										class="material-icons text-carpincho-warning text-[8rem]"
									>
										album
									</i>
								</transition>
							</div>
						</div>

						<!-- Bloque central: Información del tema con animación de transición y marquesina tipo radio -->
						<transition name="fogon-track" mode="out-in" @after-enter="checkOverflow">
							<div
								:key="currentTrackKey"
								class="fogon-track-info flex w-full shrink-0 flex-col items-center text-center select-none"
								:class="[hasLyrics ? 'my-2 sm:my-3 md:my-0' : 'my-2 md:my-3']"
							>
								<!-- Info del tema con marquesina estilo radio si desborda el ancho -->
								<div
									ref="titleContainerRef"
									class="fogon-marquee-container w-full max-w-full overflow-hidden"
									:class="{ 'has-overflow': isTitleOverflowing }"
								>
									<h1
										ref="titleTextRef"
										class="fogon-title font-black transition-all"
										:class="[
											hasLyrics
												? 'text-xl sm:text-2xl md:text-3xl xl:text-4xl'
												: 'text-2xl sm:text-3xl md:text-4xl',
											isTitleOverflowing
												? 'fogon-radio-scroll'
												: 'mb-1 w-full truncate text-center',
										]"
										:style="titleMarqueeStyle"
									>
										<span
											v-if="currentTrackInfo.isComing"
											class="text-carpincho-warning mb-1 block animate-pulse text-xs tracking-widest uppercase"
										>
											🦦 Se viene...
										</span>
										{{ currentTrackInfo.title }}
									</h1>
								</div>

								<div
									ref="artistContainerRef"
									class="fogon-marquee-container w-full max-w-full overflow-hidden"
									:class="{ 'has-overflow': isArtistOverflowing }"
								>
									<h2
										ref="artistTextRef"
										class="fogon-artist text-carpincho-secondary font-medium"
										:class="[
											hasLyrics
												? 'text-sm sm:text-base md:text-lg lg:text-xl'
												: 'text-base sm:text-lg md:text-xl',
											isArtistOverflowing ? 'fogon-radio-scroll' : 'w-full truncate text-center',
										]"
										:style="artistMarqueeStyle"
									>
										{{ currentTrackInfo.artist }}
									</h2>
								</div>
							</div>
						</transition>
					</div>

					<!-- Bloque inferior: Barra de progreso, controles y letras móviles acercados hacia el centro -->
					<div
						class="fogon-bottom-section flex w-full flex-col items-center text-center"
						:class="[
							hasLyrics
								? 'min-h-0 flex-[4] justify-start md:h-auto md:flex-none md:shrink-0 md:justify-center'
								: 'mt-3 shrink-0 sm:mt-4 md:mt-4',
						]"
					>
						<!-- Sub-bloque de barra de progreso y controles -->
						<div
							class="fogon-controls-wrapper flex w-full shrink-0 flex-col items-center text-center"
							:class="[hasLyrics ? 'pt-1 md:mt-4 md:pt-0' : '']"
						>
							<!-- Barra de progreso personalizada -->
							<div
								v-show="currentTrackPath"
								class="fogon-seekbar-wrapper tabular-nums flex w-[90vw] max-w-[380px] items-center gap-3 text-[12px] font-medium text-[var(--text-secondary)] select-none md:w-full md:max-w-none"
							>
								<span class="w-10 shrink-0 text-right">{{ formattedTimePos }}</span>

								<div
									class="group flex h-10 w-full cursor-pointer touch-none items-center"
									@pointerdown="startSeek"
									@pointermove="moveSeek"
									@pointerup="endSeek"
									@pointercancel="endSeek"
								>
									<div
										class="pointer-events-none relative h-[6px] w-full rounded-full bg-[rgba(255,236,210,0.16)] transition-[height] duration-150 group-active:h-[10px]"
									>
										<div
											class="absolute top-0 left-0 h-full rounded-full bg-[var(--accent-primary)]"
											:style="{ width: progressPercent + '%' }"
										/>
										<div
											class="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full bg-[#f5efe6] shadow-[0_2px_6px_rgba(0,0,0,0.45)] transition-transform group-active:scale-110"
											:style="{ left: progressPercent + '%', marginLeft: '-7px' }"
										/>
									</div>
								</div>

								<span class="w-10 shrink-0">{{ formattedDuration }}</span>
							</div>

							<!-- Controles de reproducción centrados con más aire -->
							<div
								class="fogon-controls-row relative z-30 mt-2 flex w-full items-center justify-center gap-4 sm:mt-3 sm:gap-6 md:mt-4"
							>
								<!-- Barra de volumen desplegable flotante -->
								<div
									v-if="showFogonVolume"
									class="fogon-volume-bar absolute bottom-full left-1/2 z-50 mb-3 flex w-[90%] max-w-xs -translate-x-1/2 items-center gap-4 rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg-strong)] px-4 py-2 text-[var(--text-primary)] shadow-2xl [backdrop-filter:var(--glass-blur)] transition select-none sm:max-w-sm"
								>
									<button
										type="button"
										aria-label="Silenciar"
										class="touch-target"
										@click="toggleMute"
									>
										<i
											class="material-icons cursor-pointer text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
											aria-hidden="true"
										>
											{{ muteIcon }}
										</i>
									</button>

									<DragSlider
										:model-value="volume"
										:max="isNativeAndroidHost() ? 100 : 110"
										@update:model-value="handleVolumeUpdate"
										@commit="handleVolumeCommit"
									/>
									<i class="material-icons text-sm text-[var(--text-secondary)]" aria-hidden="true">
										volume_up
									</i>
								</div>

								<button
									type="button"
									aria-label="Ajustar volumen"
									class="fogon-volume-btn touch-target tap-feedback z-20 flex h-10 w-10 items-center justify-center rounded-full text-[var(--text-primary)]/88 hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]"
									@click="toggleVolumePopup"
								>
									<i class="material-icons !text-[24px]" aria-hidden="true">{{ volIcon }}</i>
								</button>

								<button
									type="button"
									aria-label="Pista anterior"
									class="fogon-prev-btn touch-target tap-feedback z-20 flex h-11 w-11 items-center justify-center rounded-full text-[var(--text-primary)]/88 hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]"
									@click="skipPrev"
								>
									<i class="material-icons !text-[32px]" aria-hidden="true">skip_previous</i>
								</button>

								<button
									type="button"
									:aria-label="isPlaying ? 'Pausar' : 'Reproducir'"
									class="fogon-play-btn tap-feedback z-20 flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-[var(--accent-primary)] text-[#120e0b] shadow-[0_8px_28px_rgba(212,150,66,0.35)] hover:brightness-110"
									@click="togglePlay"
								>
									<i class="material-icons !text-[38px]" aria-hidden="true">
										{{ playPauseIcon }}
									</i>
								</button>

								<button
									type="button"
									aria-label="Pista siguiente"
									class="fogon-next-btn touch-target tap-feedback z-20 flex h-11 w-11 items-center justify-center rounded-full text-[var(--text-primary)]/88 hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]"
									@click="skipNext"
								>
									<i class="material-icons !text-[32px]" aria-hidden="true">skip_next</i>
								</button>

								<!-- Botón para frenar después de este tema -->
								<button
									type="button"
									:class="[timerClass, 'touch-target']"
									:title="timerTitle"
									:aria-label="timerTitle"
									@click="handleTimerToggle"
								>
									<i class="material-icons !text-[24px]" aria-hidden="true">timer</i>
								</button>
							</div>

							<!-- Next song en pantallas anchas (abajo de los controles, similar al floating player) -->
							<UpNextCard @select="goToQueueFromFogon" />
						</div>

						<!-- MODO VERTICAL (Mobile / Portrait): Ocupa el 100% del ancho y se posiciona cercano a los controles -->
						<div
							v-if="hasLyrics"
							class="lyrics-mask-vertical fogon-lyrics-mobile relative mt-2 flex min-h-0 w-full flex-1 flex-col items-center justify-start overflow-hidden px-4 pt-1 text-center md:hidden"
						>
							<div class="flex flex-col items-center justify-start space-y-2 select-none sm:space-y-3">
								<div
									v-for="(line, idx) in portraitLyricLines"
									:key="'portrait-' + idx + '-' + line.time"
									class="cursor-pointer whitespace-pre-wrap transition-[color,opacity,transform] duration-300"
									:class="[
										isLineActive(line)
											? 'scale-[1.03] text-lg leading-relaxed font-black text-[var(--text-primary)] opacity-100 sm:text-xl'
											: 'text-xs font-semibold text-[var(--text-primary)] opacity-[0.42] hover:opacity-75 sm:text-sm',
									]"
									@click="handleLineClick(line.time)"
								>
									<template v-if="isLineActive(line)">
										<template v-if="line.syllables && line.syllables.length > 0">
											<span
												v-for="(syl, sIdx) in line.syllables"
												:key="sIdx"
												:class="getSyllableClass(syl)"
											>
												{{ syl.text }}
											</span>
										</template>
										<template v-else>
											<span class="text-carpincho-warning font-black">
												{{ line.text }}
											</span>
										</template>
									</template>
									<template v-else>
										<span>{{ line.text }}</span>
									</template>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- COLUMNA DERECHA: Letras completas en flujo vertical con estética Carpincha (solo en escritorio / apaisado) -->
				<transition name="fogon-lyrics">
					<div
						v-if="hasLyrics"
						class="lyrics-mask fogon-lyrics-container relative hidden h-[78vh] w-full flex-1 flex-col justify-center overflow-hidden md:flex lg:h-[84vh]"
					>
						<div
							ref="lyricsContainerRef"
							class="fogon-lyrics-scroll no-scrollbar h-full w-full space-y-7 overflow-y-auto overscroll-contain scroll-smooth px-6 py-[38vh] select-none md:space-y-8 md:px-12"
							@scroll="handleUserScroll"
							@wheel="handleUserScroll"
							@touchmove="handleUserScroll"
						>
							<div
								v-for="(line, idx) in lyrics"
								:key="idx + '-' + line.time"
								:ref="(el) => (lineRefs[idx] = el as HTMLElement)"
								class="cursor-pointer text-left whitespace-pre-wrap transition-[color,opacity,transform] duration-300"
								:class="[
									isLineActive(line)
										? 'origin-left scale-[1.03] text-3xl leading-tight font-black tracking-tight text-[var(--text-primary)] opacity-100 sm:text-4xl lg:text-5xl'
										: 'text-xl leading-snug font-extrabold tracking-tight text-[var(--text-primary)] opacity-[0.42] hover:opacity-75 sm:text-2xl lg:text-3xl',
								]"
								@click="handleLineClick(line.time)"
							>
								<template v-if="isLineActive(line)">
									<template v-if="line.syllables && line.syllables.length > 0">
										<span
											v-for="(syl, sIdx) in line.syllables"
											:key="sIdx"
											:class="getSyllableClass(syl)"
										>
											{{ syl.text }}
										</span>
									</template>
									<template v-else>
										<span class="text-carpincho-warning font-black">
											{{ line.text }}
										</span>
									</template>
								</template>
								<template v-else>
									<span>{{ line.text }}</span>
								</template>
							</div>
						</div>
					</div>
				</transition>
			</div>
		</div>
	</transition>
</template>

<style scoped>
	.fogon-enter-active,
	.fogon-leave-active {
		transition: opacity 0.35s ease-out;
	}

	.fogon-enter-from,
	.fogon-leave-to {
		opacity: 0;
	}

	/* Animaciones para cambio de tema (fogon-track) */
	.fogon-track-enter-active,
	.fogon-track-leave-active {
		transition:
			opacity 0.28s cubic-bezier(0.2, 0, 0, 1),
			transform 0.28s cubic-bezier(0.2, 0, 0, 1),
			filter 0.28s ease;
	}

	.fogon-track-enter-from {
		opacity: 0;
		transform: translateY(8px) scale(0.98);
		filter: blur(2px);
	}

	.fogon-track-leave-to {
		opacity: 0;
		transform: translateY(-8px) scale(0.98);
		filter: blur(2px);
	}

	/* Animaciones para cambio de carátula (fogon-cover) */
	.fogon-cover-enter-active,
	.fogon-cover-leave-active {
		transition:
			opacity 0.35s ease-out,
			transform 0.35s ease-out;
	}

	.fogon-cover-enter-from {
		opacity: 0;
		transform: scale(0.95);
	}

	.fogon-cover-leave-to {
		opacity: 0;
		transform: scale(1.02);
	}

	/* Animaciones para carga de letras (fogon-lyrics y fogon-lyrics-mobile) */
	.fogon-lyrics-enter-active,
	.fogon-lyrics-leave-active {
		transition:
			opacity 0.4s cubic-bezier(0.16, 1, 0.3, 1),
			transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
	}

	.fogon-lyrics-enter-from {
		opacity: 0;
		transform: translateY(16px);
	}

	.fogon-lyrics-leave-to {
		opacity: 0;
		transform: translateY(-12px);
	}

	.fogon-lyrics-mobile {
		animation: fogon-lyrics-appear 0.35s cubic-bezier(0.16, 1, 0.3, 1) backwards;
	}

	@keyframes fogon-lyrics-appear {
		from {
			opacity: 0;
			transform: translateY(12px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	/* Ocultar barra de scroll en el contenedor de letras */
	.no-scrollbar::-webkit-scrollbar {
		display: none;
	}
	.no-scrollbar {
		-ms-overflow-style: none;
		scrollbar-width: none;
	}

	/* Máscara de desvanecimiento suave superior e inferior */
	.lyrics-mask {
		mask-image: linear-gradient(to bottom, transparent 0%, black 14%, black 86%, transparent 100%);
		-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 14%, black 86%, transparent 100%);
	}

	/* Máscara de desvanecimiento para el modo vertical */
	.lyrics-mask-vertical {
		mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%);
		-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%);
	}

	/* Marquesina estilo radio vieja para títulos/artistas largos */
	.fogon-marquee-container {
		display: flex;
		justify-content: center;
		width: 100%;
		max-width: 100%;
		overflow: hidden;
		position: relative;
	}

	.fogon-marquee-container.has-overflow {
		justify-content: flex-start;
		mask-image: linear-gradient(to right, transparent 0%, black 14px, black calc(100% - 14px), transparent 100%);
		-webkit-mask-image: linear-gradient(
			to right,
			transparent 0%,
			black 14px,
			black calc(100% - 14px),
			transparent 100%
		);
	}

	.fogon-radio-scroll {
		display: inline-block;
		white-space: nowrap;
		animation: fogon-radio-marquee var(--marquee-duration, 8s) ease-in-out infinite;
		will-change: transform;
	}

	.fogon-marquee-container:hover .fogon-radio-scroll,
	.fogon-marquee-container:focus-within .fogon-radio-scroll,
	.fogon-radio-scroll:hover,
	.fogon-radio-scroll:focus-visible {
		animation-play-state: paused;
	}

	@keyframes fogon-radio-marquee {
		0%,
		18% {
			transform: translateX(0);
		}
		50%,
		68% {
			transform: translateX(var(--marquee-offset, -40px));
		}
		100% {
			transform: translateX(0);
		}
	}

	/* Contenedor responsivo con soporte de Container Queries */
	.fogon-container {
		container-type: size;
	}

	/* Modo PIP ultra-compacto (pantallas/contenedores <= 260px): SOLO se muestra la carátula sin botón de fav */
	@container (max-height: 260px) or (max-width: 260px) {
		.fogon-track-info,
		.fogon-bottom-section,
		.fogon-controls-wrapper,
		.fogon-lyrics-container,
		.lyrics-mask-vertical,
		.fogon-next-song {
			display: none !important;
		}

		.fogon-container {
			padding: 0 !important;
		}

		.fogon-main-layout,
		.fogon-player-column,
		.fogon-cover-section {
			height: 100% !important;
			width: 100% !important;
			max-height: 100% !important;
			max-width: 100% !important;
			margin: 0 !important;
			padding: 0 !important;
			display: flex !important;
			justify-content: center !important;
			align-items: center !important;
		}

		.fogon-cover-wrapper {
			height: 100% !important;
			width: 100% !important;
			max-height: 100% !important;
			max-width: 100% !important;
			aspect-ratio: auto !important;
			margin: 0 !important;
			border-radius: 0 !important;
			border: none !important;
			overflow: hidden !important;
		}

		:deep(.fogon-cover-wrapper button) {
			display: none !important;
		}

		:deep(.fogon-cover-wrapper),
		:deep(.fogon-cover-wrapper > div),
		:deep(.fogon-cover-wrapper img) {
			height: 100% !important;
			width: 100% !important;
			max-height: 100% !important;
			max-width: 100% !important;
			object-fit: cover !important;
		}

		.fogon-close-btn {
			top: 0.25rem !important;
			right: 0.25rem !important;
			padding: 0.25rem !important;
			opacity: 0.3 !important;
		}

		.fogon-close-btn:hover {
			opacity: 1 !important;
		}

		.fogon-close-btn i {
			font-size: 1.25rem !important;
		}
	}

	@media (max-height: 260px), (max-width: 260px) {
		.fogon-track-info,
		.fogon-bottom-section,
		.fogon-controls-wrapper,
		.fogon-lyrics-container,
		.lyrics-mask-vertical,
		.fogon-next-song {
			display: none !important;
		}

		.fogon-container {
			padding: 0 !important;
		}

		.fogon-main-layout,
		.fogon-player-column,
		.fogon-cover-section {
			height: 100% !important;
			width: 100% !important;
			max-height: 100% !important;
			max-width: 100% !important;
			margin: 0 !important;
			padding: 0 !important;
			display: flex !important;
			justify-content: center !important;
			align-items: center !important;
		}

		.fogon-cover-wrapper {
			height: 100% !important;
			width: 100% !important;
			max-height: 100% !important;
			max-width: 100% !important;
			aspect-ratio: auto !important;
			margin: 0 !important;
			border-radius: 0 !important;
			border: none !important;
			overflow: hidden !important;
		}

		:deep(.fogon-cover-wrapper button) {
			display: none !important;
		}

		:deep(.fogon-cover-wrapper),
		:deep(.fogon-cover-wrapper > div),
		:deep(.fogon-cover-wrapper img) {
			height: 100% !important;
			width: 100% !important;
			max-height: 100% !important;
			max-width: 100% !important;
			object-fit: cover !important;
		}

		.fogon-close-btn {
			top: 0.25rem !important;
			right: 0.25rem !important;
			padding: 0.25rem !important;
			opacity: 0.3 !important;
		}

		.fogon-close-btn:hover {
			opacity: 1 !important;
		}

		.fogon-close-btn i {
			font-size: 1.25rem !important;
		}
	}

	/* Modo PiP nativo en Android (incluso en pantallas de alta densidad donde la ventana excede 260px) */
	.fogon-container.is-android-pip {
		padding: 0 !important;
	}

	.fogon-container.is-android-pip .fogon-track-info,
	.fogon-container.is-android-pip .fogon-bottom-section,
	.fogon-container.is-android-pip .fogon-controls-wrapper,
	.fogon-container.is-android-pip .fogon-lyrics-container,
	.fogon-container.is-android-pip .lyrics-mask-vertical,
	.fogon-container.is-android-pip .fogon-next-song,
	.fogon-container.is-android-pip .fogon-close-btn,
	.fogon-container.is-android-pip .fogon-pip-btn {
		display: none !important;
	}

	.fogon-container.is-android-pip .fogon-main-layout,
	.fogon-container.is-android-pip .fogon-player-column,
	.fogon-container.is-android-pip .fogon-cover-section {
		height: 100% !important;
		width: 100% !important;
		max-height: 100% !important;
		max-width: 100% !important;
		margin: 0 !important;
		padding: 0 !important;
		display: flex !important;
		justify-content: center !important;
		align-items: center !important;
	}

	.fogon-container.is-android-pip .fogon-cover-wrapper {
		height: 100% !important;
		width: 100% !important;
		max-height: 100% !important;
		max-width: 100% !important;
		aspect-ratio: auto !important;
		margin: 0 !important;
		border-radius: 0 !important;
		border: none !important;
		overflow: hidden !important;
	}

	.fogon-container.is-android-pip :deep(.fogon-cover-wrapper button) {
		display: none !important;
	}

	.fogon-container.is-android-pip :deep(.fogon-cover-wrapper),
	.fogon-container.is-android-pip :deep(.fogon-cover-wrapper > div),
	.fogon-container.is-android-pip :deep(.fogon-cover-wrapper img) {
		height: 100% !important;
		width: 100% !important;
		max-height: 100% !important;
		max-width: 100% !important;
		object-fit: cover !important;
	}

	/* Soporte adaptativo para dispositivos móviles en apaisado / pantallas de altura reducida */
	@media (min-height: 261px) and (max-height: 550px) {
		.fogon-container {
			padding: 0.5rem 1.25rem !important;
		}

		.fogon-main-layout {
			gap: 1.5rem !important;
		}

		.fogon-main-layout.has-lyrics .fogon-player-column {
			width: 44% !important;
			max-width: 320px !important;
			height: 100% !important;
			justify-content: center !important;
		}

		.fogon-cover-wrapper {
			height: 34vh !important;
			width: 34vh !important;
			max-height: 34vh !important;
			max-width: 34vh !important;
			aspect-ratio: 1 / 1 !important;
			flex-shrink: 0 !important;
			margin-bottom: 0.35rem !important;
			border-radius: 1rem !important;
		}

		.fogon-cover-wrapper i {
			font-size: 3.5rem !important;
		}

		.fogon-track-info {
			padding-top: 0 !important;
			margin-top: 0 !important;
			margin-bottom: 0 !important;
		}

		.fogon-title {
			font-size: 1rem !important;
			line-height: 1.25 !important;
			margin-bottom: 0 !important;
		}

		.fogon-artist {
			font-size: 0.75rem !important;
		}

		.fogon-controls-wrapper {
			margin-top: 0.25rem !important;
			padding-top: 0 !important;
		}

		.fogon-controls-row {
			margin-top: 0.25rem !important;
			gap: 0.75rem !important;
		}

		.fogon-play-btn {
			height: 2.75rem !important;
			width: 2.75rem !important;
		}

		.fogon-play-btn i {
			font-size: 1.75rem !important;
		}

		.fogon-lyrics-container {
			height: 88vh !important;
		}

		.fogon-lyrics-scroll {
			padding-top: 40vh !important;
			padding-bottom: 40vh !important;
			padding-left: 1rem !important;
			padding-right: 1rem !important;
		}

		.fogon-lyrics-scroll > div {
			margin-top: 0.75rem !important;
			font-size: 1.125rem !important;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.fogon-enter-active,
		.fogon-leave-active,
		.fogon-track-enter-active,
		.fogon-track-leave-active,
		.fogon-cover-enter-active,
		.fogon-cover-leave-active,
		.fogon-lyrics-enter-active,
		.fogon-lyrics-leave-active,
		.fogon-lyrics-mobile,
		.fogon-radio-scroll {
			transition: none !important;
			animation: none !important;
			transform: none !important;
			filter: none !important;
		}
	}
</style>
