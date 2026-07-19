<script setup>
	import { ref, computed, watch } from 'vue';
	import { usePlayer } from '../composables/usePlayer';
	import { useContextMenu } from '../composables/useContextMenu';

	// Pull data from the global store
	const {
		currentTrackPath,
		currentTracks,
		favorites,
		handleLibraryClick,
		haptic,
		isPaused,
		librarySearchQuery: searchQuery,
		normalizeString,
		queueIndex,
		toggleFavorite,
	} = usePlayer();

	const { openCtxMenu, onCtxTouchStart, onCtxTouchEnd } = useContextMenu();

	// Local state for this tab only
	const showFavoritesOnly = ref(false);
	const librarySection = ref(null);

	watch(searchQuery, () => {
		if (librarySection.value) {
			librarySection.value.scrollTop = 0;
		}
	});

	const filteredTracks = computed(() => {
		let tracks = currentTracks.value;

		if (showFavoritesOnly.value) {
			tracks = tracks.filter((t) => favorites.value.includes(t.path));
		}

		if (!searchQuery.value) return tracks;

		const q = normalizeString(searchQuery.value);
		const exact = [],
			fuzzy = [];

		tracks.forEach((t) => {
			const target = normalizeString((t.artist || '') + ' ' + (t.title || ''));

			if (target.includes(q)) {
				exact.push(t);
			} else {
				let qIdx = 0;
				for (const char of target) {
					if (char === q[qIdx]) qIdx++;

					if (qIdx === q.length) {
						fuzzy.push(t);
						break;
					}
				}
			}
		});

		return exact.concat(fuzzy);
	});

	function clearSearch() {
		searchQuery.value = '';
		setTimeout(scrollToCurrent, 50);
	}

	function scrollToCurrent() {
		const el = document.getElementById('current-library-row');

		if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}
</script>

<template>
	<section ref="librarySection" class="tab-content bg-carpincho-bg relative h-full overflow-y-auto">
		<!-- Tab Sticky Header -->
		<div class="bg-carpincho-bg sticky top-0 z-10 flex items-center gap-2 px-4 py-3 shadow-md">
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

		<!-- Track Table -->
		<table class="w-full border-collapse text-left">
			<thead>
				<tr>
					<th class="text-carpincho-primary bg-carpincho-panel sticky top-0 z-0 w-16 p-3 text-center">
						Orden
					</th>
					<th class="text-carpincho-primary bg-carpincho-panel sticky top-0 z-0 p-3">El Temón</th>
					<th class="text-carpincho-primary bg-carpincho-panel sticky top-0 z-0 p-3">Artista</th>
					<th
						class="text-carpincho-primary bg-carpincho-panel sticky top-0 z-0 hidden w-20 p-3 text-right sm:table-cell"
					>
						Duración
					</th>
				</tr>
			</thead>
			<tbody>
				<tr
					v-for="track in filteredTracks"
					:id="currentTrackPath === track.path ? 'current-library-row' : ''"
					:key="track.path"
					:class="[
						'border-carpincho-border hover:bg-carpincho-border cursor-pointer border-b transition-colors active:scale-[0.98]',
						currentTrackPath === track.path ? 'bg-carpincho-panel' : '',
					]"
					@click="handleLibraryClick(track)"
					@contextmenu.prevent="openCtxMenu($event, track, 'library')"
					@touchstart="onCtxTouchStart($event, track, 'library')"
					@touchend="onCtxTouchEnd"
					@touchmove="onCtxTouchEnd"
				>
					<td class="p-4 text-center">
						<div v-if="currentTrackPath === track.path" class="flex items-center justify-center">
							<div :class="['equalizer', isPaused ? 'paused' : '']">
								<span />
								<span />
								<span />
							</div>
						</div>
						<span v-else-if="queueIndex(track.path) !== -1" class="text-carpincho-warning font-bold">
							{{ queueIndex(track.path) + 1 }}
						</span>
					</td>
					<td class="max-w-[200px] p-4 font-medium">
						<div class="flex items-center justify-start gap-3">
							<!-- BOTÓN FAVORITO -->
							<i
								class="material-icons favorite-icon hidden shrink-0 cursor-pointer !text-[1.1rem] transition-colors sm:block"
								:class="
									favorites.includes(track.path)
										? 'text-carpincho-warning scale-110 drop-shadow-md'
										: 'hover:text-carpincho-warning text-gray-600'
								"
								@click.stop="
									toggleFavorite(track.path);
									haptic();
								"
							>
								{{ favorites.includes(track.path) ? 'favorite' : 'favorite_border' }}
							</i>
							<span class="truncate">{{ track.title || track.display_title }}</span>
						</div>
					</td>
					<td class="truncate p-4 text-[#a6adc8]">
						{{ track.artist || track.display_artist }}
					</td>
					<td class="hidden p-4 text-right text-[#a6adc8] sm:table-cell">
						{{ track.duration_str }}
					</td>
				</tr>
				<tr v-if="filteredTracks.length === 0">
					<td colspan="4" class="text-carpincho-primary p-8 text-center italic">
						No hay nada por acá con ese nombre, fiera.
					</td>
				</tr>
			</tbody>
		</table>
	</section>
</template>

<style scoped>
	@media (max-width: 639px) {
		.favorite-icon {
			display: none !important;
		}
	}
</style>
