<script setup>
	import { ref, computed } from 'vue';
	import { usePlayer } from '../composables/usePlayer';

	const {
		currentTrackPath,
		djCarpinchoEnabled,
		djNextTrack,
		getTrackInfo,
		haptic,
		isPlaying,
		pauseAfterPath,
		queueState,
		sendCmd,
		switchTab,
		togglePauseAfterCurrent,
	} = usePlayer();

	const brokenNextCover = ref(false);

	const upNextTitle = computed(() => {
		if (queueState.value.length > 0) {
			const t = getTrackInfo(queueState.value[0]);
			return `${t.display_title} - ${t.display_artist}`;
		}

		if (djCarpinchoEnabled.value && djNextTrack.value) {
			const t = djNextTrack.value;
			return `${t.display_title || t.title} - ${t.display_artist || t.artist}`;
		}

		if (djCarpinchoEnabled.value) return 'DJ Carpincho eligiendo...';

		return currentTrackPath.value ? 'Termina este y nos re vimos' : "Agregá algo pa' escuchar";
	});

	const upNextCoverUrl = computed(() => {
		if (brokenNextCover.value) return null;

		if (queueState.value.length > 0 && !queueState.value[0].startsWith('http')) {
			return '/cover?path=' + encodeURIComponent(queueState.value[0]);
		}

		if (djCarpinchoEnabled.value && djNextTrack.value) {
			const p = djNextTrack.value.path;
			if (p && !p.startsWith('http')) return '/cover?path=' + encodeURIComponent(p);
		}

		return null;
	});

	function goToQueue() {
		switchTab('queue');
		haptic();
	}
</script>

<template>
	<section
		class="floating-player from-carpincho-panel border-carpincho-border flex items-center justify-between rounded-xl border bg-gradient-to-br to-[#2a2420] p-3 shadow-[0_4px_15px_rgba(0,0,0,0.5)]"
	>
		<div class="flex grow cursor-pointer items-center overflow-hidden" @click="goToQueue">
			<div
				class="bg-carpincho-bg relative mr-3 flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg"
			>
				<img
					v-if="upNextCoverUrl"
					:src="upNextCoverUrl"
					class="absolute h-full w-full object-cover"
					@error="brokenNextCover = true"
				/>
				<i
					v-else-if="djCarpinchoEnabled && queueState.length === 0"
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
							: djCarpinchoEnabled
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
					sendCmd('pause');
					haptic(true);
				"
			>
				<i class="material-icons !text-4xl">{{ isPlaying ? 'pause' : 'play_arrow' }}</i>
			</button>
			<button
				class="flex h-10 w-10 items-center justify-center rounded-full bg-gray-700 text-white shadow transition hover:bg-gray-600 active:scale-90"
				@click="
					sendCmd('skip');
					haptic();
				"
			>
				<i class="material-icons !text-2xl">skip_next</i>
			</button>
		</div>
	</section>
</template>
