<script setup lang="ts">
	import { useTrack } from '../../composables/useTrack';
	import { useContextMenuBindings } from '../../composables/useContextMenu';
	import FavoritableCover from './FavoritableCover.vue';
	import type { Track } from '../../types';

	// Variante basada en div/grid hermana de TrackRow, usada exclusivamente por la lista
	// virtualizada de LibraryTab: `useVirtualList` de vueuse renderiza los elementos visibles como
	// hijos directos en un wrapper `<div>`, y un `<div>` no puede convivir legalmente
	// adentro de una `<table>` (el navegador lo saca para afuera), por lo que esta fila
	// no puede ser `<tr>`/`<td>` como TrackRow. Los anchos de columna de abajo están ajustados
	// a ojo con el layout de tabla anterior; ajustar las clases grid-cols acá si cambian.
	const props = defineProps<{
		track: Track;
		isCurrent: boolean;
		isPaused: boolean;
		queuePosition: number;

		contextSource?: string;
		index?: number | null;
		contextMenuOnly?: boolean;
	}>();

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
		class="border-carpincho-border hover:bg-carpincho-border grid h-[72px] cursor-pointer grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)] items-center border-b transition-colors active:scale-[0.98] sm:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_5rem]"
		v-on="bindings"
		@click="emit('click', track)"
	>
		<div class="relative flex items-center justify-center p-2">
			<FavoritableCover :track="track" />

			<!-- Indicador de tema sonando, superpuesto a la portada -->
			<div
				v-if="isCurrent"
				class="bg-carpincho-panel absolute flex h-7 w-7 cursor-pointer items-center justify-center rounded-full shadow"
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
				class="bg-carpincho-panel text-carpincho-warning absolute flex h-7 w-7 cursor-pointer items-center justify-center rounded-full text-base font-bold shadow"
				@click.stop.prevent="toggleFavorite"
			>
				{{ queuePosition + 1 }}
			</span>
		</div>

		<div class="truncate p-4 font-medium">
			{{ displayTitle }}
		</div>

		<div class="text-carpincho-muted truncate p-4">
			{{ displayArtist }}
		</div>

		<div class="text-carpincho-muted hidden p-4 text-right sm:block">
			{{ durationStr }}
		</div>
	</div>
</template>
