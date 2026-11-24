<script setup lang="ts">
	import { computed, onMounted, watch } from 'vue';
	import { useVirtualList } from '@vueuse/core';
	import { isNativeAndroidHost, pickAndApplyMusicFolder } from '../composables/useAndroidHost';
	import { usePlayer } from '../composables/usePlayer';
	import { usePullToRefresh } from '../composables/usePullToRefresh';
	import { restoreTabScroll, saveTabScrollDebounced } from '../composables/useUiPersistence';
	import {
		isHostMode,
		libraryFolderError,
		libraryFolderStatus,
		localMusicDir,
	} from '../stores/useServerConnectionStore';
	import LibraryRow from './ui/LibraryRow.vue';

	// Traemos los datos del store global
	const {
		currentTrackPath,
		filteredTracks,
		handleLibraryClick,
		handleScroll,
		haptic,
		historyState,
		isPaused,
		isScanning,
		librarySearchQuery: searchQuery,
		loadLibrary,
		queueIndex,
		scanStatus,
		showFavoritesOnly,
	} = usePlayer();

	// Pull-to-refresh estilo Material cuando el listado está arriba
	const {
		pullThreshold: PULL_THRESHOLD,
		pullDistance,
		pullProgress,
		onPullTouchStart,
		onPullTouchMove,
		onPullTouchEnd,
		resetPull,
	} = usePullToRefresh({
		canRefresh: () => !isScanning.value && !scanStatus.value?.is_analyzing_mood,
		onThresholdCrossed: () => haptic('tick'),
		onHaptic: haptic,
		// Pull-to-refresh recarga la lista liviana (/library); el re-escaneo completo (/scan) es explícito
		onRefresh: () => loadLibrary(false),
	});

	// Conjunto de temas que ya sonaron en la sesión para lookup O(1)
	const historyPathsSet = computed(() => new Set(historyState.value));

	// Configuración de la lista virtualizada
	const {
		list: virtualTracks,
		containerProps,
		wrapperProps,
		scrollTo,
	} = useVirtualList(filteredTracks, {
		itemHeight: 72, // Debe coincidir con la clase fija h-[72px] en LibraryRow.vue
		overscan: 6,
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
	function onTabScroll(e: Event) {
		const target = e.target as HTMLElement;
		if (target) {
			handleScroll(target.scrollTop);
			saveTabScrollDebounced('library', target.scrollTop);
		}
	}

	let restoredInitialScroll = false;
	function restoreScrollIfNeeded() {
		if (restoredInitialScroll) return;
		const savedTop = restoreTabScroll('library');
		const el = containerProps.ref.value;
		if (savedTop > 0 && el && filteredTracks.value.length > 0) {
			restoredInitialScroll = true;
			el.scrollTop = savedTop;
		}
	}

	onMounted(() => {
		restoreScrollIfNeeded();
	});

	watch(
		() => filteredTracks.value.length,
		() => {
			restoreScrollIfNeeded();
		}
	);
</script>

<template>
	<!-- Contenedor con scroll para la lista virtualizada -->
	<section
		v-bind="containerProps"
		class="tab-content relative h-full overflow-y-auto bg-[var(--bg-canvas)]"
		@scroll.passive="onTabScroll"
		@touchstart.passive="onPullTouchStart"
		@touchmove="onPullTouchMove"
		@touchend="onPullTouchEnd"
		@touchcancel="resetPull"
	>
		<!-- Indicador pull-to-refresh circular estilo Material -->
		<div
			v-if="pullDistance > 0"
			class="library-pull-indicator flex items-center justify-center overflow-hidden transition-[height] duration-150"
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

		<!-- Encabezado fijo con buscador iOS y filtros cálidos -->
		<div
			class="sticky top-[var(--headbar-h)] z-30 flex items-center gap-2 border-b-[0.5px] border-[var(--glass-border)] bg-[var(--glass-bg-strong)] px-3 py-2.5 [backdrop-filter:var(--glass-blur)] [-webkit-backdrop-filter:var(--glass-blur)]"
		>
			<button
				type="button"
				aria-label="Ir al tema actual"
				class="touch-target tap-feedback flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]"
				title="Ir al tema actual"
				@click="
					scrollToCurrent();
					haptic();
				"
			>
				<i class="material-icons !text-[20px]">my_location</i>
			</button>
			<button
				type="button"
				aria-label="Mostrar sólo favoritos"
				:class="[
					'touch-target tap-feedback flex h-10 w-10 shrink-0 items-center justify-center rounded-full border',
					showFavoritesOnly
						? 'border-[var(--accent-primary)]/40 bg-[var(--accent-primary-soft)] text-[var(--accent-primary)]'
						: 'border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]',
				]"
				title="Mostrar sólo favoritos"
				@click="
					showFavoritesOnly = !showFavoritesOnly;
					haptic();
					scrollTo(0);
				"
			>
				<i class="material-icons !text-[20px]">{{ showFavoritesOnly ? 'favorite' : 'favorite_border' }}</i>
			</button>

			<div
				class="flex h-[42px] min-w-0 flex-grow items-center rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--bg-input)] px-3 transition-colors focus-within:border-[rgba(212,150,66,0.45)]"
			>
				<i class="material-icons mr-2 shrink-0 !text-[18px] text-[var(--text-secondary)]" aria-hidden="true">
					search
				</i>
				<input
					id="library-search-input"
					v-model="searchQuery"
					type="text"
					aria-label="Buscar canciones o artistas"
					placeholder="Buscá un buen tema pa' acompañar los mates..."
					class="min-w-0 flex-1 truncate bg-transparent text-[14px] text-ellipsis text-[var(--text-primary)] placeholder-[var(--text-tertiary)] !outline-none focus:outline-none focus-visible:outline-none"
				/>
				<button
					v-show="searchQuery"
					type="button"
					aria-label="Limpiar búsqueda"
					class="tap-feedback ml-1.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--bg-surface-active)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
					@click="clearSearch"
				>
					<i class="material-icons !text-[15px]" aria-hidden="true">close</i>
				</button>
			</div>
		</div>

		<!-- Banner de estado del escaneo -->
		<div
			v-if="isScanning || scanStatus?.is_analyzing_mood"
			class="flex items-center justify-between border-b border-[var(--hairline)] bg-[var(--bg-elevated)] px-4 py-2.5 text-xs font-semibold text-[var(--text-primary)]"
		>
			<div class="flex items-center gap-2 truncate">
				<i class="material-icons animate-spin text-base text-[var(--accent-primary)]">sync</i>
				<span class="truncate">
					{{
						isScanning
							? scanStatus?.message
								? scanStatus.message
								: scanStatus?.total
									? `Chusmeando temas: ${scanStatus.current} de ${scanStatus.total} listos 🧉`
									: 'Chusmeando la biblioteca, aguantá fiera... 🧉'
							: scanStatus?.total
								? `Sintonizando vibra: ${scanStatus.current} de ${scanStatus.total} temas analizados 🎶`
								: 'Sintonizando vibra de los temas en segundo plano... 🎶'
					}}
				</span>
			</div>
			<div v-if="scanStatus?.total" class="ml-2 shrink-0 font-bold text-[var(--accent-primary)] tabular-nums">
				{{ Math.round((scanStatus.current / scanStatus.total) * 100) }}%
			</div>
		</div>

		<!-- Encabezado de la tabla (solo pantallas anchas >= 720px) -->
		<div
			class="hidden border-b border-[var(--hairline)] bg-[var(--bg-elevated)] text-[12px] font-semibold tracking-wide text-[var(--text-secondary)] uppercase min-[720px]:grid min-[720px]:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_5rem] min-[720px]:items-center"
		>
			<div class="p-3 text-center">Orden</div>
			<div class="p-3">El Temón</div>
			<div class="p-3">Artista</div>
			<div class="p-3 text-right">Duración</div>
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
				:has-played="historyPathsSet.has(item.data.path)"
				@click="handleLibraryClick(item.data)"
			/>

			<!-- Estado vacío cuando no hay resultados o falta permiso/carpeta en Android Host -->
			<div v-if="filteredTracks.length === 0" class="text-carpincho-primary p-4 text-center sm:p-8">
				<template v-if="isScanning">
					<p class="mb-4 text-sm italic">
						🧉 Chusmeando la biblioteca por primera vez... Aguantá que ya asoman los temazos.
					</p>
					<div class="library-skeleton-list space-y-2 text-left" aria-hidden="true">
						<div
							v-for="idx in 6"
							:key="idx"
							class="border-carpincho-border/40 bg-carpincho-panel/40 grid grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)] items-center gap-3 rounded-lg border px-3 py-3 sm:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem]"
						>
							<div class="bg-carpincho-border/50 mx-auto h-10 w-10 animate-pulse rounded-md" />
							<div class="bg-carpincho-border/50 h-4 w-3/4 animate-pulse rounded" />
							<div class="bg-carpincho-border/40 h-3.5 w-1/2 animate-pulse rounded" />
							<div
								class="bg-carpincho-border/40 ml-auto hidden h-3.5 w-10 animate-pulse rounded sm:block"
							/>
						</div>
					</div>
				</template>
				<template
					v-else-if="isNativeAndroidHost() && isHostMode && (!localMusicDir || libraryFolderStatus !== 'ok')"
				>
					<p class="text-carpincho-warning mb-3 font-semibold">
						{{
							libraryFolderError ||
							(libraryFolderStatus === 'permission_denied'
								? 'Se revocó el permiso sobre tu carpeta de música.'
								: libraryFolderStatus === 'storage_unavailable'
									? 'La carpeta o tarjeta SD no está disponible.'
									: 'Todavía no elegiste una carpeta de música en este teléfono.')
						}}
					</p>
					<button
						type="button"
						class="touch-target bg-carpincho-warning text-carpincho-panel inline-flex cursor-pointer items-center gap-2 rounded-full px-4 py-2 text-sm font-bold shadow transition hover:brightness-110"
						@click="pickAndApplyMusicFolder"
					>
						<i class="material-icons text-base" aria-hidden="true">sd_card</i>
						<span>Elegir carpeta de música</span>
					</button>
				</template>
				<template v-else>
					<p class="italic">No hay nada por acá con ese nombre, fiera.</p>
				</template>
			</div>
		</div>
	</section>
</template>
