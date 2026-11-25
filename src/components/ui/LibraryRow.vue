<script setup lang="ts">
	import { useTrack } from '../../composables/useTrack';
	import { useContextMenuBindings } from '../../composables/useContextMenu';
	import FavoritableCover from './FavoritableCover.vue';
	import type { HTMLAttributes } from 'vue';
	import type { Track } from '../../types';

	// Variante basada en div/grid hermana de TrackRow, usada exclusivamente por la lista
	// virtualizada de LibraryTab: `useVirtualList` de vueuse renderiza los elementos visibles como
	// hijos directos en un wrapper `<div>`, y un `<div>` no puede convivir legalmente
	// adentro de una `<table>` (el navegador lo saca para afuera), por lo que esta fila
	// no puede ser `<tr>`/`<td>` como TrackRow. Los anchos de columna de abajo están ajustados
	// a ojo con el layout de tabla anterior; ajustar las clases grid-cols acá si cambian.
	const props = withDefaults(
		defineProps<
			{
				track: Track;
				isCurrent: boolean;
				isPaused: boolean;
				queuePosition: number;
				hasPlayed?: boolean;

				contextSource?: string;
				index?: number | null;
				contextMenuOnly?: boolean;
			} & /* @vue-ignore */ HTMLAttributes
		>(),
		{
			hasPlayed: false,
			contextSource: 'library',
			index: null,
			contextMenuOnly: false,
		}
	);

	const emit = defineEmits<{
		(e: 'click', track: Track): void;
	}>();

	// Forma de getter (no `props.track` por valor) para seguir el rastro de la prop
	// actual cuando una fila reutiliza su `:key` para nuevos datos de tema
	// (por ejemplo tras una actualización por websocket que reemplace la lista).
	const { displayArtist, displayTitle, durationStr, toggleFavorite } = useTrack(() => props.track);

	const bindings = useContextMenuBindings(
		() => props.track,
		() => props.contextSource ?? 'library',
		() => props.index ?? null,
		{ touch: !(props.contextMenuOnly ?? false) }
	);
</script>

<template>
	<div
		:id="isCurrent ? 'current-library-row' : undefined"
		class="tap-feedback relative flex h-[72px] cursor-pointer items-center gap-3 px-4 transition-colors [contain:layout_style_paint] select-none hover:bg-[var(--bg-surface-hover)] min-[720px]:grid min-[720px]:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_6rem] min-[720px]:gap-0 min-[720px]:px-0"
		:class="isCurrent ? 'bg-[var(--accent-primary-soft)]' : ''"
		v-on="bindings"
		@click="emit('click', track)"
	>
		<div class="relative flex shrink-0 items-center justify-center min-[720px]:p-2">
			<FavoritableCover :track="track" size="h-12 w-12" rounded="rounded-[var(--radius-sm)]" :size-px="128" />

			<!-- Indicador de tema sonando, superpuesto a la portada -->
			<div
				v-if="isCurrent"
				class="absolute flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-[var(--hairline)] bg-[var(--glass-bg-strong)] shadow"
				@click.stop.prevent="toggleFavorite"
			>
				<div :class="['equalizer', isPaused ? 'paused' : '']">
					<span />
					<span />
					<span />
				</div>
			</div>

			<!-- Posición en la fila, superpuesta a la portada -->
			<span
				v-else-if="queuePosition !== -1"
				class="absolute flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-[var(--hairline)] bg-[var(--glass-bg-strong)] text-sm font-bold text-[var(--accent-primary)] tabular-nums shadow"
				@click.stop.prevent="toggleFavorite"
			>
				{{ queuePosition + 1 }}
			</span>

			<!-- Indicador de tema ya reproducido -->
			<span
				v-else-if="hasPlayed"
				title="Ya sonó"
				class="played-indicator absolute flex h-6 w-6 items-center justify-center rounded-full bg-[#1c1612]/90 text-[var(--text-secondary)] shadow"
			>
				<i class="material-icons !text-sm">history</i>
			</span>
		</div>

		<div class="flex min-w-0 flex-1 flex-col justify-center min-[720px]:contents">
			<div class="flex min-w-0 items-center gap-2 min-[720px]:px-4">
				<span
					class="truncate text-[15px] font-semibold min-[720px]:font-medium"
					:class="isCurrent ? 'text-[var(--accent-primary)]' : 'text-[var(--text-primary)]'"
				>
					{{ displayTitle }}
				</span>
				<span
					v-if="track.is_duplicate"
					class="duplicate-warning inline-flex shrink-0 items-center gap-1 rounded bg-[var(--accent-primary-soft)] px-1.5 py-0.5 text-[11px] font-semibold text-[var(--accent-primary)]"
					:title="`Archivo duplicado (${track.duplicate_count || 2} copias detectadas en la biblioteca)`"
				>
					<i class="material-icons !text-xs">warning_amber</i>
					<span>Duplicado</span>
				</span>
			</div>

			<div class="truncate text-[13px] text-[var(--text-secondary)] min-[720px]:px-4 min-[720px]:text-[14px]">
				{{ displayArtist }}
			</div>
		</div>

		<div
			class="shrink-0 text-[12px] text-[var(--text-tertiary)] tabular-nums min-[720px]:px-4 min-[720px]:text-right min-[720px]:text-[13px]"
		>
			{{ durationStr }}
		</div>

		<!-- Separador hairline inset estilo iOS -->
		<div
			class="pointer-events-none absolute right-0 bottom-0 left-[76px] h-px bg-[var(--hairline)] min-[720px]:left-0"
			aria-hidden="true"
		/>
	</div>
</template>
