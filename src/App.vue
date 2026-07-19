<script setup>
	import { computed, onMounted } from 'vue';
	import { useDragSlider } from './composables/useDragSlider';
	import { useKeyboardShortcuts } from './composables/useKeyboardShortcuts';
	import { useLyrics } from './composables/useLyrics';
	import { usePlayer } from './composables/usePlayer';

	// Import your isolated components
	import ContextMenu from './components/ContextMenu.vue';
	import ControlsTab from './components/ControlsTab.vue';
	import FloatingPlayer from './components/FloatingPlayer.vue';
	import FogonMode from './components/FogonMode.vue';
	import LibraryTab from './components/LibraryTab.vue';
	import QueueTab from './components/QueueTab.vue';
	import TopTab from './components/TopTab.vue';

	const {
		_sendLocalPlayerUpdate,
		activeTab,
		connectWebSocket,
		currentTrackPath,
		duration,
		getTrackInfo,
		haptic,
		ignoreServerTimeUntil,
		isDraggingSeek,
		isFogonMode,
		isPlaying,
		isScanning,
		listenLocally,
		loadLibrary,
		localPlayerRef,
		localTimePos,
		queueState,
		sendCmd,
		switchTab,
		toasts,
	} = usePlayer();

	const {
		progressPercent,
		startDrag: startSeek,
		moveDrag: moveSeek,
		endDrag: endSeek,
	} = useDragSlider({
		max: () => duration.value,
		getValue: () => localTimePos.value,
		onUpdate: (val) => {
			isDraggingSeek.value = true; // Syncs with global state
			localTimePos.value = val;
		},
		onCommit: (val) => {
			isDraggingSeek.value = false;
			localTimePos.value = val;
			ignoreServerTimeUntil.value = Date.now() + 2000;

			if (listenLocally.value && localPlayerRef.value) {
				localPlayerRef.value.currentTime = val;
				_sendLocalPlayerUpdate({ time_pos: val });
			} else {
				sendCmd('seek_absolute', { amount: val });
			}
		},
	});

	const { currentLyricLine } = useLyrics({ localTimePos });

	// Keyboard shortcuts (space, arrows, f, l, t, n, p, m, esc...) — wire it up
	useKeyboardShortcuts();

	const tabs = [
		{ id: 'library', name: 'Los Temazos', icon: 'library_music' },
		{ id: 'queue', name: 'La Ronda', icon: 'queue_music' },
		{ id: 'top', name: 'Los Clásicos', icon: 'local_fire_department' },
		{ id: 'controls', name: 'Las Perillas', icon: 'settings' },
	];

	const currentTrackTitle = computed(() => {
		if (!currentTrackPath.value) return 'Silencio estampa. Poné algo, fiera.';

		const t = getTrackInfo(currentTrackPath.value);
		return `${t.display_artist} - ${t.display_title}`;
	});

	onMounted(() => {
		loadLibrary(false);
		connectWebSocket();
	});
</script>

<template>
	<!-- Reproductor interno para escuchar en el cliente -->
	<audio ref="localPlayerRef" style="display: none" />

	<!-- TOASTS -->
	<div
		class="pointer-events-none fixed top-4 left-1/2 z-[9999] flex w-[90%] max-w-sm -translate-x-1/2 flex-col gap-2"
	>
		<transition-group name="toast">
			<div
				v-for="toast in toasts"
				:key="toast.id"
				:class="[
					'flex items-center gap-3 rounded-lg px-4 py-3 font-medium text-white shadow-lg',
					toast.colorClasses,
				]"
			>
				<i class="material-icons">{{ toast.icon }}</i>
				<!-- eslint-disable-next-line vue/no-v-html -->
				<span v-html="toast.msg" />
			</div>
		</transition-group>
	</div>

	<!-- MODO FOGÓN -->
	<FogonMode />

	<!-- CONTEXT MENU (global, shared across tabs) -->
	<ContextMenu />

	<!-- HEADER NAV -->
	<nav
		class="bg-carpincho-panel border-carpincho-primary shrink-0 cursor-pointer overflow-hidden border-b px-5 pt-[max(10px,env(safe-area-inset-top))] pb-2"
		@click="
			isFogonMode = true;
			haptic();
		"
	>
		<div class="text-carpincho-text flex w-full items-center justify-start gap-3 font-bold">
			<div class="flex h-[40px] min-w-0 flex-1 items-center overflow-hidden">
				<transition name="lyric" mode="out-in">
					<span v-if="isScanning" class="block w-full truncate text-left">
						[Avisando] Chusmeando temas, aguantá fiera... 🧉
					</span>
					<span
						v-else-if="currentTrackPath && currentLyricLine && currentLyricLine.trim() !== ''"
						:key="currentLyricLine"
						class="text-carpincho-warning block w-full truncate text-left text-[0.95rem] font-medium italic drop-shadow-sm"
					>
						{{ currentLyricLine }}
					</span>
					<span v-else class="block w-full truncate text-left">
						{{ currentTrackTitle }}
					</span>
				</transition>
			</div>
			<img
				v-if="currentTrackPath && !currentTrackPath.startsWith('http') && !isScanning"
				:src="'/cover?path=' + encodeURIComponent(currentTrackPath)"
				class="h-10 w-10 shrink-0 rounded object-cover shadow-sm"
				@error="$event.target.style.display = 'none'"
			/>
			<div v-else class="flex h-10 w-10 shrink-0 items-center justify-center rounded shadow-sm">
				<i class="material-icons text-carpincho-warning">
					{{ isScanning ? 'sync' : isPlaying ? 'nightlife' : 'music_note' }}
				</i>
			</div>
		</div>
	</nav>

	<!-- BARRA DE PROGRESO / SCAN INFERIOR NAV -->
	<div v-show="isScanning" class="bg-carpincho-panel h-1 w-full shrink-0 overflow-hidden">
		<div class="bg-carpincho-primary h-full w-1/3 animate-[pulse_1s_ease-in-out_infinite]" />
	</div>
	<div
		v-show="!isScanning && currentTrackPath"
		class="bg-carpincho-panel group relative flex h-4 w-full shrink-0 cursor-pointer touch-none items-start"
		style="-webkit-tap-highlight-color: transparent"
		@pointerdown="startSeek"
		@pointermove="moveSeek"
		@pointerup="endSeek"
		@pointercancel="endSeek"
	>
		<div
			class="relative h-1 w-full bg-[#38312c] transition-all duration-100 ease-out group-hover:h-2 group-active:h-2"
		>
			<div class="bg-carpincho-warning absolute top-0 left-0 h-full" :style="{ width: progressPercent + '%' }" />
			<!-- Bolita que solo aparece al pasar el dedo/mouse -->
			<div
				class="bg-carpincho-warning absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full opacity-0 shadow-md group-hover:opacity-100 group-active:opacity-100"
				:style="{ left: progressPercent + '%', marginLeft: '-6px' }"
			/>
		</div>
	</div>

	<!-- PESTAÑAS -->
	<div class="bg-carpincho-panel border-carpincho-border relative z-10 flex shrink-0 border-b shadow-md">
		<div
			v-for="tab in tabs"
			:key="tab.id"
			:class="[
				'flex flex-1 cursor-pointer touch-manipulation items-center justify-center gap-1 py-3 text-center text-sm font-medium tracking-wide uppercase transition-colors active:scale-95',
				activeTab === tab.id
					? 'text-carpincho-primary border-carpincho-primary border-b-2'
					: 'hover:bg-carpincho-border/50 text-carpincho-muted border-b-2 border-transparent',
			]"
			@click="switchTab(tab.id)"
		>
			<div class="relative">
				<i class="material-icons">{{ tab.icon }}</i>
				<span
					v-if="tab.id === 'queue' && queueState.length > 0"
					class="bg-carpincho-primary absolute -top-1.5 -right-3 flex h-[14px] min-w-[14px] items-center justify-center rounded-full px-[3px] text-[0.55rem] leading-none font-bold text-white"
				>
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
