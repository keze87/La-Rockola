<script setup lang="ts">
	import { useTrack } from '../../composables/useTrack';
	import CoverImage from './CoverImage.vue';
	import type { Track } from '../../types';

	const props = withDefaults(
		defineProps<{
			track: Track | string;
			size?: string;
			rounded?: string;
			iconSize?: string;
			buttonSize?: string;
			buttonIconSize?: string;
		}>(),
		{
			size: 'h-10 w-10',
			rounded: 'rounded',
			iconSize: '!text-lg',
			buttonSize: 'h-6 w-6',
			buttonIconSize: '!text-[0.9rem]',
		}
	);

	const { isFavorite, path, toggleFavorite } = useTrack(() => props.track);
</script>

<template>
	<div class="relative shrink-0" :class="size">
		<CoverImage
			:path="path && !path.startsWith('http') ? path : undefined"
			:size="size"
			:rounded="rounded"
			:icon-size="iconSize"
			class="cursor-pointer"
			@click.stop.prevent="toggleFavorite"
		/>
		<button
			type="button"
			class="bg-carpincho-panel absolute -right-2 -bottom-2 flex cursor-pointer items-center justify-center rounded-full shadow transition active:scale-90"
			:class="buttonSize"
			:aria-label="isFavorite ? 'Quitar de favoritos' : 'Agregar a favoritos'"
			@click.stop.prevent="toggleFavorite"
		>
			<i
				class="material-icons favorite-icon transition-colors"
				:class="[
					isFavorite ? 'text-carpincho-warning drop-shadow-md' : 'hover:text-carpincho-warning text-gray-400',
					buttonIconSize,
				]"
			>
				{{ isFavorite ? 'favorite' : 'favorite_border' }}
			</i>
		</button>
	</div>
</template>
