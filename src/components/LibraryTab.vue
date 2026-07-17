<script setup>
import { ref, computed } from 'vue'
import { usePlayer } from '../composables/usePlayer'
import { useContextMenu } from '../composables/useContextMenu'

// Pull data from the global store
const {
	currentTracks, favorites, currentTrackPath, isPaused, sendCmd, haptic,
	normalizeString, queueIndex, toggleFavorite, handleLibraryClick,
	librarySearchQuery: searchQuery,
} = usePlayer()
const { openCtxMenu } = useContextMenu()

// Local state for this tab only
const showFavoritesOnly = ref(false)
const librarySection = ref(null)

let ctxLongPressTimer = null

const filteredTracks = computed(() => {
	let tracks = currentTracks.value;

	if (showFavoritesOnly.value) {
		tracks = tracks.filter(t => favorites.value.includes(t.path));
	}

	if (!searchQuery.value) return tracks;

	const q = normalizeString(searchQuery.value);
	const exact = [], fuzzy = [];
	tracks.forEach(t => {
		const target = normalizeString((t.artist || '') + ' ' + (t.title || ''));
		if (target.includes(q)) {
			exact.push(t);
		} else {
			let qIdx = 0;
			for (const char of target) {
				if (char === q[qIdx]) qIdx++;
				if (qIdx === q.length) { fuzzy.push(t); break; }
			}
		}
	});
	return exact.concat(fuzzy);
})

function clearSearch() {
	searchQuery.value = '';
	setTimeout(scrollToCurrent, 50);
}

function scrollToCurrent() {
	const el = document.getElementById('current-library-row');
	if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function ctxTouchStart(e, track) {
	const touch = e.touches[0];
	ctxLongPressTimer = setTimeout(() => {
		haptic(true);
		openCtxMenu(touch, track, 'library');
	}, 500);
}
function ctxTouchEnd() { clearTimeout(ctxLongPressTimer); }
</script>

<template>
	<section ref="librarySection" class="tab-content bg-carpincho-bg relative h-full overflow-y-auto">
		<!-- Tab Sticky Header -->
		<div class="sticky top-0 bg-carpincho-bg px-4 py-3 z-10 shadow-md flex gap-2 items-center">
			<button @click="scrollToCurrent(); haptic()"
				class="bg-gray-800 w-10 h-10 shrink-0 flex justify-center items-center rounded-full text-white hover:text-carpincho-warning active:scale-90 transition shadow"
				title="Ir al tema actual">
				<i class="material-icons">my_location</i>
			</button>
			<button @click="showFavoritesOnly = !showFavoritesOnly; haptic()"
				:class="['w-10 h-10 shrink-0 flex justify-center items-center rounded-full transition shadow', showFavoritesOnly ? 'bg-carpincho-warning text-carpincho-panel' : 'bg-gray-800 text-white hover:text-carpincho-warning']"
				title="Mostrar sólo favoritos">
				<i class="material-icons">{{ showFavoritesOnly ? 'favorite' : 'favorite_border' }}</i>
			</button>

			<div class="relative flex-grow">
				<input v-model="searchQuery" type="text" placeholder="Buscá un buen tema pa' acompañar los mates..."
					class="w-full bg-transparent border-b border-carpincho-primary focus:border-carpincho-secondary outline-none py-2 text-carpincho-text pr-8 placeholder-gray-500 transition-colors">
				<i v-show="searchQuery" @click="clearSearch"
					class="material-icons absolute right-2 top-2 cursor-pointer text-carpincho-secondary">close</i>
			</div>
		</div>

		<!-- Track Table -->
		<table class="w-full text-left border-collapse">
			<thead>
				<tr>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel sticky top-0 z-0 w-16 text-center">Orden
					</th>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel sticky top-0 z-0">El Temón</th>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel sticky top-0 z-0">Artista</th>
					<th
						class="p-3 text-carpincho-primary bg-carpincho-panel sticky top-0 z-0 hidden sm:table-cell w-20 text-right">
						Duración</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="track in filteredTracks" :key="track.path" @click="handleLibraryClick(track)"
					@contextmenu.prevent="openCtxMenu($event, track, 'library')"
					@touchstart="ctxTouchStart($event, track)" @touchend="ctxTouchEnd" @touchmove="ctxTouchEnd"
					:id="currentTrackPath === track.path ? 'current-library-row' : ''"
					:class="['border-b border-carpincho-border hover:bg-carpincho-border cursor-pointer transition-colors active:scale-[0.98]', currentTrackPath === track.path ? 'bg-carpincho-panel' : '']">
					<td class="p-4 text-center">
						<div v-if="currentTrackPath === track.path" class="flex justify-center items-center">
							<div :class="['equalizer', isPaused ? 'paused' : '']">
								<span></span><span></span><span></span>
							</div>
						</div>
						<span v-else-if="queueIndex(track.path) !== -1" class="text-carpincho-warning font-bold">{{
							queueIndex(track.path) + 1 }}</span>
						<span v-else class="text-gray-500">-</span>
					</td>
					<td class="p-4 font-medium max-w-[200px]">
						<div class="flex items-center justify-start gap-3">
							<!-- BOTÓN FAVORITO -->
							<i @click.stop="toggleFavorite(track.path); haptic()"
								class="material-icons !text-[1.1rem] shrink-0 transition-colors cursor-pointer hidden sm:block favorite-icon"
								:class="favorites.includes(track.path) ? 'text-carpincho-warning drop-shadow-md scale-110' : 'text-gray-600 hover:text-carpincho-warning'">
								{{ favorites.includes(track.path) ? 'favorite' : 'favorite_border' }}
							</i>
							<span class="truncate">{{ track.title || track.display_title }}</span>
						</div>
					</td>
					<td class="p-4 text-[#a6adc8] truncate">{{ track.artist || track.display_artist }}</td>
					<td class="p-4 text-[#a6adc8] hidden sm:table-cell text-right">{{ track.duration_str }}</td>
				</tr>
				<tr v-if="filteredTracks.length === 0">
					<td colspan="4" class="p-8 text-center text-carpincho-primary italic">No hay nada por acá con ese
						nombre,
						fiera.</td>
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
