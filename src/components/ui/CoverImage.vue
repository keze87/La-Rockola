<script setup lang="ts">
	import { ref, watch } from 'vue';
	import { useIntersectionObserver } from '@vueuse/core';
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
				unloadWhenHidden?: boolean;
			} & /* @vue-ignore */ HTMLAttributes
		>(),
		{
			path: null,
			size: 'h-10 w-10',
			rounded: 'rounded',
			iconSize: '!text-lg',
			sizePx: 512,
			unloadWhenHidden: true,
		}
	);

	// Forma de getter para que se recalcule si cambia la prop `path` o `sizePx`
	const { coverUrl, onCoverError } = useCover(() => props.path, {
		size: () => props.sizePx,
	});

	const elRef = ref<HTMLElement | null>(null);
	const imgRef = ref<HTMLImageElement | null>(null);
	const isLoaded = ref(false);
	const isVisible = ref(import.meta.env.MODE === 'test' || !props.unloadWhenHidden);

	watch(
		[coverUrl, isVisible],
		([nextUrl, nextVisible]) => {
			isLoaded.value = false;
			if (nextUrl && nextVisible && imgRef.value?.complete && imgRef.value.naturalWidth > 0) {
				isLoaded.value = true;
			}
		},
		{ flush: 'sync' }
	);

	function onImgLoad() {
		isLoaded.value = true;
	}

	function onImgError() {
		isLoaded.value = false;
		onCoverError();
	}

	if (props.unloadWhenHidden && typeof window !== 'undefined' && 'IntersectionObserver' in window) {
		useIntersectionObserver(
			elRef,
			(entries) => {
				const entry = entries[0];
				if (entry) {
					isVisible.value = entry.isIntersecting;
				}
			},
			{
				rootMargin: '150px',
			}
		);
	}
</script>

<template>
	<div ref="elRef" :class="[size, rounded, 'relative flex shrink-0 items-center justify-center overflow-hidden']">
		<div
			v-if="isVisible && coverUrl && !isLoaded"
			:class="[
				size,
				rounded,
				'cover-skeleton bg-carpincho-border/60 absolute inset-0 h-full w-full shrink-0 animate-pulse',
			]"
		/>
		<img
			v-if="isVisible && coverUrl"
			ref="imgRef"
			:src="coverUrl"
			:class="[
				size,
				rounded,
				'absolute inset-0 h-full w-full shrink-0 object-cover transition-opacity duration-200',
				isLoaded ? 'opacity-100' : 'opacity-0',
			]"
			loading="lazy"
			decoding="async"
			alt=""
			@load="onImgLoad"
			@error="onImgError"
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
