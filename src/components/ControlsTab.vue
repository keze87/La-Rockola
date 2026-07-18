<script setup>
    import { ref, computed } from 'vue';
    import { usePlayer } from '../composables/usePlayer';
    import QRCode from 'qrcode.vue';

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

        <div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
            <i class="material-icons mr-1 align-middle">sort</i>
            Acomodando la gilada
        </div>
        <div class="mb-8 flex flex-wrap justify-center gap-3">
            <button
                class="flex items-center gap-2 rounded-full bg-gray-800 px-5 py-2 font-medium text-white transition hover:bg-gray-700 active:scale-95"
                @click="sortLibrary('time')"
            >
                <i class="material-icons">access_time</i>
                Como llegaron
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-gray-800 px-5 py-2 font-medium text-white transition hover:bg-gray-700 active:scale-95"
                @click="sortLibrary('artist')"
            >
                <i class="material-icons">person</i>
                Por el que canta
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-gray-800 px-5 py-2 font-medium text-white transition hover:bg-gray-700 active:scale-95"
                @click="sortLibrary('shuffle', false)"
            >
                <i class="material-icons">shuffle</i>
                Mezcladito (A lo loco)
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-gray-800 px-5 py-2 font-medium text-white transition hover:bg-gray-700 active:scale-95"
                @click="sortLibrary('mood')"
            >
                <i class="material-icons">bolt</i>
                Más Manija
            </button>
        </div>

        <div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
            <i class="material-icons mr-1 align-middle">celebration</i>
            La Joda
        </div>

        <!-- Local Listen Toggle -->
        <div
            class="bg-carpincho-panel border-carpincho-warning mx-auto mb-8 flex w-full max-w-lg items-center justify-between rounded-xl border-l-4 p-4 shadow-md"
        >
            <div class="text-left">
                <div class="text-carpincho-text flex items-center gap-2 font-bold">
                    <i class="material-icons text-carpincho-warning">headphones</i>
                    Escuchar acá
                </div>
                <div class="mt-1 text-xs text-[#a6adc8]">Stremea la música directo a tu celular o PC.</div>
            </div>
            <label class="relative ml-4 inline-flex cursor-pointer items-center">
                <input v-model="listenLocally" type="checkbox" class="peer sr-only" />
                <div
                    class="peer peer-checked:bg-carpincho-warning h-6 w-11 rounded-full bg-gray-700 peer-focus:outline-none after:absolute after:top-[2px] after:left-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white"
                />
            </label>
        </div>

        <!-- DJ Carpincho Toggle -->
        <div
            class="bg-carpincho-panel border-carpincho-warning mx-auto mb-8 flex w-full max-w-lg items-center justify-between rounded-xl border-l-4 p-4 shadow-md"
        >
            <div class="text-left">
                <div class="text-carpincho-text flex items-center gap-2 font-bold">
                    <i class="material-icons text-carpincho-warning">shuffle</i>
                    DJ Carpincho
                </div>
                <div class="text-xs text-[#a6adc8]">Tira un tema random nuevo si se vacía la fila</div>
            </div>
            <label class="relative ml-4 inline-flex cursor-pointer items-center">
                <input type="checkbox" :checked="djCarpinchoEnabled" class="peer sr-only" @change="toggleDjCarpincho" />
                <div
                    class="peer peer-checked:bg-carpincho-success h-6 w-11 rounded-full bg-gray-700 peer-focus:outline-none after:absolute after:top-[2px] after:left-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white"
                />
            </label>
        </div>

        <!-- DJ Safe Mode Toggle -->
        <div
            v-show="djCarpinchoEnabled"
            class="bg-carpincho-panel border-carpincho-warning mx-auto mb-8 flex w-full max-w-lg items-center justify-between rounded-xl border-l-4 p-4 shadow-md transition-all"
        >
            <div class="text-left">
                <div class="text-carpincho-text flex items-center gap-2 font-bold">
                    <i class="material-icons text-carpincho-warning">favorite</i>
                    Capincho seguro
                </div>
                <div class="text-xs text-[#a6adc8]">Prioriza favoritos para que no decaiga</div>
            </div>
            <label class="relative ml-4 inline-flex cursor-pointer items-center">
                <input type="checkbox" :checked="djSafeModeEnabled" class="peer sr-only" @change="toggleDjSafeMode" />
                <div
                    class="peer peer-checked:bg-carpincho-success h-6 w-11 rounded-full bg-gray-700 peer-focus:outline-none after:absolute after:top-[2px] after:left-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white"
                />
            </label>
        </div>

        <div class="mb-4 flex flex-wrap justify-center gap-3">
            <button
                class="flex items-center gap-2 rounded-full bg-red-700 px-5 py-2 font-medium text-white transition hover:bg-red-600 active:scale-95"
                @click="sendCmd('stop')"
            >
                <i class="material-icons">stop</i>
                Cortala de una
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-blue-700 px-5 py-2 font-medium text-white transition hover:bg-blue-600 active:scale-95"
                @click="sendCmd('fullscreen')"
            >
                <i class="material-icons">fullscreen</i>
                Todo pantalla, ñeri
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-gray-700 px-5 py-2 font-medium text-white transition hover:bg-gray-600 active:scale-95"
                @click="toggleMpvVisibility"
            >
                <i class="material-icons">{{ mpvVisible ? 'visibility_off' : 'visibility' }}</i>
                {{ mpvVisible ? 'Ocultar MPV' : 'Mostrar MPV' }}
            </button>
        </div>
        <div class="mb-8 flex flex-wrap justify-center gap-3">
            <button
                :class="[
                    'flex items-center gap-2 rounded-full px-5 py-2 font-medium transition active:scale-95',
                    serverMuted ? 'bg-red-700 text-white hover:bg-red-600' : 'bg-gray-700 text-white hover:bg-gray-600',
                ]"
                @click="
                    sendCmd('set_mute', { state: !serverMuted });
                    haptic();
                "
            >
                <i class="material-icons">{{ serverMuted ? 'volume_off' : 'volume_up' }}</i>
                {{ serverMuted ? 'Desmutear' : 'Mutear' }}
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-green-700 px-5 py-2 font-medium text-white transition hover:bg-green-600 active:scale-95"
                @click="loadLibrary(true)"
            >
                <i class="material-icons">refresh</i>
                Pegale otra escaneada
            </button>
            <button
                class="flex items-center gap-2 rounded-full bg-purple-700 px-5 py-2 font-medium text-white transition hover:bg-purple-600 active:scale-95"
                @click="toggleWebFullscreen"
            >
                <i class="material-icons">open_in_full</i>
                Full Rockola
            </button>
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
            <p class="mt-3 text-sm text-[#a6adc8]">Escaneá para entrar desde tu celu</p>
        </div>
    </section>
</template>
