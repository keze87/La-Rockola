<script setup>
import { ref, computed } from 'vue'
import { usePlayer } from '../composables/usePlayer'

const {
	queueState, currentTrackPath, djCarpinchoEnabled, djNextTrack,
	getTrackInfo, sendCmd, haptic, pauseAfterPath, togglePauseAfterCurrent, isPlaying, switchTab
} = usePlayer()

const brokenNextCover = ref(false)

const upNextTitle = computed(() => {
	if (queueState.value.length > 0) {
		const t = getTrackInfo(queueState.value[0]);
		return `${t.display_title} - ${t.display_artist}`;
	}
	if (djCarpinchoEnabled.value && djNextTrack.value) {
		const t = djNextTrack.value;
		return `${t.display_title || t.title} - ${t.display_artist || t.artist}`;
	}
	if (djCarpinchoEnabled.value)
		return "DJ Carpincho eligiendo...";

	return currentTrackPath.value ? "Termina este y nos re vimos" : "Agregá algo pa' escuchar";
})

const upNextCoverUrl = computed(() => {
	if (brokenNextCover.value)
		return null;

	if (queueState.value.length > 0 && !queueState.value[0].startsWith('http')) {
		return '/cover?path=' + encodeURIComponent(queueState.value[0]);
	}

	if (djCarpinchoEnabled.value && djNextTrack.value) {
		const p = djNextTrack.value.path;
		if (p && !p.startsWith('http')) return '/cover?path=' + encodeURIComponent(p);
	}

	return null;
})

function goToQueue() {
	switchTab('queue');
	haptic();
}
</script>

<template>
	<section
		class="floating-player bg-gradient-to-br from-carpincho-panel to-[#2a2420] border border-carpincho-border rounded-xl p-3 flex justify-between items-center shadow-[0_4px_15px_rgba(0,0,0,0.5)]">
		<div class="flex items-center grow overflow-hidden cursor-pointer" @click="goToQueue">
			<div
				class="w-12 h-12 mr-3 shrink-0 bg-carpincho-bg rounded-lg flex justify-center items-center overflow-hidden relative">
				<img v-if="upNextCoverUrl" :src="upNextCoverUrl" class="absolute w-full h-full object-cover"
					@error="brokenNextCover = true">
				<i v-else-if="djCarpinchoEnabled && queueState.length === 0"
					class="material-icons text-carpincho-warning !text-[2rem] animate-pulse">auto_awesome</i>
				<i v-else class="material-icons text-carpincho-warning !text-[2rem]">album</i>
			</div>
			<div class="grow overflow-hidden flex flex-col justify-center">
				<div class="text-[0.7rem] text-carpincho-primary uppercase tracking-wider font-bold">
					<!-- NO CORTAR -->
					{{ queueState.length > 0 ? 'Próximo Temazo' : (djCarpinchoEnabled ? (djNextTrack ? '🦦 Arranca en unos segundos...' : 'Eligiendo...') : 'Fin de la fila') }}
				</div>
				<div class="text-[0.95rem] font-bold truncate text-carpincho-text">{{ upNextTitle }}</div>
			</div>
		</div>

		<div class="flex items-center gap-3 shrink-0 ml-2">
			<button @click="togglePauseAfterCurrent(); haptic()"
				:class="['w-10 h-10 hidden sm:flex justify-center items-center rounded-full active:scale-90 transition', pauseAfterPath === currentTrackPath && currentTrackPath ? 'text-carpincho-warning' : 'text-gray-400 hover:text-white']"
				:title="pauseAfterPath === currentTrackPath && currentTrackPath ? 'Cancelar pausa al terminar' : 'Frenar tras este tema'">
				<i class="material-icons !text-2xl">timer</i>
			</button>
			<button @click="sendCmd('pause'); haptic(true)"
				:class="['w-14 h-14 rounded-full flex justify-center items-center text-white shadow-lg active:scale-90 transition', isPlaying ? 'bg-orange-600 hover:bg-orange-500' : 'bg-green-600 hover:bg-green-500']">
				<i class="material-icons !text-4xl">{{ isPlaying ? 'pause' : 'play_arrow' }}</i>
			</button>
			<button @click="sendCmd('skip'); haptic()"
				class="w-10 h-10 bg-gray-700 hover:bg-gray-600 text-white rounded-full flex justify-center items-center active:scale-90 transition shadow">
				<i class="material-icons !text-2xl">skip_next</i>
			</button>
		</div>
	</section>
</template>
