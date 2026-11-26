<script setup lang="ts">
	import { onMounted, ref } from 'vue';
	import { useVirtualList } from '@vueuse/core';
	import { isNativeAndroidHost } from '../composables/useAndroidHost';
	import { isRemoteMode } from '../stores/useServerConnectionStore';
	import { useQueueDragDrop, type UnifiedTrackItem } from '../composables/player/useQueueDragDrop';
	import { useContextMenu } from '../composables/useContextMenu';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import { restoreTabScroll, saveTabScrollDebounced } from '../composables/useUiPersistence';
	import DjBanner from './queue/DjBanner.vue';
	import TrackRow from './ui/TrackRow.vue';

	// Clases de estructura y maquetado extraídas
	const trackGridClass = '@min-[600px]:grid @min-[600px]:grid-cols-[3.5rem_minmax(0,2fr)_minmax(0,1.1fr)_auto]';
	const btnBaseClass =
		'tap-feedback flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-[var(--radius-sm)] bg-[var(--bg-input)] text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface-active)] hover:text-[var(--text-primary)]';

	const {
		currentTrackPath,
		djBaraEnabled,
		djNextTrack,
		getTrackInfo,
		handleScroll,
		haptic,
		historyState,
		isPaused,
		pauseAfterPath,
		queueState,
		togglePauseAfterCurrent,
	} = usePlayer();

	const { openCtxMenu } = useContextMenu();

	const {
		addUrl: addUrlCmd,
		clearRound,
		insertQueueItem,
		jumpToHistory,
		jumpToQueue,
		moveInPlaylist,
		moveQueueItem: moveQueueItemCmd,
		pause,
		removeHistoryItem: removeHistoryItemCmd,
		removeQueueItem: removeQueueItemCmd,
	} = usePlaybackControls();

	const newUrl = ref('');

	async function addUrl() {
		if (!newUrl.value.trim()) return;
		await addUrlCmd(newUrl.value.trim());
		newUrl.value = '';
	}

	function removeQueueItem(index: number, rowEl?: HTMLElement | null) {
		const el = rowEl || document.querySelector(`[data-queue-index="${index}"]`);

		if (el) {
			el.classList.add('deleting');
			setTimeout(() => removeQueueItemCmd(index), 450);
		} else {
			removeQueueItemCmd(index);
		}
	}

	function onRemoveClick(index: number, event: Event) {
		const target = event.currentTarget as HTMLElement | null;
		removeQueueItem(index, target?.closest('tr'));
	}

	function moveQueueItem(index: number, target: 'first' | 'last' | number) {
		let newIndex = target === 'first' ? 0 : queueState.value.length - 1;
		if (typeof target === 'number') newIndex = target;

		if (newIndex !== index) {
			moveQueueItemCmd(index, newIndex);
		}
	}

	const {
		unifiedQueue,
		swipeOffsets,
		queueTouchStart,
		queueTouchMove,
		queueTouchEnd,
		cancelQueueTouch,
		historySwipeOffsets,
		historyTouchStart,
		historyTouchMove,
		historyTouchEnd,
		cancelHistoryTouch,
		dragStart,
		dragOver,
		dragLeave,
		dragDrop,
		dragEnd,
		dropAtEnd,
	} = useQueueDragDrop({
		historyState,
		currentTrackPath,
		queueState,
		getTrackInfo,
		haptic,
		openCtxMenu,
		moveInPlaylist,
		moveQueueItem,
		removeQueueItemCmd,
		addHistoryToQueueCmd: (path) => {
			void insertQueueItem(path, queueState.value.length);
		},
		removeHistoryItemCmd: (historyIndex) => {
			void removeHistoryItemCmd(historyIndex);
		},
	});

	const {
		list: virtualQueue,
		containerProps,
		wrapperProps,
	} = useVirtualList(unifiedQueue, {
		itemHeight: 72,
		overscan: 6,
	});

	function onTrackClick(item: UnifiedTrackItem) {
		if (item.status === 'history' && item.historyIndex !== undefined) {
			jumpToHistory(item.historyIndex);
		} else if (item.status === 'current') {
			pause();
		} else if (item.status === 'queue' && item.queueIndex !== undefined) {
			jumpToQueue(item.queueIndex);
		}
	}

	function onTabScroll(e: Event) {
		cancelQueueTouch();
		cancelHistoryTouch();
		const target = e.target as HTMLElement;
		if (target) {
			handleScroll(target.scrollTop);
			saveTabScrollDebounced('queue', target.scrollTop);
		}
	}

	onMounted(() => {
		const savedTop = restoreTabScroll('queue');
		const container = containerProps.ref.value;
		if (savedTop > 0 && container) {
			container.scrollTop = savedTop;
		}
	});
</script>

<template>
	<section
		v-bind="{ ...containerProps, 'data-tab-panel': 'queue' }"
		class="tab-content @container h-full overflow-y-auto bg-[var(--bg-canvas)]"
		@scroll.passive="onTabScroll"
	>
		<!-- Agregador de URLs -->
		<div
			v-if="!isNativeAndroidHost() || isRemoteMode"
			class="sticky top-0 z-10 border-b border-[var(--hairline)] bg-[var(--glass-bg)] px-3 py-2.5 [backdrop-filter:var(--glass-blur)] [-webkit-backdrop-filter:var(--glass-blur)]"
		>
			<div
				class="flex h-[42px] items-center gap-2 rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--bg-input)] px-3 transition-colors focus-within:border-[rgba(212,150,66,0.45)]"
			>
				<i class="material-icons shrink-0 !text-[18px] text-[var(--accent-primary)]">link</i>
				<input
					v-model="newUrl"
					type="url"
					inputmode="url"
					enterkeyhint="go"
					autocapitalize="off"
					autocorrect="off"
					spellcheck="false"
					placeholder="Pegá el link de YouTube acá, máquina..."
					class="min-w-0 flex-1 bg-transparent text-[14px] text-[var(--text-primary)] placeholder-[var(--text-tertiary)] outline-none"
					@keydown.enter="addUrl"
				/>
				<button
					type="button"
					class="tap-feedback flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--accent-primary)] text-[#120e0b] shadow-sm hover:brightness-110"
					aria-label="Agregar link a la fila"
					@click="addUrl"
				>
					<i class="material-icons !text-[18px]">add</i>
				</button>
			</div>
		</div>

		<!-- Barra de acciones rápidas de la ronda -->
		<div
			v-if="unifiedQueue.length > 0"
			class="flex items-center justify-between border-b border-[var(--hairline)] px-4 py-2"
		>
			<span
				class="text-[12px] font-semibold tracking-[0.04em] text-[var(--text-secondary)] uppercase tabular-nums"
			>
				{{ unifiedQueue.length }} {{ unifiedQueue.length === 1 ? 'tema en ronda' : 'temas en ronda' }}
			</span>
			<button
				type="button"
				aria-label="Limpiar ronda"
				class="tap-feedback inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-[var(--accent-danger)]/35 bg-[var(--accent-danger)]/12 px-3 py-1 text-[12px] font-semibold text-[var(--accent-danger)] transition-colors hover:bg-[var(--accent-danger)]/20"
				@click="
					clearRound();
					haptic();
				"
			>
				<i class="material-icons !text-[15px]" aria-hidden="true">delete_sweep</i>
				<span>Limpiar ronda</span>
			</button>
		</div>

		<!-- Encabezado de la grilla (oculto en portrait < 720px para dar aire a títulos y artistas) -->
		<div
			:class="[
				'hidden items-center border-b border-[var(--hairline)] bg-[var(--bg-elevated)] text-[12px] font-semibold tracking-wide text-[var(--text-secondary)] uppercase',
				trackGridClass,
			]"
		>
			<div class="p-3 text-center">Estado</div>
			<div class="p-3">El Temón</div>
			<div class="p-3">De quién es</div>
			<div class="p-3 text-right">Acciones</div>
		</div>

		<div class="overflow-hidden pt-1">
			<!-- Lista única unificada de temas (virtualizada para colas de 100+ canciones) -->
			<div v-bind="wrapperProps" class="relative w-full">
				<div v-for="{ data: item } in virtualQueue" :key="item.id" class="relative h-[72px] overflow-hidden">
					<!-- Fondo fijo estilo Gmail revelado detrás de la fila al deslizar -->
					<div
						v-if="
							(item.status === 'queue' &&
								item.queueIndex !== undefined &&
								swipeOffsets.has(item.queueIndex)) ||
							(item.status === 'history' &&
								item.historyIndex !== undefined &&
								historySwipeOffsets.has(item.historyIndex))
						"
						class="pointer-events-none absolute inset-0 flex items-center justify-between bg-[var(--bg-elevated)] px-5"
						aria-hidden="true"
					>
						<div class="flex items-center">
							<span
								v-if="item.status === 'queue' && (swipeOffsets.get(item.queueIndex!) ?? 0) > 0"
								:class="[
									'swipe-promote-indicator inline-flex h-10 w-10 items-center justify-center rounded-full transition-all duration-150',
									(swipeOffsets.get(item.queueIndex!) ?? 0) >= 80
										? 'swipe-promote-ready scale-110 bg-[var(--accent-primary)] text-[#120e0b] shadow-sm'
										: 'scale-90 bg-[var(--bg-surface)] text-[var(--text-secondary)]',
								]"
							>
								<i class="material-icons !text-[20px]">vertical_align_top</i>
							</span>
							<span
								v-else-if="
									item.status === 'history' && (historySwipeOffsets.get(item.historyIndex!) ?? 0) > 0
								"
								:class="[
									'history-swipe-add-indicator inline-flex h-10 w-10 items-center justify-center rounded-full transition-all duration-150',
									(historySwipeOffsets.get(item.historyIndex!) ?? 0) >= 80
										? 'swipe-promote-ready scale-110 bg-[var(--accent-primary)] text-[#120e0b] shadow-sm'
										: 'scale-90 bg-[var(--bg-surface)] text-[var(--text-secondary)]',
								]"
							>
								<i class="material-icons !text-[20px]">playlist_add</i>
							</span>
						</div>
						<div class="flex items-center">
							<span
								v-if="item.status === 'queue' && (swipeOffsets.get(item.queueIndex!) ?? 0) < 0"
								:class="[
									'swipe-delete-indicator inline-flex h-10 w-10 items-center justify-center rounded-full transition-all duration-150',
									(swipeOffsets.get(item.queueIndex!) ?? 0) <= -80
										? 'swipe-delete-ready scale-110 bg-[var(--accent-danger)] text-[#120e0b] shadow-sm'
										: 'scale-90 bg-[var(--bg-surface)] text-[var(--text-secondary)]',
								]"
							>
								<i class="material-icons !text-[20px]">delete</i>
							</span>
							<span
								v-else-if="
									item.status === 'history' && (historySwipeOffsets.get(item.historyIndex!) ?? 0) < 0
								"
								:class="[
									'history-swipe-delete-indicator inline-flex h-10 w-10 items-center justify-center rounded-full transition-all duration-150',
									(historySwipeOffsets.get(item.historyIndex!) ?? 0) <= -80
										? 'swipe-delete-ready scale-110 bg-[var(--accent-danger)] text-[#120e0b] shadow-sm'
										: 'scale-90 bg-[var(--bg-surface)] text-[var(--text-secondary)]',
								]"
							>
								<i class="material-icons !text-[20px]">delete</i>
							</span>
						</div>
					</div>

					<TrackRow
						:id="item.status === 'current' ? 'current-queue-row' : undefined"
						:class="[
							item.status === 'history'
								? 'history-swipe-row bg-[var(--bg-canvas)] transition-opacity [&>*]:opacity-[0.52]'
								: '',
							item.status === 'queue' ? 'swipe-row bg-[var(--bg-canvas)]' : '',
							trackGridClass,
						]"
						:data-history-path="item.status === 'history' ? item.path : undefined"
						:data-history-index="item.historyIndex"
						:data-queue-index="item.queueIndex"
						:data-current-track="item.status === 'current' ? true : undefined"
						:data-track-status="item.status"
						:data-playlist-index="item.index"
						:track="getTrackInfo(item.path)"
						:context-source="item.status"
						:index="
							item.status === 'history'
								? item.historyIndex
								: item.status === 'queue'
									? item.queueIndex
									: null
						"
						:context-menu-only="item.status === 'queue' || item.status === 'history'"
						:style="
							item.status === 'queue' &&
							item.queueIndex !== undefined &&
							swipeOffsets.has(item.queueIndex)
								? {
										transform: `translateX(${swipeOffsets.get(item.queueIndex)}px)`,
										transition: 'none',
									}
								: item.status === 'history' &&
									  item.historyIndex !== undefined &&
									  historySwipeOffsets.has(item.historyIndex)
									? {
											transform: `translateX(${historySwipeOffsets.get(item.historyIndex)}px)`,
											transition: 'none',
										}
									: undefined
						"
						draggable="true"
						@click="onTrackClick(item)"
						@dragstart="dragStart($event, item.index)"
						@dragover.prevent="dragOver($event, item.index)"
						@dragleave="dragLeave($event)"
						@drop.prevent="dragDrop($event, item.index)"
						@dragend="dragEnd($event)"
						@touchstart="
							item.status === 'queue' && item.queueIndex !== undefined
								? queueTouchStart($event, item.path, item.queueIndex)
								: item.status === 'history' && item.historyIndex !== undefined
									? historyTouchStart($event, item.path, item.historyIndex)
									: undefined
						"
						@touchend="
							item.status === 'queue' && item.queueIndex !== undefined
								? queueTouchEnd($event, item.queueIndex)
								: item.status === 'history' && item.historyIndex !== undefined
									? historyTouchEnd($event, item.historyIndex)
									: undefined
						"
						@touchmove="
							item.status === 'queue' && item.queueIndex !== undefined
								? queueTouchMove($event, item.queueIndex)
								: item.status === 'history' && item.historyIndex !== undefined
									? historyTouchMove($event, item.historyIndex)
									: undefined
						"
						@touchcancel="
							item.status === 'queue' && item.queueIndex !== undefined
								? cancelQueueTouch(item.queueIndex)
								: item.status === 'history' && item.historyIndex !== undefined
									? cancelHistoryTouch(item.historyIndex)
									: undefined
						"
					>
						<template #prefix>
							<template v-if="item.status === 'history'">
								<i class="material-icons !text-[18px] text-[var(--accent-mate)]">check</i>
							</template>

							<template v-else-if="item.status === 'current'">
								<div :class="['equalizer', isPaused ? 'paused' : '']">
									<span />
									<span />
									<span />
								</div>
							</template>

							<template v-else-if="item.status === 'queue' && item.queueIndex !== undefined">
								<span class="text-[12px] font-semibold text-[var(--text-tertiary)] tabular-nums">
									{{ item.queueIndex + 1 }}
								</span>
							</template>
						</template>

						<template #title-extra>
							<i
								v-if="item.path === pauseAfterPath"
								class="material-icons shrink-0 !text-[15px] text-[var(--accent-primary)]"
								title="Se frena acá"
							>
								timer
							</i>
						</template>

						<template
							v-if="
								item.status === 'current' || (item.status === 'queue' && item.queueIndex !== undefined)
							"
							#suffix
						>
							<div v-if="item.status === 'current'" class="flex items-center" @click.stop>
								<button
									type="button"
									:aria-label="
										pauseAfterPath === currentTrackPath
											? 'Cancelar pausa al terminar'
											: 'Frenar tras este tema'
									"
									:title="
										pauseAfterPath === currentTrackPath
											? 'Cancelar pausa al terminar'
											: 'Frenar tras este tema'
									"
									:class="[
										btnBaseClass,
										pauseAfterPath === currentTrackPath
											? 'bg-[var(--accent-primary-soft)] text-[var(--accent-primary)]'
											: '',
									]"
									@click="
										togglePauseAfterCurrent();
										haptic();
									"
								>
									<i class="material-icons !text-[18px]" aria-hidden="true">timer</i>
								</button>
							</div>

							<div
								v-else-if="item.status === 'queue' && item.queueIndex !== undefined"
								class="flex items-center gap-1"
								@click.stop
							>
								<button
									type="button"
									aria-label="Subir a próximo"
									:class="btnBaseClass"
									title="Subir a próximo"
									@click="moveQueueItem(item.queueIndex, 'first')"
								>
									<i class="material-icons !text-[18px]" aria-hidden="true">vertical_align_top</i>
								</button>
								<button
									type="button"
									aria-label="Mover al final"
									:class="btnBaseClass"
									title="Mover al final"
									@click="moveQueueItem(item.queueIndex, 'last')"
								>
									<i class="material-icons !text-[18px]" aria-hidden="true">vertical_align_bottom</i>
								</button>
								<button
									type="button"
									aria-label="Sacar de la fila"
									:class="[
										btnBaseClass,
										'hidden hover:bg-[var(--accent-danger)]/20 hover:text-[var(--accent-danger)] sm:flex',
									]"
									title="Sacar de la fila"
									@click="onRemoveClick(item.queueIndex, $event)"
								>
									<i class="material-icons !text-[18px]" aria-hidden="true">delete</i>
								</button>
							</div>
						</template>
					</TrackRow>
				</div>
			</div>

			<!-- Drop zone al final de la lista unificada -->
			<div
				v-if="unifiedQueue.length > 0"
				id="playlist-bottom-drop-zone"
				class="min-h-[48px] w-full"
				@dragover.prevent
				@drop.prevent="dropAtEnd"
			/>

			<!-- EMPTY STATE -->
			<div
				v-if="unifiedQueue.length === 0 && !djBaraEnabled"
				id="empty-queue-full-state"
				class="border-b border-[var(--hairline)]"
			>
				<div class="p-12 text-center">
					<div class="flex flex-col items-center gap-2 text-[var(--text-secondary)]">
						<p class="text-base font-bold text-[var(--text-primary)]">
							El Carpincho está esperando el mate...
						</p>
						<p class="text-sm">Agregá música para que empiece a cantar.</p>
					</div>
				</div>
			</div>

			<!-- DJ Bara PLACEHOLDER -->
			<DjBanner
				:dj-bara-enabled="djBaraEnabled"
				:queue-length="queueState.length"
				:dj-next-track="djNextTrack"
				:track-grid-class="trackGridClass"
			/>
		</div>
	</section>
</template>

<style scoped>
	.swipe-row {
		transition: transform 0.24s cubic-bezier(0.22, 1, 0.36, 1);
		touch-action: pan-y;
	}

	/* Respuesta visual cuando se elimina un ítem de la fila */
	@keyframes delete-flash {
		0% {
			background-color: transparent;
		}

		20% {
			background-color: rgba(217, 101, 91, 0.4);
		}

		60% {
			background-color: rgba(217, 101, 91, 0.18);
		}

		100% {
			background-color: transparent;
			opacity: 0;
			transform: scaleY(0);
		}
	}

	tr.deleting {
		animation: delete-flash 0.45s ease forwards;
		pointer-events: none;
		overflow: hidden;
	}
</style>
