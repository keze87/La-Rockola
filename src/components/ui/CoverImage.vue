<script setup lang="ts">
	import { computed, onMounted, ref, watch } from 'vue';
	import { useCover } from '../../composables/useCover';
	import type { HTMLAttributes } from 'vue';

	const props = withDefaults(
		defineProps<
			{
				path?: string | null;
				size?: string;
				rounded?: string;
				iconSize?: string;
				sizePx?: number | null;
			} & /* @vue-ignore */ HTMLAttributes
		>(),
		{
			path: null,
			size: 'h-10 w-10',
			rounded: 'rounded',
			iconSize: '!text-lg',
			sizePx: 512,
		}
	);

	// Forma de getter para que se recalcule si cambia la prop `path` o `sizePx`
	const { coverUrl, onCoverError } = useCover(() => props.path, {
		size: () => props.sizePx,
	});
	const { coverUrl: rawThumbUrl } = useCover(() => props.path, { size: 128 });
	const thumbUrl = computed(() => (coverUrl.value && props.sizePx && props.sizePx > 128 ? rawThumbUrl.value : null));

	const imgRef = ref<HTMLImageElement | null>(null);
	const isLoaded = ref(false);
	const isThumbLoaded = ref(false);

	function syncLoadedFromDom() {
		if (coverUrl.value && imgRef.value?.complete && imgRef.value.naturalWidth > 0) {
			isLoaded.value = true;
		}
	}

	watch(
		coverUrl,
		() => {
			isLoaded.value = false;
			isThumbLoaded.value = false;
			syncLoadedFromDom();
		},
		{ flush: 'post' }
	);

	onMounted(() => {
		syncLoadedFromDom();
	});

	function onImgLoad() {
		isLoaded.value = true;
	}

	function onImgError() {
		isLoaded.value = false;
		onCoverError();
	}
</script>

<template>
	<div :class="[size, rounded, 'relative isolate flex shrink-0 items-center justify-center overflow-hidden']">
		<div
			v-if="coverUrl && !isLoaded && !(thumbUrl && isThumbLoaded)"
			:class="[
				size,
				rounded,
				'cover-skeleton bg-carpincho-border/60 absolute inset-0 h-full w-full shrink-0 animate-pulse',
			]"
		/>
		<img
			v-if="coverUrl"
			ref="imgRef"
			:src="coverUrl"
			:class="[
				size,
				rounded,
				'cover-main-img absolute inset-0 z-10 h-full w-full shrink-0 object-cover transition-opacity duration-200',
				isLoaded ? 'opacity-100' : 'opacity-0',
			]"
			decoding="async"
			alt=""
			@load="onImgLoad"
			@error="onImgError"
		/>
		<img
			v-if="thumbUrl && !isLoaded"
			:src="thumbUrl"
			:class="[
				size,
				rounded,
				'cover-thumb-img absolute inset-0 h-full w-full shrink-0 object-cover transition-opacity duration-150',
				isThumbLoaded ? 'opacity-100' : 'opacity-0',
			]"
			decoding="async"
			alt=""
			@load="isThumbLoaded = true"
		/>
		<div
			v-else-if="!coverUrl"
			:class="[size, rounded, 'bg-carpincho-bg flex h-full w-full shrink-0 items-center justify-center']"
		>
			<i class="material-icons text-carpincho-warning" :class="iconSize">album</i>
		</div>
		<div
			v-else
			:class="[size, rounded, 'bg-carpincho-bg/40 flex h-full w-full shrink-0 items-center justify-center']"
		>
			<i class="material-icons text-carpincho-muted/30" :class="iconSize">album</i>
		</div>
	</div>
</template>
