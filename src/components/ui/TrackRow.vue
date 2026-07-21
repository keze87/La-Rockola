<script setup>
	import { useTrack } from '../../composables/useTrack';
	import { useContextMenuBindings } from '../../composables/useContextMenu';
	import CoverImage from './CoverImage.vue';

	const props = defineProps({
		track: { type: [Object, String], required: true },
		contextSource: { type: String, default: 'library' },
		index: { type: Number, default: null },
		// Queue rows own their long-press-vs-swipe-to-delete touch logic
		// themselves, so they set this to skip the default touch bindings.
		contextMenuOnly: { type: Boolean, default: false },
		hideCover: { type: Boolean, default: false }, // Added to control cover visibility
	});

	const emit = defineEmits(['click']);

	// Getter form (not `props.track` by value) so this keeps tracking the
	// current prop when a `:key`-stable row is reused for fresh track data
	// (e.g. after a websocket state_update replaces the library array).
	const { path, displayTitle, displayArtist, durationStr, isFavorite, isPlaying, isPaused, toggleFavorite } =
		useTrack(() => props.track);

	const bindings = useContextMenuBindings(
		() => props.track,
		() => props.contextSource,
		() => props.index,
		{ touch: !props.contextMenuOnly }
	);
</script>

<template>
	<tr
		class="border-carpincho-border hover:bg-carpincho-border cursor-pointer border-b transition-colors active:scale-[0.98]"
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
					<div v-if="!hideCover" class="relative shrink-0">
						<CoverImage
							:path="path && !path.startsWith('http') ? path : null"
							size="h-10 w-10"
							rounded="rounded"
						/>
						<button
							type="button"
							class="bg-carpincho-panel absolute -right-2 -bottom-2 flex h-6 w-6 cursor-pointer items-center justify-center rounded-full shadow transition active:scale-90"
							:aria-label="isFavorite ? 'Quitar de favoritos' : 'Agregar a favoritos'"
							@click.stop.prevent="toggleFavorite"
						>
							<i
								class="material-icons favorite-icon !text-[0.9rem] transition-colors"
								:class="
									isFavorite
										? 'text-carpincho-warning drop-shadow-md'
										: 'hover:text-carpincho-warning text-gray-400'
								"
							>
								{{ isFavorite ? 'favorite' : 'favorite_border' }}
							</i>
						</button>
					</div>
					<!-- No cover (e.g. Library rows): favorite stands on its own as a full-size touch target -->
					<button
						v-else
						type="button"
						class="hover:bg-carpincho-border flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors active:scale-90"
						:aria-label="isFavorite ? 'Quitar de favoritos' : 'Agregar a favoritos'"
						@click.stop.prevent="toggleFavorite"
					>
						<i
							class="material-icons favorite-icon !text-xl transition-colors"
							:class="
								isFavorite
									? 'text-carpincho-warning drop-shadow-md'
									: 'hover:text-carpincho-warning text-gray-400'
							"
						>
							{{ isFavorite ? 'favorite' : 'favorite_border' }}
						</i>
					</button>
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
