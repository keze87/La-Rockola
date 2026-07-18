<script setup>
import { ref, computed, watch } from 'vue'
import { usePlayer } from '../composables/usePlayer'
import QRCode from 'qrcode.vue'

const {
	sendCmd, serverMuted, volume, setVolume, haptic, listenLocally,
	djCarpinchoEnabled, djSafeModeEnabled, sortLibrary, loadLibrary,
	toggleMpvVisibility, mpvVisible
} = usePlayer()

const currentUrl = window.location.href // Easy access to the current URL

// --- Volume Drag Logic ---
const isDraggingVol = ref(false)

const volPercent = computed(() => Math.min(100, (volume.value / 110) * 100))
const volIcon = computed(() => {
	if (serverMuted.value || volume.value == 0) return "volume_off";
	if (volume.value <= 40) return "volume_down";
	if (volume.value <= 100) return "volume_up";
	return "surround_sound";
})

function startVol(e) { isDraggingVol.value = true; updateVol(e); }

function moveVol(e) { if (!isDraggingVol.value) return; updateVol(e); }

function endVol(e) {
	if (!isDraggingVol.value) return;
	updateVol(e);
	isDraggingVol.value = false;
	setVolume();
}

function updateVol(e) {
	const el = e.currentTarget;
	const rect = el.getBoundingClientRect();
	const clientX = e.touches && e.touches.length > 0 ? e.touches[0].clientX : (e.changedTouches ? e.changedTouches[0].clientX : e.clientX);
	let clickX = clientX - rect.left;
	clickX = Math.max(0, Math.min(clickX, rect.width));
	volume.value = Math.round((clickX / rect.width) * 110);
	if (serverMuted.value && volume.value > 0) {
		sendCmd('set_mute', { state: false });
	}
}

// --- Toggles ---
function toggleDjCarpincho() {
	sendCmd("toggle_dj_carpincho", { state: !djCarpinchoEnabled.value });
	haptic();
}

function toggleDjSafeMode() {
	sendCmd("toggle_dj_safe_mode", { state: !djSafeModeEnabled.value });
	haptic();
}

function toggleWebFullscreen() {
	if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(e => console.warn(e));
	else if (document.exitFullscreen) document.exitFullscreen();
}
</script>

<template>
	<section class="tab-content px-6 pt-6 h-full overflow-y-auto bg-carpincho-bg">
		<!-- Volume Slider -->
		<div class="flex items-center text-carpincho-warning mb-8 bg-carpincho-panel p-4 rounded-xl shadow">
			<i class="material-icons mr-3 cursor-pointer hover:text-white transition-colors"
				@click="sendCmd('set_mute', { state: !serverMuted }); haptic()"
				:title="serverMuted ? 'Desmutear' : 'Mutear'">{{ volIcon }}</i>
			<div class="w-full h-8 flex items-center group cursor-pointer touch-none"
				:class="{ 'opacity-50': serverMuted }" @mousedown="startVol" @mousemove="moveVol" @mouseup="endVol"
				@mouseleave="endVol" @touchstart.prevent="startVol" @touchmove.prevent="moveVol"
				@touchend.prevent="endVol">
				<div class="w-full h-2 bg-gray-800 rounded-full relative">
					<div class="absolute top-0 left-0 h-full bg-carpincho-warning rounded-full"
						:style="{ width: volPercent + '%' }"></div>
					<div class="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-carpincho-warning shadow group-active:scale-125 transition-transform"
						:style="{ left: volPercent + '%', marginLeft: '-8px' }"></div>
				</div>
			</div>
		</div>

		<div class="text-center font-bold text-carpincho-secondary mb-4 uppercase tracking-wider text-sm">
			<i class="material-icons align-middle mr-1">sort</i> Acomodando la gilada
		</div>
		<div class="flex justify-center gap-3 mb-8 flex-wrap">
			<button @click="sortLibrary('time')"
				class="bg-gray-800 hover:bg-gray-700 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">access_time</i> Como llegaron</button>
			<button @click="sortLibrary('artist')"
				class="bg-gray-800 hover:bg-gray-700 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">person</i> Por el que canta</button>
			<button @click="sortLibrary('shuffle', false)"
				class="bg-gray-800 hover:bg-gray-700 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">shuffle</i> Mezcladito (A lo loco)</button>
			<button @click="sortLibrary('mood')"
				class="bg-gray-800 hover:bg-gray-700 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">bolt</i> Más Manija</button>
		</div>

		<div class="text-center font-bold text-carpincho-secondary mb-4 uppercase tracking-wider text-sm">
			<i class="material-icons align-middle mr-1">celebration</i> La Joda
		</div>

		<!-- Local Listen Toggle -->
		<div
			class="w-full max-w-lg mx-auto flex items-center justify-between bg-carpincho-panel p-4 rounded-xl border-l-4 border-carpincho-warning shadow-md mb-8">
			<div class="text-left">
				<div class="font-bold text-carpincho-text flex items-center gap-2">
					<i class="material-icons text-carpincho-warning">headphones</i> Escuchar acá
				</div>
				<div class="text-xs text-[#a6adc8] mt-1">Stremea la música directo a tu celular o PC.</div>
			</div>
			<label class="relative inline-flex items-center cursor-pointer ml-4">
				<input type="checkbox" v-model="listenLocally" class="sr-only peer">
				<div
					class="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-carpincho-warning">
				</div>
			</label>
		</div>

		<!-- DJ Carpincho Toggle -->
		<div
			class="w-full max-w-lg mx-auto flex items-center justify-between bg-carpincho-panel p-4 rounded-xl border-l-4 border-carpincho-warning shadow-md mb-8">
			<div class="text-left">
				<div class="font-bold text-carpincho-text flex items-center gap-2">
					<i class="material-icons text-carpincho-warning">shuffle</i> DJ Carpincho
				</div>
				<div class="text-xs text-[#a6adc8]">Tira un tema random nuevo si se vacía la fila</div>
			</div>
			<label class="relative inline-flex items-center cursor-pointer ml-4">
				<input type="checkbox" :checked="djCarpinchoEnabled" @change="toggleDjCarpincho" class="sr-only peer">
				<div
					class="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-carpincho-success">
				</div>
			</label>
		</div>

		<!-- DJ Safe Mode Toggle -->
		<div v-show="djCarpinchoEnabled"
			class="w-full max-w-lg mx-auto flex items-center justify-between bg-carpincho-panel p-4 rounded-xl border-l-4 border-carpincho-warning shadow-md mb-8 transition-all">
			<div class="text-left">
				<div class="font-bold text-carpincho-text flex items-center gap-2">
					<i class="material-icons text-carpincho-warning">favorite</i> Capincho seguro
				</div>
				<div class="text-xs text-[#a6adc8]">Prioriza favoritos para que no decaiga</div>
			</div>
			<label class="relative inline-flex items-center cursor-pointer ml-4">
				<input type="checkbox" :checked="djSafeModeEnabled" @change="toggleDjSafeMode" class="sr-only peer">
				<div
					class="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-carpincho-success">
				</div>
			</label>
		</div>

		<div class="flex justify-center gap-3 mb-4 flex-wrap">
			<button @click="sendCmd('stop')"
				class="bg-red-700 hover:bg-red-600 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">stop</i> Cortala de una
			</button>
			<button @click="sendCmd('fullscreen')"
				class="bg-blue-700 hover:bg-blue-600 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">fullscreen</i> Todo pantalla, ñeri
			</button>
			<button @click="toggleMpvVisibility"
				class="bg-gray-700 hover:bg-gray-600 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">{{ mpvVisible ? 'visibility_off' : 'visibility' }}</i> {{ mpvVisible ?
					'Ocultar MPV' : 'Mostrar MPV' }}
			</button>
		</div>
		<div class="flex justify-center gap-3 mb-8 flex-wrap">
			<button @click="sendCmd('set_mute', { state: !serverMuted }); haptic()"
				:class="['px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2', serverMuted ? 'bg-red-700 hover:bg-red-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-white']">
				<i class="material-icons">{{ serverMuted ? 'volume_off' : 'volume_up' }}</i> {{ serverMuted ?
					'Desmutear' : 'Mutear' }}
			</button>
			<button @click="loadLibrary(true)"
				class="bg-green-700 hover:bg-green-600 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">refresh</i> Pegale otra escaneada
			</button>
			<button @click="toggleWebFullscreen"
				class="bg-purple-700 hover:bg-purple-600 text-white px-5 py-2 rounded-full font-medium active:scale-95 transition flex items-center gap-2">
				<i class="material-icons">open_in_full</i> Full Rockola
			</button>
		</div>

		<!-- QR Code -->
		<div class="text-center font-bold text-carpincho-secondary mb-4 uppercase tracking-wider text-sm">
			<i class="material-icons align-middle mr-1">qr_code_2</i> Sumate a la joda
		</div>
		<div class="flex flex-col items-center pb-20">
			<!-- Note the 'relative' class added here to contain the absolute image -->
			<div class="relative bg-white p-4 rounded-xl shadow-lg flex justify-center items-center">

				<!-- The Vue QR Component with your exact colors -->
				<QRCode :value="currentUrl" :size="200" level="H" foreground="#2b2622" background="#ffffff" />

				<!-- La impronta del carpincho -->
				<img src="/favicon.ico" alt="Logo Carpincho"
					class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[88px] h-[88px] p-1 rounded-lg" />

			</div>
			<p class="text-[#a6adc8] text-sm mt-3">Escaneá para entrar desde tu celu</p>
		</div>
	</section>
</template>
