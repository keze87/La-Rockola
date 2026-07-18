<script setup>
    import { ref } from 'vue';
    import { usePlayer } from '../composables/usePlayer';

    const { topPlayedState, getTrackInfo, toggleQueue } = usePlayer();
    const brokenCovers = ref([]);
</script>

<template>
    <section class="tab-content bg-carpincho-bg h-full overflow-y-auto px-4 pt-4">
        <ul v-if="topPlayedState.length > 0" class="flex flex-col">
            <li
                v-for="(t, i) in topPlayedState"
                :key="t.path"
                class="border-carpincho-border hover:bg-carpincho-panel flex cursor-pointer items-center rounded-lg border-b p-4 transition active:scale-[0.98]"
                @click="toggleQueue(t.path)"
            >
                <div class="text-carpincho-warning mr-4 w-8 text-center text-xl font-bold">#{{ i + 1 }}</div>

                <img
                    v-if="!t.path.startsWith('http') && !brokenCovers.includes(t.path)"
                    :src="'/cover?path=' + encodeURIComponent(t.path)"
                    class="mr-4 h-12 w-12 shrink-0 rounded-md object-cover"
                    @error="brokenCovers.push(t.path)"
                />
                <i v-else class="material-icons text-carpincho-primary mr-4 shrink-0 text-4xl">album</i>

                <div class="flex-grow overflow-hidden">
                    <div class="text-carpincho-text truncate font-bold">
                        {{ getTrackInfo(t.path).display_title }}
                    </div>
                    <div class="truncate text-sm text-[#a6adc8]">
                        {{ getTrackInfo(t.path).display_artist }} • Sonó {{ t.count }} veces
                    </div>
                </div>
                <i class="material-icons text-carpincho-primary ml-2 shrink-0">playlist_add</i>
            </li>
        </ul>
        <div v-else class="text-carpincho-primary p-8 text-center font-medium">Todavía no sonó nada, maestro.</div>
    </section>
</template>
