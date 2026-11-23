<script setup lang="ts">
	import { onMounted, ref } from 'vue';
	import { usePlayer } from '../composables/usePlayer';
	import { useContextMenuBindings } from '../composables/useContextMenu';
	import { usePullToRefresh } from '../composables/usePullToRefresh';
	import { restoreTabScroll, saveTabScroll } from '../composables/useUiPersistence';
	import FavoritableCover from './ui/FavoritableCover.vue';

	const { topPlayedState, getTrackInfo, toggleQueue, handleScroll, loadLibrary, haptic, isScanning } = usePlayer();
	const sectionRef = ref<HTMLElement | null>(null);

	const {
		pullThreshold: PULL_THRESHOLD,
		pullDistance,
		pullProgress,
		onPullTouchStart,
		onPullTouchMove,
		onPullTouchEnd,
		resetPull,
	} = usePullToRefresh({
		canRefresh: () => !isScanning.value,
		onThresholdCrossed: () => haptic('tick'),
		onHaptic: haptic,
		onRefresh: () => loadLibrary(false),
	});

	function onTabScroll(e: Event) {
		const target = e.target as HTMLElement;
		if (target) {
			handleScroll(target.scrollTop);
			saveTabScroll('top', target.scrollTop);
		}
	}

	onMounted(() => {
		const savedTop = restoreTabScroll('top');
		if (savedTop > 0 && sectionRef.value) {
			sectionRef.value.scrollTop = savedTop;
		}
	});
</script>

<template>
	<section
		ref="sectionRef"
		class="tab-content bg-carpincho-bg h-full overflow-y-auto px-4 pt-4"
		@scroll.passive="onTabScroll"
		@touchstart.passive="onPullTouchStart"
		@touchmove="onPullTouchMove"
		@touchend="onPullTouchEnd"
		@touchcancel="resetPull"
	>
		<!-- Indicador pull-to-refresh circular estilo Material -->
		<div
			v-if="pullDistance > 0"
			class="mb-2 flex items-center justify-center overflow-hidden transition-[height] duration-150"
			:style="{ height: pullDistance + 'px' }"
		>
			<div
				class="bg-carpincho-panel border-carpincho-border flex h-10 w-10 items-center justify-center rounded-full border shadow-lg"
				:style="{ opacity: Math.max(0.35, pullProgress) }"
			>
				<svg
					viewBox="0 0 24 24"
					class="text-carpincho-warning h-5 w-5"
					:class="{ 'material-ptr-spin': pullDistance >= PULL_THRESHOLD }"
					:style="
						pullDistance < PULL_THRESHOLD
							? { transform: `rotate(${Math.round(pullProgress * 270)}deg)` }
							: undefined
					"
					aria-hidden="true"
				>
					<circle
						cx="12"
						cy="12"
						r="9"
						fill="none"
						stroke="currentColor"
						stroke-width="2.5"
						stroke-linecap="round"
						:stroke-dasharray="56"
						:stroke-dashoffset="Math.round(56 * (1 - Math.max(0.2, pullProgress * 0.8)))"
					/>
				</svg>
			</div>
		</div>
		<ul v-if="topPlayedState.length > 0" class="flex flex-col">
			<li
				v-for="(t, i) in topPlayedState"
				:key="t.path"
				:class="[
					'border-carpincho-border hover:bg-carpincho-panel flex cursor-pointer items-center rounded-lg border-b p-4 transition select-none active:scale-[0.98]',
					i >= 10 ? 'deferred-row' : '',
				]"
				@click="toggleQueue(t.path)"
				v-on="useContextMenuBindings(() => getTrackInfo(t.path), 'library')"
			>
				<div class="text-carpincho-warning mr-4 hidden w-8 text-center text-xl font-bold sm:block">
					#{{ i + 1 }}
				</div>

				<FavoritableCover :track="t" size="h-12 w-12" rounded="rounded-md" class="mr-4" icon-size="!text-4xl" />

				<div class="flex-grow overflow-hidden">
					<div class="text-carpincho-text truncate font-bold">
						{{ getTrackInfo(t.path).display_title }}
					</div>
					<div class="text-carpincho-muted truncate text-sm">
						{{ getTrackInfo(t.path).display_artist }} • Sonó {{ t.count }} veces
					</div>
				</div>
				<i class="material-icons text-carpincho-primary ml-2 shrink-0">playlist_add</i>
			</li>
		</ul>
		<div v-else class="text-carpincho-primary p-8 text-center font-medium">Todavía no sonó nada, maestro.</div>
	</section>
</template>
