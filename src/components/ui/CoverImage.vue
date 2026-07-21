<script setup>
	import { useCover } from '../../composables/useCover';

	const props = defineProps({
		path: { type: String, default: null },
		size: { type: String, default: 'h-10 w-10' },
		rounded: { type: String, default: 'rounded' },
		iconSize: { type: String, default: '!text-lg' },
	});

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
