<script setup lang="ts">
	import { ref, computed, watch } from 'vue';
	import Fuse from 'fuse.js';
	import { useVirtualList } from '@vueuse/core';
	import { usePlayer } from '../composables/usePlayer';
	import LibraryRow from './ui/LibraryRow.vue';

	// Traemos los datos del store global
	const {
		currentTrackPath,
		currentTracks,
		favorites,
		handleLibraryClick,
		haptic,
		isPaused,
		isScanning,
		librarySearchQuery: searchQuery,
		queueIndex,
		scanStatus,
	} = usePlayer();

	// Estado local exclusivo de esta pestaña
	const showFavoritesOnly = ref(false);

	// Inicializamos Fuse.js (se recalcula si la biblioteca cambia por completo)
	const fuse = computed(() => {
		return new Fuse(currentTracks.value, {
			keys: ['title', 'artist', 'display_title', 'display_artist'],
			threshold: 0.3, // 0.0 es coincidencia exacta, 1.0 coincide con cualquier cosa
			ignoreLocation: true,
		});
	});

	const filteredTracks = computed(() => {
		let tracks = currentTracks.value;

		if (showFavoritesOnly.value) {
			tracks = tracks.filter((t) => favorites.value.includes(t.path));
		}

		if (!searchQuery.value) return tracks;

		// Delegamos en Fuse.js para tolerar errores de tipeo y ordenar por relevancia
		return fuse.value.search(searchQuery.value).map((result) => result.item);
	});

	// Configuración de la lista virtualizada
	const {
		list: virtualTracks,
		containerProps,
		wrapperProps,
		scrollTo,
	} = useVirtualList(filteredTracks, {
		itemHeight: 72, // Debe coincidir con la clase fija h-[72px] en LibraryRow.vue
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
	<!-- Contenedor con scroll para la lista virtualizada -->
	<section v-bind="containerProps" class="tab-content bg-carpincho-bg relative h-full overflow-y-auto">
		<!-- Encabezado fijo con buscador y filtros -->
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

		<!-- Banner de estado del escaneo -->
		<div
			v-if="isScanning || scanStatus?.is_analyzing_mood"
			class="bg-carpincho-panel border-carpincho-border text-carpincho-text flex items-center justify-between border-b px-4 py-2.5 text-xs font-semibold shadow-inner"
		>
			<div class="flex items-center gap-2 truncate">
				<i class="material-icons text-carpincho-warning animate-spin text-base">sync</i>
				<span class="truncate">
					{{
						isScanning
							? scanStatus?.total
								? `Chusmeando temas: ${scanStatus.current} de ${scanStatus.total} listos 🧉`
								: 'Chusmeando la biblioteca, aguantá fiera... 🧉'
							: scanStatus?.total
								? `Sintonizando vibra: ${scanStatus.current} de ${scanStatus.total} temas analizados 🎶`
								: 'Sintonizando vibra de los temas en segundo plano... 🎶'
					}}
				</span>
			</div>
			<div v-if="scanStatus?.total" class="text-carpincho-warning ml-2 shrink-0 font-bold">
				{{ Math.round((scanStatus.current / scanStatus.total) * 100) }}%
			</div>
		</div>

		<!-- Encabezado de la tabla (con CSS Grid) -->
		<div
			class="bg-carpincho-panel text-carpincho-primary border-carpincho-border grid grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)] items-center border-b shadow-sm sm:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem]"
		>
			<div class="p-3 text-center font-bold">Orden</div>
			<div class="p-3 font-bold">El Temón</div>
			<div class="p-3 font-bold">Artista</div>
			<div class="hidden p-3 text-right font-bold sm:block">Duración</div>
		</div>

		<!-- Filas virtualizadas de canciones -->
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

			<!-- Estado vacío cuando no hay resultados -->
			<div v-if="filteredTracks.length === 0" class="text-carpincho-primary p-8 text-center italic">
				<template v-if="isScanning">
					🧉 Chusmeando la biblioteca por primera vez... Aguantá que ya asoman los temazos.
				</template>
				<template v-else>No hay nada por acá con ese nombre, fiera.</template>
			</div>
		</div>
	</section>
</template>
