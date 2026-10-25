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
		djCarpinchoEnabled,
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

	// Para el modo vertical en pantallas chicas o celulares: mostramos solo 2 o 3 líneas
	const portraitLyricLines = computed(() => {
		if (!lyrics.value.length) return [];
		if (activeLineIndex.value < 0) {
			// Antes de que arranque el tema: mostramos los primeros 2 versos
			return lyrics.value.slice(0, 2);
		}
		const activeIdx = activeLineIndex.value;
		const activeCount = activeLyricLines.value.length;

		// Si hay varias líneas activas a la vez (dueto/coros), mostramos las activas más la siguiente
		if (activeCount > 1) {
			const start = Math.max(0, activeIdx);
			const end = Math.min(lyrics.value.length, activeIdx + activeCount + 1);
			return lyrics.value.slice(start, end);
		}

		// Si hay una sola línea activa: anterior (si hay), actual y siguiente (2 o 3 líneas)
		const start = Math.max(0, activeIdx - 1);
		const end = Math.min(lyrics.value.length, activeIdx + 2);
		return lyrics.value.slice(start, end);
	});

	function scrollToActiveLine(smooth = true) {
		if (userIsScrolling.value || activeLineIndex.value < 0) return;
		const activeEl = lineRefs.value[activeLineIndex.value];
		if (activeEl && lyricsContainerRef.value) {
			activeEl.scrollIntoView({
				behavior: smooth ? 'smooth' : 'auto',
				block: 'center',
			});
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

	// Estilo para cada sílaba en el modo karaoke según el momento de la canción (estilo Apple Music con resplandor luminoso)
	function getSyllableClass(syl: LyricSyllable): string {
		const pos = localTimePos.value;
		if (pos >= syl.end) {
			// Ya sonó: blanco pleno nítido y brillante
			return 'text-white font-black drop-shadow-sm transition-colors duration-150 inline';
		} else if (pos >= syl.start && pos < syl.end) {
			// Cantándose justo ahora: blanco puro con resplandor luminoso estilo Apple Music (sin subrayado tosco)
			return 'text-white font-black scale-105 drop-shadow-[0_0_16px_rgba(255,255,255,1)] transition-all duration-100 inline-block';
		}
		// Futura: blanca translúcida para lectura anticipada tipo Apple Music
		return 'text-white/30 font-bold transition-colors duration-150 inline';
	}

	// --- Propiedades computadas para simplificar el template ---
	const coverSource = computed(() => {
		if (currentTrackPath.value) return currentTrackPath.value;
		if (djCarpinchoEnabled.value && djNextTrack.value?.path) return djNextTrack.value.path;
		return null;
	});

	const { coverUrl: currentCoverUrl } = useCover(coverSource, { size: null });

	const currentTrackInfo = computed(() => {
		if (isSynthesizingRadio.value || (isPlayingRadioAnnouncement.value && !currentTrackPath.value)) {
			return {
				title: 'El locutor carpincho se está preparando...',
				artist: 'Carpincho Locutor 🎙️',
				isComing: true,
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

		if (djCarpinchoEnabled.value && djNextTrack.value) {
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
	});
</script>

<template>
	<transition name="fogon">
		<div
			v-if="isFogonMode"
			class="fixed inset-0 z-[10000] flex items-center justify-center overflow-hidden bg-black p-4 text-white sm:p-6 md:p-10"
			:class="{ 'cursor-none [&_*]:cursor-none': isCursorInactive }"
		>
			<!-- Fondo ambiental saturado y desenfocado estilo Apple Music / blyrics -->
			<div
				v-if="currentCoverUrl"
				class="pointer-events-none absolute inset-0 scale-135 bg-cover bg-center opacity-60 blur-[80px] saturate-200 transition-all duration-1000 md:blur-[110px]"
				:style="{ backgroundImage: `url('${currentCoverUrl}')` }"
			/>
			<div
				class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(0,0,0,0.3)_0%,_rgba(0,0,0,0.85)_100%)] backdrop-blur-xl"
			/>

			<!-- Botón flotante para cerrar el fogón (arriba a la derecha) -->
			<button
				aria-label="Cerrar vista de fogón"
				class="absolute top-4 right-4 z-40 p-2 text-gray-400 transition hover:scale-110 hover:text-white active:scale-95 md:top-8 md:right-8"
				@click="closeFogon"
			>
				<i class="material-icons !text-4xl">keyboard_arrow_down</i>
			</button>

			<!-- Capa para cerrar el popup de volumen al tocar afuera -->
			<div v-if="showFogonVolume" class="fixed inset-0 z-30" @click="showFogonVolume = false" />

			<!-- Contenedor principal expandido (estilo Apple Music / blyrics) -->
			<div
				class="relative z-20 flex h-full w-full max-w-7xl items-center justify-center transition-all duration-500"
				:class="[
					hasLyrics
						? 'flex-col justify-center md:flex-row md:items-center md:gap-12 lg:gap-16'
						: 'mx-auto max-w-md flex-col justify-center text-center',
				]"
			>
				<!-- COLUMNA IZQUIERDA: Carátula, info y controles del reproductor -->
				<div
					class="flex w-full shrink-0 flex-col items-center justify-center transition-all duration-500"
					:class="[
						hasLyrics
							? 'text-center md:w-[380px] md:items-start md:text-left lg:w-[440px] xl:w-[480px]'
							: 'max-w-md text-center',
					]"
				>
					<!-- Bloque superior: Carátula e información de la canción -->
					<div class="flex w-full flex-col items-center md:items-start">
						<!-- Tapa del disco con sombra profunda, más grande y con esquinas redondeadas modernas -->
						<div
							class="bg-carpincho-bg flex shrink-0 items-center justify-center overflow-hidden rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.85)] transition-all duration-500 md:rounded-3xl"
							:class="[
								hasLyrics
									? 'mb-3 aspect-square h-48 w-48 sm:h-56 sm:w-56 md:mb-6 md:h-88 md:max-h-none md:w-88 lg:h-[400px] lg:w-[400px] xl:h-[440px] xl:w-[440px]'
									: 'mb-8 h-64 w-64 md:h-80 md:w-80',
							]"
						>
							<FavoritableCover
								v-if="coverSource"
								:track="coverSource"
								size="h-full w-full"
								rounded="rounded-2xl md:rounded-3xl"
								:size-px="null"
								:unload-when-hidden="false"
								button-size="h-10 w-10 md:h-12 md:w-12"
								button-icon-size="!text-xl md:!text-2xl"
							/>
							<i v-else class="material-icons text-carpincho-warning !text-[8rem]">album</i>
						</div>

						<!-- Info del tema -->
						<h1
							class="mb-0.5 w-full truncate font-black transition-all"
							:class="hasLyrics ? 'text-xl sm:text-2xl md:text-3xl xl:text-4xl' : 'text-3xl'"
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
							class="text-carpincho-secondary w-full truncate font-medium"
							:class="hasLyrics ? 'text-sm sm:text-base md:text-lg lg:text-xl' : 'text-xl'"
						>
							{{ currentTrackInfo.artist }}
						</h2>
					</div>

					<!-- Bloque medio: Barra de progreso y controles de reproducción -->
					<div class="mt-2.5 flex w-full flex-col items-center sm:mt-3 md:mt-4 md:items-start">
						<!-- Barra de progreso personalizada -->
						<div
							v-show="currentTrackPath"
							class="text-carpincho-secondary flex w-full max-w-xs items-center gap-3 text-xs font-medium select-none sm:max-w-sm md:max-w-none"
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

						<!-- Controles de reproducción -->
						<div
							class="relative z-30 mt-1 flex w-full items-center gap-4 sm:mt-2 sm:gap-6 md:mt-4"
							:class="hasLyrics ? 'justify-center md:justify-start' : 'justify-center'"
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
								class="bg-carpincho-primary hover:bg-carpincho-secondary z-20 flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-white shadow-[0_0_30px_rgba(166,124,82,0.4)] transition active:scale-90 sm:h-16 sm:w-16 md:h-20 md:w-20"
								@click="togglePlay"
							>
								<i class="material-icons !text-3xl sm:!text-4xl md:!text-5xl">{{ playPauseIcon }}</i>
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
							class="relative z-40 mt-3 flex w-full items-center gap-4 px-2 text-gray-300 opacity-90 transition select-none hover:opacity-100"
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

					<!-- MODO VERTICAL (Mobile / Portrait): Muestra únicamente 2 o 3 líneas centradas con máscara y desenfoque -->
					<div
						v-if="hasLyrics"
						class="lyrics-mask-vertical relative mt-3 flex h-24 w-full max-w-sm flex-col items-center justify-center overflow-hidden px-2 text-center sm:mt-4 sm:h-28 md:hidden"
					>
						<div class="flex flex-col items-center justify-center space-y-1.5 select-none sm:space-y-2">
							<div
								v-for="(line, idx) in portraitLyricLines"
								:key="'portrait-' + idx + '-' + line.time"
								class="cursor-pointer whitespace-pre-wrap transition-all duration-300"
								:class="[
									isLineActive(line)
										? 'scale-105 text-base leading-snug font-black text-white blur-none drop-shadow-[0_0_16px_rgba(255,255,255,0.7)] sm:text-lg'
										: 'text-xs font-semibold text-white/35 blur-[0.8px] hover:text-white/60 hover:blur-none sm:text-sm',
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
										<span
											class="font-black text-white drop-shadow-[0_0_16px_rgba(255,255,255,0.8)]"
										>
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

				<!-- COLUMNA DERECHA: Letras completas en flujo vertical estilo Apple Music / blyrics-am-theme (solo en escritorio) -->
				<div
					v-if="hasLyrics"
					class="lyrics-mask relative hidden h-[78vh] w-full flex-1 flex-col justify-center overflow-hidden md:flex lg:h-[84vh]"
				>
					<div
						ref="lyricsContainerRef"
						class="no-scrollbar h-full w-full space-y-7 overflow-y-auto scroll-smooth px-6 py-[38vh] select-none md:space-y-8 md:px-12"
						@scroll="handleUserScroll"
						@wheel="handleUserScroll"
						@touchmove="handleUserScroll"
					>
						<div
							v-for="(line, idx) in lyrics"
							:key="idx + '-' + line.time"
							:ref="(el) => (lineRefs[idx] = el as HTMLElement)"
							class="cursor-pointer text-left whitespace-pre-wrap transition-all duration-400"
							:class="[
								isLineActive(line)
									? 'origin-left scale-[1.02] text-3xl leading-tight font-black tracking-tight text-white blur-none drop-shadow-[0_2px_24px_rgba(0,0,0,0.9)] sm:text-4xl lg:text-5xl'
									: 'text-xl leading-snug font-extrabold tracking-tight text-white/30 blur-[1.5px] hover:text-white/70 hover:blur-none sm:text-2xl lg:text-3xl',
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
									<span class="font-black text-white drop-shadow-[0_0_20px_rgba(255,255,255,0.8)]">
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

				<!-- En caso de que no haya letras cargadas -->
				<div v-else class="mt-4 flex h-[4rem] w-full items-center justify-center text-sm text-gray-500 italic">
					<span>Sin letras sincronizadas para este tema</span>
				</div>
			</div>
		</div>
	</transition>
</template>

<style scoped>
	.fogon-enter-active,
	.fogon-leave-active {
		transition:
			opacity 0.5s,
			backdrop-filter 0.5s;
	}

	.fogon-enter-from,
	.fogon-leave-to {
		opacity: 0;
		backdrop-filter: blur(0);
	}

	/* Ocultar barra de scroll en el contenedor de letras */
	.no-scrollbar::-webkit-scrollbar {
		display: none;
	}
	.no-scrollbar {
		-ms-overflow-style: none;
		scrollbar-width: none;
	}

	/* Máscara de desvanecimiento suave superior e inferior estilo Apple Music */
	.lyrics-mask {
		mask-image: linear-gradient(to bottom, transparent 0%, black 14%, black 86%, transparent 100%);
		-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 14%, black 86%, transparent 100%);
	}

	/* Máscara de desvanecimiento para el modo vertical (2 o 3 líneas) */
	.lyrics-mask-vertical {
		mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%);
		-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%);
	}
</style>
