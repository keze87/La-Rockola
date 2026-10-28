<script setup lang="ts">
	import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
	import { useLyrics, type LyricSyllable, type LyricLine } from '../composables/useLyrics';
	import { useCover } from '../composables/useCover';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import { useSliderFactory } from '../composables/useSliderFactory';
	import DragSlider from './ui/DragSlider.vue';
	import FavoritableCover from './ui/FavoritableCover.vue';

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
		if (userIsScrolling.value || activeLineIndex.value < 0) return;
		const activeEl = lineRefs.value[activeLineIndex.value];
		const container = lyricsContainerRef.value;
		if (activeEl && container) {
			const targetTop = Math.max(0, activeEl.offsetTop - container.clientHeight / 2 + activeEl.clientHeight / 2);
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

	// Lógica del botón de temporizador / pausa programada
	const isTimerActive = computed(() => pauseAfterPath.value === currentTrackPath.value && currentTrackPath.value);
	const timerClass = computed(() => [
		'p-2 transition active:scale-90 z-20',
		isTimerActive.value
			? 'text-carpincho-warning drop-shadow-[0_0_8px_rgba(233,196,106,0.8)]'
			: 'text-white hover:text-carpincho-warning',
	]);
	const timerTitle = computed(() => (isTimerActive.value ? 'Cancelar pausa al terminar' : 'Frenar tras este tema'));

	watch(currentTrackPath, (newPath) => {
		loadLyrics(newPath); // Traer y parsear letras al cambiar de tema
	});

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

	watch(
		isFogonMode,
		(active) => {
			if (active) {
				window.addEventListener('mousemove', handleMouseMove);
				resetCursorTimer();
			} else {
				window.removeEventListener('mousemove', handleMouseMove);
				if (cursorTimer) {
					clearTimeout(cursorTimer);
					cursorTimer = null;
				}
				isCursorInactive.value = false;
			}
		},
		{ immediate: true }
	);

	onUnmounted(() => {
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
			class="fogon-container bg-carpincho-panel text-carpincho-text fixed inset-0 z-[10000] flex items-center justify-center overflow-hidden overscroll-contain p-4 sm:p-6 md:p-10"
			:class="{ 'cursor-none [&_*]:cursor-none': isCursorInactive }"
		>
			<!-- Fondo ambiental cálido y liviano cohesivo con la estética carpincha -->
			<div
				v-if="currentCoverUrl"
				class="pointer-events-none absolute inset-0 scale-110 bg-cover bg-center opacity-25 blur-2xl saturate-150 transition-opacity duration-700"
				:style="{ backgroundImage: `url('${currentCoverUrl}')` }"
			/>
			<div
				class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(43,38,34,0.35)_0%,_rgba(31,26,23,0.92)_100%)]"
			/>

			<!-- Botón flotante para cerrar el fogón (arriba a la derecha) -->
			<button
				aria-label="Cerrar vista de fogón"
				class="text-carpincho-text/70 hover:text-carpincho-warning absolute top-4 right-4 z-40 p-2 transition hover:scale-110 active:scale-95 md:top-8 md:right-8"
				@click="closeFogon"
			>
				<i class="material-icons !text-4xl">keyboard_arrow_down</i>
			</button>

			<!-- Capa para cerrar el popup de volumen al tocar afuera -->
			<div v-if="showFogonVolume" class="fixed inset-0 z-30" @click="showFogonVolume = false" />

			<!-- Contenedor principal expandido (estilo Apple Music / blyrics) -->
			<div
				class="fogon-main-layout relative z-20 flex h-full w-full max-w-7xl items-center justify-center transition-all duration-500"
				:class="[
					hasLyrics
						? 'flex-col justify-center md:flex-row md:items-center md:gap-12 lg:gap-16'
						: 'mx-auto flex-col justify-center text-center',
				]"
			>
				<!-- COLUMNA IZQUIERDA: Carátula, info y controles del reproductor (centrado simétrico impecable) -->
				<div
					class="fogon-player-column flex w-full shrink-0 flex-col items-center justify-center text-center transition-all duration-500"
					:class="[
						hasLyrics
							? 'h-full py-2 sm:py-4 md:h-auto md:w-88 md:py-0 lg:w-[380px] xl:w-[420px]'
							: 'max-w-md',
					]"
				>
					<!-- Bloque superior: Carátula del álbum bajada hacia el título central en móviles -->
					<div
						class="flex w-full flex-col items-center text-center"
						:class="[
							hasLyrics
								? 'min-h-0 flex-[6] justify-end pb-1 sm:pb-2 md:h-auto md:flex-none md:shrink-0 md:justify-center md:pb-0'
								: 'shrink-0 justify-center',
						]"
					>
						<!-- Tapa del disco con marco carpincho, 90% del ancho en móviles (estrictamente cuadrada) y tamaño balanceado en escritorio -->
						<div
							class="fogon-cover-wrapper bg-carpincho-bg border-carpincho-border/60 flex shrink-0 items-center justify-center overflow-hidden rounded-2xl border shadow-2xl transition-all duration-500 md:rounded-3xl"
							:class="[
								hasLyrics
									? 'aspect-square h-[90vw] max-h-[380px] w-[90vw] max-w-[380px] md:mb-5 md:h-auto md:max-h-none md:w-full md:max-w-none'
									: 'mb-4 aspect-square h-56 w-56 sm:h-64 sm:w-64 md:mb-6 md:h-80 md:w-80 lg:h-88 lg:w-88',
							]"
						>
							<FavoritableCover
								v-if="coverSource"
								:track="coverSource"
								size="h-full w-full"
								rounded="rounded-2xl md:rounded-3xl"
								:size-px="512"
								:unload-when-hidden="false"
								button-size="h-10 w-10 md:h-12 md:w-12"
								button-icon-size="!text-xl md:!text-2xl"
								:show-favorite="!isSynthesizingRadio && !isPlayingRadioAnnouncement"
							/>
							<i v-else class="material-icons text-carpincho-warning !text-[8rem]">album</i>
						</div>
					</div>

					<!-- Bloque central: Información del tema clavado en el centro vertical de la pantalla en móviles -->
					<div
						class="fogon-track-info flex w-full shrink-0 flex-col items-center text-center"
						:class="[hasLyrics ? 'my-2 sm:my-3 md:my-0' : '']"
					>
						<!-- Info del tema -->
						<h1
							class="fogon-title mb-1 w-full truncate text-center font-black transition-all"
							:class="
								hasLyrics
									? 'text-xl sm:text-2xl md:text-3xl xl:text-4xl'
									: 'text-2xl sm:text-3xl md:text-4xl'
							"
						>
							<span
								v-if="currentTrackInfo.isComing"
								class="text-carpincho-warning mb-1 block animate-pulse text-xs tracking-widest uppercase"
							>
								🦦 Se viene...
							</span>
							{{ currentTrackInfo.title }}
						</h1>
						<h2
							class="fogon-artist text-carpincho-secondary w-full truncate text-center font-medium"
							:class="
								hasLyrics
									? 'text-sm sm:text-base md:text-lg lg:text-xl'
									: 'text-base sm:text-lg md:text-xl'
							"
						>
							{{ currentTrackInfo.artist }}
						</h2>
					</div>

					<!-- Bloque inferior: Barra de progreso, controles y letras móviles acercados hacia el centro -->
					<div
						class="flex w-full flex-col items-center text-center"
						:class="[
							hasLyrics
								? 'min-h-0 flex-[4] justify-start md:h-auto md:flex-none md:shrink-0 md:justify-center'
								: 'mt-4 shrink-0 sm:mt-5 md:mt-4',
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
								class="text-carpincho-secondary flex w-[90vw] max-w-[380px] items-center gap-3 text-xs font-medium select-none md:w-full md:max-w-none"
							>
								<span class="w-10 shrink-0 text-right">{{ formattedTimePos }}</span>

								<div
									class="group flex h-10 w-full cursor-pointer touch-none items-center"
									@pointerdown="startSeek"
									@pointermove="moveSeek"
									@pointerup="endSeek"
									@pointercancel="endSeek"
								>
									<div class="pointer-events-none relative h-1.5 w-full rounded-full bg-white/15">
										<div
											class="bg-carpincho-warning absolute top-0 left-0 h-full rounded-full"
											:style="{ width: progressPercent + '%' }"
										/>
										<div
											class="bg-carpincho-warning absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full shadow transition-transform group-active:scale-125"
											:style="{ left: progressPercent + '%', marginLeft: '-7px' }"
										/>
									</div>
								</div>

								<span class="w-10 shrink-0">{{ formattedDuration }}</span>
							</div>

							<!-- Controles de reproducción centrados con más aire -->
							<div
								class="fogon-controls-row relative z-30 mt-2 flex w-full items-center justify-center gap-5 sm:mt-3 sm:gap-7 md:mt-4"
							>
								<button
									aria-label="Ajustar volumen"
									class="hover:text-carpincho-warning z-20 p-2 text-white transition active:scale-90"
									@click="toggleVolumePopup"
								>
									<i class="material-icons !text-2xl sm:!text-3xl">{{ volIcon }}</i>
								</button>

								<button
									aria-label="Pista anterior"
									class="hover:text-carpincho-warning z-20 p-1 text-white transition active:scale-90"
									@click="skipPrev"
								>
									<i class="material-icons !text-3xl sm:!text-4xl">skip_previous</i>
								</button>

								<button
									:aria-label="isPlaying ? 'Pausar' : 'Reproducir'"
									class="fogon-play-btn bg-carpincho-primary hover:bg-carpincho-secondary z-20 flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-white shadow-[0_0_30px_rgba(166,124,82,0.4)] transition active:scale-90 sm:h-16 sm:w-16 md:h-20 md:w-20"
									@click="togglePlay"
								>
									<i class="material-icons !text-3xl sm:!text-4xl md:!text-5xl">
										{{ playPauseIcon }}
									</i>
								</button>

								<button
									aria-label="Pista siguiente"
									class="hover:text-carpincho-warning z-20 p-1 text-white transition active:scale-90"
									@click="skipNext"
								>
									<i class="material-icons !text-3xl sm:!text-4xl">skip_next</i>
								</button>

								<!-- Botón para frenar después de este tema -->
								<button
									:class="timerClass"
									:title="timerTitle"
									:aria-label="timerTitle"
									@click="handleTimerToggle"
								>
									<i class="material-icons !text-2xl sm:!text-3xl">timer</i>
								</button>
							</div>

							<!-- Barra de volumen desplegable -->
							<div
								v-if="showFogonVolume"
								class="bg-carpincho-bg/95 border-carpincho-border text-carpincho-text relative z-40 mt-3 flex w-full max-w-xs items-center gap-4 rounded-full border px-4 py-1.5 opacity-95 shadow-lg transition select-none hover:opacity-100 sm:max-w-sm md:max-w-none"
							>
								<button aria-label="Silenciar" @click="toggleMute">
									<i class="material-icons cursor-pointer text-sm hover:text-white">{{ muteIcon }}</i>
								</button>

								<DragSlider
									:model-value="volume"
									:max="110"
									@update:model-value="handleVolumeUpdate"
									@commit="handleVolumeCommit"
								/>
								<i class="material-icons text-sm" aria-hidden="true">volume_up</i>
							</div>
						</div>

						<!-- MODO VERTICAL (Mobile / Portrait): Ocupa el 100% del ancho y se posiciona cercano a los controles -->
						<div
							v-if="hasLyrics"
							class="lyrics-mask-vertical relative mt-2 flex min-h-0 w-full flex-1 flex-col items-center justify-start overflow-hidden px-4 pt-1 text-center md:hidden"
						>
							<div class="flex flex-col items-center justify-start space-y-2 select-none sm:space-y-3">
								<div
									v-for="(line, idx) in portraitLyricLines"
									:key="'portrait-' + idx + '-' + line.time"
									class="cursor-pointer whitespace-pre-wrap transition-[color,opacity,transform] duration-300"
									:class="[
										isLineActive(line)
											? 'scale-105 text-lg leading-relaxed font-black text-white sm:text-xl'
											: 'text-carpincho-text/35 hover:text-carpincho-text/75 text-xs font-semibold sm:text-sm',
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
									? 'origin-left scale-[1.02] text-3xl leading-tight font-black tracking-tight text-white sm:text-4xl lg:text-5xl'
									: 'text-carpincho-text/35 hover:text-carpincho-text/75 text-xl leading-snug font-extrabold tracking-tight sm:text-2xl lg:text-3xl',
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

	/* Soporte adaptativo para dispositivos móviles en apaisado / pantallas de altura reducida */
	@media (max-height: 550px) {
		.fogon-container {
			padding: 0.5rem 1.25rem !important;
		}

		.fogon-main-layout {
			gap: 1.5rem !important;
		}

		.fogon-player-column {
			width: 44% !important;
			max-width: 320px !important;
			height: 100% !important;
			justify-content: center !important;
		}

		.fogon-cover-wrapper {
			height: 38vh !important;
			width: 38vh !important;
			max-height: 38vh !important;
			max-width: 38vh !important;
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
</style>
