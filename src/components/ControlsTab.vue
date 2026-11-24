<script setup lang="ts">
	import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
	import { registerOpenModal, unregisterOpenModal } from '../stores/useUiStore';
	import { apiUrl } from '../composables/useApi';
	import {
		activeRemoteServerUrl,
		androidNotificationPermission,
		androidServerStatus,
		connectToRemoteServer,
		disconnectFromRemoteServer,
		initAndroidServer,
		isAndroidFullscreen,
		isNativeAndroidHost,
		lastRemoteServerUrl,
		openAndroidNotificationSettings,
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
		clearRound,
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
		haptic(next ? 'toggle_on' : 'toggle_off');
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
			haptic('confirm');
			void loadLibrary(false);
		} catch (err) {
			const msg = err instanceof Error ? err.message : 'No se pudo conectar al servidor';
			showToast(msg, 'error');
			haptic('reject');
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
		class="tab-content h-full overflow-y-auto bg-[var(--bg-canvas)] px-4 pt-5 sm:px-6"
		@scroll.passive="onTabScroll"
	>
		<!-- Control deslizante de volumen -->
		<div
			class="mx-auto mb-7 max-w-lg rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)] px-4 py-3.5"
		>
			<div class="mb-2 flex items-center justify-between">
				<span class="text-[12px] font-semibold tracking-[0.06em] text-[var(--text-secondary)] uppercase">
					Volumen
				</span>
				<span class="text-[12px] font-bold text-[var(--accent-primary)] tabular-nums">
					{{ serverMuted ? 'Muteado' : `${Math.round(volPercent)}%` }}
				</span>
			</div>
			<div class="flex items-center gap-3">
				<button
					type="button"
					:aria-label="serverMuted ? 'Desmutear audio' : 'Mutear audio'"
					:title="serverMuted ? 'Desmutear' : 'Mutear'"
					class="touch-target tap-feedback inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full bg-[var(--bg-input)] text-[var(--text-primary)] opacity-85 transition-opacity hover:opacity-100"
					@click="
						setMute(!serverMuted);
						haptic();
					"
				>
					<i class="material-icons !text-[19px]" aria-hidden="true">
						{{ volIcon }}
					</i>
				</button>
				<div
					class="no-tab-swipe group flex h-9 w-full cursor-pointer touch-none items-center"
					:class="{ 'opacity-45': serverMuted }"
					@pointerdown="startVol"
					@pointermove="moveVol"
					@pointerup="endVol"
					@pointercancel="endVol"
				>
					<div
						class="relative h-[8px] w-full overflow-hidden rounded-full bg-[rgba(255,236,210,0.12)] transition-[height] duration-150 group-active:h-[10px]"
					>
						<div
							class="absolute top-0 left-0 h-full rounded-full bg-[var(--accent-primary)]"
							:style="{ width: volPercent + '%' }"
						/>
						<div
							class="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--text-primary)] shadow-[0_1px_4px_rgba(0,0,0,0.45)] transition-transform group-active:scale-110"
							:style="{ left: `clamp(7px, ${volPercent}%, calc(100% - 7px))` }"
						/>
					</div>
				</div>
				<i class="material-icons shrink-0 !text-[18px] text-[var(--text-secondary)]" aria-hidden="true">
					volume_up
				</i>
			</div>
		</div>

		<!-- Opciones de ordenamiento -->
		<div class="mx-auto mb-2 max-w-lg px-1">
			<div
				class="flex items-center gap-1.5 text-[12px] font-semibold tracking-[0.06em] text-[var(--text-secondary)] uppercase"
			>
				<i class="material-icons !text-[16px] text-[var(--accent-primary)]" aria-hidden="true">sort</i>
				<span>Acomodando la gilada</span>
			</div>
			<p class="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
				Tocá de nuevo el orden activo para fijarlo por defecto
			</p>
		</div>

		<div
			class="mx-auto mb-7 flex max-w-lg flex-col gap-1 rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)] p-1.5"
		>
			<template v-for="opt in sortOptions" :key="opt.id">
				<PillButton
					v-if="opt.visible"
					:icon="opt.icon"
					:title="getSortTooltip(opt.id)"
					:disabled="opt.disabled"
					:color-class="
						activeSort === opt.id
							? 'w-full justify-between !rounded-[11px] border-transparent bg-[var(--accent-primary)] text-[#120e0b] font-bold shadow-sm'
							: 'w-full justify-between !rounded-[11px] border-transparent bg-transparent text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)]'
					"
					@click="handleSortClick(opt.id)"
				>
					<span class="flex-1 text-left">{{ opt.label }}</span>
					<i
						v-if="defaultSort === opt.id"
						class="material-icons ml-1 !text-[18px]"
						:class="activeSort === opt.id ? 'text-[#120e0b]' : 'text-[var(--accent-primary)]'"
						aria-label="Orden por defecto"
						title="Guardado como orden por defecto"
					>
						push_pin
					</i>
				</PillButton>
			</template>
		</div>

		<!-- Interruptores de opciones -->
		<div class="mx-auto mb-2 max-w-lg px-1">
			<div
				class="flex items-center gap-1.5 text-[12px] font-semibold tracking-[0.06em] text-[var(--text-secondary)] uppercase"
			>
				<i class="material-icons !text-[16px] text-[var(--accent-primary)]" aria-hidden="true">celebration</i>
				<span>La Joda</span>
			</div>
		</div>

		<div
			class="mx-auto mb-6 max-w-lg divide-y divide-[var(--hairline)] overflow-hidden rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)]"
		>
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
				@update:model-value="toggleRadioMode"
			/>

			<ToggleRow
				:model-value="djBaraEnabled"
				icon="shuffle"
				title="DJ Bara"
				description="Continúa la música si se vacía la fila"
				@update:model-value="toggleDjBara"
			/>
		</div>

		<!-- Selector de modo para DJ Bara -->
		<div
			v-show="djBaraEnabled"
			class="mx-auto mb-6 max-w-lg rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)] p-4"
		>
			<div
				class="mb-3 flex items-center justify-center gap-1.5 text-[12px] font-semibold tracking-[0.06em] text-[var(--text-secondary)] uppercase"
			>
				<i class="material-icons !text-[16px] text-[var(--accent-primary)]" aria-hidden="true">auto_fix_high</i>
				<span>Modo del DJ Bara</span>
			</div>
			<div class="flex flex-wrap justify-center gap-2">
				<PillButton
					icon="shuffle"
					:color-class="
						djMode === 'shuffle'
							? 'border-transparent bg-[var(--accent-primary)] text-[#120e0b] font-bold'
							: 'border border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)]'
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
							? 'border-transparent bg-[var(--accent-primary)] text-[#120e0b] font-bold'
							: 'border border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)]'
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
							? 'border-transparent bg-[var(--accent-primary)] text-[#120e0b] font-bold'
							: 'border border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)]'
					"
					title="Reproduce el siguiente tema respetando el orden y filtro de la biblioteca"
					@click="handleSetDjMode('library')"
				>
					Lista de librería
				</PillButton>
			</div>
		</div>

		<div
			v-if="showRemoteServerSelector"
			class="mx-auto mb-6 max-w-lg overflow-hidden rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)]"
		>
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

		<div
			v-if="isNativeAndroidHost() && androidNotificationPermission === 'denied'"
			class="mx-auto mb-6 flex max-w-lg items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)] px-4 py-3 text-xs"
		>
			<div class="min-w-0 flex-1">
				<p class="font-bold text-[var(--accent-primary)]">Notificaciones desactivadas</p>
				<p class="mt-0.5 text-[var(--text-secondary)]">
					Habilitalas para manejar la Rockola desde la pantalla de bloqueo.
				</p>
			</div>
			<button
				type="button"
				class="tap-feedback shrink-0 rounded-[var(--radius-sm)] bg-[var(--accent-primary)] px-3 py-2 font-bold text-[#120e0b]"
				@click="openAndroidNotificationSettings"
			>
				Ajustes
			</button>
		</div>

		<!-- Botones de acción -->
		<div class="mx-auto mb-2 max-w-lg px-1">
			<div
				class="flex items-center gap-1.5 text-[12px] font-semibold tracking-[0.06em] text-[var(--text-secondary)] uppercase"
			>
				<i class="material-icons !text-[16px] text-[var(--accent-primary)]" aria-hidden="true">settings</i>
				<span>Lo controle</span>
			</div>
		</div>

		<div v-if="hasEdgeTts" class="mx-auto mb-4 flex max-w-lg flex-wrap justify-center gap-2.5">
			<PillButton
				icon="map"
				color-class="border border-[var(--hairline)] bg-[var(--bg-grouped)] hover:bg-[var(--bg-surface-hover)] text-[var(--text-primary)]"
				@click="isWeatherModalOpen = true"
			>
				{{ displayWeatherLocation ? `Ubicación del Clima: ${displayWeatherLocation}` : 'Configurar ubicación' }}
			</PillButton>
		</div>

		<div
			v-if="hasMpv && hasLocalPlayer && !listenLocally"
			class="mx-auto mb-4 flex max-w-lg flex-wrap justify-center gap-2.5"
		>
			<PillButton
				icon="volume_up"
				color-class="bg-[var(--accent-carpincho)] hover:bg-[var(--accent-carpincho-hover)] text-[#f5efe6]"
				@click="returnToServerSpeakers"
			>
				Volver a parlantes del servidor
			</PillButton>
		</div>

		<div
			v-if="!hasMpv && !listenLocally && !hasLocalPlayer && (!isNativeAndroidHost() || isRemoteMode)"
			class="mx-auto mb-4 flex max-w-lg flex-wrap justify-center gap-2.5"
		>
			<PillButton
				icon="headphones"
				color-class="bg-[var(--accent-mate)] hover:brightness-110 text-[#f5efe6] font-bold"
				@click="
					listenLocally = true;
					haptic();
				"
			>
				Escuchar en este dispositivo
			</PillButton>
		</div>

		<div v-if="showAndroidFolderPicker" class="mx-auto mb-4 flex max-w-lg flex-col items-center gap-2">
			<PillButton
				icon="sd_card"
				color-class="bg-[var(--accent-carpincho)] hover:bg-[var(--accent-carpincho-hover)] text-[#f5efe6]"
				@click="handlePickMusicFolder"
			>
				Elegir carpeta de música
			</PillButton>
			<p v-if="androidServerStatus.musicDir" class="max-w-xs truncate text-xs text-[var(--text-secondary)]">
				{{ androidServerStatus.musicDir }}
			</p>
		</div>

		<dialog
			ref="remoteDialogRef"
			aria-labelledby="remote-dialog-title"
			class="m-auto w-[min(92vw,28rem)] rounded-[var(--radius-lg)] border border-[var(--glass-border)] bg-[var(--glass-bg-strong)] p-5 text-[var(--text-primary)] shadow-2xl [backdrop-filter:var(--glass-blur)] backdrop:bg-black/75 backdrop:backdrop-blur-sm"
			@cancel.prevent="isRemoteServerModalOpen = false"
			@close="isRemoteServerModalOpen = false"
			@pointerdown="onRemoteDialogPointerDown"
			@pointerup="onRemoteDialogPointerUp"
		>
			<div class="mb-3 flex items-center justify-between gap-2">
				<h3
					id="remote-dialog-title"
					class="flex items-center gap-2 text-base font-bold text-[var(--accent-primary)]"
				>
					<i class="material-icons !text-lg" aria-hidden="true">dns</i>
					<span>Conectar a otro servidor</span>
				</h3>
				<button
					type="button"
					aria-label="Cerrar diálogo"
					class="touch-target inline-flex cursor-pointer items-center justify-center rounded-full p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
					@click="isRemoteServerModalOpen = false"
				>
					<i class="material-icons !text-lg" aria-hidden="true">close</i>
				</button>
			</div>
			<label for="remote-server-input" class="mb-3 block text-xs text-[var(--text-secondary)]">
				Ingresá la IP o URL de tu PC (ej: 192.168.0.55). Se guarda el último servidor para volver fácil.
			</label>
			<input
				id="remote-server-input"
				v-model="remoteServerInput"
				type="text"
				placeholder="IP de tu PC (ej: 192.168.0.55)"
				class="mb-4 w-full rounded-[var(--radius-md)] border border-[var(--hairline)] bg-[var(--bg-input)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)] focus:border-[var(--accent-primary)]"
				@keyup.enter="handleConnectRemoteServer"
			/>
			<div class="flex flex-wrap justify-end gap-2">
				<PillButton
					v-if="isRemoteMode"
					icon="smartphone"
					color-class="border border-[var(--hairline)] bg-[var(--bg-input)] hover:bg-[var(--bg-surface-hover)] text-[var(--text-primary)]"
					@click="handleUseLocalServer"
				>
					Usar este teléfono
				</PillButton>
				<PillButton
					icon="close"
					color-class="border border-[var(--hairline)] bg-[var(--bg-input)] hover:bg-[var(--bg-surface-hover)] text-[var(--text-secondary)]"
					@click="isRemoteServerModalOpen = false"
				>
					Cancelar
				</PillButton>
				<PillButton
					icon="link"
					color-class="bg-[var(--accent-primary)] text-[#120e0b] font-bold hover:brightness-110"
					:disabled="isConnectingRemote || !remoteServerInput.trim()"
					@click="handleConnectRemoteServer"
				>
					{{ isConnectingRemote ? 'Conectando...' : 'Conectar' }}
				</PillButton>
			</div>
		</dialog>

		<div class="mx-auto mb-3 flex max-w-lg flex-wrap justify-center gap-2.5">
			<PillButton
				icon="stop"
				color-class="bg-[var(--accent-danger)] text-[#f5efe6] hover:brightness-110"
				@click="stop"
			>
				Cortala de una
			</PillButton>

			<PillButton
				icon="delete_sweep"
				color-class="border border-[var(--accent-danger)]/40 bg-[var(--accent-danger)]/15 text-[var(--accent-danger)] hover:bg-[var(--accent-danger)]/25"
				@click="
					clearRound();
					haptic();
				"
			>
				Limpiar ronda
			</PillButton>

			<PillButton
				v-if="hasMpv"
				icon="fullscreen"
				color-class="border border-[var(--hairline)] bg-[var(--bg-grouped)] hover:bg-[var(--bg-surface-hover)] text-[var(--text-primary)]"
				@click="fullscreen"
			>
				Todo pantalla, ñeri
			</PillButton>

			<PillButton
				v-if="hasMpv"
				:icon="mpvVisible ? 'visibility_off' : 'visibility'"
				color-class="border border-[var(--hairline)] bg-[var(--bg-grouped)] hover:bg-[var(--bg-surface-hover)] text-[var(--text-primary)]"
				@click="toggleMpvVisibility"
			>
				{{ mpvVisible ? 'Ocultar MPV' : 'Mostrar MPV' }}
			</PillButton>
		</div>

		<div class="mx-auto mb-8 flex max-w-lg flex-wrap justify-center gap-2.5">
			<PillButton
				:icon="serverMuted ? 'volume_off' : 'volume_up'"
				:color-class="
					serverMuted
						? 'bg-[var(--accent-danger)] text-[#f5efe6] hover:brightness-110'
						: 'border border-[var(--hairline)] bg-[var(--bg-grouped)] hover:bg-[var(--bg-surface-hover)] text-[var(--text-primary)]'
				"
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
						? 'border border-[var(--hairline)] bg-[var(--bg-input)] text-[var(--text-tertiary)]'
						: 'bg-[var(--accent-mate)] text-[#f5efe6] hover:brightness-110'
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
				color-class="bg-[var(--accent-carpincho)] hover:bg-[var(--accent-carpincho-hover)] text-[#f5efe6]"
				@click="toggleFullRockola"
			>
				Full Rockola
			</PillButton>
		</div>

		<!-- Código QR -->
		<div class="mx-auto mb-3 max-w-lg px-1">
			<div
				class="flex items-center justify-center gap-1.5 text-[12px] font-semibold tracking-[0.06em] text-[var(--text-secondary)] uppercase"
			>
				<i class="material-icons !text-[16px] text-[var(--accent-primary)]" aria-hidden="true">qr_code_2</i>
				<span>Sumate a la joda</span>
			</div>
		</div>

		<div class="flex flex-col items-center pb-6">
			<!-- Clase 'relative' agregada para contener la imagen absoluta -->
			<div
				class="relative flex items-center justify-center rounded-[var(--radius-lg)] bg-[#f5efe6] p-4 shadow-lg"
			>
				<!-- Componente QR con los colores de la aplicación -->
				<QRCode :value="currentUrl" :size="200" level="H" foreground="#120e0b" background="#f5efe6" />

				<!-- La impronta del carpincho -->
				<img
					:src="apiUrl('/favicon.png')"
					alt="Logo Carpincho"
					class="absolute top-1/2 left-1/2 h-[88px] w-[88px] -translate-x-1/2 -translate-y-1/2 rounded-lg p-1"
				/>
			</div>
			<p class="mt-3 text-sm text-[var(--text-secondary)]">Escaneá para entrar desde tu celu</p>
			<PillButton
				icon="share"
				color-class="mt-4 bg-[var(--accent-primary)] text-[#120e0b] font-bold hover:brightness-110"
				@click="handleShareUrl"
			>
				Compartir link
			</PillButton>
		</div>

		<div
			v-if="showRemoteServerSelector"
			class="mx-auto mb-6 max-w-lg rounded-[var(--radius-lg)] border border-[var(--hairline)] bg-[var(--bg-grouped)] p-4"
		>
			<div class="mb-2 flex items-center justify-between gap-2">
				<span class="text-xs font-bold tracking-wider text-[var(--accent-primary)] uppercase">
					{{ isRemoteMode ? 'Modo Cliente remoto' : 'Modo Host local' }}
				</span>
				<span
					class="rounded-full px-2.5 py-0.5 text-xs font-bold"
					:class="
						isRemoteMode || localServerState === 'ready'
							? 'bg-[var(--accent-mate)]/25 text-[var(--accent-primary)]'
							: 'bg-[var(--bg-input)] text-[var(--text-secondary)]'
					"
				>
					{{ isRemoteMode ? 'Conectado' : hostStateLabel }}
				</span>
			</div>

			<div v-if="isHostMode" class="space-y-1 text-xs text-[var(--text-secondary)]">
				<p v-if="localServerState === 'ready'">
					Dirección en tu Wi-Fi:
					<span class="font-mono text-[var(--text-primary)]">{{ localServerLanUrl }}</span>
				</p>
				<p v-if="androidServerStatus.musicDir || libraryFolderStatus !== 'ok'">
					Carpeta:
					<span class="text-[var(--text-primary)]">
						{{ localMusicDisplayName || androidServerStatus.musicDir || 'Sin elegir' }}
					</span>
					<span v-if="libraryFolderError" class="text-[var(--accent-danger)]">
						· {{ libraryFolderError }}
					</span>
				</p>
				<p class="leading-relaxed">
					El servidor embebido se mantiene activo mientras suena música o la app está abierta; Android puede
					detenerlo si la cerrás en reposo.
				</p>
				<div class="flex flex-wrap gap-2 pt-2">
					<button
						v-if="localServerState === 'stopped' || localServerState === 'unavailable'"
						type="button"
						class="touch-target tap-feedback cursor-pointer rounded-full bg-[var(--accent-mate)] px-3.5 py-1.5 text-xs font-bold text-[#f5efe6] shadow hover:brightness-110"
						@click="handleStartLocalHost"
					>
						Prender servidor
					</button>
					<button
						v-else
						type="button"
						class="touch-target tap-feedback cursor-pointer rounded-full bg-[var(--accent-danger)] px-3.5 py-1.5 text-xs font-bold text-[#f5efe6] shadow hover:brightness-110"
						:disabled="localServerState === 'stopping'"
						@click="handleStopLocalHost"
					>
						Apagar servidor
					</button>
				</div>
			</div>
			<p v-else class="text-xs text-[var(--text-secondary)]">
				Controlando el servidor remoto
				<span class="font-mono text-[var(--text-primary)]">{{ activeRemoteServerUrl }}</span>
			</p>

			<div
				v-if="lastServerError"
				role="alert"
				class="mt-3 flex items-start justify-between gap-2 rounded-[var(--radius-md)] border border-[var(--accent-danger)]/40 bg-[var(--accent-danger)]/15 px-3 py-2 text-xs text-[var(--text-primary)]"
			>
				<span>{{ lastServerError.message }}</span>
				<button
					type="button"
					aria-label="Descartar aviso"
					class="touch-target shrink-0 cursor-pointer rounded px-1.5 font-bold text-[var(--accent-danger)] hover:text-[var(--text-primary)]"
					@click="clearServerError()"
				>
					✕
				</button>
			</div>
		</div>

		<WeatherLocationModal :is-open="isWeatherModalOpen" @close="isWeatherModalOpen = false" />
	</section>
</template>
