<script setup>
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

    function ctxFilterByArtist() {
        const track = ctxMenu.track;
        closeCtxMenu();
        librarySearchQuery.value = track.artist || track.display_artist || '';
        switchTab('library');
        haptic();
    }

    // --- Shared Actions ---
    async function ctxPlayNow() {
        const track = ctxMenu.track;
        closeCtxMenu();
        await sendCmd('play', { path: track.path });
        haptic();
    }

    async function ctxToggleFavorite() {
        const track = ctxMenu.track;
        closeCtxMenu();
        await toggleFavorite(track.path);
        haptic();
    }

    async function ctxPauseAfter() {
        const track = ctxMenu.track;
        closeCtxMenu();

        if (pauseAfterPath.value === track.path) {
            pauseAfterPath.value = null;
            await sendCmd('pause_after', { path: '' });
            showToast(`Cancelamos la pausa al terminar 🦦`, 'info');
            haptic();
            return;
        }

        const inQueue = queueState.value.includes(track.path);
        if (!inQueue && currentTrackPath.value !== track.path) {
            await sendCmd('toggle_queue', { path: track.path });
        }

        pauseAfterPath.value = track.path;
        await sendCmd('pause_after', { path: track.path });
        showToast(`Frenamos la joda después de <b>${track.title || track.display_title}</b> ⏸`, 'warning');
        haptic();
    }

    // --- Library Source Actions ---
    async function ctxPlayNext() {
        const track = ctxMenu.track;
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
            haptic();
        }
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

            showToast('¡Voleo en el orto! Afuera de la fila', 'warning');
            haptic();
        }
    }

    // --- History Source Actions ---
    function ctxHistoryPlayAgain() {
        const track = ctxMenu.track;
        closeCtxMenu();
        sendCmd('toggle_queue', { path: track.path || historyState.value[ctxMenu.index] });
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
        <div class="ctx-menu absolute" :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }">
            <div class="ctx-menu-header truncate">🦦 {{ ctxMenu.track?.title || ctxMenu.track?.display_title }}</div>

            <!-- LIBRARY ACTIONS -->
            <template v-if="ctxMenu.source === 'library'">
                <div class="ctx-menu-item" @click="ctxPlayNext">
                    <i class="material-icons">queue_play_next</i>
                    Que suene de próximo
                </div>
                <div class="ctx-menu-item" @click="ctxPlayNow">
                    <i class="material-icons">play_arrow</i>
                    Mandale play de una
                </div>
                <div class="ctx-menu-item" @click="ctxAddToQueue">
                    <i class="material-icons">playlist_add</i>
                    Al fondo de la fila
                </div>
                <div class="ctx-menu-item" @click="ctxToggleFavorite">
                    <i class="material-icons">
                        {{ favorites?.includes(ctxMenu.track?.path) ? 'favorite_border' : 'favorite' }}
                    </i>
                    {{ favorites?.includes(ctxMenu.track?.path) ? 'Sacar de favoritos' : 'A los favoritos' }}
                </div>
                <div class="ctx-menu-item" @click="ctxFilterByArtist">
                    <i class="material-icons">person_search</i>
                    Chusmear más del artista
                </div>
                <div class="ctx-menu-item" @click="ctxPauseAfter">
                    <i class="material-icons">timer</i>
                    Frenar la chata tras este tema
                </div>
            </template>

            <!-- QUEUE ACTIONS -->
            <template v-if="ctxMenu.source === 'queue'">
                <div class="ctx-menu-item" @click="ctxPlayNextQueue">
                    <i class="material-icons">vertical_align_top</i>
                    Subir a próximo
                </div>
                <div class="ctx-menu-item" @click="ctxPlayNow">
                    <i class="material-icons">play_arrow</i>
                    Mandale play de una
                </div>
                <div class="ctx-menu-item" @click="ctxToggleFavorite">
                    <i class="material-icons">
                        {{ favorites?.includes(ctxMenu.track?.path) ? 'favorite_border' : 'favorite' }}
                    </i>
                    {{ favorites?.includes(ctxMenu.track?.path) ? 'Sacar de favoritos' : 'A los favoritos' }}
                </div>
                <div class="ctx-menu-item" @click="ctxPauseAfter">
                    <i class="material-icons">timer</i>
                    Frenar la chata tras este tema
                </div>
                <div class="ctx-menu-item" @click="ctxFilterByArtist">
                    <i class="material-icons">person_search</i>
                    Buscar en la librería
                </div>
                <div class="ctx-menu-item delete-item" @click="ctxRemoveFromQueue">
                    <i class="material-icons text-red-400">delete</i>
                    <span class="text-red-400">Pegarle un voleo</span>
                </div>
            </template>

            <!-- HISTORY ACTIONS -->
            <template v-if="ctxMenu.source === 'history'">
                <div class="ctx-menu-item" @click="ctxHistoryPlayAgain">
                    <i class="material-icons">add_circle_outline</i>
                    Agregar a la fila
                </div>
                <div class="ctx-menu-item" @click="ctxToggleFavorite">
                    <i class="material-icons">
                        {{ favorites?.includes(ctxMenu.track?.path) ? 'favorite_border' : 'favorite' }}
                    </i>
                    {{ favorites?.includes(ctxMenu.track?.path) ? 'Sacar de favoritos' : 'A los favoritos' }}
                </div>
                <div class="ctx-menu-item" @click="ctxFilterByArtist">
                    <i class="material-icons">person_search</i>
                    Buscar en la librería
                </div>
                <div class="ctx-menu-item delete-item" @click="ctxRemoveFromHistory">
                    <i class="material-icons text-red-400">delete</i>
                    <span class="text-red-400">Borrar del historial</span>
                </div>
            </template>
        </div>
    </div>
</template>

<style scoped>
    .ctx-menu {
        min-width: 220px;
        background: #1f1a17;
        border: 1px solid #4a3f35;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
        overflow: hidden;
    }

    .ctx-menu-header {
        padding: 10px 16px 8px;
        border-bottom: 1px solid #4a3f35;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #a67c52;
    }

    .ctx-menu-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 12px 16px;
        cursor: pointer;
        color: #e8d5c4;
        font-size: 0.92rem;
        transition: background 0.12s;
    }

    .ctx-menu-item:hover,
    .ctx-menu-item:active {
        background: #2b2622;
    }

    .ctx-menu-item i {
        color: #a67c52;
        font-size: 1.1rem;
    }

    .ctx-menu-item.delete-item:hover,
    .ctx-menu-item.delete-item:active {
        background: rgba(239, 68, 68, 0.3) !important;
    }
</style>
