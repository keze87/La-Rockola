<script setup>
    import { ref } from 'vue';
    import { usePlayer } from '../composables/usePlayer';
    import { useContextMenu } from '../composables/useContextMenu';

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
        sendCmd,
        togglePauseAfterCurrent,
    } = usePlayer();
    const { openCtxMenu } = useContextMenu();

    const newUrl = ref('');
    const dragFromIndex = ref(null);

    // Touch logic variables
    let touchStartX = 0;
    let ctxLongPressTimer = null;
    let _queueLongPressFired = false;

    async function addUrl() {
        if (!newUrl.value.trim()) return;

        await sendCmd('add_url', { path: newUrl.value.trim() });
        newUrl.value = '';
    }

    function removeQueueItem(index, rowEl) {
        const el = rowEl || document.querySelector(`[data-queue-index="${index}"]`);

        if (el) {
            el.classList.add('deleting');
            setTimeout(() => sendCmd('remove_queue_item', { index }), 450);
        } else {
            sendCmd('remove_queue_item', { index });
        }
    }

    function moveQueueItem(index, target) {
        let newIndex = target === 'first' ? 0 : queueState.value.length - 1;

        if (newIndex !== index) {
            sendCmd('move_queue_item', { index, new_index: newIndex });
        }
    }

    // --- Touch Handlers (Shared base for Queue & History rows) ---
    function ctxTouchStart(e, track, source, index) {
        touchStartX = e.changedTouches[0].screenX;
        _queueLongPressFired = false;
        const touch = e.touches[0];
        ctxLongPressTimer = setTimeout(() => {
            _queueLongPressFired = true;
            haptic(true);
            openCtxMenu(touch, track, source, index);
        }, 500);
    }

    function ctxTouchEnd() {
        clearTimeout(ctxLongPressTimer);
    }

    function queueTouchMove(e) {
        const dx = Math.abs(e.touches[0].screenX - touchStartX);

        if (dx > 10) clearTimeout(ctxLongPressTimer);
    }

    function queueTouchEnd(e, index) {
        clearTimeout(ctxLongPressTimer);

        if (_queueLongPressFired) return;

        let diff = touchStartX - e.changedTouches[0].screenX;
        let row = e.currentTarget;

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
        <table class="w-full border-collapse text-left">
            <thead>
                <tr>
                    <th class="text-carpincho-primary bg-carpincho-panel w-28 p-3 text-center">Acciones</th>
                    <th class="text-carpincho-primary bg-carpincho-panel p-3">El Temón</th>
                    <th class="text-carpincho-primary bg-carpincho-panel p-3">De quién es</th>
                    <th class="text-carpincho-primary bg-carpincho-panel hidden w-20 p-3 text-right sm:table-cell">
                        Duración
                    </th>
                </tr>
            </thead>
            <tbody class="overflow-hidden">
                <!-- History Items -->
                <tr
                    v-for="(path, i) in historyState"
                    :key="'hist-' + path"
                    :data-history-path="path"
                    class="border-carpincho-border hover:bg-carpincho-border cursor-pointer border-b opacity-70"
                    @click="sendCmd('jump', { type: 'history', index: i })"
                    @contextmenu.prevent="openCtxMenu($event, getTrackInfo(path), 'history', i)"
                    @touchstart="ctxTouchStart($event, getTrackInfo(path), 'history', i)"
                    @touchend="ctxTouchEnd"
                    @touchmove="ctxTouchEnd"
                >
                    <td class="text-carpincho-success p-4 text-center">
                        <i class="material-icons text-sm">check</i>
                    </td>
                    <td class="max-w-[200px] truncate p-4">
                        {{ getTrackInfo(path).display_title }}
                    </td>
                    <td class="truncate p-4 text-[#a6adc8]">
                        {{ getTrackInfo(path).display_artist }}
                    </td>
                    <td class="hidden p-4 text-right text-[#a6adc8] sm:table-cell">
                        {{ getTrackInfo(path).duration_str }}
                    </td>
                </tr>

                <!-- Current Track -->
                <tr
                    v-if="currentTrackPath"
                    id="current-queue-row"
                    class="border-carpincho-border bg-carpincho-panel cursor-pointer border-b"
                    @click="sendCmd('pause')"
                >
                    <td class="text-carpincho-primary p-4 text-center font-bold" @click.stop>
                        <div class="items-center gap-1">
                            <div :class="['equalizer', isPaused ? 'paused' : '']">
                                <span />
                                <span />
                                <span />
                            </div>
                            <button
                                :title="
                                    pauseAfterPath === currentTrackPath
                                        ? 'Cancelar pausa al terminar'
                                        : 'Frenar tras este tema'
                                "
                                :class="[
                                    'transition active:scale-90',
                                    pauseAfterPath === currentTrackPath
                                        ? 'text-carpincho-warning'
                                        : 'hover:text-carpincho-warning text-gray-500',
                                ]"
                                @click="
                                    togglePauseAfterCurrent();
                                    haptic();
                                "
                            >
                                <i class="material-icons text-lg">timer</i>
                            </button>
                        </div>
                    </td>
                    <td class="text-carpincho-primary max-w-[200px] truncate p-4 font-bold">
                        {{ getTrackInfo(currentTrackPath).display_title }}
                    </td>
                    <td class="text-carpincho-primary truncate p-4">
                        {{ getTrackInfo(currentTrackPath).display_artist }}
                    </td>
                    <td class="text-carpincho-primary hidden p-4 text-right sm:table-cell">
                        {{ getTrackInfo(currentTrackPath).duration_str }}
                    </td>
                </tr>

                <!-- Render queued items -->
                <tr
                    v-for="(path, i) in queueState"
                    :key="path"
                    :data-queue-index="i"
                    draggable="true"
                    class="swipe-row border-carpincho-border hover:bg-carpincho-border cursor-pointer border-b transition-all duration-200"
                    @dragstart="dragStart($event, i)"
                    @dragover.prevent="dragOver($event, i)"
                    @dragleave="dragLeave($event)"
                    @drop.prevent="dragDrop($event, i)"
                    @dragend="dragEnd($event)"
                    @touchstart="ctxTouchStart($event, getTrackInfo(path), 'queue', i)"
                    @touchend="queueTouchEnd($event, i)"
                    @touchmove="queueTouchMove($event)"
                    @contextmenu.prevent="openCtxMenu($event, getTrackInfo(path), 'queue', i)"
                >
                    <!-- Actions Column -->
                    <td class="p-4" @click.stop>
                        <div class="flex items-center justify-center gap-2">
                            <i
                                class="material-icons hidden cursor-grab text-gray-500 select-none active:cursor-grabbing sm:block"
                            >
                                drag_indicator
                            </i>
                            <i
                                class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition"
                                @click="moveQueueItem(i, 'first')"
                            >
                                vertical_align_top
                            </i>
                            <i
                                class="material-icons text-carpincho-primary hover:text-carpincho-secondary transition"
                                @click="moveQueueItem(i, 'last')"
                            >
                                vertical_align_bottom
                            </i>
                            <i
                                class="material-icons text-carpincho-secondary hidden transition hover:text-red-400 sm:block"
                                @click="removeQueueItem(i, $event.currentTarget.closest('tr'))"
                            >
                                delete
                            </i>
                        </div>
                    </td>

                    <!-- Track Info -->
                    <td class="max-w-[200px] p-4" @click="sendCmd('jump', { type: 'queue', index: i })">
                        <div class="flex items-center gap-2 truncate">
                            <span class="block truncate">{{ getTrackInfo(path).display_title }}</span>
                            <i
                                v-if="path === pauseAfterPath"
                                class="material-icons text-carpincho-warning shrink-0 text-sm"
                                title="Se frena acá"
                            >
                                timer
                            </i>
                        </div>
                    </td>

                    <td class="p-4 text-[#a6adc8]" @click="sendCmd('jump', { type: 'queue', index: i })">
                        {{ getTrackInfo(path).display_artist }}
                    </td>

                    <td
                        class="hidden p-4 text-right text-[#a6adc8] sm:table-cell"
                        @click="sendCmd('jump', { type: 'queue', index: i })"
                    >
                        {{ getTrackInfo(path).duration_str }}
                    </td>
                </tr>

                <!-- EMPTY STATE: Cuando no hay nada en la fila ni está sonando nada -->
                <tr v-if="queueState.length === 0 && !currentTrackPath" class="border-carpincho-border border-b">
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
                    <td class="p-4 italic" :class="queueState.length === 0 ? 'text-[#a6adc8]' : 'text-[#a6adc8]'">
                        {{
                            queueState.length === 0
                                ? djNextTrack
                                    ? 'DJ Carpincho eligió: ' + (djNextTrack.display_title || djNextTrack.title)
                                    : 'Eligiendo...'
                                : 'Al vaciarse la fila, entra el DJ Carpincho'
                        }}
                    </td>
                    <td class="p-4 text-[#a6adc8] italic">🦦</td>
                    <td class="hidden p-4 text-right text-[#a6adc8] sm:table-cell" />
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
