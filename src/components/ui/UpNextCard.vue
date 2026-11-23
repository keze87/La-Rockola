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
		class="fogon-next-song tap-feedback mt-4 hidden w-full cursor-pointer items-center justify-between rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--glass-bg-strong)] p-3 text-left shadow-lg [backdrop-filter:var(--glass-blur)] select-none hover:border-[var(--accent-primary)]/40 md:flex"
		@click="emit('select')"
	>
		<div class="flex w-full items-center overflow-hidden">
			<div
				class="relative mr-3 flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-sm)] border border-[var(--hairline)] bg-[var(--bg-input)]"
			>
				<img
					v-if="upNextCoverUrl"
					:src="upNextCoverUrl"
					class="absolute h-full w-full object-cover"
					@error="onUpNextCoverError"
				/>
				<i
					v-else-if="djBaraEnabled && queueState.length === 0"
					class="material-icons animate-pulse !text-[24px] text-[var(--accent-primary)]"
				>
					auto_awesome
				</i>
				<i v-else class="material-icons !text-[24px] text-[var(--accent-primary)]">album</i>
			</div>

			<div class="flex min-w-0 grow flex-col justify-center overflow-hidden">
				<div class="text-[10px] font-semibold tracking-[0.06em] text-[var(--accent-primary)]/90 uppercase">
					{{ upNextBadge }}
				</div>
				<div class="truncate text-sm font-semibold text-[var(--text-primary)]">
					{{ upNextTitle }}
				</div>
			</div>
			<i class="material-icons ml-2 shrink-0 text-lg text-[var(--text-tertiary)]">chevron_right</i>
		</div>
	</button>
</template>
