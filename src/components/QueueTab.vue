<script setup>
	import { ref } from 'vue';
	import { usePlayer } from '../composables/usePlayer';
	import { useContextMenu } from '../composables/useContextMenu';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import TrackRow from './ui/TrackRow.vue';

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
		moveQueueItem: moveQueueItemCmd,
		pause,
		removeQueueItem: removeQueueItemCmd,
	} = usePlaybackControls();

	const newUrl = ref('');
	const dragFromIndex = ref(null);

	// Queue rows need both long-press (open context menu) AND horizontal swipe
	// (delete / move-to-first), so they get their own handler instead of the
	// shared onCtxTouchStart/onCtxTouchEnd (which only knows about long-press).
	let touchStartX = 0;
	let queueLongPressTimer = null;
	let queueLongPressFired = false;

	function queueTouchStart(e, path, i) {
		touchStartX = e.changedTouches[0].screenX;
		queueLongPressFired = false;

		queueLongPressTimer = setTimeout(() => {
			queueLongPressFired = true;
			haptic(true);
			openCtxMenu(e, getTrackInfo(path), 'queue', i);
		}, 500);
	}

	function queueTouchMove(e) {
		if (Math.abs(e.touches[0].screenX - touchStartX) > 10) clearTimeout(queueLongPressTimer);
	}

	function queueTouchEnd(e, index) {
		clearTimeout(queueLongPressTimer);

		if (queueLongPressFired) return;

		const diff = touchStartX - e.changedTouches[0].screenX;
		const row = e.currentTarget;

		if (diff > 80) {
			haptic(true);
			row.style.transform = 'translateX(-100vw)';
			setTimeout(() => {
				removeQueueItem(index, row);
				row.style.transform = 'translateX(0)';
			}, 250);
		} else if (diff < -80) {
			haptic();
			row.style.transform = 'translateX(100vw)';
			setTimeout(() => {
				moveQueueItem(index, 'first');
				row.style.transform = 'translateX(0)';
			}, 250);
		} else {
			row.style.transform = 'translateX(0)';
		}
	}

	async function addUrl() {
		if (!newUrl.value.trim()) return;

		await addUrlCmd(newUrl.value.trim());
		newUrl.value = '';
	}

	function removeQueueItem(index, rowEl) {
		const el = rowEl || document.querySelector(`[data-queue-index="${index}"]`);

		if (el) {
			el.classList.add('deleting');
			setTimeout(() => removeQueueItemCmd(index), 450);
		} else {
			removeQueueItemCmd(index);
		}
	}

	function moveQueueItem(index, target) {
		let newIndex = target === 'first' ? 0 : queueState.value.length - 1;

		if (newIndex !== index) {
			moveQueueItemCmd(index, newIndex);
		}
	}

	// --- Drag & Drop Handlers ---
	function dragStart(e, index) {
		dragFromIndex.value = index;
		e.currentTarget.classList.add('opacity-40');
		e.dataTransfer.effectAllowed = 'move';
	}

	function dragOver(e, index) {
		if (dragFromIndex.value === null || dragFromIndex.value === index) return;

		const rect = e.currentTarget.getBoundingClientRect();
		const midY = rect.top + rect.height / 2;

		// Clean previous visual classes
		e.currentTarget.classList.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

		// Add visual feedback
		if (e.clientY < midY) e.currentTarget.classList.add('border-t-2', 'border-carpincho-primary');
		else e.currentTarget.classList.add('border-b-2', 'border-carpincho-primary');
	}

	function dragLeave(e) {
		e.currentTarget.classList.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');
	}

	function dragDrop(e, toIndex) {
		e.currentTarget.classList.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

		if (dragFromIndex.value === null || dragFromIndex.value === toIndex) return;

		const rect = e.currentTarget.getBoundingClientRect();
		const midY = rect.top + rect.height / 2;

		let finalIndex = e.clientY < midY ? toIndex : toIndex + 1;

		if (finalIndex > dragFromIndex.value) finalIndex--;

		if (finalIndex !== dragFromIndex.value) {
			moveQueueItemCmd(dragFromIndex.value, finalIndex);
		}

		dragFromIndex.value = null;
	}

	function dragEnd(e) {
		e.currentTarget.classList.remove('opacity-40', 'border-t-2', 'border-b-2', 'border-carpincho-primary');
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
			<button
				class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-green-700 text-white shadow transition active:scale-90"
				@click="addUrl"
			>
				<i class="material-icons">add</i>
			</button>
		</div>

		<!-- Queue Table -->
		<table class="w-full table-fixed border-collapse text-left">
			<thead>
				<tr>
					<th class="text-carpincho-primary bg-carpincho-panel w-40 p-3 text-center">Acciones</th>
					<th class="text-carpincho-primary bg-carpincho-panel p-3">El Temón</th>
					<th class="text-carpincho-primary bg-carpincho-panel p-3">De quién es</th>
					<th class="text-carpincho-primary bg-carpincho-panel hidden w-20 p-3 text-right sm:table-cell">
						Duración
					</th>
				</tr>
			</thead>
			<tbody class="overflow-hidden">
				<!-- History Items -->
				<TrackRow
					v-for="(path, i) in historyState"
					:key="'hist-' + path"
					:data-history-path="path"
					:track="getTrackInfo(path)"
					context-source="history"
					:index="i"
					class="opacity-70"
					@click="jumpToHistory(i)"
				>
					<template #prefix>
						<i class="material-icons text-carpincho-success text-sm">check</i>
					</template>
				</TrackRow>

				<!-- Current Track -->
				<TrackRow
					v-if="currentTrackPath"
					id="current-queue-row"
					:track="getTrackInfo(currentTrackPath)"
					context-source="queue"
					@click="pause"
				>
					<template #prefix>
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
									'flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition active:scale-90',
									pauseAfterPath === currentTrackPath
										? 'text-carpincho-warning drop-shadow-[0_0_8px_rgba(233,196,106,0.8)]'
										: 'hover:text-carpincho-warning text-gray-500 hover:bg-black/20 active:bg-black/30',
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
				</TrackRow>

				<!-- Render queued items -->
				<TrackRow
					v-for="(path, i) in queueState"
					:key="path"
					:data-queue-index="i"
					:track="getTrackInfo(path)"
					context-source="queue"
					:index="i"
					context-menu-only
					draggable="true"
					class="swipe-row"
					@click="jumpToQueue(i)"
					@dragstart="dragStart($event, i)"
					@dragover.prevent="dragOver($event, i)"
					@dragleave="dragLeave($event)"
					@drop.prevent="dragDrop($event, i)"
					@dragend="dragEnd($event)"
					@touchstart="queueTouchStart($event, path, i)"
					@touchend="queueTouchEnd($event, i)"
					@touchmove="queueTouchMove($event)"
				>
					<!-- Actions Column -->
					<template #prefix>
						<div class="flex items-center justify-center gap-1" @click.stop>
							<button
								type="button"
								class="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-black/20 active:bg-black/30"
								title="Subir a próximo"
								@click="moveQueueItem(i, 'first')"
							>
								<i
									class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition"
								>
									vertical_align_top
								</i>
							</button>
							<button
								type="button"
								class="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-black/20 active:bg-black/30"
								title="Mover al final"
								@click="moveQueueItem(i, 'last')"
							>
								<i
									class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition"
								>
									vertical_align_bottom
								</i>
							</button>
							<button
								type="button"
								class="hidden h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-red-500/20 active:bg-red-500/30 sm:flex"
								title="Sacar de la fila"
								@click="removeQueueItem(i, $event.currentTarget.closest('tr'))"
							>
								<i class="material-icons text-carpincho-secondary transition hover:text-red-400">
									delete
								</i>
							</button>
						</div>
					</template>

					<!-- Track Info -->
					<template #title-extra>
						<i
							v-if="path === pauseAfterPath"
							class="material-icons text-carpincho-warning shrink-0 text-sm"
							title="Se frena acá"
						>
							timer
						</i>
					</template>
				</TrackRow>

				<!-- EMPTY STATE: Cuando no hay nada en la fila ni está sonando nada -->
				<tr
					v-if="queueState.length === 0 && !currentTrackPath && !djCarpinchoEnabled"
					class="border-carpincho-border border-b"
				>
					<td colspan="4" class="p-12 text-center">
						<div class="text-carpincho-primary flex flex-col items-center gap-4 opacity-80">
							<p class="text-lg font-bold">El Carpincho está esperando el mate...</p>
							<p class="text-sm">Agregá música para que empiece a cantar.</p>
						</div>
					</td>
				</tr>

				<!-- DJ Carpincho Placeholder -->
				<tr v-if="djCarpinchoEnabled" class="border-carpincho-border bg-carpincho-panel/50 border-b">
					<td class="flex justify-center p-4">
						<i
							class="material-icons text-carpincho-warning"
							:class="{ 'animate-pulse': queueState.length === 0 }"
						>
							auto_awesome
						</i>
					</td>
					<td
						class="p-4 italic"
						:class="queueState.length === 0 ? 'text-carpincho-muted' : 'text-carpincho-muted'"
					>
						{{
							queueState.length === 0
								? djNextTrack
									? 'DJ Carpincho eligió: ' + (djNextTrack.display_title || djNextTrack.title)
									: 'Eligiendo...'
								: 'Al vaciarse la fila, entra el DJ Carpincho'
						}}
					</td>
					<td class="text-carpincho-muted p-4 italic">
						{{
							queueState.length === 0 && djNextTrack
								? djNextTrack.display_artist || djNextTrack.artist
								: ''
						}}
					</td>
					<td class="text-carpincho-muted hidden p-4 text-right sm:table-cell">🦦</td>
				</tr>
			</tbody>
		</table>
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
