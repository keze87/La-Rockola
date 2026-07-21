<script setup lang="ts">
	import { computed, watch } from 'vue';
	import { useLyrics } from '../composables/useLyrics';
	import { usePlayer } from '../composables/usePlayer';
	import { useSliderFactory } from '../composables/useSliderFactory';
	import DragSlider from './ui/DragSlider.vue';

	const player = usePlayer();
	const {
		currentTrackPath,
		djCarpinchoEnabled,
		djNextTrack,
		duration,
		haptic,
		ignoreServerTimeUntil,
		isDraggingSeek,
		isFogonMode,
		isPlaying,
		listenLocally,
		localPlayerRef,
		localTimePos,
		pauseAfterPath,
		sendCmd,
		serverMuted,
		showFogonVolume,
		togglePauseAfterCurrent,
		volIcon,
		volume,
		setVolume,
	} = player;

	const { createSlider } = useSliderFactory();

	// 1. Seek Slider
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
			ignoreServerTimeUntil.value = Date.now() + 2000;

			if (listenLocally.value && localPlayerRef.value) {
				localPlayerRef.value.currentTime = val;
				player._sendLocalPlayerUpdate?.({ time_pos: val });
			} else {
				sendCmd('seek_absolute', { amount: val });
			}
		}
	);

	const formattedTimePos = computed(() => formatTime(dragTimePos.value));
	const formattedDuration = computed(() => formatTime(duration.value));

	function handleVolumeUpdate(val: number) {
		volume.value = Math.round(val);
		if (serverMuted.value && volume.value > 0) {
			sendCmd('set_mute', { state: false });
		}
	}

	// Pass the global player instance to our lyrics composable to sync localTimePos
	const { currentLyricLine, loadLyrics } = useLyrics(player);

	// --- Computed Properties for Template Cleanliness ---
	const currentCoverUrl = computed(() => {
		if (currentTrackPath.value && !currentTrackPath.value.startsWith('http')) {
			return '/cover?path=' + encodeURIComponent(currentTrackPath.value);
		}

		if (
			!currentTrackPath.value &&
			djCarpinchoEnabled.value &&
			djNextTrack.value &&
			djNextTrack.value.path &&
			!djNextTrack.value.path.startsWith('http')
		) {
			return '/cover?path=' + encodeURIComponent(djNextTrack.value.path);
		}

		return null;
	});

	const fogonBgStyle = computed(() =>
		currentCoverUrl.value ? { backgroundImage: `url('${currentCoverUrl.value}')` } : { backgroundColor: '#1f1a17' }
	);

	const currentTrackInfo = computed(() => {
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

	// Timer Button Logic
	const isTimerActive = computed(() => pauseAfterPath.value === currentTrackPath.value && currentTrackPath.value);
	const timerClass = computed(() => [
		'p-2 transition active:scale-90 z-20',
		isTimerActive.value
			? 'text-carpincho-warning drop-shadow-[0_0_8px_rgba(233,196,106,0.8)]'
			: 'text-white hover:text-carpincho-warning',
	]);
	const timerTitle = computed(() => (isTimerActive.value ? 'Cancelar pausa al terminar' : 'Frenar tras este tema'));

	watch(currentTrackPath, (newPath) => {
		loadLyrics(newPath); // Fetch and parse lyrics on track change
	});

	function formatTime(sec: number) {
		if (!sec || isNaN(sec)) return '0:00';

		const m = Math.floor(sec / 60);
		const s = Math.floor(sec % 60)
			.toString()
			.padStart(2, '0');
		return `${m}:${s}`;
	}

	// --- Action Handlers ---
	function closeFogon() {
		isFogonMode.value = false;
		haptic();
	}

	function toggleVolumePopup() {
		showFogonVolume.value = !showFogonVolume.value;
		haptic();
	}

	function togglePlay() {
		sendCmd('pause');
		haptic(true);
	}

	function skipPrev() {
		sendCmd('prev');
		haptic();
	}

	function skipNext() {
		sendCmd('skip');
		haptic();
	}

	function toggleMute() {
		sendCmd('set_mute', { state: !serverMuted.value });
		haptic();
	}

	function handleTimerToggle() {
		togglePauseAfterCurrent();
		haptic();
	}
</script>

<template>
	<transition name="fogon">
		<div
			v-if="isFogonMode"
			class="fixed inset-0 z-[10000] flex flex-col items-center justify-center bg-black bg-cover bg-center p-6 text-white"
			:style="fogonBgStyle"
		>
			<!-- Background Overlay -->
			<div class="pointer-events-none absolute inset-0 bg-black/80 backdrop-blur-xl" />

			<!-- Volume Popup Overlay Layer (Moved outside controls for predictable stacking) -->
			<div v-if="showFogonVolume" class="fixed inset-0 z-10" @click="showFogonVolume = false" />

			<div class="relative z-20 flex w-full max-w-md flex-col items-center text-center">
				<button
					aria-label="Cerrar vista de fogón"
					class="absolute -top-16 right-0 p-2 text-gray-400 transition hover:text-white"
					@click="closeFogon"
				>
					<i class="material-icons !text-4xl">keyboard_arrow_down</i>
				</button>

				<!-- Album Art -->
				<div
					class="bg-carpincho-bg mb-8 flex h-64 w-64 items-center justify-center overflow-hidden rounded-2xl shadow-[0_10px_50px_rgba(0,0,0,0.8)] md:h-80 md:w-80"
				>
					<img
						v-if="currentCoverUrl"
						:src="currentCoverUrl"
						alt="Portada del álbum"
						draggable="false"
						loading="eager"
						class="h-full w-full object-cover"
					/>
					<i v-else class="material-icons text-carpincho-warning !text-[8rem]">album</i>
				</div>

				<!-- Track Info -->
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

				<!-- Custom Seek Bar -->
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

				<!-- Controls -->
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

					<!-- Timer / Pause After Toggle -->
					<button :class="timerClass" :title="timerTitle" :aria-label="timerTitle" @click="handleTimerToggle">
						<i class="material-icons !text-3xl">timer</i>
					</button>
				</div>

				<!-- Custom Volume Bar -->
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
						@commit="setVolume"
					/>
					<i class="material-icons text-sm" aria-hidden="true">volume_up</i>
				</div>

				<!-- Lyrics -->
				<div class="mt-2 flex h-[6rem] w-full items-center justify-center overflow-hidden px-8">
					<transition name="lyric" mode="out-in">
						<p
							v-if="currentLyricLine"
							:key="currentLyricLine"
							class="text-carpincho-secondary text-center text-xl font-bold italic md:text-2xl"
						>
							{{ currentLyricLine }}
						</p>
					</transition>
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
