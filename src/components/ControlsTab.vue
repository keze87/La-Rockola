<script setup lang="ts">
	import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
	import { registerOpenModal, unregisterOpenModal } from '../stores/useUiStore';
	import { apiUrl } from '../composables/useApi';
	import {
		activeRemoteServerUrl,
		androidServerStatus,
		connectToRemoteServer,
		disconnectFromRemoteServer,
		initAndroidServer,
		isAndroidFullscreen,
		isNativeAndroidHost,
		lastRemoteServerUrl,
		pickAndApplyMusicFolder,
		shareAndroidUrl,
		stopAndroidServer,
		toggleAndroidFullscreen,
	} from '../composables/useAndroidHost';
	import {
		clearServerError,
		isHostMode,
		isRemoteMode,
		lastServerError,
		libraryFolderError,
		libraryFolderStatus,
		localMusicDisplayName,
		localServerLanUrl,
		localServerState,
	} from '../stores/useServerConnectionStore';
	import { serverUrl, weatherLocation } from '../composables/player/state';
	import { useDragSlider } from '../composables/useDragSlider';
	import { useFullscreen } from '@vueuse/core';
	import { usePlaybackControls } from '../composables/usePlaybackControls';
	import { usePlayer } from '../composables/usePlayer';
	import PillButton from './ui/PillButton.vue';
	import QRCode from 'qrcode.vue';
	import ToggleRow from './ui/ToggleRow.vue';
	import WeatherLocationModal from './WeatherLocationModal.vue';

	const {
		fullscreen,
		setMute,
		setDjMode: setDjModeCmd,
		stop,
		toggleDjBara: toggleDjCmd,
		toggleRadioMode: toggleRadioCmd,
	} = usePlaybackControls();

	const {
		activeSort,
		defaultSort,
		djBaraEnabled,
		djMode,
		filteredTracks,
		handleScroll,
		haptic,
		hasEdgeTts,
		hasFfmpeg,
		hasLocalPlayer,
		hasMpv,
		isScanning,
		listenLocally,
		loadLibrary,
		mpvVisible,
		radioModeEnabled,
		returnToServerSpeakers,
		saveDefaultSort,
		scanStatus,
		serverMuted,
		setVolume,
		showToast,
		sortLibrary,
		switchTab,
		toggleMpvVisibility,
		volIcon,
		volume,
	} = usePlayer();

	async function handleSortClick(type: 'time' | 'artist' | 'mood' | 'shuffle') {
		if (activeSort.value === type) {
			try {
				await saveDefaultSort(type);
				showToast('¡Joyita! Guardado como orden por defecto', 'success');
				haptic();
			} catch (err) {
				console.error(err);
				showToast('Uy, no se pudo guardar la configuración', 'error');
			}
		} else {
			sortLibrary(type);
			haptic();
		}
		switchTab('library');
	}

	function getSortTooltip(type: 'time' | 'artist' | 'mood' | 'shuffle') {
		if (activeSort.value === type) {
			return defaultSort.value === type
				? 'Orden actual y por defecto en configuración'
				: 'Orden actual. Apretá de nuevo para guardar por defecto en la configuración';
		}
		return defaultSort.value === type ? 'Guardado como orden por defecto' : 'Ordenar sólo por esta sesión';
	}

	const sortOptions = computed(() => [
		{ id: 'time' as const, icon: 'access_time', label: 'Como llegaron', visible: true, disabled: false },
		{ id: 'artist' as const, icon: 'person', label: 'Por el que canta', visible: true, disabled: false },
		{
			id: 'mood' as const,
			icon: 'bolt',
			label: scanStatus.value?.is_analyzing_mood ? 'Sintonizando vibra...' : 'Más Manija',
			visible: hasFfmpeg.value,
			disabled: Boolean(scanStatus.value?.is_analyzing_mood),
		},
		{ id: 'shuffle' as const, icon: 'shuffle', label: 'Mezcladito (A lo loco)', visible: true, disabled: false },
	]);

	const isWeatherModalOpen = ref(false);

	let lastVolSent = 0;
	let volThrottleTimer: ReturnType<typeof setTimeout> | null = null;

	function throttledSetVolume() {
		const now = Date.now();
		if (now - lastVolSent >= 150) {
			lastVolSent = now;
			setVolume();
		} else if (!volThrottleTimer) {
			volThrottleTimer = setTimeout(() => {
				volThrottleTimer = null;
				lastVolSent = Date.now();
				setVolume();
			}, 150);
		}
	}

	const {
		progressPercent: volPercent,
		startDrag: startVol,
		moveDrag: moveVol,
		endDrag: endVol,
	} = useDragSlider({
		max: () => (isNativeAndroidHost() ? 100 : 110),
		getValue: () => volume.value,
		onUpdate: (val) => {
			volume.value = Math.round(val);

			if (serverMuted.value && volume.value > 0) {
				setMute(false);
			}
			throttledSetVolume();
		},
		onCommit: (val) => {
			if (volThrottleTimer) {
				clearTimeout(volThrottleTimer);
				volThrottleTimer = null;
			}
			volume.value = Math.round(val);
			setVolume();
		},
	});

	const currentUrl = computed(() => {
		// Si el usuario abrió la app desde localhost o 127.0.0.1 pero el servidor
		// conoce la IP de la red local, usamos la URL de red para que el código QR
		// sirva para escanear desde celulares conectados al mismo Wi-Fi.
		const isLocalhost =
			window.location.hostname === 'localhost' ||
			window.location.hostname === '127.0.0.1' ||
			window.location.hostname === '::1';

		if ((isLocalhost || isNativeAndroidHost()) && serverUrl.value) {
			return serverUrl.value;
		}
		return window.location.href;
	});

	const showAndroidFolderPicker = computed(() => isNativeAndroidHost() && isHostMode.value);
	const showRemoteServerSelector = computed(() => isNativeAndroidHost());
	const isRemoteServerModalOpen = ref(false);
	const remoteDialogRef = ref<HTMLDialogElement | null>(null);
	let pointerStartedOutsideDialog = false;
	const remoteServerInput = ref(lastRemoteServerUrl.value ?? '');
	const isConnectingRemote = ref(false);

	const hostStateLabel = computed(() => {
		switch (localServerState.value) {
			case 'ready':
				return 'Encendido';
			case 'starting':
				return 'Arrancando...';
			case 'recovering':
				return 'Reconectando...';
			case 'stopping':
				return 'Apagando...';
			case 'unavailable':
				return 'Con error';
			default:
				return 'Detenido';
		}
	});

	watch(isRemoteServerModalOpen, async (open) => {
		if (open) {
			registerOpenModal('remote-server-modal', () => {
				isRemoteServerModalOpen.value = false;
			});
		} else {
			unregisterOpenModal('remote-server-modal');
		}
		await nextTick();
		const dlg = remoteDialogRef.value;
		if (!dlg) return;
		if (!dlg.hasAttribute('closedby')) {
			dlg.setAttribute('closedby', 'any');
		}
		if (open) {
			if (typeof dlg.showModal === 'function') {
				if (!dlg.open) dlg.showModal();
			} else {
				dlg.setAttribute('open', '');
			}
		} else if (typeof dlg.close === 'function') {
			if (dlg.open) dlg.close();
		} else {
			dlg.removeAttribute('open');
		}
	});

	onUnmounted(() => {
		unregisterOpenModal('remote-server-modal');
	});

	function isPointerOutsideDialog(e: PointerEvent, dlg: HTMLDialogElement): boolean {
		const rect = dlg.getBoundingClientRect();
		return e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom;
	}

	function onRemoteDialogPointerDown(e: PointerEvent) {
		const dlg = remoteDialogRef.value;
		pointerStartedOutsideDialog = Boolean(dlg && e.target === dlg && isPointerOutsideDialog(e, dlg));
	}

	function onRemoteDialogPointerUp(e: PointerEvent) {
		const dlg = remoteDialogRef.value;
		if (pointerStartedOutsideDialog && dlg && e.target === dlg && isPointerOutsideDialog(e, dlg)) {
			isRemoteServerModalOpen.value = false;
		}
		pointerStartedOutsideDialog = false;
	}

	async function handleStartLocalHost() {
		haptic();
		const ok = await initAndroidServer();
		if (ok) {
			showToast('Servidor local encendido', 'success');
			void loadLibrary(false);
		}
	}

	async function handleStopLocalHost() {
		haptic();
		try {
			await stopAndroidServer();
			showToast('Servidor local apagado', 'info');
		} catch (err) {
			showToast(err instanceof Error ? err.message : 'No se pudo apagar el servidor', 'error');
		}
	}

	function handleToggleRemoteServerSwitch(next: boolean) {
		haptic();
		if (next) {
			remoteServerInput.value = activeRemoteServerUrl.value ?? lastRemoteServerUrl.value ?? '';
			isRemoteServerModalOpen.value = true;
		} else {
			isRemoteServerModalOpen.value = false;
			if (isRemoteMode.value) {
				disconnectFromRemoteServer();
				void loadLibrary(false);
				showToast('Volviste al servidor de este teléfono', 'info');
			}
		}
	}

	async function handleConnectRemoteServer() {
		if (isConnectingRemote.value) return;
		isConnectingRemote.value = true;
		try {
			const url = await connectToRemoteServer(remoteServerInput.value);
			isRemoteServerModalOpen.value = false;
			showToast(`Conectado al servidor ${url}`, 'success');
			haptic();
			void loadLibrary(false);
		} catch (err) {
			const msg = err instanceof Error ? err.message : 'No se pudo conectar al servidor';
			showToast(msg, 'error');
		} finally {
			isConnectingRemote.value = false;
		}
	}

	function handleUseLocalServer() {
		disconnectFromRemoteServer();
		isRemoteServerModalOpen.value = false;
		haptic();
		void loadLibrary(false);
		showToast('Volviste al servidor de este teléfono', 'info');
	}

	async function handlePickMusicFolder() {
		try {
			const selected = await pickAndApplyMusicFolder();
			if (selected) {
				showToast(`Carpeta de música actualizada: ${selected}`, 'success');
				haptic();
			}
		} catch (err) {
			console.error(err);
			showToast('No se pudo acceder a la carpeta elegida', 'error');
		}
	}

	// --- Interruptores ---
	function toggleDjBara() {
		toggleDjCmd(!djBaraEnabled.value);
		haptic();
	}

	function handleSetDjMode(mode: 'shuffle' | 'favorites' | 'library') {
		const paths = mode === 'library' ? filteredTracks.value.map((t) => t.path) : undefined;
		setDjModeCmd(mode, paths);
		haptic();
	}

	function toggleRadioMode() {
		toggleRadioCmd(!radioModeEnabled.value);
		haptic();
	}

	const { isFullscreen, toggle: toggleWebFullscreen } = useFullscreen();
	const isFullRockola = computed(() => (isNativeAndroidHost() ? isAndroidFullscreen.value : isFullscreen.value));

	async function toggleFullRockola() {
		if (isNativeAndroidHost()) {
			await toggleAndroidFullscreen();
		} else {
			await toggleWebFullscreen();
		}
		haptic();
	}

	async function handleShareUrl() {
		const url = currentUrl.value;
		const title = 'La Rockola del Carpincho';
		const text = 'Sumate a la ronda desde tu celu:';

		if (isNativeAndroidHost()) {
			const shared = await shareAndroidUrl({ url, title, text });
			if (shared) haptic();
			return;
		}

		if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
			try {
				await navigator.share({ title, text, url });
				haptic();
				return;
			} catch (err) {
				if ((err as Error)?.name === 'AbortError') return;
			}
		}

		try {
			await navigator.clipboard?.writeText(url);
			showToast('¡Joyita! Link copiado al portapapeles', 'success');
			haptic();
		} catch (err) {
			console.error(err);
			showToast('Uy, no se pudo compartir el link', 'error');
		}
	}

	const resolvedWeatherArea = ref<string | null>(null);

	const isCoordinatesLocation = (loc: string): boolean =>
		/^[-+]?\d+(\.\d+)?\s*,\s*[-+]?\d+(\.\d+)?$/.test(loc.trim());

	async function resolveWttrLocation(loc: string) {
		const trimmed = loc.trim();
		if (!trimmed) {
			resolvedWeatherArea.value = null;
			return;
		}

		if (!isCoordinatesLocation(trimmed)) {
			resolvedWeatherArea.value = null;
			return;
		}

		try {
			const res = await fetch(apiUrl(`/api/weather/preview?location=${encodeURIComponent(trimmed)}`));
			const data = await res.json();
			if (data && data.ok && data.area_name) {
				resolvedWeatherArea.value = data.area_name;
			}
		} catch {
			// En caso de fallo de red o error de wttr, se mantiene el fallback reactivo
		}
	}

	watch(
		weatherLocation,
		(newLoc) => {
			if (newLoc) {
				resolveWttrLocation(newLoc);
			} else {
				resolvedWeatherArea.value = null;
			}
		},
		{ immediate: true }
	);

	const displayWeatherLocation = computed(() => {
		if (!weatherLocation.value) return '';
		if (isCoordinatesLocation(weatherLocation.value)) {
			return resolvedWeatherArea.value || weatherLocation.value;
		}
		return weatherLocation.value;
	});
	function onTabScroll(e: Event) {
		const target = e.target as HTMLElement;
		if (target) {
			handleScroll(target.scrollTop);
		}
	}
</script>

<template>
	<section
		id="controls-tab"
		class="tab-content bg-carpincho-bg h-full overflow-y-auto px-6 pt-6"
		@scroll.passive="onTabScroll"
	>
		<!-- Control deslizante de volumen -->
		<div class="text-carpincho-warning bg-carpincho-panel mb-8 flex items-center rounded-xl p-4 shadow">
			<button
				type="button"
				:aria-label="serverMuted ? 'Desmutear audio' : 'Mutear audio'"
				:title="serverMuted ? 'Desmutear' : 'Mutear'"
				class="touch-target inline-flex cursor-pointer items-center justify-center rounded-full"
				@click="
					setMute(!serverMuted);
					haptic();
				"
			>
				<i class="material-icons mr-3 cursor-pointer transition-colors hover:text-white" aria-hidden="true">
					{{ volIcon }}
				</i>
			</button>
			<div
				class="no-tab-swipe group flex h-8 w-full cursor-pointer touch-none items-center"
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

		<!-- Opciones de ordenamiento -->
		<div class="text-carpincho-secondary mb-1 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">sort</i>
			Acomodando la gilada
		</div>
		<p class="text-carpincho-muted mb-4 text-center text-xs">
			Tocá de nuevo el orden activo para fijarlo por defecto
		</p>

		<div class="mb-8 flex flex-wrap justify-center gap-3">
			<template v-for="opt in sortOptions" :key="opt.id">
				<PillButton
					v-if="opt.visible"
					:icon="opt.icon"
					:title="getSortTooltip(opt.id)"
					:disabled="opt.disabled"
					:color-class="
						activeSort === opt.id
							? 'bg-amber-700 hover:bg-amber-600 ring-2 ring-carpincho-warning'
							: 'bg-gray-800 hover:bg-gray-700'
					"
					@click="handleSortClick(opt.id)"
				>
					{{ opt.label }}
					<i
						v-if="defaultSort === opt.id"
						class="material-icons text-carpincho-warning ml-1 align-middle text-sm"
						aria-label="Orden por defecto"
						title="Guardado como orden por defecto"
					>
						push_pin
					</i>
				</PillButton>
			</template>
		</div>

		<!-- Interruptores de opciones -->
		<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">celebration</i>
			La Joda
		</div>

		<!-- Interruptor para escuchar en el cliente -->
		<ToggleRow
			v-if="!isNativeAndroidHost() || isRemoteMode"
			v-model="listenLocally"
			icon="headphones"
			title="Escuchar acá"
			description="Stremea la música directo a tu celular o PC."
		/>

		<ToggleRow
			v-if="hasEdgeTts"
			:model-value="radioModeEnabled"
			icon="record_voice_over"
			title="Carpincho locutor"
			description="Tira la hora, una fortuna y comenta entre temas"
			active-class="bg-carpincho-success"
			@update:model-value="toggleRadioMode"
		/>

		<ToggleRow
			:model-value="djBaraEnabled"
			icon="shuffle"
			title="DJ Bara"
			description="Continúa la música si se vacía la fila"
			active-class="bg-carpincho-success"
			@update:model-value="toggleDjBara"
		/>

		<!-- Selector de modo para DJ Bara -->
		<div v-show="djBaraEnabled" class="mb-4 flex flex-col items-center gap-2 pb-4">
			<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
				<i class="material-icons mr-1 align-middle">auto_fix_high</i>
				Modo del DJ Bara
			</div>
			<div class="flex flex-wrap justify-center gap-2">
				<PillButton
					icon="shuffle"
					:color-class="
						djMode === 'shuffle'
							? 'bg-carpincho-primary text-carpincho-panel font-bold'
							: 'bg-neutral-800 hover:bg-neutral-700 text-white'
					"
					title="Elige temas al azar de la biblioteca"
					@click="handleSetDjMode('shuffle')"
				>
					Aleatorio
				</PillButton>
				<PillButton
					icon="favorite"
					:color-class="
						djMode === 'favorites'
							? 'bg-carpincho-primary text-carpincho-panel font-bold'
							: 'bg-neutral-800 hover:bg-neutral-700 text-white'
					"
					title="Elige temas al azar priorizando tus favoritos"
					@click="handleSetDjMode('favorites')"
				>
					Favoritos
				</PillButton>
				<PillButton
					icon="format_list_bulleted"
					:color-class="
						djMode === 'library'
							? 'bg-carpincho-primary text-carpincho-panel font-bold'
							: 'bg-neutral-800 hover:bg-neutral-700 text-white'
					"
					title="Reproduce el siguiente tema respetando el orden y filtro de la biblioteca"
					@click="handleSetDjMode('library')"
				>
					Lista de librería
				</PillButton>
			</div>
		</div>

		<div v-if="showRemoteServerSelector" class="mx-auto mb-6 max-w-md">
			<ToggleRow
				:model-value="isRemoteMode || isRemoteServerModalOpen"
				title="Conectar a otro servidor"
				:description="
					isRemoteMode ? `Conectado a ${activeRemoteServerUrl}` : 'Usando este teléfono (servidor local)'
				"
				icon="dns"
				@update:model-value="handleToggleRemoteServerSwitch"
			/>
		</div>

		<!-- Botones de acción -->
		<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">settings</i>
			Lo controle
		</div>

		<div v-if="hasEdgeTts" class="mb-4 flex flex-wrap justify-center gap-3">
			<PillButton icon="map" color-class="bg-neutral-800 hover:bg-neutral-700" @click="isWeatherModalOpen = true">
				{{ displayWeatherLocation ? `Ubicación del Clima: ${displayWeatherLocation}` : 'Configurar ubicación' }}
			</PillButton>
		</div>

		<div v-if="hasMpv && hasLocalPlayer && !listenLocally" class="mb-4 flex flex-wrap justify-center gap-3">
			<PillButton icon="volume_up" color-class="bg-amber-700 hover:bg-amber-600" @click="returnToServerSpeakers">
				Volver a parlantes del servidor
			</PillButton>
		</div>

		<div
			v-if="!hasMpv && !listenLocally && !hasLocalPlayer && (!isNativeAndroidHost() || isRemoteMode)"
			class="mb-4 flex flex-wrap justify-center gap-3"
		>
			<PillButton
				icon="headphones"
				color-class="bg-carpincho-success hover:brightness-110 text-white font-bold"
				@click="
					listenLocally = true;
					haptic();
				"
			>
				Escuchar en este dispositivo
			</PillButton>
		</div>

		<div v-if="showAndroidFolderPicker" class="mb-4 flex flex-col items-center gap-2">
			<PillButton icon="sd_card" color-class="bg-amber-700 hover:bg-amber-600" @click="handlePickMusicFolder">
				Elegir carpeta de música
			</PillButton>
			<p v-if="androidServerStatus.musicDir" class="text-carpincho-muted max-w-xs truncate text-xs">
				{{ androidServerStatus.musicDir }}
			</p>
		</div>

		<dialog
			ref="remoteDialogRef"
			aria-labelledby="remote-dialog-title"
			class="border-carpincho-border bg-carpincho-panel text-carpincho-text m-auto w-[min(92vw,28rem)] rounded-2xl border p-5 shadow-2xl backdrop:bg-black/75 backdrop:backdrop-blur-sm"
			@cancel.prevent="isRemoteServerModalOpen = false"
			@close="isRemoteServerModalOpen = false"
			@pointerdown="onRemoteDialogPointerDown"
			@pointerup="onRemoteDialogPointerUp"
		>
			<div class="mb-3 flex items-center justify-between gap-2">
				<h3
					id="remote-dialog-title"
					class="text-carpincho-secondary flex items-center gap-2 text-base font-bold"
				>
					<i class="material-icons !text-lg" aria-hidden="true">dns</i>
					<span>Conectar a otro servidor</span>
				</h3>
				<button
					type="button"
					aria-label="Cerrar diálogo"
					class="touch-target text-carpincho-muted hover:text-carpincho-text inline-flex cursor-pointer items-center justify-center rounded-full p-1"
					@click="isRemoteServerModalOpen = false"
				>
					<i class="material-icons !text-lg" aria-hidden="true">close</i>
				</button>
			</div>
			<label for="remote-server-input" class="text-carpincho-muted mb-3 block text-xs">
				Ingresá la IP o URL de tu PC (ej: 192.168.0.55). Se guarda el último servidor para volver fácil.
			</label>
			<input
				id="remote-server-input"
				v-model="remoteServerInput"
				type="text"
				placeholder="IP de tu PC (ej: 192.168.0.55)"
				class="border-carpincho-border bg-carpincho-bg text-carpincho-text placeholder:text-carpincho-muted/60 focus:border-carpincho-warning mb-4 w-full rounded-lg border px-3 py-2 text-sm outline-none"
				@keyup.enter="handleConnectRemoteServer"
			/>
			<div class="flex flex-wrap justify-end gap-2">
				<PillButton
					v-if="isRemoteMode"
					icon="smartphone"
					color-class="bg-neutral-700 hover:bg-neutral-600"
					@click="handleUseLocalServer"
				>
					Usar este teléfono
				</PillButton>
				<PillButton
					icon="close"
					color-class="bg-neutral-800 hover:bg-neutral-700"
					@click="isRemoteServerModalOpen = false"
				>
					Cancelar
				</PillButton>
				<PillButton
					icon="link"
					color-class="bg-amber-700 hover:bg-amber-600"
					:disabled="isConnectingRemote || !remoteServerInput.trim()"
					@click="handleConnectRemoteServer"
				>
					{{ isConnectingRemote ? 'Conectando...' : 'Conectar' }}
				</PillButton>
			</div>
		</dialog>

		<div class="mb-4 flex flex-wrap justify-center gap-3">
			<PillButton icon="stop" color-class="bg-red-700 hover:bg-red-600" @click="stop">Cortala de una</PillButton>

			<PillButton v-if="hasMpv" icon="fullscreen" color-class="bg-blue-700 hover:bg-blue-600" @click="fullscreen">
				Todo pantalla, ñeri
			</PillButton>

			<PillButton
				v-if="hasMpv"
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

			<PillButton
				:icon="isScanning ? 'sync' : 'refresh'"
				:color-class="
					isScanning || Boolean(scanStatus?.is_analyzing_mood)
						? 'bg-gray-700'
						: 'bg-green-700 hover:bg-green-600'
				"
				:disabled="isScanning || Boolean(scanStatus?.is_analyzing_mood)"
				@click="loadLibrary(true)"
			>
				<template v-if="isScanning">
					Escaneando...
					<template v-if="scanStatus?.total > 0">({{ scanStatus.current }}/{{ scanStatus.total }})</template>
				</template>
				<template v-else>Pegale otra escaneada</template>
			</PillButton>

			<PillButton
				:icon="isFullRockola ? 'fullscreen_exit' : 'open_in_full'"
				color-class="bg-purple-700 hover:bg-purple-600"
				@click="toggleFullRockola"
			>
				Full Rockola
			</PillButton>
		</div>

		<!-- Código QR -->
		<div class="text-carpincho-secondary mb-4 text-center text-sm font-bold tracking-wider uppercase">
			<i class="material-icons mr-1 align-middle">qr_code_2</i>
			Sumate a la joda
		</div>

		<div class="flex flex-col items-center pb-20">
			<!-- Clase 'relative' agregada para contener la imagen absoluta -->
			<div class="relative flex items-center justify-center rounded-xl bg-white p-4 shadow-lg">
				<!-- Componente QR con los colores de la aplicación -->
				<QRCode :value="currentUrl" :size="200" level="H" foreground="#2b2622" background="#ffffff" />

				<!-- La impronta del carpincho -->
				<img
					:src="apiUrl('/favicon.png')"
					alt="Logo Carpincho"
					class="absolute top-1/2 left-1/2 h-[88px] w-[88px] -translate-x-1/2 -translate-y-1/2 rounded-lg p-1"
				/>
			</div>
			<p class="text-carpincho-muted mt-3 text-sm">Escaneá para entrar desde tu celu</p>
			<PillButton icon="share" color-class="bg-amber-700 hover:bg-amber-600 mt-4" @click="handleShareUrl">
				Compartir link
			</PillButton>
		</div>

		<div
			v-if="showRemoteServerSelector"
			class="border-carpincho-border bg-carpincho-panel mx-auto mb-6 max-w-md rounded-xl border p-4 shadow"
		>
			<div class="mb-2 flex items-center justify-between gap-2">
				<span class="text-carpincho-secondary text-xs font-bold tracking-wider uppercase">
					{{ isRemoteMode ? 'Modo Cliente remoto' : 'Modo Host local' }}
				</span>
				<span
					class="rounded-full px-2.5 py-0.5 text-xs font-bold"
					:class="
						isRemoteMode || localServerState === 'ready'
							? 'bg-carpincho-success/25 text-carpincho-warning'
							: 'text-carpincho-muted bg-neutral-800'
					"
				>
					{{ isRemoteMode ? 'Conectado' : hostStateLabel }}
				</span>
			</div>

			<div v-if="isHostMode" class="text-carpincho-muted space-y-1 text-xs">
				<p v-if="localServerState === 'ready'">
					Dirección en tu Wi-Fi:
					<span class="text-carpincho-text font-mono">{{ localServerLanUrl }}</span>
				</p>
				<p v-if="androidServerStatus.musicDir || libraryFolderStatus !== 'ok'">
					Carpeta:
					<span class="text-carpincho-text">
						{{ localMusicDisplayName || androidServerStatus.musicDir || 'Sin elegir' }}
					</span>
					<span v-if="libraryFolderError" class="text-red-400">· {{ libraryFolderError }}</span>
				</p>
				<p class="leading-relaxed">
					El servidor embebido se mantiene activo mientras suena música o la app está abierta; Android puede
					detenerlo si la cerrás en reposo.
				</p>
				<div class="flex flex-wrap gap-2 pt-2">
					<button
						v-if="localServerState === 'stopped' || localServerState === 'unavailable'"
						type="button"
						class="touch-target bg-carpincho-success cursor-pointer rounded-full px-3.5 py-1.5 text-xs font-bold text-white shadow transition hover:brightness-110"
						@click="handleStartLocalHost"
					>
						Prender servidor
					</button>
					<button
						v-else
						type="button"
						class="touch-target cursor-pointer rounded-full bg-red-800 px-3.5 py-1.5 text-xs font-bold text-white shadow transition hover:bg-red-700"
						:disabled="localServerState === 'stopping'"
						@click="handleStopLocalHost"
					>
						Apagar servidor
					</button>
				</div>
			</div>
			<p v-else class="text-carpincho-muted text-xs">
				Controlando el servidor remoto
				<span class="text-carpincho-text font-mono">{{ activeRemoteServerUrl }}</span>
			</p>

			<div
				v-if="lastServerError"
				role="alert"
				class="mt-3 flex items-start justify-between gap-2 rounded-lg border border-red-500/40 bg-red-950/50 px-3 py-2 text-xs text-red-200"
			>
				<span>{{ lastServerError.message }}</span>
				<button
					type="button"
					aria-label="Descartar aviso"
					class="touch-target shrink-0 cursor-pointer rounded px-1.5 font-bold text-red-300 hover:text-white"
					@click="clearServerError()"
				>
					✕
				</button>
			</div>
		</div>

		<WeatherLocationModal :is-open="isWeatherModalOpen" @close="isWeatherModalOpen = false" />
	</section>
</template>
