<script setup>
import { ref } from 'vue'
import { usePlayer } from '../composables/usePlayer'

const { topPlayedState, getTrackInfo, toggleQueue } = usePlayer()

const brokenCovers = ref([])
</script>

<template>
	<section class="tab-content px-4 pt-4 h-full overflow-y-auto bg-carpincho-bg">
		<ul v-if="topPlayedState.length > 0" class="flex flex-col">
			<li v-for="(t, i) in topPlayedState" :key="t.path" @click="toggleQueue(t.path)"
				class="p-4 border-b border-carpincho-border flex items-center cursor-pointer active:scale-[0.98] transition hover:bg-carpincho-panel rounded-lg">
				<div class="font-bold text-carpincho-warning text-xl w-8 text-center mr-4">#{{ i + 1 }}</div>

				<img v-if="!t.path.startsWith('http') && !brokenCovers.includes(t.path)"
					:src="'/cover?path=' + encodeURIComponent(t.path)"
					class="w-12 h-12 object-cover rounded-md mr-4 shrink-0" @error="brokenCovers.push(t.path)">
				<i v-else class="material-icons text-carpincho-primary text-4xl mr-4 shrink-0">album</i>

				<div class="flex-grow overflow-hidden">
					<div class="font-bold truncate text-carpincho-text">{{ getTrackInfo(t.path).display_title }}</div>
					<div class="text-sm text-[#a6adc8] truncate">{{ getTrackInfo(t.path).display_artist }} • Sonó {{
						t.count }} veces</div>
				</div>
				<i class="material-icons text-carpincho-primary ml-2 shrink-0">playlist_add</i>
			</li>
		</ul>
		<div v-else class="text-center p-8 text-carpincho-primary font-medium">Todavía no sonó nada, maestro.</div>
	</section>
</template>
