<script setup lang="ts">
	import { usePlayer } from '../composables/usePlayer';
	import { useContextMenuBindings } from '../composables/useContextMenu';
	import { usePullToRefresh } from '../composables/usePullToRefresh';
	import FavoritableCover from './ui/FavoritableCover.vue';

	const { topPlayedState, getTrackInfo, toggleQueue, handleScroll, loadLibrary, haptic, isScanning } = usePlayer();

	const {
		pullThreshold: PULL_THRESHOLD,
		pullDistance,
		onPullTouchStart,
		onPullTouchMove,
		onPullTouchEnd,
		resetPull,
	} = usePullToRefresh({
		canRefresh: () => !isScanning.value,
		onHaptic: haptic,
		onRefresh: () => loadLibrary(false),
	});

	function onTabScroll(e: Event) {
		const target = e.target as HTMLElement;
		if (target) {
			handleScroll(target.scrollTop);
		}
	}
</script>

<template>
	<section
		class="tab-content bg-carpincho-bg h-full overflow-y-auto px-4 pt-4"
		@scroll.passive="onTabScroll"
		@touchstart.passive="onPullTouchStart"
		@touchmove="onPullTouchMove"
		@touchend="onPullTouchEnd"
		@touchcancel="resetPull"
	>
		<!-- Indicador pull-to-refresh -->
		<div
			v-if="pullDistance > 0"
			class="bg-carpincho-panel/90 text-carpincho-warning mb-2 flex items-center justify-center gap-2 overflow-hidden rounded-lg text-xs font-bold transition-[height] duration-150"
			:style="{ height: pullDistance + 'px' }"
		>
			<i
				class="material-icons text-base transition-transform duration-150"
				:class="{ 'animate-spin': pullDistance >= PULL_THRESHOLD }"
				aria-hidden="true"
			>
				refresh
			</i>
			<span>
				{{
					pullDistance >= PULL_THRESHOLD ? 'Soltá para actualizar los tops 🧉' : 'Deslizá para actualizar...'
				}}
			</span>
		</div>
		<ul v-if="topPlayedState.length > 0" class="flex flex-col">
			<li
				v-for="(t, i) in topPlayedState"
				:key="t.path"
				class="border-carpincho-border hover:bg-carpincho-panel flex cursor-pointer items-center rounded-lg border-b p-4 transition select-none active:scale-[0.98]"
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
