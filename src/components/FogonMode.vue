<script setup>
import { computed, ref, watch } from 'vue'
import { usePlayer } from '../composables/usePlayer'
import { useLyrics } from '../composables/useLyrics'

const player = usePlayer()
const {
	isFogonMode,
	currentTrackPath,
	isPlaying,
	sendCmd,
	haptic,
	volume,
	serverMuted,
	duration,
	localTimePos,
	ignoreServerTimeUntil,
	listenLocally,
	localPlayerRef,
	pauseAfterPath,
	togglePauseAfterCurrent,
	isDraggingSeek,
	djCarpinchoEnabled,
	djNextTrack,
	showFogonVolume
} = player

// Pass the global player instance to our lyrics composable to sync localTimePos
const { currentLyricLine, loadLyrics } = useLyrics(player)

// --- Computed Properties for Template Cleanliness ---
const currentCoverUrl = computed(() => {
	if (currentTrackPath.value && !currentTrackPath.value.startsWith('http')) {
		return '/cover?path=' + encodeURIComponent(currentTrackPath.value)
	}
	if (!currentTrackPath.value && djCarpinchoEnabled.value && djNextTrack.value && djNextTrack.value.path && !djNextTrack.value.path.startsWith('http')) {
		return '/cover?path=' + encodeURIComponent(djNextTrack.value.path)
	}
	return null
})

const fogonBgStyle = computed(() =>
	currentCoverUrl.value
		? { backgroundImage: `url('${currentCoverUrl.value}')` }
		: { backgroundColor: '#1f1a17' }
)

const currentTrackInfo = computed(() => {
	if (currentTrackPath.value) {
		const info = player.getTrackInfo(currentTrackPath.value)
		return {
			title: info.display_title || "Silencio estampa",
			artist: info.display_artist || "Nadie",
			isComing: false
		}
	}
	if (djCarpinchoEnabled.value && djNextTrack.value) {
		return {
			title: djNextTrack.value.display_title || djNextTrack.value.title,
			artist: djNextTrack.value.display_artist || djNextTrack.value.artist,
			isComing: true
		}
	}
	return { title: "Silencio estampa", artist: "Nadie", isComing: false }
})

const playPauseIcon = computed(() => isPlaying.value ? 'pause' : 'play_arrow')
const muteIcon = computed(() => (serverMuted.value || volume.value == 0) ? 'volume_off' : 'volume_down')

// Timer Button Logic
const isTimerActive = computed(() => pauseAfterPath.value === currentTrackPath.value && currentTrackPath.value)
const timerClass = computed(() => [
	'p-2 transition active:scale-90 z-20',
	isTimerActive.value
		? 'text-carpincho-warning drop-shadow-[0_0_8px_rgba(233,196,106,0.8)]'
		: 'text-white hover:text-carpincho-warning'
])
const timerTitle = computed(() => isTimerActive.value ? 'Cancelar pausa al terminar' : 'Frenar tras este tema')

watch(currentTrackPath, (newPath) => {
	loadLyrics(newPath); // Fetch and parse lyrics on track change
})

function formatTime(sec) {
	if (!sec || isNaN(sec))
		return '0:00'

	const m = Math.floor(sec / 60)
	const s = Math.floor(sec % 60).toString().padStart(2, '0')
	return `${m}:${s}`
}

// --- Action Handlers ---
function closeFogon() {
	isFogonMode.value = false
	haptic()
}

function toggleVolumePopup() {
	showFogonVolume.value = !showFogonVolume.value
	haptic()
}

function togglePlay() {
	sendCmd('pause')
	haptic(true)
}

function skipPrev() {
	sendCmd('prev')
	haptic()
}

function skipNext() {
	sendCmd('skip')
	haptic()
}

function toggleMute() {
	sendCmd('set_mute', { state: !serverMuted.value })
	haptic()
}

function handleTimerToggle() {
	togglePauseAfterCurrent()
	haptic()
}

// --- Seek Drag Logic (Pointer Events) ---
const dragTimePos = ref(0)

const progressPercent = computed(() => {
	if (!duration.value)
		return 0

	const current = isDraggingSeek.value ? dragTimePos.value : localTimePos.value
	return (current / duration.value) * 100
})

const formattedTimePos = computed(() => formatTime(isDraggingSeek.value ? dragTimePos.value : localTimePos.value))
const formattedDuration = computed(() => formatTime(duration.value))

function startSeek(e) {
	if (!duration.value)
		return

	isDraggingSeek.value = true
	e.target.setPointerCapture(e.pointerId)
	updateSeek(e)
}

function moveSeek(e) {
	if (!isDraggingSeek.value)
		return

	updateSeek(e)
}

function endSeek(e) {
	if (!isDraggingSeek.value)
		return

	updateSeek(e)
	isDraggingSeek.value = false
	e.target.releasePointerCapture(e.pointerId)

	localTimePos.value = dragTimePos.value
	const t = parseFloat(localTimePos.value)
	ignoreServerTimeUntil.value = Date.now() + 2000

	if (listenLocally.value && localPlayerRef.value) {
		localPlayerRef.value.currentTime = t
		player._sendLocalPlayerUpdate?.({ time_pos: t })
	} else {
		sendCmd('seek_absolute', { amount: t })
	}
}

function updateSeek(e) {
	if (!duration.value)
		return

	const el = e.currentTarget
	const rect = el.getBoundingClientRect()
	// Pointer events normalize mouse and touch, so we can always just use clientX!
	let clickX = e.clientX - rect.left
	clickX = Math.max(0, Math.min(clickX, rect.width))
	dragTimePos.value = (clickX / rect.width) * duration.value
}

// --- Volume Drag Logic (Pointer Events) ---
const isDraggingVol = ref(false)
const volPercent = computed(() => Math.min(100, (volume.value / 110) * 100))
const volIcon = computed(() => {
	if (serverMuted.value || volume.value == 0)
		return "volume_off"

	if (volume.value <= 40)
		return "volume_down"

	return "volume_up"
})

function startVol(e) {
	isDraggingVol.value = true
	e.target.setPointerCapture(e.pointerId)
	updateVol(e)
}

function moveVol(e) {
	if (!isDraggingVol.value)
		return

	updateVol(e)
}

function endVol(e) {
	if (!isDraggingVol.value)
		return

	updateVol(e)
	isDraggingVol.value = false
	e.target.releasePointerCapture(e.pointerId)
	player.setVolume()
}

function updateVol(e) {
	const el = e.currentTarget
	const rect = el.getBoundingClientRect()
	let clickX = e.clientX - rect.left
	clickX = Math.max(0, Math.min(clickX, rect.width))
	volume.value = Math.round((clickX / rect.width) * 110)
	if (serverMuted.value && volume.value > 0)
		sendCmd('set_mute', { state: false })
}
</script>

<template>
	<transition name="fogon">
		<div v-if="isFogonMode"
			class="fixed inset-0 z-[10000] bg-black text-white flex flex-col items-center justify-center p-6 bg-cover bg-center"
			:style="fogonBgStyle">

			<!-- Background Overlay -->
			<div class="absolute inset-0 bg-black/80 backdrop-blur-xl pointer-events-none"></div>

			<!-- Volume Popup Overlay Layer (Moved outside controls for predictable stacking) -->
			<div v-if="showFogonVolume" class="fixed inset-0 z-10" @click="showFogonVolume = false"></div>

			<div class="relative z-20 flex flex-col items-center text-center w-full max-w-md">

				<button @click="closeFogon" aria-label="Cerrar vista de fogón"
					class="absolute -top-16 right-0 p-2 text-gray-400 hover:text-white transition">
					<i class="material-icons !text-4xl">keyboard_arrow_down</i>
				</button>

				<!-- Album Art -->
				<div
					class="w-64 h-64 md:w-80 md:h-80 bg-carpincho-bg rounded-2xl shadow-[0_10px_50px_rgba(0,0,0,0.8)] mb-8 flex items-center justify-center overflow-hidden">
					<img v-if="currentCoverUrl" :src="currentCoverUrl" alt="Portada del álbum" draggable="false" loading="eager"
						class="w-full h-full object-cover">
					<i v-else class="material-icons !text-[8rem] text-carpincho-warning">album</i>
				</div>

				<!-- Track Info -->
				<h1 class="text-3xl font-bold mb-2 truncate w-full px-4">
					<span v-if="currentTrackInfo.isComing"
						class="block text-sm text-carpincho-warning uppercase tracking-widest mb-2 animate-pulse">🦦 Se
						viene...</span>
					{{ currentTrackInfo.title }}
				</h1>
				<h2 class="text-xl text-carpincho-secondary truncate w-full px-4">{{ currentTrackInfo.artist }}</h2>

				<!-- Custom Seek Bar -->
				<div v-show="currentTrackPath"
					class="w-full px-6 mt-6 flex items-center gap-4 text-xs text-carpincho-secondary font-medium select-none">
					<span class="w-10 text-right shrink-0">{{ formattedTimePos }}</span>

					<div class="w-full h-10 flex items-center group cursor-pointer touch-none" @pointerdown="startSeek"
						@pointermove="moveSeek" @pointerup="endSeek" @pointercancel="endSeek">

						<div class="w-full h-1.5 bg-gray-600/50 rounded-full relative pointer-events-none">
							<div class="absolute top-0 left-0 h-full bg-carpincho-warning rounded-full"
								:style="{ width: progressPercent + '%' }"></div>
							<div
								class="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-carpincho-warning shadow group-active:scale-125 transition-transform"
								:style="{ left: progressPercent + '%', marginLeft: '-8px' }"></div>
						</div>
					</div>

					<span class="w-10 shrink-0">{{ formattedDuration }}</span>
				</div>

				<!-- Controls -->
				<div class="mt-8 flex items-center justify-center gap-4 sm:gap-6 w-full px-4 relative z-30">
					<button @click="toggleVolumePopup" aria-label="Ajustar volumen"
						class="text-white hover:text-carpincho-warning transition active:scale-90 p-2 z-20">
						<i class="material-icons !text-3xl">{{ volIcon }}</i>
					</button>

					<button @click="skipPrev" aria-label="Pista anterior"
						class="text-white hover:text-carpincho-warning transition active:scale-90 p-1 z-20">
						<i class="material-icons !text-4xl sm:!text-5xl">skip_previous</i>
					</button>

					<button @click="togglePlay" :aria-label="isPlaying ? 'Pausar' : 'Reproducir'"
						class="bg-carpincho-primary hover:bg-carpincho-secondary text-white w-20 h-20 shrink-0 rounded-full flex items-center justify-center shadow-[0_0_30px_rgba(166,124,82,0.4)] active:scale-90 transition z-20">
						<i class="material-icons !text-5xl">{{ playPauseIcon }}</i>
					</button>

					<button @click="skipNext" aria-label="Pista siguiente"
						class="text-white hover:text-carpincho-warning transition active:scale-90 p-1 z-20">
						<i class="material-icons !text-4xl sm:!text-5xl">skip_next</i>
					</button>

					<!-- Timer / Pause After Toggle -->
					<button @click="handleTimerToggle" :class="timerClass" :title="timerTitle" :aria-label="timerTitle">
						<i class="material-icons !text-3xl">timer</i>
					</button>
				</div>

				<!-- Custom Volume Bar -->
				<div v-if="showFogonVolume"
					class="mt-8 flex items-center text-gray-300 w-full px-8 gap-4 opacity-80 hover:opacity-100 transition relative z-30 select-none">

					<button @click="toggleMute" aria-label="Silenciar">
						<i class="material-icons text-sm cursor-pointer hover:text-white">{{ muteIcon }}</i>
					</button>

					<div class="w-full h-10 flex items-center group cursor-pointer touch-none"
						:class="{ 'opacity-50': serverMuted }" @pointerdown="startVol" @pointermove="moveVol" @pointerup="endVol"
						@pointercancel="endVol">
						<div class="w-full h-1.5 bg-gray-600 rounded-full relative pointer-events-none">
							<div class="absolute top-0 left-0 h-full bg-carpincho-warning rounded-full"
								:style="{ width: volPercent + '%' }"></div>
							<div
								class="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-carpincho-warning shadow group-active:scale-125 transition-transform"
								:style="{ left: volPercent + '%', marginLeft: '-10px' }"></div>
						</div>
					</div>

					<i class="material-icons text-sm" aria-hidden="true">volume_up</i>
				</div>

				<!-- Lyrics -->
				<div class="h-[6rem] mt-2 flex items-center justify-center w-full px-8 overflow-hidden">
					<transition name="lyric" mode="out-in">
						<p v-if="currentLyricLine" :key="currentLyricLine"
							class="text-xl md:text-2xl font-bold text-carpincho-secondary italic text-center">
							{{ currentLyricLine }}
						</p>
					</transition>
				</div>
			</div>
		</div>
	</transition>
</template>

<style scoped>
.fogon-enter-active,
.fogon-leave-active {
	transition: opacity 0.5s, backdrop-filter 0.5s;
}

.fogon-enter-from,
.fogon-leave-to {
	opacity: 0;
}
</style>