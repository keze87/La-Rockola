<script setup lang="ts">
	import { computed, onUnmounted, ref, watch } from 'vue';
	import { useLyrics, type LyricSyllable } from '../composables/useLyrics';
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
	const { currentLyricLine, activeLyricLines, loadLyrics } = useLyrics(player);

	// Estilo para cada sílaba en el modo karaoke según el momento de la canción
	function getSyllableClass(syl: LyricSyllable): string {
		const pos = localTimePos.value;
		if (pos >= syl.end) {
			// Ya sonó esta sílaba: la dejamos bien visible y marcada
			return 'text-carpincho-warning font-bold drop-shadow-sm transition-colors duration-150 inline';
		} else if (pos >= syl.start && pos < syl.end) {
			// Está sonando justo ahora: le metemos brillo y escala
			return 'text-carpincho-warning font-extrabold scale-105 drop-shadow-[0_0_8px_rgba(233,196,106,0.9)] underline decoration-carpincho-warning/40 transition-all duration-100 inline-block';
		}
		// Todavía no llegó su turno: atenuada para que se pueda leer pero sin robar cámara
		return 'text-gray-400/60 font-medium transition-colors duration-150 inline';
	}

	// --- Propiedades computadas para simplificar el template ---
	const coverSource = computed(() => {
		if (currentTrackPath.value) return currentTrackPath.value;
		if (djCarpinchoEnabled.value && djNextTrack.value?.path) return djNextTrack.value.path;
		return null;
	});

	const { coverUrl: currentCoverUrl } = useCover(coverSource, { size: null });

	const fogonBgStyle = computed(() =>
		currentCoverUrl.value ? { backgroundImage: `url('${currentCoverUrl.value}')` } : { backgroundColor: '#1f1a17' }
	);

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
			class="fixed inset-0 z-[10000] flex flex-col items-center justify-center bg-black bg-cover bg-center p-6 text-white"
			:class="{ 'cursor-none [&_*]:cursor-none': isCursorInactive }"
			:style="fogonBgStyle"
		>
			<!-- Capa de fondo oscurecida -->
			<div class="pointer-events-none absolute inset-0 bg-black/80 backdrop-blur-xl" />

			<!-- Capa para cerrar el popup de volumen al tocar afuera -->
			<div v-if="showFogonVolume" class="fixed inset-0 z-10" @click="showFogonVolume = false" />

			<div class="relative z-20 flex w-full max-w-md flex-col items-center text-center">
				<button
					aria-label="Cerrar vista de fogón"
					class="absolute -top-16 right-0 p-2 text-gray-400 transition hover:text-white"
					@click="closeFogon"
				>
					<i class="material-icons !text-4xl">keyboard_arrow_down</i>
				</button>

				<!-- Tapa del disco -->
				<div
					class="bg-carpincho-bg mb-8 flex h-64 w-64 items-center justify-center overflow-hidden rounded-2xl shadow-[0_10px_50px_rgba(0,0,0,0.8)] md:h-80 md:w-80"
				>
					<FavoritableCover
						v-if="coverSource"
						:track="coverSource"
						size="h-full w-full"
						rounded="rounded-2xl"
						:size-px="null"
						:unload-when-hidden="false"
						button-size="h-10 w-10 md:h-12 md:w-12"
						button-icon-size="!text-xl md:!text-2xl"
					/>
					<i v-else class="material-icons text-carpincho-warning !text-[8rem]">album</i>
				</div>

				<!-- Info del tema -->
				<h1 class="mb-2 w-full truncate px-4 text-3xl font-bold">
					<span
						v-if="currentTrackInfo.isComing"
						class="text-carpincho-warning mb-2 block animate-pulse text-sm tracking-widest uppercase"
					>
						🦦 Se viene...
					</span>
					{{ currentTrackInfo.title }}
				</h1>
				<h2 class="text-carpincho-secondary w-full truncate px-4 text-xl">
					{{ currentTrackInfo.artist }}
				</h2>

				<!-- Barra de progreso personalizada -->
				<div
					v-show="currentTrackPath"
					class="text-carpincho-secondary mt-6 flex w-full items-center gap-4 px-6 text-xs font-medium select-none"
				>
					<span class="w-10 shrink-0 text-right">{{ formattedTimePos }}</span>

					<div
						class="group flex h-10 w-full cursor-pointer touch-none items-center"
						@pointerdown="startSeek"
						@pointermove="moveSeek"
						@pointerup="endSeek"
						@pointercancel="endSeek"
					>
						<div class="pointer-events-none relative h-1.5 w-full rounded-full bg-gray-600/50">
							<div
								class="bg-carpincho-warning absolute top-0 left-0 h-full rounded-full"
								:style="{ width: progressPercent + '%' }"
							/>
							<div
								class="bg-carpincho-warning absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full shadow transition-transform group-active:scale-125"
								:style="{ left: progressPercent + '%', marginLeft: '-8px' }"
							/>
						</div>
					</div>

					<span class="w-10 shrink-0">{{ formattedDuration }}</span>
				</div>

				<!-- Controles de reproducción -->
				<div class="relative z-30 mt-8 flex w-full items-center justify-center gap-4 px-4 sm:gap-6">
					<button
						aria-label="Ajustar volumen"
						class="hover:text-carpincho-warning z-20 p-2 text-white transition active:scale-90"
						@click="toggleVolumePopup"
					>
						<i class="material-icons !text-3xl">{{ volIcon }}</i>
					</button>

					<button
						aria-label="Pista anterior"
						class="hover:text-carpincho-warning z-20 p-1 text-white transition active:scale-90"
						@click="skipPrev"
					>
						<i class="material-icons !text-4xl sm:!text-5xl">skip_previous</i>
					</button>

					<button
						:aria-label="isPlaying ? 'Pausar' : 'Reproducir'"
						class="bg-carpincho-primary hover:bg-carpincho-secondary z-20 flex h-20 w-20 shrink-0 items-center justify-center rounded-full text-white shadow-[0_0_30px_rgba(166,124,82,0.4)] transition active:scale-90"
						@click="togglePlay"
					>
						<i class="material-icons !text-5xl">{{ playPauseIcon }}</i>
					</button>

					<button
						aria-label="Pista siguiente"
						class="hover:text-carpincho-warning z-20 p-1 text-white transition active:scale-90"
						@click="skipNext"
					>
						<i class="material-icons !text-4xl sm:!text-5xl">skip_next</i>
					</button>

					<!-- Botón para frenar después de este tema -->
					<button :class="timerClass" :title="timerTitle" :aria-label="timerTitle" @click="handleTimerToggle">
						<i class="material-icons !text-3xl">timer</i>
					</button>
				</div>

				<!-- Barra de volumen personalizada -->
				<div
					v-if="showFogonVolume"
					class="relative z-30 mt-8 flex w-full items-center gap-4 px-8 text-gray-300 opacity-80 transition select-none hover:opacity-100"
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

				<!-- Letras en tiempo real (soporte palabra por palabra y múltiples líneas simultáneas) -->
				<div
					class="mt-2 flex max-h-[8rem] min-h-[6rem] w-full flex-col items-center justify-center overflow-y-auto px-8"
				>
					<transition-group name="lyric" tag="div" class="flex flex-col items-center justify-center gap-2">
						<template v-if="activeLyricLines.length > 0">
							<div
								v-for="(line, idx) in activeLyricLines"
								:key="idx + '-' + line.time"
								class="text-center text-xl leading-relaxed font-bold whitespace-pre-wrap italic md:text-2xl"
							>
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
									<span class="text-carpincho-secondary">{{ line.text }}</span>
								</template>
							</div>
						</template>
						<p
							v-else-if="currentLyricLine && currentLyricLine.trim() !== ''"
							key="fallback-lyric"
							class="text-carpincho-secondary text-center text-xl font-bold italic md:text-2xl"
						>
							{{ currentLyricLine }}
						</p>
					</transition-group>
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
</style>
