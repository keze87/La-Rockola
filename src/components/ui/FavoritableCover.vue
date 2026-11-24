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
			sizePx?: number | null;
			showFavorite?: boolean;
			buttonPosition?: string;
		}>(),
		{
			size: 'h-10 w-10',
			rounded: 'rounded',
			iconSize: '!text-lg',
			buttonSize: 'h-[22px] w-[22px]',
			buttonIconSize: '!text-[13px]',
			sizePx: 512,
			showFavorite: true,
			buttonPosition: '-right-2 -bottom-2',
		}
	);

	const { isFavorite, path, toggleFavorite } = useTrack(() => props.track);
</script>

<template>
	<div class="relative isolate shrink-0" :class="size">
		<CoverImage
			:path="path && !path.startsWith('http') ? path : undefined"
			:size="size"
			:rounded="rounded"
			:icon-size="iconSize"
			:size-px="sizePx"
			class="cursor-pointer"
			@click.stop.prevent="toggleFavorite"
		/>
		<button
			v-if="showFavorite"
			type="button"
			class="touch-target-hit tap-feedback absolute z-20 flex cursor-pointer items-center justify-center rounded-full border border-[var(--hairline)] bg-[#1c1612]/95 shadow-[0_2px_8px_rgba(0,0,0,0.45)] select-none"
			:class="[buttonPosition, buttonSize]"
			:aria-label="isFavorite ? 'Quitar de favoritos' : 'Agregar a favoritos'"
			@click.stop.prevent="toggleFavorite"
		>
			<i
				class="material-icons favorite-icon transition-colors"
				:class="[
					isFavorite
						? 'text-[var(--accent-danger)]'
						: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
					buttonIconSize,
				]"
			>
				{{ isFavorite ? 'favorite' : 'favorite_border' }}
			</i>
		</button>
	</div>
</template>
