<script setup>
import { ref } from 'vue'
import { usePlayer } from '../composables/usePlayer'
import { useContextMenu } from '../composables/useContextMenu'

const { queueState, historyState, currentTrackPath, djCarpinchoEnabled, djNextTrack, getTrackInfo, sendCmd, haptic, isPaused, pauseAfterPath, togglePauseAfterCurrent } = usePlayer()
const { openCtxMenu } = useContextMenu()

const newUrl = ref('')
const dragFromIndex = ref(null)

// Touch logic variables
let touchStartX = 0;
let ctxLongPressTimer = null;
let _queueLongPressFired = false;

async function addUrl() {
	if (!newUrl.value.trim()) return;
	await sendCmd("add_url", { path: newUrl.value.trim() });
	newUrl.value = '';
}

function removeQueueItem(index, rowEl) {
	const el = rowEl || document.querySelector(`[data-queue-index="${index}"]`);
	if (el) {
		el.classList.add('deleting');
		setTimeout(() => sendCmd("remove_queue_item", { index }), 450);
	} else {
		sendCmd("remove_queue_item", { index });
	}
}

function moveQueueItem(index, target) {
	let newIndex = target === 'first' ? 0 : queueState.value.length - 1;
	if (newIndex !== index) {
		sendCmd("move_queue_item", { index, new_index: newIndex });
	}
}

// --- Touch & Swipe Handlers ---
function queueTouchStart(e, index) {
	touchStartX = e.changedTouches[0].screenX;
	_queueLongPressFired = false;
	const touch = e.touches[0];
	ctxLongPressTimer = setTimeout(() => {
		_queueLongPressFired = true;
		haptic(true);
		openCtxMenu(touch, getTrackInfo(queueState.value[index]), 'queue', index);
	}, 500);
}

function queueTouchMove(e) {
	const dx = Math.abs(e.touches[0].screenX - touchStartX);
	if (dx > 10)
		clearTimeout(ctxLongPressTimer);
}

function queueTouchEnd(e, index) {
	clearTimeout(ctxLongPressTimer);
	if (_queueLongPressFired)
		return;

	let diff = touchStartX - e.changedTouches[0].screenX;
	let row = e.currentTarget;
	if (diff > 80) {
		haptic(true);
		row.style.transform = "translateX(-100vw)";
		setTimeout(() => {
			removeQueueItem(index, row);
			row.style.transform = "translateX(0)";
		}, 250);
	} else if (diff < -80) {
		haptic();
		row.style.transform = "translateX(100vw)";
		setTimeout(() => {
			moveQueueItem(index, 'first');
			row.style.transform = "translateX(0)";
		}, 250);
	} else {
		row.style.transform = "translateX(0)";
	}
}

// --- Drag & Drop Handlers ---
function dragStart(e, index) {
	dragFromIndex.value = index;
	e.currentTarget.classList.add('opacity-40');
	e.dataTransfer.effectAllowed = 'move';
}

function dragOver(e, index) {
	if (dragFromIndex.value === null || dragFromIndex.value === index)
		return;

	const rect = e.currentTarget.getBoundingClientRect();
	const midY = rect.top + rect.height / 2;

	// Clean previous visual classes
	e.currentTarget.classList.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

	// Add visual feedback
	if (e.clientY < midY)
		e.currentTarget.classList.add('border-t-2', 'border-carpincho-primary');
	else
		e.currentTarget.classList.add('border-b-2', 'border-carpincho-primary');
}

function dragLeave(e) {
	e.currentTarget.classList.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');
}

function dragDrop(e, toIndex) {
	e.currentTarget.classList.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');
	if (dragFromIndex.value === null || dragFromIndex.value === toIndex)
		return;

	const rect = e.currentTarget.getBoundingClientRect();
	const midY = rect.top + rect.height / 2;

	let finalIndex = e.clientY < midY ? toIndex : toIndex + 1;
	if (finalIndex > dragFromIndex.value)
		finalIndex--;

	if (finalIndex !== dragFromIndex.value) {
		sendCmd('move_queue_item', { index: dragFromIndex.value, new_index: finalIndex });
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
		<div class="sticky top-0 bg-carpincho-bg px-4 py-3 z-10 shadow-md flex gap-2 items-center">
			<i class="material-icons text-carpincho-success shrink-0">link</i>
			<input v-model="newUrl" type="text" placeholder="Pegá el link de YouTube acá, máquina..."
				class="w-full bg-transparent border-b border-carpincho-primary focus:border-carpincho-secondary outline-none py-2 text-carpincho-text">
			<button @click="addUrl"
				class="bg-green-700 w-10 h-10 shrink-0 flex justify-center items-center rounded-full text-white active:scale-90 transition shadow">
				<i class="material-icons">add</i>
			</button>
		</div>

		<!-- Queue Table -->
		<table class="w-full text-left border-collapse">
			<thead>
				<tr>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel w-28 text-center">Acciones</th>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel">El Temón</th>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel">De quién es</th>
					<th class="p-3 text-carpincho-primary bg-carpincho-panel hidden sm:table-cell w-20 text-right">
						Duración</th>
				</tr>
			</thead>
			<tbody class="overflow-hidden">

				<!-- History Items -->
				<tr v-for="(path, i) in historyState" :key="'hist-' + path" :data-history-path="path"
					@click="sendCmd('jump', { type: 'history', index: i })"
					@contextmenu.prevent="openCtxMenu($event, getTrackInfo(path), 'history', i)"
					class="border-b border-carpincho-border hover:bg-carpincho-border cursor-pointer opacity-70">
					<td class="p-4 text-carpincho-success text-center">
						<i class="material-icons text-sm">check</i>
					</td>
					<td class="p-4 max-w-[200px] truncate">{{ getTrackInfo(path).display_title }}</td>
					<td class="p-4 text-[#a6adc8] truncate">{{ getTrackInfo(path).display_artist }}</td>
					<td class="p-4 text-[#a6adc8] hidden sm:table-cell text-right">{{ getTrackInfo(path).duration_str }}
					</td>
				</tr>

				<!-- Current Track -->
				<tr v-if="currentTrackPath" id="current-queue-row" @click="sendCmd('pause')"
					class="border-b border-carpincho-border bg-carpincho-panel cursor-pointer">
					<td class="p-4 text-carpincho-primary font-bold text-center" @click.stop>
						<div class="items-center gap-1">
							<div :class="['equalizer', isPaused ? 'paused' : '']">
								<span></span><span></span><span></span>
							</div>
							<button @click="togglePauseAfterCurrent(); haptic()"
								:title="pauseAfterPath === currentTrackPath ? 'Cancelar pausa al terminar' : 'Frenar tras este tema'"
								:class="['transition active:scale-90', pauseAfterPath === currentTrackPath ? 'text-carpincho-warning' : 'text-gray-500 hover:text-carpincho-warning']">
								<i class="material-icons text-lg">timer</i>
							</button>
						</div>
					</td>
					<td class="p-4 text-carpincho-primary font-bold max-w-[200px] truncate">{{
						getTrackInfo(currentTrackPath).display_title }}</td>
					<td class="p-4 text-carpincho-primary truncate">{{ getTrackInfo(currentTrackPath).display_artist }}
					</td>
					<td class="p-4 text-carpincho-primary hidden sm:table-cell text-right">{{
						getTrackInfo(currentTrackPath).duration_str }}</td>
				</tr>

				<!-- Render queued items -->
				<tr v-for="(path, i) in queueState" :key="path" :data-queue-index="i" draggable="true"
					@dragstart="dragStart($event, i)" @dragover.prevent="dragOver($event, i)"
					@dragleave="dragLeave($event)" @drop.prevent="dragDrop($event, i)" @dragend="dragEnd($event)"
					@touchstart="queueTouchStart($event, i)" @touchend="queueTouchEnd($event, i)"
					@touchmove="queueTouchMove($event)"
					@contextmenu.prevent="openCtxMenu($event, getTrackInfo(path), 'queue', i)"
					class="swipe-row border-b border-carpincho-border hover:bg-carpincho-border cursor-pointer transition-all duration-200">

					<!-- Actions Column -->
					<td class="p-4" @click.stop>
						<div class="flex items-center justify-center gap-2">
							<i
								class="material-icons text-gray-500 cursor-grab active:cursor-grabbing hidden sm:block select-none">drag_indicator</i>
							<i @click="moveQueueItem(i, 'first')"
								class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition">vertical_align_top</i>
							<i @click="moveQueueItem(i, 'last')"
								class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition">vertical_align_bottom</i>
							<i @click="removeQueueItem(i, $event.currentTarget.closest('tr'))"
								class="material-icons text-carpincho-secondary hidden sm:block hover:text-red-400 transition">delete</i>
						</div>
					</td>

					<!-- Track Info -->
					<td class="p-4 max-w-[200px]" @click="sendCmd('jump', { type: 'queue', index: i })">
						<span class="truncate block">{{ getTrackInfo(path).display_title }}</span>
					</td>
					<td class="p-4 text-[#a6adc8]" @click="sendCmd('jump', { type: 'queue', index: i })">
						{{ getTrackInfo(path).display_artist }}
					</td>
					<td class="p-4 text-[#a6adc8] hidden sm:table-cell text-right"
						@click="sendCmd('jump', { type: 'queue', index: i })">{{ getTrackInfo(path).duration_str }}
					</td>
				</tr>

				<!-- EMPTY STATE: Cuando no hay nada en la fila ni está sonando nada -->
				<tr v-if="queueState.length === 0 && !currentTrackPath" class="border-b border-carpincho-border">
					<td colspan="4" class="p-12 text-center">
						<div class="flex flex-col items-center gap-4 text-carpincho-primary opacity-80">
							<p class="font-bold text-lg">El Carpincho está esperando el mate...</p>
							<p class="text-sm">Agregá música para que empiece a cantar.</p>
						</div>
					</td>
				</tr>

				<!-- DJ Carpincho Placeholder -->
				<tr v-if="djCarpinchoEnabled" class="border-b border-carpincho-border bg-carpincho-panel/50">
					<td class="p-4 flex justify-center">
						<i class="material-icons text-carpincho-warning"
							:class="{ 'animate-pulse': queueState.length === 0 }">auto_awesome</i>
					</td>
					<td class="p-4 italic" :class="queueState.length === 0 ? 'text-[#a6adc8]' : 'text-[#a6adc8]'">
						{{ queueState.length === 0 ? (djNextTrack ? 'DJ Carpincho eligió: ' + djNextTrack.display_title
							:
							'Eligiendo...') : 'Al vaciarse la fila, entra el DJ Carpincho' }}
					</td>
					<td class="p-4 text-[#a6adc8] italic">🦦</td>
					<td class="p-4 text-[#a6adc8] hidden sm:table-cell text-right"></td>
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

/* Drag & Drop en la fila */
.drag-over-top {
	border-top: 2px solid #a67c52 !important;
}

.drag-over-bottom {
	border-bottom: 2px solid #a67c52 !important;
}

tr.dragging {
	opacity: 0.4;
}
</style>
