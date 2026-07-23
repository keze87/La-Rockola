<script setup lang="ts">
	import { useDragSlider } from '../composables/useDragSlider';
	import { useFullscreen } from '@vueuse/core';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import PillButton from './ui/PillButton.vue';
	import QRCode from 'qrcode.vue';
	import ToggleRow from './ui/ToggleRow.vue';

	const {
		fullscreen,
		setMute,
		stop,
		toggleDjCarpincho: toggleDjCmd,
		toggleDjSafeMode: toggleSafeCmd,
	} = usePlaybackControls();

	const {
		djCarpinchoEnabled,
		djSafeModeEnabled,
		haptic,
		listenLocally,
		loadLibrary,
		mpvVisible,
		serverMuted,
		setVolume,
		sortLibrary,
		toggleMpvVisibility,
		volIcon,
		volume,
	} = usePlayer();

	const {
		progressPercent: volPercent,
		startDrag: startVol,
		moveDrag: moveVol,
		endDrag: endVol,
	} = useDragSlider({
		max: 110,
		getValue: () => volume.value,
		onUpdate: (val) => {
			volume.value = Math.round(val);

			if (serverMuted.value && volume.value > 0) {
				setMute(false);
			}
		},
		onCommit: (val) => {
			volume.value = Math.round(val);
			setVolume();
		},
	});

	const currentUrl = window.location.href; // Easy access to the current URL

	// --- Toggles ---
	function toggleDjCarpincho() {
		toggleDjCmd(!djCarpinchoEnabled.value);
		haptic();
	}

	function toggleDjSafeMode() {
		toggleSafeCmd(!djSafeModeEnabled.value);
		haptic();
	}

	const { isFullscreen, toggle: toggleWebFullscreen } = useFullscreen();
</script>

<template>
	<section id="controls-tab" class="tab-content bg-carpincho-bg h-full overflow-y-auto px-6 pt-6">
		<!-- Volume Slider -->
		<div class="text-carpincho-warning bg-carpincho-panel mb-8 flex items-center rounded-xl p-4 shadow">
			<i
				class="material-icons mr-3 cursor-pointer transition-colors hover:text-white"
				:title="serverMuted ? 'Desmutear' : 'Mutear'"
				@click="
					setMute(!serverMuted);
					haptic();
				"
			>
				{{ volIcon }}
			</i>
			<div
				class="group flex h-8 w-full cursor-pointer touch-none items-center"
				:class="{ 'opacity-50': serverMuted }"
				@pointerdown="startVol"
				@pointermove="moveVol"
				@pointerup="endVol"
				@pointercancel="endVol"
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
			<PillButton icon="bolt" @click="sortLibrary('mood')">Más Manija</PillButton>
			<PillButton icon="shuffle" @click="sortLibrary('shuffle', false)">Mezcladito (A lo loco)</PillButton>
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
			description="Prioriza favoritos, para que no decaiga"
			active-class="bg-carpincho-success"
			@update:model-value="toggleDjSafeMode"
		/>

		<!-- Action Buttons -->
		<div class="mb-4 flex flex-wrap justify-center gap-3">
			<PillButton icon="stop" color-class="bg-red-700 hover:bg-red-600" @click="stop">Cortala de una</PillButton>

			<PillButton icon="fullscreen" color-class="bg-blue-700 hover:bg-blue-600" @click="fullscreen">
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
					setMute(!serverMuted);
					haptic();
				"
			>
				{{ serverMuted ? 'Desmutear' : 'Mutear' }}
			</PillButton>

			<PillButton icon="refresh" color-class="bg-green-700 hover:bg-green-600" @click="loadLibrary(true)">
				Pegale otra escaneada
			</PillButton>

			<PillButton
				:icon="isFullscreen ? 'fullscreen_exit' : 'open_in_full'"
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
