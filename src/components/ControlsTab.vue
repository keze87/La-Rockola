<script setup>
	import { ref, computed } from 'vue';
	import { usePlayer } from '../composables/usePlayer';
	import QRCode from 'qrcode.vue';
	import PillButton from './ui/PillButton.vue';
	import ToggleRow from './ui/ToggleRow.vue';

	const {
		djCarpinchoEnabled,
		djSafeModeEnabled,
		haptic,
		listenLocally,
		loadLibrary,
		mpvVisible,
		sendCmd,
		serverMuted,
		setVolume,
		sortLibrary,
		toggleMpvVisibility,
		volume,
	} = usePlayer();

	const currentUrl = window.location.href; // Easy access to the current URL

	// --- Volume Drag Logic ---
	const isDraggingVol = ref(false);

	const volPercent = computed(() => Math.min(100, (volume.value / 110) * 100));
	const volIcon = computed(() => {
		if (serverMuted.value || volume.value == 0) return 'volume_off';

		if (volume.value <= 40) return 'volume_down';

		if (volume.value <= 100) return 'volume_up';

		return 'surround_sound';
	});

	function startVol(e) {
		isDraggingVol.value = true;
		updateVol(e);
	}

	function moveVol(e) {
		if (!isDraggingVol.value) return;

		updateVol(e);
	}

	function endVol(e) {
		if (!isDraggingVol.value) return;

		updateVol(e);
		isDraggingVol.value = false;
		setVolume();
	}

	function updateVol(e) {
		const el = e.currentTarget;
		const rect = el.getBoundingClientRect();
		const clientX =
			e.touches && e.touches.length > 0
				? e.touches[0].clientX
				: e.changedTouches
					? e.changedTouches[0].clientX
					: e.clientX;
		let clickX = clientX - rect.left;
		clickX = Math.max(0, Math.min(clickX, rect.width));
		volume.value = Math.round((clickX / rect.width) * 110);

		if (serverMuted.value && volume.value > 0) {
			sendCmd('set_mute', { state: false });
		}
	}

	// --- Toggles ---
	function toggleDjCarpincho() {
		sendCmd('toggle_dj_carpincho', { state: !djCarpinchoEnabled.value });
		haptic();
	}

	function toggleDjSafeMode() {
		sendCmd('toggle_dj_safe_mode', { state: !djSafeModeEnabled.value });
		haptic();
	}

	function toggleWebFullscreen() {
		if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch((e) => console.warn(e));
		else if (document.exitFullscreen) document.exitFullscreen();
	}
</script>

<template>
	<section class="tab-content bg-carpincho-bg h-full overflow-y-auto px-6 pt-6">
		<!-- Volume Slider -->
		<div class="text-carpincho-warning bg-carpincho-panel mb-8 flex items-center rounded-xl p-4 shadow">
			<i
				class="material-icons mr-3 cursor-pointer transition-colors hover:text-white"
				:title="serverMuted ? 'Desmutear' : 'Mutear'"
				@click="
					sendCmd('set_mute', { state: !serverMuted });
					haptic();
				"
			>
				{{ volIcon }}
			</i>
			<div
				class="group flex h-8 w-full cursor-pointer touch-none items-center"
				:class="{ 'opacity-50': serverMuted }"
				@mousedown="startVol"
				@mousemove="moveVol"
				@mouseup="endVol"
				@mouseleave="endVol"
				@touchstart.prevent="startVol"
				@touchmove.prevent="moveVol"
				@touchend.prevent="endVol"
			>
				<div class="relative h-2 w-full rounded-full bg-gray-800">
					<div
						class="bg-carpincho-warning absolute top-0 left-0 h-full rounded-full"
						:style="{ width: volPercent + '%' }"
					/>
					<div
						class="bg-carpincho-warning absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full shadow transition-transform group-active:scale-125"
						:style="{ left: volPercent + '%', marginLeft: '-8px' }"
					/>
				</div>
			</div>
		</div>

		<!-- Sorters -->
		<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">sort</i>
			Acomodando la gilada
		</div>

		<div class="mb-8 flex flex-wrap justify-center gap-3">
			<PillButton icon="access_time" @click="sortLibrary('time')">Como llegaron</PillButton>
			<PillButton icon="person" @click="sortLibrary('artist')">Por el que canta</PillButton>
			<PillButton icon="shuffle" @click="sortLibrary('shuffle', false)">Mezcladito (A lo loco)</PillButton>
			<PillButton icon="bolt" @click="sortLibrary('mood')">Más Manija</PillButton>
		</div>

		<!-- The Toggles -->
		<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">celebration</i>
			La Joda
		</div>

		<!-- Local Listen Toggle -->
		<ToggleRow
			v-model="listenLocally"
			icon="headphones"
			title="Escuchar acá"
			description="Stremea la música directo a tu celular o PC."
		/>

		<ToggleRow
			:model-value="djCarpinchoEnabled"
			icon="shuffle"
			title="DJ Carpincho"
			description="Tira un tema random nuevo si se vacía la fila"
			active-class="bg-carpincho-success"
			@update:model-value="toggleDjCarpincho"
		/>

		<ToggleRow
			v-show="djCarpinchoEnabled"
			:model-value="djSafeModeEnabled"
			icon="favorite"
			title="Capincho seguro"
			description="Prioriza favoritos para que no decaiga"
			active-class="bg-carpincho-success"
			@update:model-value="toggleDjSafeMode"
		/>

		<!-- Action Buttons -->
		<div class="mb-4 flex flex-wrap justify-center gap-3">
			<PillButton icon="stop" color-class="bg-red-700 hover:bg-red-600" @click="sendCmd('stop')">
				Cortala de una
			</PillButton>

			<PillButton icon="fullscreen" color-class="bg-blue-700 hover:bg-blue-600" @click="sendCmd('fullscreen')">
				Todo pantalla, ñeri
			</PillButton>

			<PillButton
				:icon="mpvVisible ? 'visibility_off' : 'visibility'"
				color-class="bg-gray-700 hover:bg-gray-600"
				@click="toggleMpvVisibility"
			>
				{{ mpvVisible ? 'Ocultar MPV' : 'Mostrar MPV' }}
			</PillButton>
		</div>

		<div class="mb-8 flex flex-wrap justify-center gap-3">
			<PillButton
				:icon="serverMuted ? 'volume_off' : 'volume_up'"
				:color-class="serverMuted ? 'bg-red-700 hover:bg-red-600' : 'bg-gray-700 hover:bg-gray-600'"
				@click="
					sendCmd('set_mute', { state: !serverMuted });
					haptic();
				"
			>
				{{ serverMuted ? 'Desmutear' : 'Mutear' }}
			</PillButton>

			<PillButton icon="refresh" color-class="bg-green-700 hover:bg-green-600" @click="loadLibrary(true)">
				Pegale otra escaneada
			</PillButton>

			<PillButton
				icon="open_in_full"
				color-class="bg-purple-700 hover:bg-purple-600"
				@click="toggleWebFullscreen"
			>
				Full Rockola
			</PillButton>
		</div>

		<!-- QR Code -->
		<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">qr_code_2</i>
			Sumate a la joda
		</div>

		<div class="flex flex-col items-center pb-20">
			<!-- Note the 'relative' class added here to contain the absolute image -->
			<div class="relative flex items-center justify-center rounded-xl bg-white p-4 shadow-lg">
				<!-- The Vue QR Component with your exact colors -->
				<QRCode :value="currentUrl" :size="200" level="H" foreground="#2b2622" background="#ffffff" />

				<!-- La impronta del carpincho -->
				<img
					src="/favicon.ico"
					alt="Logo Carpincho"
					class="absolute top-1/2 left-1/2 h-[88px] w-[88px] -translate-x-1/2 -translate-y-1/2 rounded-lg p-1"
				/>
			</div>
			<p class="text-carpincho-muted mt-3 text-sm">Escaneá para entrar desde tu celu</p>
		</div>
	</section>
</template>
