<script setup lang="ts">
	import { ref, watch } from 'vue';
	import { useContextMenu } from '../composables/useContextMenu';
	import { usePlayer } from '../composables/usePlayer';

	const { ctxMenu, closeCtxMenu } = useContextMenu();
	const {
		currentTrackPath,
		favorites,
		haptic,
		historyState,
		librarySearchQuery,
		pauseAfterPath,
		queueState,
		sendCmd,
		showToast,
		switchTab,
		toggleFavorite,
	} = usePlayer();

	// Whether the focus ring should be shown. We can't rely on CSS
	// `:focus-visible` alone: opening the menu always focuses the first item
	// programmatically (so keyboard users can drive it at all), and some
	// browsers treat that as focus-visible-worthy even when the menu was
	// opened with a mouse/touch. Tracking real keyup navigation ourselves
	// keeps the ring tied to actually navigating by keyboard.
	const keyboardNav = ref(false);

	watch(
		() => ctxMenu.visible,
		(visible) => {
			if (visible) keyboardNav.value = false;
		}
	);

	function ctxFilterByArtist() {
		const track = ctxMenu.track;

		if (!track) return;

		closeCtxMenu();
		librarySearchQuery.value = track.artist || track.display_artist || '';
		switchTab('library');
		haptic();
	}

	// Arrow keys move focus between items, Escape closes and returns focus to
	// the row that opened the menu, and Tab is trapped inside the menu while
	// it's open - without this the menu can only be driven with a mouse/touch.
	function ctxMenuKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			closeCtxMenu();
			return;
		}
		const items = Array.from(
			(e.currentTarget as HTMLElement).querySelectorAll('[role="menuitem"]')
		) as HTMLElement[];

		if (items.length === 0) return;

		const currentIndex = items.indexOf(document.activeElement as HTMLElement);

		if (e.key === 'ArrowDown') {
			e.preventDefault();
			keyboardNav.value = true;
			items[(currentIndex + 1) % items.length].focus();
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			keyboardNav.value = true;
			items[(currentIndex - 1 + items.length) % items.length].focus();
		} else if (e.key === 'Tab') {
			keyboardNav.value = true;

			if (e.shiftKey && currentIndex === 0) {
				e.preventDefault();
				items[items.length - 1].focus();
			} else if (!e.shiftKey && currentIndex === items.length - 1) {
				e.preventDefault();
				items[0].focus();
			}
		}
	}

	// --- Shared Actions ---
	async function ctxPlayNow() {
		const track = ctxMenu.track;

		if (!track) return;

		closeCtxMenu();
		await sendCmd('play', { path: track.path });
		haptic();
	}

	async function ctxToggleFavorite() {
		const track = ctxMenu.track;

		if (!track) return;

		closeCtxMenu();
		await toggleFavorite(track.path);
		haptic();
	}

	async function ctxPauseAfter() {
		const track = ctxMenu.track;

		if (!track) return;

		closeCtxMenu();

		if (pauseAfterPath.value === track.path) {
			pauseAfterPath.value = null;
			await sendCmd('pause_after', { path: '' });
			showToast(`Cancelamos la pausa al terminar 🤠`, 'info');
			haptic();
			return;
		}

		const inQueue = queueState.value.includes(track.path);

		if (!inQueue && currentTrackPath.value !== track.path) {
			await sendCmd('toggle_queue', { path: track.path });
		}

		pauseAfterPath.value = track.path;
		await sendCmd('pause_after', { path: track.path });
		showToast({ prefix: 'Frenamos la joda después de ', highlight: track.title || track.display_title }, 'warning');
		haptic();
	}

	// --- Library Source Actions ---
	async function ctxPlayNext() {
		const track = ctxMenu.track;

		if (!track) return;

		closeCtxMenu();

		const inQueue = queueState.value.indexOf(track.path);

		if (inQueue !== -1) await sendCmd('remove_queue_item', { index: inQueue });

		const res = await sendCmd('toggle_queue', { path: track.path });

		if (res && res.status === 'ok') {
			const newIndex = queueState.value.indexOf(track.path);

			if (newIndex > 0) await sendCmd('move_queue_item', { index: newIndex, new_index: 0 });
		}

		haptic();
	}

	async function ctxAddToQueue() {
		const track = ctxMenu.track;
		if (!track) return;
		closeCtxMenu();

		if (!queueState.value.includes(track.path)) {
			await sendCmd('toggle_queue', { path: track.path });
		}

		haptic();
	}

	// --- Queue Source Actions ---
	function ctxPlayNextQueue() {
		const index = ctxMenu.index;
		closeCtxMenu();

		if (index !== null && index > 0) {
			sendCmd('move_queue_item', { index, new_index: 0 });
		}

		haptic();
	}

	function ctxRemoveFromQueue() {
		const index = ctxMenu.index;
		closeCtxMenu();

		if (index !== null) {
			const rowEl = document.querySelector(`[data-queue-index="${index}"]`);

			if (rowEl) {
				rowEl.classList.add('deleting');
				setTimeout(() => sendCmd('remove_queue_item', { index }), 450);
			} else {
				sendCmd('remove_queue_item', { index });
			}

			showToast('¡Voleo en el orto! Afuera de la fila', 'error');
			haptic();
		}
	}

	// --- History Source Actions ---
	function ctxHistoryPlayAgain() {
		const track = ctxMenu.track;

		if (ctxMenu.index === null) return;

		closeCtxMenu();
		sendCmd('toggle_queue', { path: track?.path || historyState.value[ctxMenu.index] });
		haptic();
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

			showToast(`Borrado del historial`, 'warning');
			haptic();
		}
	}
</script>

<template>
	<div
		v-if="ctxMenu.visible"
		class="fixed inset-0 z-[9998]"
		@click.self="closeCtxMenu"
		@contextmenu.prevent="closeCtxMenu"
	>
		<div
			class="ctx-menu absolute"
			role="menu"
			aria-labelledby="ctx-menu-title"
			:class="{ 'kbd-nav': keyboardNav }"
			:style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }"
			@keydown="ctxMenuKeydown"
			@pointerdown="keyboardNav = false"
		>
			<div id="ctx-menu-title" class="ctx-menu-header truncate">
				🦦 {{ ctxMenu.track?.title || ctxMenu.track?.display_title }}
			</div>

			<!-- LIBRARY ACTIONS -->
			<template v-if="ctxMenu.source === 'library'">
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxPlayNext">
					<i class="material-icons">queue_play_next</i>
					Que suene de próximo
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxPlayNow">
					<i class="material-icons">play_arrow</i>
					Mandale play de una
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxAddToQueue">
					<i class="material-icons">playlist_add</i>
					Al fondo de la fila
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxToggleFavorite">
					<i class="material-icons">
						{{ favorites?.includes(ctxMenu.track?.path || '') ? 'favorite' : 'favorite_border' }}
					</i>
					{{ favorites?.includes(ctxMenu.track?.path || '') ? 'Sacar de favoritos' : 'A los favoritos' }}
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxFilterByArtist">
					<i class="material-icons">person_search</i>
					Chusmear más del artista
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxPauseAfter">
					<i class="material-icons">timer</i>
					Frenar la chata tras este tema
				</button>
			</template>

			<!-- QUEUE ACTIONS -->
			<template v-if="ctxMenu.source === 'queue'">
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxPlayNextQueue">
					<i class="material-icons">vertical_align_top</i>
					Subir a próximo
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxPlayNow">
					<i class="material-icons">play_arrow</i>
					Mandale play de una
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxToggleFavorite">
					<i class="material-icons">
						{{ favorites?.includes(ctxMenu.track?.path || '') ? 'favorite' : 'favorite_border' }}
					</i>
					{{ favorites?.includes(ctxMenu.track?.path || '') ? 'Sacar de favoritos' : 'A los favoritos' }}
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxPauseAfter">
					<i class="material-icons">timer</i>
					Frenar la chata tras este tema
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxFilterByArtist">
					<i class="material-icons">person_search</i>
					Buscar en la librería
				</button>
				<button type="button" class="ctx-menu-item delete-item" role="menuitem" @click="ctxRemoveFromQueue">
					<i class="material-icons text-red-400">delete</i>
					<span class="text-red-400">Pegarle un voleo</span>
				</button>
			</template>

			<!-- HISTORY ACTIONS -->
			<template v-if="ctxMenu.source === 'history'">
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxHistoryPlayAgain">
					<i class="material-icons">add_circle_outline</i>
					Agregar a la fila
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxToggleFavorite">
					<i class="material-icons">
						{{ favorites?.includes(ctxMenu.track?.path || '') ? 'favorite' : 'favorite_border' }}
					</i>
					{{ favorites?.includes(ctxMenu.track?.path || '') ? 'Sacar de favoritos' : 'A los favoritos' }}
				</button>
				<button type="button" class="ctx-menu-item" role="menuitem" @click="ctxFilterByArtist">
					<i class="material-icons">person_search</i>
					Buscar en la librería
				</button>
				<button type="button" class="ctx-menu-item delete-item" role="menuitem" @click="ctxRemoveFromHistory">
					<i class="material-icons text-red-400">delete</i>
					<span class="text-red-400">Borrar del historial</span>
				</button>
			</template>
		</div>
	</div>
</template>

<style scoped>
	.ctx-menu {
		background: var(--color-carpincho-panel);
		border-radius: 12px;
		border: 1px solid var(--color-carpincho-border);
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
		min-width: 220px;
		overflow: hidden;
	}

	.ctx-menu-header {
		border-bottom: 1px solid var(--color-carpincho-border);
		color: var(--color-carpincho-primary);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		padding: 10px 16px 8px;
		text-transform: uppercase;
	}

	.ctx-menu-item {
		align-items: center;
		background: none;
		border: none;
		color: var(--color-carpincho-text);
		cursor: pointer;
		display: flex;
		font: inherit;
		font-size: 0.92rem;
		gap: 10px;
		padding: 12px 16px;
		text-align: left;
		transition: background 0.12s;
		width: 100%;
	}

	.ctx-menu-item:hover,
	.ctx-menu-item:active {
		background: var(--color-carpincho-bg);
	}

	.ctx-menu-item:focus {
		outline: none;
	}

	.ctx-menu.kbd-nav .ctx-menu-item:focus {
		background: var(--color-carpincho-bg);
		outline: 2px solid var(--color-carpincho-warning);
		outline-offset: -2px;
	}

	.ctx-menu-item i {
		color: var(--color-carpincho-primary);
		font-size: 1.1rem;
	}

	.ctx-menu-item.delete-item:hover,
	.ctx-menu-item.delete-item:active {
		background: rgba(239, 68, 68, 0.3) !important;
	}

	.ctx-menu.kbd-nav .ctx-menu-item.delete-item:focus {
		background: rgba(239, 68, 68, 0.3) !important;
	}
</style>
