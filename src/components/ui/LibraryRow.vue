<script setup lang="ts">
	import { useTrack } from '../../composables/useTrack';
	import { useContextMenuBindings } from '../../composables/useContextMenu';
	import FavoritableCover from './FavoritableCover.vue';
	import type { Track } from '../../types';

	// A div/grid-based sibling of TrackRow, used only by LibraryTab's
	// virtualized list: vueuse's `useVirtualList` renders its visible slice as
	// plain block children of a wrapper `<div>`, and a `<div>` can't legally
	// live inside a `<table>` (the browser hoists it back out), so this row
	// can't be a `<tr>`/`<td>` like TrackRow. Column widths below are matched
	// by eye to the old `<table>` layout — nudge the grid-cols classes here
	// (and ROW_HEIGHT in LibraryTab.vue) if they drift from the real render.
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

	// Getter form (not `props.track` by value) so this keeps tracking the
	// current prop when a `:key`-stable row is reused for fresh track data
	// (e.g. after a websocket state_update replaces the library array).
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

			<!-- Now-playing indicator, overlaid on the cover -->
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

			<!-- Queue order, overlaid on the cover -->
			<span
				v-else-if="queuePosition !== -1"
				class="bg-carpincho-panel text-carpincho-warning absolute flex h-7 w-7 cursor-pointer items-center justify-center rounded-full text-base font-bold shadow"
				@click.stop.prevent="toggleFavorite"
			>
				{{ queuePosition + 1 }}
			</span>
		</div>

		<div class="p-4 font-medium">
			<span class="truncate">{{ displayTitle }}</span>
		</div>

		<div class="text-carpincho-muted truncate p-4">
			{{ displayArtist }}
		</div>

		<div class="text-carpincho-muted hidden p-4 text-right sm:block">
			{{ durationStr }}
		</div>
	</div>
</template>
