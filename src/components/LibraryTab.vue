<script setup lang="ts">
	import { ref, computed, watch } from 'vue';
	import Fuse from 'fuse.js';
	import { useVirtualList } from '@vueuse/core';
	import { usePlayer } from '../composables/usePlayer';
	import LibraryRow from './ui/LibraryRow.vue';

	// Pull data from the global store
	const {
		currentTrackPath,
		currentTracks,
		favorites,
		handleLibraryClick,
		haptic,
		isPaused,
		librarySearchQuery: searchQuery,
		queueIndex,
	} = usePlayer();

	// Local state for this tab only
	const showFavoritesOnly = ref(false);

	// Initialize Fuse.js (re-computed if library updates entirely)
	const fuse = computed(() => {
		return new Fuse(currentTracks.value, {
			keys: ['title', 'artist', 'display_title', 'display_artist'],
			threshold: 0.3, // 0.0 is exact match, 1.0 is match anything
			ignoreLocation: true,
		});
	});

	const filteredTracks = computed(() => {
		let tracks = currentTracks.value;

		if (showFavoritesOnly.value) {
			tracks = tracks.filter((t) => favorites.value.includes(t.path));
		}

		if (!searchQuery.value) return tracks;

		// Delegate to Fuse.js for typo tolerance and relevance ranking
		return fuse.value.search(searchQuery.value).map((result) => result.item);
	});

	// Setup Virtualization
	const {
		list: virtualTracks,
		containerProps,
		wrapperProps,
		scrollTo,
	} = useVirtualList(filteredTracks, {
		itemHeight: 72, // Must match the fixed h-[72px] class in LibraryRow.vue
		overscan: 15,
	});

	watch(searchQuery, () => {
		scrollTo(0);
	});

	function clearSearch() {
		searchQuery.value = '';
		setTimeout(scrollToCurrent, 50);
	}

	function scrollToCurrent() {
		const currentIndex = filteredTracks.value.findIndex((t) => t.path === currentTrackPath.value);
		if (currentIndex !== -1) {
			scrollTo(currentIndex);
		}
	}
</script>

<template>
	<!-- Virtual List Scroll Container -->
	<section v-bind="containerProps" class="tab-content bg-carpincho-bg relative h-full overflow-y-auto">
		<!-- Tab Sticky Header (Search & Controls) -->
		<div class="bg-carpincho-bg sticky top-0 z-20 flex items-center gap-2 px-4 py-3 shadow-md">
			<button
				class="hover:text-carpincho-warning flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-800 text-white shadow transition active:scale-90"
				title="Ir al tema actual"
				@click="
					scrollToCurrent();
					haptic();
				"
			>
				<i class="material-icons">my_location</i>
			</button>
			<button
				:class="[
					'flex h-10 w-10 shrink-0 items-center justify-center rounded-full shadow transition',
					showFavoritesOnly
						? 'bg-carpincho-warning text-carpincho-panel'
						: 'hover:text-carpincho-warning bg-gray-800 text-white',
				]"
				title="Mostrar sólo favoritos"
				@click="
					showFavoritesOnly = !showFavoritesOnly;
					haptic();
					scrollTo(0);
				"
			>
				<i class="material-icons">{{ showFavoritesOnly ? 'favorite' : 'favorite_border' }}</i>
			</button>

			<div class="relative flex-grow">
				<input
					v-model="searchQuery"
					type="text"
					placeholder="Buscá un buen tema pa' acompañar los mates..."
					class="border-carpincho-primary focus:border-carpincho-secondary text-carpincho-text w-full border-b bg-transparent py-2 pr-8 placeholder-gray-500 transition-colors outline-none"
				/>
				<i
					v-show="searchQuery"
					class="material-icons text-carpincho-secondary absolute top-2 right-2 cursor-pointer"
					@click="clearSearch"
				>
					close
				</i>
			</div>
		</div>

		<!-- Table Header (CSS Grid Equivalent) -->
		<div
			class="bg-carpincho-panel text-carpincho-primary border-carpincho-border grid grid-cols-[4rem_minmax(0,1fr)_minmax(0,1fr)] items-center border-b shadow-sm sm:grid-cols-[4rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem]"
		>
			<div class="p-3 text-center font-bold">Orden</div>
			<div class="p-3 font-bold">El Temón</div>
			<div class="p-3 font-bold">Artista</div>
			<div class="hidden p-3 text-right font-bold sm:block">Duración</div>
		</div>

		<!-- Virtualized Track Rows -->
		<div v-bind="wrapperProps" class="w-full">
			<LibraryRow
				v-for="item in virtualTracks"
				:key="item.data.path"
				:track="item.data"
				:is-current="currentTrackPath === item.data.path"
				:is-paused="isPaused"
				:queue-position="queueIndex(item.data.path)"
				@click="handleLibraryClick(item.data)"
			/>

			<!-- Empty State -->
			<div v-if="filteredTracks.length === 0" class="text-carpincho-primary p-8 text-center italic">
				No hay nada por acá con ese nombre, fiera.
			</div>
		</div>
	</section>
</template>
