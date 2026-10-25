<script setup lang="ts">
	import { ref } from 'vue';
	import { useQueueDragDrop, type UnifiedTrackItem } from '../composables/player/useQueueDragDrop';
	import { useContextMenu } from '../composables/useContextMenu';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import DjBanner from './queue/DjBanner.vue';
	import TrackRow from './ui/TrackRow.vue';

	// Clases de estructura y maquetado extraídas
	const trackGridClass =
		'grid grid-cols-[6.5rem_minmax(0,1fr)_minmax(0,1fr)] sm:grid-cols-[9rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem]';
	const btnBaseClass = 'flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition';
	const btnHoverClass = 'hover:bg-black/20 active:bg-black/30';

	const {
		currentTrackPath,
		djBaraEnabled,
		djNextTrack,
		getTrackInfo,
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
		jumpToHistory,
		jumpToQueue,
		moveInPlaylist,
		moveQueueItem: moveQueueItemCmd,
		pause,
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
</script>

<template>
	<section class="tab-content bg-carpincho-bg h-full overflow-y-auto">
		<!-- Agregador de URLs -->
		<div class="bg-carpincho-bg sticky top-0 z-10 flex items-center gap-2 px-4 py-3 shadow-md">
			<i class="material-icons text-carpincho-success shrink-0">link</i>
			<input
				v-model="newUrl"
				type="text"
				placeholder="Pegá el link de YouTube acá, máquina..."
				class="border-carpincho-primary focus:border-carpincho-secondary text-carpincho-text w-full border-b bg-transparent py-2 outline-none"
			/>
			<button :class="[btnBaseClass, 'bg-green-700 text-white shadow active:scale-90']" @click="addUrl">
				<i class="material-icons">add</i>
			</button>
		</div>

		<!-- Encabezado de la grilla -->
		<div
			:class="[
				'bg-carpincho-panel text-carpincho-primary border-carpincho-border items-center border-b shadow-sm',
				trackGridClass,
			]"
		>
			<div class="p-3 text-center font-bold">Acciones</div>
			<div class="p-3 font-bold">El Temón</div>
			<div class="p-3 font-bold">De quién es</div>
			<div class="hidden p-3 text-right font-bold sm:block">Duración</div>
		</div>

		<div class="overflow-hidden">
			<!-- Lista única unificada de temas -->
			<TransitionGroup name="list" tag="div" class="relative w-full">
				<TrackRow
					v-for="item in unifiedQueue"
					:id="item.status === 'current' ? 'current-queue-row' : undefined"
					:key="item.id"
					:class="[
						item.status === 'history' ? 'opacity-70' : '',
						item.status === 'queue' ? 'swipe-row' : '',
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
						item.status === 'history' ? item.historyIndex : item.status === 'queue' ? item.queueIndex : null
					"
					:context-menu-only="item.status === 'queue'"
					:style="
						item.status === 'queue' && item.queueIndex !== undefined && swipeOffsets.has(item.queueIndex)
							? { transform: `translateX(${swipeOffsets.get(item.queueIndex)}px)` }
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
							: undefined
					"
					@touchend="
						item.status === 'queue' && item.queueIndex !== undefined
							? queueTouchEnd($event, item.queueIndex)
							: undefined
					"
					@touchmove="
						item.status === 'queue' && item.queueIndex !== undefined
							? queueTouchMove($event, item.queueIndex)
							: undefined
					"
				>
					<template #prefix>
						<template v-if="item.status === 'history'">
							<i class="material-icons text-carpincho-success text-sm">check</i>
						</template>

						<template v-else-if="item.status === 'current'">
							<div class="flex items-center justify-center gap-1" @click.stop>
								<div :class="['equalizer', isPaused ? 'paused' : '']">
									<span />
									<span />
									<span />
								</div>
								<button
									type="button"
									:title="
										pauseAfterPath === currentTrackPath
											? 'Cancelar pausa al terminar'
											: 'Frenar tras este tema'
									"
									:class="[
										btnBaseClass,
										'active:scale-90',
										pauseAfterPath === currentTrackPath
											? 'text-carpincho-warning drop-shadow-[0_0_8px_rgba(233,196,106,0.8)]'
											: `hover:text-carpincho-warning text-gray-500 ${btnHoverClass}`,
									]"
									@click="
										togglePauseAfterCurrent();
										haptic();
									"
								>
									<i class="material-icons text-lg">timer</i>
								</button>
							</div>
						</template>

						<template v-else-if="item.status === 'queue' && item.queueIndex !== undefined">
							<div class="flex items-center justify-center gap-1" @click.stop>
								<button
									type="button"
									:class="[btnBaseClass, btnHoverClass]"
									title="Subir a próximo"
									@click="moveQueueItem(item.queueIndex, 'first')"
								>
									<i
										class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition"
									>
										vertical_align_top
									</i>
								</button>
								<button
									type="button"
									:class="[btnBaseClass, btnHoverClass]"
									title="Mover al final"
									@click="moveQueueItem(item.queueIndex, 'last')"
								>
									<i
										class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition"
									>
										vertical_align_bottom
									</i>
								</button>
								<button
									type="button"
									:class="[btnBaseClass, 'hidden hover:bg-red-500/20 active:bg-red-500/30 sm:flex']"
									title="Sacar de la fila"
									@click="onRemoveClick(item.queueIndex, $event)"
								>
									<i class="material-icons text-carpincho-secondary transition hover:text-red-400">
										delete
									</i>
								</button>
							</div>
						</template>
					</template>

					<template #title-extra>
						<i
							v-if="item.path === pauseAfterPath"
							class="material-icons text-carpincho-warning shrink-0 text-sm"
							title="Se frena acá"
						>
							timer
						</i>
					</template>
				</TrackRow>
			</TransitionGroup>

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
				:class="['border-carpincho-border border-b', trackGridClass]"
			>
				<div class="col-span-4 p-12 text-center">
					<div class="text-carpincho-primary flex flex-col items-center gap-4 opacity-80">
						<p class="text-lg font-bold">El Carpincho está esperando el mate...</p>
						<p class="text-sm">Agregá música para que empiece a cantar.</p>
					</div>
				</div>
			</div>

			<!-- DJ Bara PLACEHOLDER -->
			<DjBanner
				:dj-carpincho-enabled="djBaraEnabled"
				:queue-length="queueState.length"
				:dj-next-track="djNextTrack"
				:track-grid-class="trackGridClass"
			/>
		</div>
	</section>
</template>

<style scoped>
	.swipe-row {
		transition: transform 0.3s ease;
		touch-action: manipulation;
	}

	/* Respuesta visual cuando se elimina un ítem de la fila */
	@keyframes delete-flash {
		0% {
			background-color: transparent;
		}

		20% {
			background-color: rgba(239, 68, 68, 0.45);
		}

		60% {
			background-color: rgba(239, 68, 68, 0.2);
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
