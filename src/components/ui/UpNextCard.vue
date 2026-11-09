<script setup lang="ts">
	import { computed } from 'vue';
	import { useCover } from '../../composables/useCover';
	import { usePlayer } from '../../composables/usePlayer';

	const emit = defineEmits<{
		(e: 'select'): void;
	}>();

	const player = usePlayer();
	const { currentTrackPath, djBaraEnabled, djNextTrack, isSynthesizingRadio, queueState } = player;

	const upNextPath = computed(() => {
		if (queueState.value.length > 0) return queueState.value[0];
		if (djBaraEnabled.value && djNextTrack.value) return djNextTrack.value.path;
		return null;
	});

	const { coverUrl: upNextCoverUrl, onCoverError: onUpNextCoverError } = useCover(upNextPath, { size: 256 });

	const upNextBadge = computed(() => {
		if (queueState.value.length > 0) return 'Próximo Temazo';
		if (djBaraEnabled.value) {
			return djNextTrack.value ? '🦦 Arranca en unos segundos...' : 'Eligiendo...';
		}
		return 'Fin de la fila';
	});

	const upNextTitle = computed(() => {
		if (isSynthesizingRadio.value) return 'Transmisión de Cabina - Acomodando los micrófonos... 🎙️';

		if (queueState.value.length > 0) {
			const info = player.getTrackInfo(queueState.value[0]);
			return `${info.display_title} - ${info.display_artist}`;
		}

		if (djBaraEnabled.value && djNextTrack.value) {
			const t = djNextTrack.value;
			const title = t.display_title || t.title;
			const artist = t.display_artist || t.artist;
			return `${title} - ${artist}`;
		}

		if (djBaraEnabled.value) return 'DJ Bara eligiendo...';

		return currentTrackPath.value ? 'Termina este y nos re vimos' : "Agregá algo pa' escuchar";
	});
</script>

<template>
	<button
		type="button"
		aria-label="Ver cola de reproducción"
		class="fogon-next-song border-carpincho-border/60 from-carpincho-panel/90 hover:border-carpincho-warning/40 mt-4 hidden w-full cursor-pointer items-center justify-between rounded-xl border bg-gradient-to-br to-[#2a2420]/90 p-3 text-left shadow-lg backdrop-blur-sm transition select-none hover:scale-[1.01] active:scale-[0.99] md:flex"
		@click="emit('select')"
	>
		<div class="flex w-full items-center overflow-hidden">
			<div
				class="bg-carpincho-bg border-carpincho-border/40 relative mr-3 flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-lg border"
			>
				<img
					v-if="upNextCoverUrl"
					:src="upNextCoverUrl"
					class="absolute h-full w-full object-cover"
					@error="onUpNextCoverError"
				/>
				<i
					v-else-if="djBaraEnabled && queueState.length === 0"
					class="material-icons text-carpincho-warning animate-pulse text-[1.75rem]"
				>
					auto_awesome
				</i>
				<i v-else class="material-icons text-carpincho-warning text-[1.75rem]">album</i>
			</div>

			<div class="flex grow flex-col justify-center overflow-hidden">
				<div class="text-carpincho-primary text-[0.65rem] font-bold tracking-wider uppercase">
					{{ upNextBadge }}
				</div>
				<div class="text-carpincho-text truncate text-sm font-bold">
					{{ upNextTitle }}
				</div>
			</div>
			<i class="material-icons text-carpincho-text/40 ml-2 shrink-0 text-lg">chevron_right</i>
		</div>
	</button>
</template>
