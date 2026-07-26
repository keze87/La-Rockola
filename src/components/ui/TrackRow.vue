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
				// Queue rows own their long-press-vs-swipe-to-delete touch logic
				// themselves, so they set this to skip the default touch bindings.
				contextMenuOnly?: boolean;
				// Explicitly declare the camelCased data attributes for vue-tsc
				dataHistoryPath?: string;
				dataQueueIndex?: number;
			} & /* @vue-ignore */ HTMLAttributes
		>(),
		{
			contextSource: 'library',
			index: null,
			contextMenuOnly: false,
			dataHistoryPath: undefined,
			dataQueueIndex: undefined,
		}
	);

	const emit = defineEmits<{
		(e: 'click', track: Track | string): void;
	}>();

	// Getter form (not `props.track` by value) so this keeps tracking the
	// current prop when a `:key`-stable row is reused for fresh track data
	// (e.g. after a websocket state_update replaces the library array).
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
		v-on="bindings"
		@click="emit('click', track)"
	>
		<!-- Prefix Slot: Used for handles, Top rankings, or EQ animations -->
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

		<!-- Main Track Info -->
		<div class="flex items-center justify-start gap-3 overflow-hidden p-4 font-medium">
			<slot name="cover">
				<FavoritableCover :track="track" class="hidden sm:block" />
			</slot>
			<span class="truncate">{{ displayTitle }}</span>
			<slot name="title-extra" />
		</div>

		<!-- Artist -->
		<div class="text-carpincho-muted truncate p-4">
			{{ displayArtist }}
		</div>

		<!-- Suffix Slot: Used for Queue delete buttons -->
		<div v-if="$slots.suffix" class="flex justify-end p-4">
			<slot name="suffix"></slot>
		</div>

		<!-- Duration -->
		<div v-else class="text-carpincho-muted hidden p-4 text-right sm:block">
			{{ durationStr }}
		</div>
	</div>
</template>
