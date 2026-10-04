<script setup lang="ts">
	import { useTrack } from '../../composables/useTrack';
	import { useContextMenuBindings } from '../../composables/useContextMenu';
	import FavoritableCover from './FavoritableCover.vue';
	import type { HTMLAttributes } from 'vue';
	import type { Track } from '../../types';

	const props = withDefaults(
		defineProps<
			{
				track: Track | string;
				contextSource?: string;
				index?: number | null;
				// Las filas de la fila manejan su propia lógica de pulsación larga vs swipe para borrar,
				// por lo que activan esto para saltear los bindings táctiles por defecto.
				contextMenuOnly?: boolean;
				// Declaramos explícitamente los atributos data en camelCase para vue-tsc
				dataHistoryPath?: string;
				dataHistoryIndex?: number;
				dataQueueIndex?: number;
				dataCurrentTrack?: boolean | string;
				dataTrackStatus?: string;
				dataPlaylistIndex?: number;
			} & /* @vue-ignore */ HTMLAttributes
		>(),
		{
			contextSource: 'library',
			index: null,
			contextMenuOnly: false,
			dataHistoryPath: undefined,
			dataHistoryIndex: undefined,
			dataQueueIndex: undefined,
			dataCurrentTrack: undefined,
			dataTrackStatus: undefined,
			dataPlaylistIndex: undefined,
		}
	);

	const emit = defineEmits<{
		(e: 'click', track: Track | string): void;
	}>();

	// Forma de getter (no `props.track` por valor) para seguir el rastro de la prop
	// actual cuando una fila reutiliza su `:key` para nuevos datos de tema
	// (por ejemplo tras una actualización por websocket que reemplace la lista).
	const { displayArtist, displayTitle, durationStr, isPaused, isPlaying, trackInfo } = useTrack(() => props.track);

	const bindings = useContextMenuBindings(
		() => trackInfo.value,
		() => props.contextSource,
		() => props.index,
		{ touch: !props.contextMenuOnly }
	);
</script>

<template>
	<div
		class="border-carpincho-border hover:bg-carpincho-border grid h-[72px] w-full cursor-pointer grid-cols-[4rem_minmax(0,1fr)_minmax(0,1fr)] items-center border-b transition-colors active:scale-[0.98] sm:grid-cols-[4rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem]"
		:class="{ 'bg-carpincho-panel': isPlaying }"
		v-bind="{
			'data-history-path': props.dataHistoryPath,
			'data-history-index': props.dataHistoryIndex,
			'data-queue-index': props.dataQueueIndex,
			'data-current-track': props.dataCurrentTrack,
			'data-track-status': props.dataTrackStatus,
			'data-playlist-index': props.dataPlaylistIndex,
		}"
		v-on="bindings"
		@click="emit('click', track)"
	>
		<!-- Slot de prefijo: Para selectores de arrastre, rankings del Top o animación del ecualizador -->
		<div class="flex items-center justify-center p-2 text-center">
			<slot name="prefix">
				<div v-if="isPlaying" class="flex items-center justify-center">
					<div :class="['equalizer', isPaused ? 'paused' : '']">
						<span />
						<span />
						<span />
					</div>
				</div>
			</slot>
		</div>

		<!-- Información principal del tema -->
		<div class="flex items-center justify-start gap-3 overflow-hidden p-4 font-medium">
			<slot name="cover">
				<FavoritableCover :track="track" class="hidden sm:block" />
			</slot>
			<span class="truncate">{{ displayTitle }}</span>
			<slot name="title-extra" />
		</div>

		<!-- Artista -->
		<div class="text-carpincho-muted truncate p-4">
			{{ displayArtist }}
		</div>

		<!-- Slot de sufijo: Usado para botones de borrar en la fila -->
		<div v-if="$slots.suffix" class="flex justify-end p-4">
			<slot name="suffix"></slot>
		</div>

		<!-- Duración -->
		<div v-else class="text-carpincho-muted hidden p-4 text-right sm:block">
			{{ durationStr }}
		</div>
	</div>
</template>
