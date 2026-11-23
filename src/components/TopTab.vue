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
		class="tab-content h-full overflow-y-auto bg-[var(--bg-canvas)] pt-2"
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
				class="flex h-10 w-10 items-center justify-center rounded-full border border-[var(--hairline)] bg-[var(--bg-elevated)] shadow-lg"
				:style="{ opacity: Math.max(0.35, pullProgress) }"
			>
				<svg
					viewBox="0 0 24 24"
					class="h-5 w-5 text-[var(--accent-primary)]"
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
					'tap-feedback relative flex min-h-[72px] cursor-pointer items-center gap-3 px-4 py-3 transition-colors select-none hover:bg-[var(--bg-surface-hover)]',
					i >= 10 ? 'deferred-row' : '',
				]"
				@click="toggleQueue(t.path)"
				v-on="useContextMenuBindings(() => getTrackInfo(t.path), 'library')"
			>
				<div
					class="hidden w-8 shrink-0 text-center text-base font-bold text-[var(--accent-primary)] tabular-nums sm:block"
				>
					#{{ i + 1 }}
				</div>

				<FavoritableCover
					:track="t"
					size="h-12 w-12"
					rounded="rounded-[var(--radius-sm)]"
					icon-size="!text-3xl"
				/>

				<div class="min-w-0 flex-1 overflow-hidden">
					<div class="truncate text-[15px] font-semibold text-[var(--text-primary)]">
						{{ getTrackInfo(t.path).display_title }}
					</div>
					<div class="truncate text-[13px] text-[var(--text-secondary)] tabular-nums">
						{{ getTrackInfo(t.path).display_artist }} •
						{{ t.count === 1 ? 'Sonó 1 vez' : `Sonó ${t.count} veces` }}
					</div>
				</div>

				<span
					class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary-soft)]"
					aria-hidden="true"
				>
					<i class="material-icons !text-[22px]">playlist_add</i>
				</span>

				<div
					class="pointer-events-none absolute right-0 bottom-0 left-[76px] h-[0.5px] bg-[var(--hairline)] sm:left-[120px]"
					aria-hidden="true"
				/>
			</li>
		</ul>
		<div v-else class="p-8 text-center font-medium text-[var(--text-secondary)]">
			Todavía no sonó nada, maestro.
		</div>
	</section>
</template>
