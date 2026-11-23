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
		class="tap-feedback relative flex min-h-[72px] w-full cursor-pointer items-center gap-3 px-3.5 py-2.5 transition-colors select-none hover:bg-[var(--bg-surface-hover)] min-[720px]:grid min-[720px]:grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)_auto] min-[720px]:gap-0 min-[720px]:px-0 min-[720px]:py-0"
		:class="
			isPlaying || props.dataTrackStatus === 'current'
				? 'mx-2 !w-[calc(100%-16px)] rounded-[var(--radius-md)] bg-[var(--accent-primary-soft)] min-[720px]:mx-0 min-[720px]:!w-full min-[720px]:rounded-none'
				: ''
		"
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
		<!-- Slot de prefijo: Indicador compacto de estado (28px en móvil) -->
		<div class="flex w-7 shrink-0 items-center justify-center text-center min-[720px]:w-auto min-[720px]:p-2">
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

		<!-- Centro apilado en móvil, columnas en pantallas >= 720px -->
		<div class="flex min-w-0 flex-1 flex-col justify-center min-[720px]:contents">
			<div class="flex min-w-0 items-center gap-2.5 min-[720px]:px-4">
				<slot name="cover">
					<FavoritableCover
						:track="track"
						size="h-10 w-10"
						rounded="rounded-[var(--radius-sm)]"
						class="hidden min-[720px]:block"
					/>
				</slot>
				<span
					class="truncate text-[15px] font-semibold min-[720px]:font-medium"
					:class="
						isPlaying || props.dataTrackStatus === 'current'
							? 'text-[var(--accent-primary)]'
							: 'text-[var(--text-primary)]'
					"
				>
					{{ displayTitle }}
				</span>
				<slot name="title-extra" />
			</div>

			<div class="truncate text-[13px] text-[var(--text-secondary)] min-[720px]:px-4 min-[720px]:text-[14px]">
				{{ displayArtist }}
			</div>
		</div>

		<!-- Slot de sufijo: Botones de acción compactos o duración -->
		<div v-if="$slots.suffix" class="flex shrink-0 items-center justify-end gap-1.5 min-[720px]:px-3">
			<slot name="suffix"></slot>
		</div>

		<div
			v-else
			class="hidden shrink-0 text-[12px] text-[var(--text-tertiary)] tabular-nums min-[720px]:block min-[720px]:px-4 min-[720px]:text-right"
		>
			{{ durationStr }}
		</div>

		<div
			v-if="!isPlaying && props.dataTrackStatus !== 'current'"
			class="pointer-events-none absolute right-0 bottom-0 left-[54px] h-[0.5px] bg-[var(--hairline)] min-[720px]:left-0"
			aria-hidden="true"
		/>
	</div>
</template>
