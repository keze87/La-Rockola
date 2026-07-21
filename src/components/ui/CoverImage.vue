<script setup lang="ts">
	import { useCover } from '../../composables/useCover';

	const props = withDefaults(
		defineProps<{
			path?: string | null;
			size?: string;
			rounded?: string;
			iconSize?: string;
		}>(),
		{
			path: null,
			size: 'h-10 w-10',
			rounded: 'rounded',
			iconSize: '!text-lg',
		}
	);

	// Getter form so a changing `path` prop keeps recomputing (see useCover/useTrack).
	const { coverUrl, onCoverError } = useCover(() => props.path);
</script>

<template>
	<img
		v-if="coverUrl"
		:src="coverUrl"
		:class="[size, rounded, 'shrink-0 object-cover']"
		loading="lazy"
		alt=""
		@error="onCoverError"
	/>
	<div v-else :class="[size, rounded, 'bg-carpincho-bg flex shrink-0 items-center justify-center']">
		<i class="material-icons text-carpincho-warning" :class="iconSize">album</i>
	</div>
</template>
