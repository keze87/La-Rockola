<script setup lang="ts">
	import { computed, ref } from 'vue';
	import { useContextMenu } from '../composables/useContextMenu';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import TrackRow from './ui/TrackRow.vue';

	// Extracted layout and structural classes
	const trackGridClass =
		'grid grid-cols-[6.5rem_minmax(0,1fr)_minmax(0,1fr)] sm:grid-cols-[9rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem]';
	const btnBaseClass = 'flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition';
	const btnHoverClass = 'hover:bg-black/20 active:bg-black/30';

	const {
		currentTrackPath,
		djCarpinchoEnabled,
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
	const swipeOffsets = ref(new Map<number, number>());

	// Queue rows need both long-press (open context menu) AND horizontal swipe
	// (delete / move-to-first), so they get their own handler instead of the
	// shared onCtxTouchStart/onCtxTouchEnd (which only knows about long-press).
	let touchStartX = 0;
	let queueLongPressTimer: ReturnType<typeof setTimeout> | null = null;
	let queueLongPressFired = false;

	function queueTouchStart(e: TouchEvent, path: string, i: number) {
		touchStartX = e.changedTouches[0].screenX;
		queueLongPressFired = false;

		queueLongPressTimer = setTimeout(() => {
			queueLongPressFired = true;
			haptic(true);
			openCtxMenu(e, getTrackInfo(path), 'queue', i);
		}, 500);
	}

	function queueTouchMove(e: TouchEvent, index: number) {
		if (Math.abs(e.touches[0].screenX - touchStartX) > 10 && queueLongPressTimer) {
			clearTimeout(queueLongPressTimer);
		}
		const diff = e.touches[0].screenX - touchStartX;
		// Only allow left/right swipes within bounds
		if (diff < 100 && diff > -100) {
			swipeOffsets.value.set(index, diff);
		}
	}

	function queueTouchEnd(e: TouchEvent, index: number) {
		if (queueLongPressTimer) {
			clearTimeout(queueLongPressTimer);
		}

		if (queueLongPressFired) return;

		const diff = touchStartX - e.changedTouches[0].screenX;

		if (diff > 80) {
			haptic(true);
			removeQueueItemCmd(index); // Vue's TransitionGroup handles the animation automatically!
		} else if (diff < -80) {
			haptic();
			moveQueueItem(index, 'first');
		}

		// Reset the offset reactively
		swipeOffsets.value.delete(index);
	}

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

	// --- Unified Queue Computation ---
	interface UnifiedTrackItem {
		id: string;
		path: string;
		status: 'history' | 'current' | 'queue';
		index: number;
		historyIndex?: number;
		queueIndex?: number;
	}

	const unifiedQueue = computed<UnifiedTrackItem[]>(() => {
		const list: UnifiedTrackItem[] = [];
		let idx = 0;

		for (let i = 0; i < historyState.value.length; i++) {
			const path = historyState.value[i];
			list.push({
				id: `hist-${i}-${path}`,
				path,
				status: 'history',
				index: idx++,
				historyIndex: i,
			});
		}

		if (currentTrackPath.value) {
			list.push({
				id: `current-${currentTrackPath.value}`,
				path: currentTrackPath.value,
				status: 'current',
				index: idx++,
			});
		}

		for (let i = 0; i < queueState.value.length; i++) {
			const path = queueState.value[i];
			list.push({
				id: `queue-${i}-${path}`,
				path,
				status: 'queue',
				index: idx++,
				queueIndex: i,
			});
		}

		return list;
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

	// --- Drag & Drop Handlers ---
	const dragFromIndex = ref<number | null>(null);

	function dragStart(e: DragEvent, index: number) {
		dragFromIndex.value = index;
		(e.currentTarget as HTMLElement)?.classList?.add('opacity-40');

		if (e.dataTransfer) {
			e.dataTransfer.effectAllowed = 'move';
			const item = unifiedQueue.value[index];
			if (item && typeof e.dataTransfer.setData === 'function') {
				e.dataTransfer.setData('text/plain', item.path);
			}
		}
	}

	function dragOver(e: DragEvent, index: number) {
		if (dragFromIndex.value === null || dragFromIndex.value === index) return;

		const target = e.currentTarget as HTMLElement | null;
		if (!target) return;

		const rect = target.getBoundingClientRect ? target.getBoundingClientRect() : { top: 0, height: 0 };
		const midY = (rect.top || 0) + (rect.height || 0) / 2;

		target.classList?.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

		if ((e.clientY ?? 0) < midY) {
			target.classList?.add('border-t-2', 'border-carpincho-primary');
		} else {
			target.classList?.add('border-b-2', 'border-carpincho-primary');
		}
	}

	function dragLeave(e: DragEvent) {
		const target = e.currentTarget as HTMLElement | null;
		target?.classList?.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');
	}

	function dragDrop(e: DragEvent, toIndex: number) {
		const target = e.currentTarget as HTMLElement | null;
		target?.classList?.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

		if (dragFromIndex.value === null || dragFromIndex.value === toIndex) return;

		const rect = target?.getBoundingClientRect ? target.getBoundingClientRect() : { top: 0, height: 0 };
		const midY = (rect.top || 0) + (rect.height || 0) / 2;

		let finalIndex = (e.clientY ?? 0) < midY ? toIndex : toIndex + 1;
		if (finalIndex > dragFromIndex.value) finalIndex--;

		if (finalIndex !== dragFromIndex.value) {
			moveInPlaylist(dragFromIndex.value, finalIndex);
		}

		dragFromIndex.value = null;
	}

	function dragEnd(e: DragEvent) {
		const target = e.currentTarget as HTMLElement | null;
		target?.classList?.remove('opacity-40', 'border-t-2', 'border-b-2', 'border-carpincho-primary');
		dragFromIndex.value = null;
	}

	function dropAtEnd() {
		if (dragFromIndex.value === null) return;
		const lastIndex = unifiedQueue.value.length - 1;
		if (lastIndex >= 0 && dragFromIndex.value !== lastIndex) {
			moveInPlaylist(dragFromIndex.value, lastIndex);
		}
		dragFromIndex.value = null;
	}
</script>

<template>
	<section class="tab-content bg-carpincho-bg h-full overflow-y-auto">
		<!-- URL Adder -->
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

		<!-- Grid Header -->
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
			<!-- Unified Single List of Tracks -->
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
					<!-- Prefix Slot: Actions / Equalizer / History Checkmark -->
					<template #prefix>
						<!-- History Icon -->
						<template v-if="item.status === 'history'">
							<i class="material-icons text-carpincho-success text-sm">check</i>
						</template>

						<!-- Current Playing Equalizer & Pause-After Button -->
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

						<!-- Queue Actions Column -->
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

					<!-- Track Info: Pause-After Indicator -->
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

			<!-- EMPTY STATE: Cuando no hay nada en la fila ni está sonando nada -->
			<div
				v-if="unifiedQueue.length === 0 && !djCarpinchoEnabled"
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

			<!-- DJ CARPINCHO PLACEHOLDER -->
			<div
				v-if="djCarpinchoEnabled"
				:class="['border-carpincho-border bg-carpincho-panel/50 items-center border-b', trackGridClass]"
			>
				<div class="flex justify-center p-4">
					<i
						class="material-icons text-carpincho-warning"
						:class="{ 'animate-pulse': queueState.length === 0 }"
					>
						auto_awesome
					</i>
				</div>

				<div class="text-carpincho-muted p-4 italic">
					{{
						queueState.length === 0
							? djNextTrack
								? 'DJ Carpincho eligió: ' + (djNextTrack.display_title || djNextTrack.title)
								: 'Eligiendo...'
							: 'Al vaciarse la fila, entra el DJ Carpincho'
					}}
				</div>

				<div class="text-carpincho-muted p-4 italic">
					{{ queueState.length === 0 && djNextTrack ? djNextTrack.display_artist || djNextTrack.artist : '' }}
				</div>

				<div class="hidden p-4 text-right sm:block">🦦</div>
			</div>
		</div>
	</section>
</template>

<style scoped>
	.swipe-row {
		transition: transform 0.3s ease;
		touch-action: manipulation;
	}

	/* Visual feedback when queue item is deleted */
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
