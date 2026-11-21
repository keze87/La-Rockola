<script setup lang="ts">
	import { computed, ref } from 'vue';
	import { useCover } from '../composables/useCover';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';

	const { skip, prev, pause } = usePlaybackControls();

	const {
		currentTrackPath,
		djBaraEnabled,
		djNextTrack,
		getTrackInfo,
		haptic,
		isFogonMode,
		isPlaying,
		isSynthesizingRadio,
		pauseAfterPath,
		queueState,
		switchTab,
		togglePauseAfterCurrent,
	} = usePlayer();

	const upNextTitle = computed(() => {
		if (isSynthesizingRadio.value) return 'Transmisión de Cabina - Acomodando los micrófonos... 🎙️';

		if (queueState.value.length > 0) {
			const t = getTrackInfo(queueState.value[0]);
			return `${t.display_title} - ${t.display_artist}`;
		}

		if (djBaraEnabled.value && djNextTrack.value) {
			const t = djNextTrack.value;
			return `${t.display_title || t.title} - ${t.display_artist || t.artist}`;
		}

		if (djBaraEnabled.value) return 'DJ Bara eligiendo...';

		return currentTrackPath.value ? 'Termina este y nos re vimos' : "Agregá algo pa' escuchar";
	});

	const upNextPath = computed(() => {
		if (queueState.value.length > 0) return queueState.value[0];

		if (djBaraEnabled.value && djNextTrack.value) return djNextTrack.value?.path;

		return null;
	});

	const { coverUrl, onCoverError } = useCover(upNextPath, { size: 512 });

	// Gestos táctiles del reproductor flotante: izquierda -> siguiente, derecha -> anterior, arriba -> Modo Fogón
	const SWIPE_X_THRESHOLD = 56;
	const SWIPE_UP_THRESHOLD = 48;
	const AXIS_LOCK_PX = 10;

	const swipeOffsetX = ref(0);
	const swipeOffsetY = ref(0);
	const isSwiping = ref(false);
	let touchStartX = 0;
	let touchStartY = 0;
	let swipeAxis: 'horizontal' | 'vertical' | 'ignored' | null = null;
	let suppressNextClick = false;

	const swipeStyle = computed(() => {
		if (swipeOffsetX.value === 0 && swipeOffsetY.value === 0) return undefined;
		return {
			transform: `translate3d(${Math.round(swipeOffsetX.value)}px, ${Math.round(swipeOffsetY.value)}px, 0)`,
			transition: isSwiping.value ? 'none' : undefined,
		};
	});

	function resetSwipe() {
		swipeOffsetX.value = 0;
		swipeOffsetY.value = 0;
		isSwiping.value = false;
		swipeAxis = null;
	}

	function onTouchStart(e: TouchEvent) {
		const touch = e.touches[0];
		if (!touch) return;
		touchStartX = touch.clientX;
		touchStartY = touch.clientY;
		isSwiping.value = true;
		swipeAxis = null;
		swipeOffsetX.value = 0;
		swipeOffsetY.value = 0;
	}

	function onTouchMove(e: TouchEvent) {
		if (!isSwiping.value) return;
		const touch = e.touches[0];
		if (!touch) return;
		const dx = touch.clientX - touchStartX;
		const dy = touch.clientY - touchStartY;

		if (!swipeAxis && (Math.abs(dx) > AXIS_LOCK_PX || Math.abs(dy) > AXIS_LOCK_PX)) {
			if (Math.abs(dx) >= Math.abs(dy)) {
				swipeAxis = 'horizontal';
			} else if (dy < 0) {
				swipeAxis = 'vertical';
			} else {
				swipeAxis = 'ignored';
			}
		}

		if (swipeAxis === 'horizontal') {
			swipeOffsetX.value = Math.max(-110, Math.min(110, dx));
			swipeOffsetY.value = 0;
			if (e.cancelable) e.preventDefault();
		} else if (swipeAxis === 'vertical') {
			swipeOffsetY.value = Math.min(0, Math.max(-80, dy));
			swipeOffsetX.value = 0;
			if (e.cancelable) e.preventDefault();
		}
	}

	function onTouchEnd() {
		if (!isSwiping.value) return;
		const axis = swipeAxis;
		const dx = swipeOffsetX.value;
		const dy = swipeOffsetY.value;
		resetSwipe();

		if (axis === 'horizontal' && dx <= -SWIPE_X_THRESHOLD) {
			suppressNextClick = true;
			skip();
			haptic();
		} else if (axis === 'horizontal' && dx >= SWIPE_X_THRESHOLD) {
			suppressNextClick = true;
			prev();
			haptic();
		} else if (axis === 'vertical' && dy <= -SWIPE_UP_THRESHOLD) {
			suppressNextClick = true;
			isFogonMode.value = true;
			haptic();
		}
	}

	function goToQueue() {
		if (suppressNextClick) {
			suppressNextClick = false;
			return;
		}
		switchTab('queue');
		haptic();
	}
</script>

<template>
	<section
		class="floating-player from-carpincho-panel border-carpincho-border flex items-center justify-between rounded-xl border bg-gradient-to-br to-[#2a2420] p-3 shadow-[0_4px_15px_rgba(0,0,0,0.5)] transition-transform duration-200"
		:style="swipeStyle"
		@touchstart.passive="onTouchStart"
		@touchmove="onTouchMove"
		@touchend="onTouchEnd"
		@touchcancel="resetSwipe"
	>
		<div class="flex grow cursor-pointer items-center overflow-hidden" @click="goToQueue">
			<div
				class="bg-carpincho-bg relative mr-3 flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg"
			>
				<img
					v-if="coverUrl"
					:src="coverUrl"
					class="absolute h-full w-full object-cover"
					@error="onCoverError"
				/>
				<i
					v-else-if="djBaraEnabled && queueState.length === 0"
					class="material-icons text-carpincho-warning animate-pulse !text-[2rem]"
				>
					auto_awesome
				</i>
				<i v-else class="material-icons text-carpincho-warning !text-[2rem]">album</i>
			</div>

			<div class="flex grow flex-col justify-center overflow-hidden">
				<div class="text-carpincho-primary text-[0.7rem] font-bold tracking-wider uppercase">
					{{
						queueState.length > 0
							? 'Próximo Temazo'
							: djBaraEnabled
								? djNextTrack
									? '🦦 Arranca en unos segundos...'
									: 'Eligiendo...'
								: 'Fin de la fila'
					}}
				</div>
				<div class="text-carpincho-text truncate text-[0.95rem] font-bold">
					{{ upNextTitle }}
				</div>
			</div>
		</div>

		<div class="ml-2 flex shrink-0 items-center gap-3">
			<button
				:class="[
					'hidden h-10 w-10 items-center justify-center rounded-full transition active:scale-90 sm:flex',
					pauseAfterPath === currentTrackPath && currentTrackPath
						? 'text-carpincho-warning'
						: 'text-gray-400 hover:text-white',
				]"
				:title="
					pauseAfterPath === currentTrackPath && currentTrackPath
						? 'Cancelar pausa al terminar'
						: 'Frenar tras este tema'
				"
				@click="
					togglePauseAfterCurrent();
					haptic();
				"
			>
				<i class="material-icons !text-2xl">timer</i>
			</button>
			<button
				:class="[
					'flex h-14 w-14 items-center justify-center rounded-full text-white shadow-lg transition active:scale-90',
					isPlaying ? 'bg-orange-600 hover:bg-orange-500' : 'bg-green-600 hover:bg-green-500',
				]"
				@click="
					pause();
					haptic(true);
				"
			>
				<i class="material-icons !text-4xl">{{ isPlaying ? 'pause' : 'play_arrow' }}</i>
			</button>
			<button
				class="flex h-10 w-10 items-center justify-center rounded-full bg-gray-700 text-white shadow transition hover:bg-gray-600 active:scale-90"
				@click="
					skip();
					haptic();
				"
			>
				<i class="material-icons !text-2xl">skip_next</i>
			</button>
		</div>
	</section>
</template>
