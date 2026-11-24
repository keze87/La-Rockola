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
	let swipeThresholdHapticFired = false;

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
		swipeThresholdHapticFired = false;
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
		swipeThresholdHapticFired = false;
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
			if (!swipeThresholdHapticFired && Math.abs(swipeOffsetX.value) >= SWIPE_X_THRESHOLD) {
				swipeThresholdHapticFired = true;
				haptic('tick');
			}
			if (e.cancelable) e.preventDefault();
		} else if (swipeAxis === 'vertical') {
			swipeOffsetY.value = Math.min(0, Math.max(-80, dy));
			swipeOffsetX.value = 0;
			if (!swipeThresholdHapticFired && swipeOffsetY.value <= -SWIPE_UP_THRESHOLD) {
				swipeThresholdHapticFired = true;
				haptic('tick');
			}
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
		class="floating-player flex h-[var(--floating-player-h)] items-center justify-between rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--glass-bg-strong)] px-3 py-2 [box-shadow:var(--glass-highlight),0_10px_30px_rgba(0,0,0,0.45)] [backdrop-filter:var(--glass-blur)] transition-transform duration-200 [-webkit-backdrop-filter:var(--glass-blur)]"
		:style="swipeStyle"
		@touchstart.passive="onTouchStart"
		@touchmove="onTouchMove"
		@touchend="onTouchEnd"
		@touchcancel="resetSwipe"
	>
		<button
			type="button"
			aria-label="Abrir fila de reproducción"
			class="flex min-w-0 grow cursor-pointer items-center overflow-hidden text-left"
			@click="goToQueue"
		>
			<div
				class="relative mr-3 flex h-[44px] w-[44px] shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-sm)] border border-[var(--hairline)] bg-[var(--bg-input)]"
			>
				<img
					v-if="coverUrl"
					:src="coverUrl"
					alt=""
					class="absolute h-full w-full object-cover"
					@error="onCoverError"
				/>
				<i
					v-else-if="djBaraEnabled && queueState.length === 0"
					class="material-icons animate-pulse !text-[24px] text-[var(--accent-primary)]"
					aria-hidden="true"
				>
					auto_awesome
				</i>
				<i v-else class="material-icons !text-[24px] text-[var(--accent-primary)]" aria-hidden="true">album</i>
			</div>

			<div class="flex min-w-0 grow flex-col justify-center overflow-hidden">
				<div class="text-[10px] font-semibold tracking-[0.06em] text-[var(--accent-primary)]/90 uppercase">
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
				<div class="truncate text-[14px] font-semibold text-[var(--text-primary)]">
					{{ upNextTitle }}
				</div>
			</div>
		</button>

		<div class="ml-2 flex shrink-0 items-center gap-2">
			<button
				type="button"
				:class="[
					'touch-target tap-feedback hidden h-9 w-9 items-center justify-center rounded-full transition-opacity sm:flex',
					pauseAfterPath === currentTrackPath && currentTrackPath
						? 'bg-[var(--accent-primary-soft)] text-[var(--accent-primary)] opacity-100'
						: 'bg-[rgba(255,236,210,0.08)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface-active)] hover:text-[var(--text-primary)]',
				]"
				:aria-label="
					pauseAfterPath === currentTrackPath && currentTrackPath
						? 'Cancelar pausa al terminar'
						: 'Frenar tras este tema'
				"
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
				<i class="material-icons !text-[20px] text-current" aria-hidden="true">timer</i>
			</button>
			<button
				type="button"
				:aria-label="isPlaying ? 'Pausar' : 'Reproducir'"
				class="touch-target tap-feedback flex h-11 w-11 items-center justify-center rounded-full bg-[var(--accent-primary)] text-[#120e0b] shadow-md hover:brightness-110"
				@click="
					pause();
					haptic(true);
				"
			>
				<i class="material-icons !text-[28px]" aria-hidden="true">{{ isPlaying ? 'pause' : 'play_arrow' }}</i>
			</button>
			<button
				type="button"
				aria-label="Siguiente tema"
				class="touch-target tap-feedback flex h-9 w-9 items-center justify-center rounded-full bg-[rgba(255,236,210,0.08)] text-[var(--text-primary)] opacity-[0.78] transition-opacity hover:bg-[var(--bg-surface-active)] hover:opacity-100"
				@click="
					skip();
					haptic();
				"
			>
				<i class="material-icons !text-[22px] text-current" aria-hidden="true">skip_next</i>
			</button>
		</div>
	</section>
</template>
