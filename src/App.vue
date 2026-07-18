<script setup>
import { computed, onMounted } from 'vue'
import { useKeyboardShortcuts } from './composables/useKeyboardShortcuts'
import { useLyrics } from './composables/useLyrics'
import { usePlayer } from './composables/usePlayer'

// Import your isolated components
import ContextMenu from './components/ContextMenu.vue'
import ControlsTab from './components/ControlsTab.vue'
import FloatingPlayer from './components/FloatingPlayer.vue'
import FogonMode from './components/FogonMode.vue'
import LibraryTab from './components/LibraryTab.vue'
import QueueTab from './components/QueueTab.vue'
import TopTab from './components/TopTab.vue'

const {
	currentTrackPath, isScanning, isPlaying, isFogonMode,
	activeTab, switchTab, queueState, getTrackInfo, haptic,
	localPlayerRef, connectWebSocket, loadLibrary, toasts,
	localTimePos, duration, isDraggingSeek, ignoreServerTimeUntil,
	listenLocally, sendCmd, _sendLocalPlayerUpdate,
} = usePlayer()

const { currentLyricLine } = useLyrics({ localTimePos })

// Keyboard shortcuts (space, arrows, f, l, t, n, p, m, esc...) — wire it up
useKeyboardShortcuts()

const tabs = [
	{ id: 'library', name: 'Los Temazos', icon: 'library_music' },
	{ id: 'queue', name: 'La Ronda', icon: 'queue_music' },
	{ id: 'top', name: 'Los Clásicos', icon: 'local_fire_department' },
	{ id: 'controls', name: 'Las Perillas', icon: 'settings' },
]

const currentTrackTitle = computed(() => {
	if (!currentTrackPath.value)
		return "Silencio estampa. Poné algo, fiera.";

	const t = getTrackInfo(currentTrackPath.value);
	return `${t.display_artist} - ${t.display_title}`;
})

const progressPercent = computed(() => {
	if (!duration.value)
		return 0;

	return (localTimePos.value / duration.value) * 100;
})

// --- Seek bar under the nav ---
function updateSeek(e) {
	if (!duration.value)
		return null;

	const el = e.currentTarget;
	const rect = el.getBoundingClientRect();
	const clientX = e.touches && e.touches.length > 0 ? e.touches[0].clientX : (e.changedTouches ? e.changedTouches[0].clientX : e.clientX);
	let clickX = clientX - rect.left;
	clickX = Math.max(0, Math.min(clickX, rect.width));
	return (clickX / rect.width) * duration.value;
}

function startSeek(e) {
	if (duration.value) {
		isDraggingSeek.value = true;
		const t = updateSeek(e);

		if (t !== null)
			localTimePos.value = t;
	}
}

function moveSeek(e) {
	if (!isDraggingSeek.value)
		return;

	const t = updateSeek(e);

	if (t !== null)
		localTimePos.value = t;
}

function endSeek(e) {
	if (!isDraggingSeek.value)
		return;

	const t = updateSeek(e);
	isDraggingSeek.value = false;

	if (t === null)
		return;

	localTimePos.value = t;
	ignoreServerTimeUntil.value = Date.now() + 2000;

	if (listenLocally.value && localPlayerRef.value) {
		localPlayerRef.value.currentTime = t;
		_sendLocalPlayerUpdate({ time_pos: t });
	} else {
		sendCmd('seek_absolute', { amount: t });
	}
}

onMounted(() => {
	loadLibrary(false);
	connectWebSocket();
})
</script>

<template>
	<!-- Reproductor interno para escuchar en el cliente -->
	<audio ref="localPlayerRef" style="display:none;"></audio>

	<!-- TOASTS -->
	<div
		class="fixed top-4 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2 w-[90%] max-w-sm pointer-events-none">
		<transition-group name="toast">
			<div v-for="toast in toasts" :key="toast.id"
				:class="['px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 text-white font-medium', toast.colorClasses]">
				<i class="material-icons">{{ toast.icon }}</i>
				<span v-html="toast.msg"></span>
			</div>
		</transition-group>
	</div>

	<!-- MODO FOGÓN -->
	<FogonMode />

	<!-- CONTEXT MENU (global, shared across tabs) -->
	<ContextMenu />

	<!-- HEADER NAV -->
	<nav @click="isFogonMode = true; haptic()"
		class="bg-carpincho-panel border-b border-carpincho-primary px-5 pb-2 pt-[max(10px,env(safe-area-inset-top))] shrink-0 cursor-pointer overflow-hidden">
		<div class="flex items-center justify-start font-bold gap-3 text-carpincho-text w-full">
			<div class="flex items-center h-[40px] overflow-hidden flex-1 min-w-0">
				<transition name="lyric" mode="out-in">
					<span v-if="isScanning" class="truncate block text-left w-full">
						[Avisando] Chusmeando temas, aguantá fiera... 🧉
					</span>
					<span v-else-if="currentTrackPath && currentLyricLine && currentLyricLine.trim() !== ''"
						:key="currentLyricLine"
						class="text-[0.95rem] text-carpincho-warning font-medium italic drop-shadow-sm truncate block text-left w-full">
						{{ currentLyricLine }}
					</span>
					<span v-else class="truncate block text-left w-full">
						{{ currentTrackTitle }}
					</span>
				</transition>
			</div>
			<img v-if="currentTrackPath && !currentTrackPath.startsWith('http') && !isScanning"
				:src="'/cover?path=' + encodeURIComponent(currentTrackPath)"
				class="w-10 h-10 rounded object-cover shrink-0 shadow-sm" @error="$event.target.style.display = 'none'">
			<div v-else class="w-10 h-10 shrink-0 rounded flex items-center justify-center shadow-sm">
				<i class="material-icons text-carpincho-warning">{{ isScanning ? 'sync' : (isPlaying ? 'nightlife' :
					'music_note') }}</i>
			</div>
		</div>
	</nav>

	<!-- BARRA DE PROGRESO / SCAN INFERIOR NAV -->
	<div v-show="isScanning" class="h-1 bg-carpincho-panel w-full overflow-hidden shrink-0">
		<div class="h-full bg-carpincho-primary w-1/3 animate-[pulse_1s_ease-in-out_infinite]"></div>
	</div>
	<div v-show="!isScanning && currentTrackPath"
		class="w-full h-4 bg-carpincho-panel cursor-pointer relative shrink-0 group touch-none flex items-start"
		style="-webkit-tap-highlight-color: transparent;" @mousedown="startSeek" @mousemove="moveSeek"
		@mouseup="endSeek" @mouseleave="endSeek" @touchstart.prevent="startSeek" @touchmove.prevent="moveSeek"
		@touchend.prevent="endSeek">
		<div
			class="w-full h-1 group-hover:h-2 group-active:h-2 bg-[#38312c] transition-all duration-100 ease-out relative">
			<div class="absolute top-0 left-0 h-full bg-carpincho-warning" :style="{ width: progressPercent + '%' }">
			</div>
			<!-- Bolita que solo aparece al pasar el dedo/mouse -->
			<div class="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-carpincho-warning opacity-0 group-hover:opacity-100 group-active:opacity-100 shadow-md"
				:style="{ left: progressPercent + '%', marginLeft: '-6px' }"></div>
		</div>
	</div>

	<!-- PESTAÑAS -->
	<div class="flex bg-carpincho-panel border-b border-carpincho-border shrink-0 shadow-md relative z-10">
		<div v-for="tab in tabs" :key="tab.id" @click="switchTab(tab.id)" :class="[
			'flex-1 text-center py-3 cursor-pointer uppercase tracking-wide text-sm font-medium transition-colors flex justify-center items-center gap-1 active:scale-95 touch-manipulation',
			activeTab === tab.id ? 'text-carpincho-primary border-b-2 border-carpincho-primary' : 'text-[#a6adc8] hover:bg-carpincho-border/50 border-b-2 border-transparent'
		]">
			<div class="relative">
				<i class="material-icons">{{ tab.icon }}</i>
				<span v-if="tab.id === 'queue' && queueState.length > 0"
					class="absolute -top-1.5 -right-3 bg-carpincho-primary text-white text-[0.55rem] font-bold rounded-full min-w-[14px] h-[14px] flex items-center justify-center px-[3px] leading-none">
					{{ queueState.length > 99 ? '99+' : queueState.length }}
				</span>
			</div>
			<span class="hidden sm:inline">{{ tab.name }}</span>
		</div>
	</div>

	<!-- TABS CONTENT -->
	<!-- Note: We use v-show to keep the components alive in the DOM so scroll position and local state (like search queries) aren't lost when switching tabs -->
	<LibraryTab v-show="activeTab === 'library'" />
	<QueueTab v-show="activeTab === 'queue'" />
	<TopTab v-show="activeTab === 'top'" />
	<ControlsTab v-show="activeTab === 'controls'" />

	<!-- REPRODUCTOR FLOTANTE -->
	<FloatingPlayer />
</template>
