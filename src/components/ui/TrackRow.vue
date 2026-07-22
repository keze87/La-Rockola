<script setup lang="ts">
	import { useTrack } from '../../composables/useTrack';
	import { useContextMenuBindings } from '../../composables/useContextMenu';
	import FavoritableCover from './FavoritableCover.vue';
	import type { Track } from '../../types';

	const props = withDefaults(
		defineProps<{
			track: Track | string;
			contextSource?: string;
			index?: number | null;
			// Queue rows own their long-press-vs-swipe-to-delete touch logic
			// themselves, so they set this to skip the default touch bindings.
			contextMenuOnly?: boolean;
			hideCover?: boolean;
		}>(),
		{
			contextSource: 'library',
			index: null,
			contextMenuOnly: false,
			hideCover: false,
		}
	);

	const emit = defineEmits<{
		(e: 'click', track: Track | string): void;
	}>();

	// Getter form (not `props.track` by value) so this keeps tracking the
	// current prop when a `:key`-stable row is reused for fresh track data
	// (e.g. after a websocket state_update replaces the library array).
	const {
		displayArtist,
		displayTitle,
		durationStr,
		isFavorite,
		isPaused,
		isPlaying,
		path,
		toggleFavorite,
		trackInfo,
	} = useTrack(() => props.track);

	const bindings = useContextMenuBindings(
		() => trackInfo.value,
		() => props.contextSource,
		() => props.index,
		{ touch: !props.contextMenuOnly }
	);
</script>

<template>
	<tr
		class="border-carpincho-border hover:bg-carpincho-border h-[72px] cursor-pointer border-b transition-colors active:scale-[0.98]"
		:class="{ 'bg-carpincho-panel': isPlaying }"
		v-on="bindings"
		@click="emit('click', track)"
	>
		<!-- Prefix Slot: Used for Queue drag handles, Top rankings, or EQ animations -->
		<td class="p-2 text-center">
			<slot name="prefix">
				<div v-if="isPlaying" class="flex items-center justify-center">
					<div :class="['equalizer', isPaused ? 'paused' : '']">
						<span />
						<span />
						<span />
					</div>
				</div>
			</slot>
		</td>

		<!-- Main Track Info -->
		<td class="max-w-[200px] p-4 font-medium">
			<div class="flex items-center justify-start gap-3">
				<slot name="cover">
					<!-- Cover shown: favorite is a badge anchored to its corner -->
					<FavoritableCover v-if="!hideCover" :track="track" class="hidden sm:block" />
				</slot>

				<span class="truncate">{{ displayTitle }}</span>
				<slot name="title-extra" />
			</div>
		</td>

		<td class="text-carpincho-muted truncate p-4">
			{{ displayArtist }}
		</td>

		<td class="text-carpincho-muted hidden p-4 text-right sm:table-cell">
			{{ durationStr }}
		</td>

		<!-- Suffix Slot: Used for Queue delete buttons -->
		<td v-if="$slots.suffix" class="p-4">
			<slot name="suffix"></slot>
		</td>
	</tr>
</template>
