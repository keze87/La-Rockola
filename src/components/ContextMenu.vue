<script setup>
import { useContextMenu } from '../composables/useContextMenu'
import { usePlayer } from '../composables/usePlayer'

const { ctxMenu, closeCtxMenu } = useContextMenu()
const { sendCmd, queueState, historyState, favorites, currentTrackPath, toggleFavorite, switchTab, librarySearchQuery } = usePlayer()

function ctxFilterByArtist() {
	const track = ctxMenu.track;
	closeCtxMenu();
	librarySearchQuery.value = track.artist || track.display_artist || '';
	switchTab('library');
}

// --- Shared Actions ---
async function ctxPlayNow() {
	const track = ctxMenu.track;
	closeCtxMenu();
	await sendCmd("play", { path: track.path });
}

async function ctxToggleFavorite() {
	const track = ctxMenu.track;
	closeCtxMenu();
	await toggleFavorite(track.path);
}

async function ctxPauseAfter() {
	const track = ctxMenu.track;
	closeCtxMenu();
	const inQueue = queueState.value.includes(track.path);
	if (!inQueue && currentTrackPath.value !== track.path) {
		await sendCmd("toggle_queue", { path: track.path });
	}
	await sendCmd("pause_after", { path: track.path });
}

// --- Library Source Actions ---
async function ctxPlayNext() {
	const track = ctxMenu.track;
	closeCtxMenu();
	const inQueue = queueState.value.indexOf(track.path);
	if (inQueue !== -1) await sendCmd("remove_queue_item", { index: inQueue });
	const res = await sendCmd("toggle_queue", { path: track.path });
	if (res && res.status === "ok") {
		const newIndex = queueState.value.indexOf(track.path);
		if (newIndex > 0) await sendCmd("move_queue_item", { index: newIndex, new_index: 0 });
	}
}

async function ctxAddToQueue() {
	const track = ctxMenu.track;
	closeCtxMenu();
	if (!queueState.value.includes(track.path)) {
		await sendCmd("toggle_queue", { path: track.path });
	}
}

// --- Queue Source Actions ---
function ctxPlayNextQueue() {
	const index = ctxMenu.index;
	closeCtxMenu();
	if (index !== null && index > 0) {
		sendCmd('move_queue_item', { index, new_index: 0 });
	}
}

function ctxRemoveFromQueue() {
	const index = ctxMenu.index;
	closeCtxMenu();
	if (index !== null) {
		const rowEl = document.querySelector(`[data-queue-index="${index}"]`);
		if (rowEl) {
			rowEl.classList.add('deleting');
			setTimeout(() => sendCmd("remove_queue_item", { index }), 450);
		} else {
			sendCmd("remove_queue_item", { index });
		}
	}
}

// --- History Source Actions ---
function ctxHistoryPlayAgain() {
	const track = ctxMenu.track;
	closeCtxMenu();
	sendCmd('toggle_queue', { path: track.path || historyState.value[ctxMenu.index] });
}

function ctxRemoveFromHistory() {
	const index = ctxMenu.index;
	closeCtxMenu();
	if (index !== null) {
		const rowEl = document.querySelector(`[data-history-path="${historyState.value[index]}"]`);
		if (rowEl) {
			rowEl.classList.add('deleting');
			setTimeout(() => sendCmd('remove_history_item', { index }), 450);
		} else {
			sendCmd('remove_history_item', { index });
		}
	}
}
</script>

<template>
	<div v-if="ctxMenu.visible" class="fixed inset-0 z-[9998]" @click.self="closeCtxMenu"
		@contextmenu.prevent="closeCtxMenu">
		<div class="ctx-menu absolute bg-carpincho-panel border border-carpincho-border rounded-xl shadow-2xl overflow-hidden animate-[ctx-appear_0.15s_ease]"
			:style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px', minWidth: '220px' }">

			<div
				class="px-4 py-2 border-b border-carpincho-border text-xs font-bold uppercase tracking-widest text-carpincho-primary truncate max-w-[300px]">
				🦦 {{ ctxMenu.track?.title || ctxMenu.track?.display_title }}
			</div>

			<!-- LIBRARY ACTIONS -->
			<template v-if="ctxMenu.source === 'library'">
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxPlayNext">
					<i class="material-icons text-carpincho-primary">queue_play_next</i> Que suene de próximo
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxPlayNow">
					<i class="material-icons text-carpincho-primary">play_arrow</i> Mandale play de una
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxAddToQueue">
					<i class="material-icons text-carpincho-primary">playlist_add</i> Al fondo de la fila
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxToggleFavorite">
					<i class="material-icons text-carpincho-primary">{{ favorites?.includes(ctxMenu.track?.path) ?
						'favorite_border' : 'favorite' }}</i>
					{{ favorites?.includes(ctxMenu.track?.path) ? 'Sacar de favoritos' : 'A los favoritos' }}
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxFilterByArtist">
					<i class="material-icons text-carpincho-primary">person_search</i> Chusmear más del artista
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxPauseAfter">
					<i class="material-icons text-carpincho-primary">timer</i> Frenar la chata tras este tema
				</div>
			</template>

			<!-- QUEUE ACTIONS -->
			<template v-if="ctxMenu.source === 'queue'">
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxPlayNextQueue">
					<i class="material-icons text-carpincho-primary">vertical_align_top</i> Subir a próximo
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxPlayNow">
					<i class="material-icons text-carpincho-primary">play_arrow</i> Mandale play de una
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxToggleFavorite">
					<i class="material-icons text-carpincho-primary">{{ favorites?.includes(ctxMenu.track?.path) ?
						'favorite_border' : 'favorite' }}</i>
					{{ favorites?.includes(ctxMenu.track?.path) ? 'Sacar de favoritos' : 'A los favoritos' }}
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxPauseAfter">
					<i class="material-icons text-carpincho-primary">timer</i> Frenar la chata tras este tema
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxFilterByArtist">
					<i class="material-icons text-carpincho-primary">person_search</i> Buscar en la librería
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-red-400 hover:bg-red-900/30 transition"
					@click="ctxRemoveFromQueue">
					<i class="material-icons text-red-400">delete</i> Pegarle un voleo
				</div>
			</template>

			<!-- HISTORY ACTIONS -->
			<template v-if="ctxMenu.source === 'history'">
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxHistoryPlayAgain">
					<i class="material-icons text-carpincho-primary">add_circle_outline</i> Agregar a la fila
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxToggleFavorite">
					<i class="material-icons text-carpincho-primary">{{ favorites?.includes(ctxMenu.track?.path) ?
						'favorite_border' : 'favorite' }}</i>
					{{ favorites?.includes(ctxMenu.track?.path) ? 'Sacar de favoritos' : 'A los favoritos' }}
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-[#e8d5c4] hover:bg-[#2b2622] transition"
					@click="ctxFilterByArtist">
					<i class="material-icons text-carpincho-primary">person_search</i> Buscar en la librería
				</div>
				<div class="flex items-center gap-3 p-3 cursor-pointer text-red-400 hover:bg-red-900/30 transition"
					@click="ctxRemoveFromHistory">
					<i class="material-icons text-red-400">delete</i> Borrar del historial
				</div>
			</template>

		</div>
	</div>
</template>

<style scoped>
@keyframes ctx-appear {
	from {
		opacity: 0;
		transform: scale(0.92);
	}

	to {
		opacity: 1;
		transform: scale(1);
	}
}
</style>