<script setup lang="ts">
	import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
	import { Toaster } from 'vue-sonner';
	import { apiUrl } from './composables/useApi';
	import {
		androidBootStage,
		androidExtractProgress,
		androidServerStatus,
		consumeAndroidPendingShortcut,
		dismissNotificationPermissionPrompt,
		ensureLocalAndroidServerAlive,
		initAndroidServer,
		isAndroidPipMode,
		isNativeAndroidHost,
		markAndroidUiReady,
		pickAndApplyMusicFolder,
		prepareContextualNotificationPrompt,
		refreshAndroidNotificationPermission,
		requestAndroidNotificationPermission,
		setAndroidBackHandlerEnabled,
		showNotificationPermissionRationale,
	} from './composables/useAndroidHost';
	import { hydrateFromBootSnapshot, isHydratedFromSnapshot } from './composables/player/useLocalSnapshot';
	import {
		activeRemoteServerUrl,
		isHostMode,
		isRemoteMode,
		libraryFolderError,
		libraryFolderStatus,
		localServerState,
	} from './stores/useServerConnectionStore';
	import { useCover } from './composables/useCover';
	import { buildSpaPath, extractSpaRoute, useAppRouter } from './composables/useAppRouter';
	import { useKeyboardShortcuts } from './composables/useKeyboardShortcuts';
	import { useLyrics, type LyricSyllable } from './composables/useLyrics';
	import { usePlaybackControls } from './composables/usePlaybackControls';
	import { usePlayer } from './composables/usePlayer';
	import { useToasts } from './composables/player/useToasts';
	import { useSliderFactory } from './composables/useSliderFactory';
	import { useContextMenu } from './composables/useContextMenu';
	import { initUiPersistence, restoreUiState } from './composables/useUiPersistence';
	import { closeTopModal, hasOpenModal, isLyricsEditorOpen } from './stores/useUiStore';

	// Componentes aislados de la interfaz
	import ContextMenu from './components/ContextMenu.vue';
	import ControlsTab from './components/ControlsTab.vue';
	import FloatingPlayer from './components/FloatingPlayer.vue';
	import FogonMode from './components/FogonMode.vue';
	import LyricsEditorView from './components/lyrics/LyricsEditorView.vue';
	import LibraryTab from './components/LibraryTab.vue';
	import QueueTab from './components/QueueTab.vue';
	import TopTab from './components/TopTab.vue';

	const { pause, seekAbsolute } = usePlaybackControls();
	const { showToast } = useToasts();

	const {
		_sendLocalPlayerUpdate,
		activeTab,
		connectWebSocket,
		currentTrackPath,
		duration,
		getTrackInfo,
		haptic,
		hasLocalPlayer,
		hasMpv,
		pendingSeekTime,
		isDraggingSeek,
		isFogonMode,
		isPlaying,
		isPlayingRadioAnnouncement,
		isScanning,
		isShortScreen,
		isSynthesizingRadio,
		isTabsBarHidden,
		listenLocally,
		loadLibrary,
		localPlayerRef,
		localTimePos,
		queueState,
		scanStatus,
		switchTab,
		volume,
	} = usePlayer();

	const { createSlider } = useSliderFactory();

	const {
		progressPercent,
		startDrag: startSeek,
		moveDrag: moveSeek,
		endDrag: endSeek,
	} = createSlider(
		localTimePos,
		duration,
		(val) => {
			isDraggingSeek.value = true;
			localTimePos.value = val;
		},
		(val) => {
			isDraggingSeek.value = false;
			localTimePos.value = val;
			pendingSeekTime.value = val;

			if (listenLocally.value && localPlayerRef.value) {
				localPlayerRef.value.currentTime = val;
				_sendLocalPlayerUpdate({ time_pos: val });
			} else {
				seekAbsolute(val);
			}
		}
	);

	const { currentLyricLine, activeLyricLines, loadLyrics } = useLyrics({ localTimePos });
	watch(
		currentTrackPath,
		(newPath: string | null) => {
			loadLyrics(newPath);
		},
		{ immediate: true }
	);

	// Estilo para cada sílaba en la barra superior (headbar) según el progreso de reproducción
	function getHeadbarSyllableClass(syl: LyricSyllable): string {
		const pos = localTimePos.value;
		if (pos >= syl.end) {
			// Ya sonó: bien destacada con el amarillo carpincho
			return 'headbar-syllable text-carpincho-warning font-bold transition-colors duration-150 inline';
		} else if (pos >= syl.start && pos < syl.end) {
			// Cantándose en este instante: blanca con brillo para captar el ojo
			return 'headbar-syllable text-white font-extrabold drop-shadow-[0_0_8px_rgba(233,196,106,0.9)] underline decoration-carpincho-warning/50 transition-all duration-100 inline-block';
		}
		// Futura: atenuada para dar efecto de lectura karaoke
		return 'headbar-syllable text-gray-400/60 font-medium transition-colors duration-150 inline';
	}

	// Conectamos los atajos de teclado (espacio, flechas, f, l, t, n, p, m, esc...)
	useKeyboardShortcuts();

	const tabs = [
		{ id: 'library', name: 'Los Temazos', icon: 'library_music' },
		{ id: 'queue', name: 'La Ronda', icon: 'queue_music' },
		{ id: 'top', name: 'Los Clásicos', icon: 'local_fire_department' },
		{ id: 'controls', name: 'Las Perillas', icon: 'settings' },
	];

	const currentTrackTitle = computed(() => {
		if (isSynthesizingRadio.value || (isPlayingRadioAnnouncement.value && !currentTrackPath.value)) {
			return 'Transmisión de Cabina - Acomodando los micrófonos... 🎙️';
		}
		if (isPlayingRadioAnnouncement.value) {
			const t = currentTrackPath.value ? getTrackInfo(currentTrackPath.value) : null;
			return `${t?.display_artist || 'Transmisión de Cabina 🎙️'} - Transmisión de Cabina`;
		}
		if (!currentTrackPath.value) return 'Silencio estampa. Poné algo, fiera.';

		const t = getTrackInfo(currentTrackPath.value);
		return `${t.display_artist} - ${t.display_title}`;
	});

	const headbarCoverSource = computed(() => {
		if (isScanning.value) return null;
		if (isPlayingRadioAnnouncement.value || isSynthesizingRadio.value) {
			return currentTrackPath.value || 'radio_announcement.mp3';
		}
		return currentTrackPath.value;
	});
	const { coverUrl: headbarCoverUrl, onCoverError: onHeadbarCoverError } = useCover(headbarCoverSource, {
		size: 512,
	});

	// Sincronizamos el favicon del documento con la carátula del tema actual (o volvemos al carpincho por defecto)
	watch(
		headbarCoverUrl,
		(url) => {
			if (typeof document === 'undefined') return;
			let link = document.querySelector<HTMLLinkElement>("link[rel*='icon']");
			if (!link) {
				link = document.createElement('link');
				link.rel = 'icon';
				document.head.appendChild(link);
			}
			if (url) {
				link.type = 'image/jpeg';
				link.href = url;
			} else {
				link.type = 'image/png';
				link.href = apiUrl('/favicon.png');
			}
		},
		{ immediate: true }
	);

	const { initRouter } = useAppRouter();

	watch(isFogonMode, (fogon) => {
		if (typeof window === 'undefined') return;
		const currentSpaRoute = extractSpaRoute(window.location.pathname);
		if (fogon) {
			if (currentSpaRoute !== '/fogon') {
				const target = `${buildSpaPath('/fogon')}${window.location.search}${window.location.hash}`;
				window.history.pushState({}, '', target);
			}
		} else if (currentSpaRoute === '/fogon') {
			const tabRoute = activeTab.value === 'library' ? '/' : `/${activeTab.value}`;
			const target = `${buildSpaPath(tabRoute)}${window.location.search}${window.location.hash}`;
			window.history.pushState({}, '', target);
		}
	});

	watch(isLyricsEditorOpen, (open) => {
		if (typeof window === 'undefined') return;
		const currentSpaRoute = extractSpaRoute(window.location.pathname);
		if (open) {
			if (currentSpaRoute !== '/letras') {
				const target = `${buildSpaPath('/letras')}${window.location.search}${window.location.hash}`;
				window.history.pushState({}, '', target);
			}
		} else if (currentSpaRoute === '/letras' || currentSpaRoute === '/lyrics') {
			const tabRoute = activeTab.value === 'library' ? '/' : `/${activeTab.value}`;
			const target = `${buildSpaPath(tabRoute)}${window.location.search}${window.location.hash}`;
			window.history.pushState({}, '', target);
		}
	});

	watch(activeTab, (tab) => {
		if (typeof window === 'undefined') return;
		if (!isFogonMode.value) {
			const tabRoute = tab === 'library' ? '/' : `/${tab}`;
			const targetPathname = buildSpaPath(tabRoute);
			if (window.location.pathname !== targetPathname) {
				const target = `${targetPathname}${window.location.search}${window.location.hash}`;
				window.history.pushState({}, '', target);
			}
		}
	});

	const showAndroidFolderBanner = computed(
		() => isNativeAndroidHost() && isHostMode.value && androidServerStatus.value.needsFolder
	);
	const { ctxMenu, closeCtxMenu } = useContextMenu();
	const isInputFocused = ref(false);

	function isTextInputElement(el: Element | null): el is HTMLElement {
		if (!(el instanceof HTMLElement)) return false;
		const tag = el.tagName;
		return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
	}

	function syncInputFocusState(): void {
		if (typeof document === 'undefined') return;
		isInputFocused.value = isTextInputElement(document.activeElement);
	}

	function handleFocusOut(): void {
		if (typeof window === 'undefined') return;
		window.setTimeout(syncInputFocusState, 0);
	}

	function handleAndroidBack(): boolean {
		if (typeof document !== 'undefined' && isTextInputElement(document.activeElement)) {
			document.activeElement.blur();
			isInputFocused.value = false;
			return true;
		}
		if (closeTopModal()) {
			return true;
		}
		if (typeof document !== 'undefined') {
			const openDialog = document.querySelector<HTMLDialogElement>('dialog[open]');
			if (openDialog) {
				if (typeof openDialog.close === 'function') {
					openDialog.close();
				} else {
					openDialog.removeAttribute('open');
				}
				return true;
			}
		}
		if (ctxMenu.visible) {
			closeCtxMenu();
			return true;
		}
		if (isLyricsEditorOpen.value) {
			isLyricsEditorOpen.value = false;
			return true;
		}
		if (isFogonMode.value) {
			isFogonMode.value = false;
			return true;
		}
		if (activeTab.value !== 'library') {
			switchTab('library');
			return true;
		}
		return false;
	}

	const hasClosableBackLayer = computed(
		() =>
			isInputFocused.value ||
			hasOpenModal.value ||
			ctxMenu.visible ||
			isLyricsEditorOpen.value ||
			isFogonMode.value ||
			activeTab.value !== 'library'
	);

	watch(
		hasClosableBackLayer,
		(enabled) => {
			setAndroidBackHandlerEnabled(enabled);
		},
		{ immediate: true }
	);

	function handleAndroidBackProgress(progress: number): void {
		if (typeof document === 'undefined') return;
		const clamped = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;
		document.documentElement.style.setProperty('--rockola-back-progress', String(clamped));
	}

	function handleAndroidImeInsets(bottomCssPx: number): void {
		if (typeof document === 'undefined') return;
		const px = Number.isFinite(bottomCssPx) ? Math.max(0, Math.round(bottomCssPx)) : 0;
		document.documentElement.style.setProperty('--rockola-ime-height', `${px}px`);
		document.documentElement.classList.toggle('ime-open', px > 0);
	}

	// Swipe horizontal entre pestañas sin interferir con filas de cola ni sliders
	const TAB_SWIPE_MIN_PX = 72;
	let tabTouchStartX = 0;
	let tabTouchStartY = 0;
	let tabTouchLastX = 0;
	let tabSwipeAxis: 'horizontal' | 'vertical' | null = null;
	let tabSwipeTracking = false;

	function resetTabSwipe() {
		tabSwipeTracking = false;
		tabSwipeAxis = null;
	}

	function onTabContentTouchStart(e: TouchEvent) {
		if (e.touches.length !== 1) {
			resetTabSwipe();
			return;
		}
		const target = e.target as HTMLElement | null;
		if (
			target?.closest(
				'[data-queue-index], [data-history-path], input, textarea, [role="slider"], .drag-slider, .no-tab-swipe'
			)
		) {
			resetTabSwipe();
			return;
		}
		const touch = e.touches[0];
		tabTouchStartX = touch.clientX;
		tabTouchStartY = touch.clientY;
		tabTouchLastX = touch.clientX;
		tabSwipeAxis = null;
		tabSwipeTracking = true;
	}

	function onTabContentTouchMove(e: TouchEvent) {
		if (!tabSwipeTracking || e.touches.length !== 1) return;
		const touch = e.touches[0];
		tabTouchLastX = touch.clientX;
		const dx = touch.clientX - tabTouchStartX;
		const dy = touch.clientY - tabTouchStartY;

		if (!tabSwipeAxis && (Math.abs(dx) > 12 || Math.abs(dy) > 12)) {
			tabSwipeAxis = Math.abs(dx) > Math.abs(dy) * 1.5 ? 'horizontal' : 'vertical';
			if (tabSwipeAxis === 'vertical') {
				resetTabSwipe();
			}
		}
	}

	function onTabContentTouchEnd() {
		if (!tabSwipeTracking || tabSwipeAxis !== 'horizontal') {
			resetTabSwipe();
			return;
		}
		const dx = tabTouchLastX - tabTouchStartX;
		resetTabSwipe();

		if (Math.abs(dx) < TAB_SWIPE_MIN_PX) return;
		const currentIdx = tabs.findIndex((t) => t.id === activeTab.value);
		if (currentIdx === -1) return;

		const nextIdx = dx < 0 ? currentIdx + 1 : currentIdx - 1;
		if (nextIdx >= 0 && nextIdx < tabs.length) {
			switchTab(tabs[nextIdx].id);
			haptic();
		}
	}

	function openFogonFromAndroid(): void {
		isLyricsEditorOpen.value = false;
		isFogonMode.value = true;
	}

	function openLibraryFromAndroid(): void {
		isLyricsEditorOpen.value = false;
		isFogonMode.value = false;
		switchTab('library');
	}

	function openQueueFromAndroid(): void {
		isLyricsEditorOpen.value = false;
		isFogonMode.value = false;
		switchTab('queue');
	}

	function openTopsFromAndroid(): void {
		isLyricsEditorOpen.value = false;
		isFogonMode.value = false;
		switchTab('top');
	}

	function resumeLastFromAndroid(): void {
		isLyricsEditorOpen.value = false;
		isFogonMode.value = false;
		switchTab('queue');
		if (!isPlaying.value && currentTrackPath.value) {
			void pause();
		}
	}

	function applyShortcutAction(action: string | null): void {
		if (action === 'ar.carpincho.rockola.ACTION_OPEN_FOGON') {
			openFogonFromAndroid();
		} else if (action === 'ar.carpincho.rockola.ACTION_OPEN_LIBRARY') {
			openLibraryFromAndroid();
		} else if (action === 'ar.carpincho.rockola.ACTION_OPEN_QUEUE') {
			openQueueFromAndroid();
		} else if (action === 'ar.carpincho.rockola.ACTION_OPEN_TOPS') {
			openTopsFromAndroid();
		} else if (action === 'ar.carpincho.rockola.ACTION_RESUME_LAST') {
			resumeLastFromAndroid();
		}
	}

	function handleAndroidPipMode(active: boolean): void {
		const enabled = Boolean(active);
		isAndroidPipMode.value = enabled;
		if (typeof document !== 'undefined') {
			document.documentElement.classList.toggle('android-pip', enabled);
		}
	}

	function handleAndroidMediaVolumeChanged(level: number): void {
		if ((listenLocally.value || isHostMode.value) && Number.isFinite(level)) {
			volume.value = Math.max(0, Math.min(100, Math.round(level)));
		}
	}

	function handleNativeCommandError(_cmd: string, _code: string, message: string): void {
		showToast(message || 'No se pudo ejecutar el control multimedia en el servidor.', 'error');
	}

	let stopUiPersistence: (() => void) | null = null;

	onMounted(() => {
		initRouter();
		if (typeof window !== 'undefined' && extractSpaRoute(window.location.pathname) === '/') {
			restoreUiState();
		}
		stopUiPersistence = initUiPersistence();
		window.__rockolaHandleBack = handleAndroidBack;
		window.__rockolaOnBackProgress = handleAndroidBackProgress;
		window.__rockolaSetImeInsets = handleAndroidImeInsets;
		window.__rockolaOpenFogon = openFogonFromAndroid;
		window.__rockolaOpenLibrary = openLibraryFromAndroid;
		window.__rockolaOpenQueue = openQueueFromAndroid;
		window.__rockolaOpenTops = openTopsFromAndroid;
		window.__rockolaResumeLast = resumeLastFromAndroid;
		window.__rockolaSetPipMode = handleAndroidPipMode;
		window.__rockolaOnMediaVolumeChanged = handleAndroidMediaVolumeChanged;
		window.__rockolaOnNativeCommandError = handleNativeCommandError;
		if (typeof document !== 'undefined') {
			document.addEventListener('focusin', syncInputFocusState);
			document.addEventListener('focusout', handleFocusOut);
			syncInputFocusState();
		}
		if (isNativeAndroidHost()) {
			const snapshotKey = isHostMode.value ? 'host' : `remote:${activeRemoteServerUrl.value}`;
			hydrateFromBootSnapshot(snapshotKey);
			void consumeAndroidPendingShortcut().then(applyShortcutAction);
			requestAnimationFrame(() => markAndroidUiReady());
			initAndroidServer().then((ok) => {
				if (!ok) return;
				loadLibrary(false);
				connectWebSocket();
			});
			if (typeof document !== 'undefined') {
				document.addEventListener('visibilitychange', handleAndroidVisibilityChange);
			}
		} else {
			loadLibrary(false);
			connectWebSocket();
		}
	});

	function handleAndroidVisibilityChange() {
		if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
			void ensureLocalAndroidServerAlive();
			void refreshAndroidNotificationPermission();
		}
	}

	watch(isPlaying, (playing) => {
		if (playing && isNativeAndroidHost()) {
			void prepareContextualNotificationPrompt();
		}
	});

	onUnmounted(() => {
		stopUiPersistence?.();
		stopUiPersistence = null;
		if (typeof document !== 'undefined') {
			document.removeEventListener('focusin', syncInputFocusState);
			document.removeEventListener('focusout', handleFocusOut);
			document.removeEventListener('visibilitychange', handleAndroidVisibilityChange);
			document.documentElement.classList.remove('android-pip', 'ime-open');
			document.documentElement.style.removeProperty('--rockola-back-progress');
			document.documentElement.style.removeProperty('--rockola-ime-height');
		}
		isAndroidPipMode.value = false;
		if (typeof window === 'undefined') return;
		if (window.__rockolaHandleBack === handleAndroidBack) {
			delete window.__rockolaHandleBack;
		}
		if (window.__rockolaOnBackProgress === handleAndroidBackProgress) {
			delete window.__rockolaOnBackProgress;
		}
		if (window.__rockolaSetImeInsets === handleAndroidImeInsets) {
			delete window.__rockolaSetImeInsets;
		}
		if (window.__rockolaOpenFogon === openFogonFromAndroid) {
			delete window.__rockolaOpenFogon;
		}
		if (window.__rockolaOpenLibrary === openLibraryFromAndroid) {
			delete window.__rockolaOpenLibrary;
		}
		if (window.__rockolaOpenQueue === openQueueFromAndroid) {
			delete window.__rockolaOpenQueue;
		}
		if (window.__rockolaOpenTops === openTopsFromAndroid) {
			delete window.__rockolaOpenTops;
		}
		if (window.__rockolaResumeLast === resumeLastFromAndroid) {
			delete window.__rockolaResumeLast;
		}
		if (window.__rockolaSetPipMode === handleAndroidPipMode) {
			delete window.__rockolaSetPipMode;
		}
		if (window.__rockolaOnMediaVolumeChanged === handleAndroidMediaVolumeChanged) {
			delete window.__rockolaOnMediaVolumeChanged;
		}
		if (window.__rockolaOnNativeCommandError === handleNativeCommandError) {
			delete window.__rockolaOnNativeCommandError;
		}
	});
</script>

<template>
	<!-- Reproductor interno para escuchar en el cliente -->
	<audio ref="localPlayerRef" preload="auto" style="display: none" />

	<!-- TOASTS -->
	<Toaster
		position="bottom-left"
		theme="dark"
		rich-colors
		:close-button="false"
		:toast-options="{
			classes: {
				toast: 'bg-[var(--color-carpincho-panel)] text-[var(--color-carpincho-text)] border border-[var(--color-carpincho-border)] shadow-xl rounded-xl font-sans',
				title: 'font-bold text-[var(--color-carpincho-text)]',
				description: 'text-[var(--color-carpincho-muted)] text-sm',
				success: '!bg-[var(--color-carpincho-success)] !text-white !border-[var(--color-carpincho-success)]',
				warning:
					'!bg-[var(--color-carpincho-warning)] !text-[var(--color-carpincho-panel)] !border-[var(--color-carpincho-warning)] font-medium',
				error: '!bg-red-900 !text-white !border-red-700',
				actionButton: 'bg-[var(--color-carpincho-primary)] text-white',
				cancelButton: 'bg-gray-700 text-gray-300',
				closeButton:
					'text-[var(--color-carpincho-text)] hover:text-white bg-[var(--color-carpincho-border)] border-[var(--color-carpincho-border)]',
			},
		}"
	/>

	<!-- MODO FOGÓN -->
	<FogonMode />

	<!-- TALLER DE LETRAS (EDITOR ASS) -->
	<LyricsEditorView v-if="isLyricsEditorOpen" />

	<!-- MENÚ CONTEXTUAL (global, compartido entre pestañas) -->
	<ContextMenu />

	<!-- BIENVENIDA ANDROID: ELEGIR CARPETA ANTES DE ENTRAR A LA UI -->
	<section
		v-if="isNativeAndroidHost() && isHostMode && libraryFolderStatus === 'unconfigured'"
		class="android-folder-onboarding bg-carpincho-bg text-carpincho-text flex h-full w-full flex-col items-center justify-center px-6 text-center"
	>
		<div
			class="bg-carpincho-panel border-carpincho-border flex max-w-sm flex-col items-center rounded-2xl border p-6 shadow-xl"
		>
			<img
				src="/favicon.png"
				alt="La Rockola del Carpincho"
				class="mb-4 h-20 w-20 rounded-2xl shadow"
			/>
			<h1 class="text-carpincho-warning mb-2 text-xl font-bold">Elegí tu carpeta de música</h1>
			<p class="text-carpincho-muted mb-6 text-sm leading-relaxed">
				Para arrancar la ronda en este celu, seleccioná la carpeta de tu memoria interna o tarjeta MicroSD donde
				guardás tus temas.
			</p>
			<button
				type="button"
				class="touch-target bg-carpincho-primary hover:bg-carpincho-secondary flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-bold text-white shadow transition-colors"
				@click="pickAndApplyMusicFolder"
			>
				<i class="material-icons text-lg" aria-hidden="true">folder_open</i>
				<span>Elegir carpeta de música</span>
			</button>
		</div>
	</section>

	<!-- VISTA PRINCIPAL (se oculta cuando el fogón o el editor de letras están abiertos a pantalla completa para no recalcular repintados) -->
	<div
		v-else
		v-show="!isFogonMode && !isLyricsEditorOpen"
		class="app-main-content flex min-h-0 w-full flex-1 flex-col overflow-hidden"
	>
		<!-- BARRA SUPERIOR DE NAVEGACIÓN -->
		<nav
			class="bg-carpincho-panel border-carpincho-primary shrink-0 cursor-pointer overflow-hidden border-b px-5 pt-[calc(10px+var(--rockola-safe-top))] pb-2"
			@click="
				isFogonMode = true;
				haptic();
			"
		>
			<div class="text-carpincho-text flex w-full items-center justify-start gap-3 font-bold">
				<div class="flex h-[40px] min-w-0 flex-1 items-center overflow-hidden">
					<transition name="lyric" mode="out-in">
						<span v-if="isScanning" class="block w-full truncate text-left">
							{{
								scanStatus?.message
									? `[Avisando] ${scanStatus.message}`
									: scanStatus?.total
										? `[Avisando] Chusmeando temas (${scanStatus.current}/${scanStatus.total}), aguantá fiera... 🧉`
										: '[Avisando] Chusmeando temas, aguantá fiera... 🧉'
							}}
						</span>
						<div
							v-else-if="currentTrackPath && activeLyricLines.length > 0"
							:key="activeLyricLines.map((l) => l.text).join('-')"
							class="block w-full truncate text-left text-[0.95rem] font-medium whitespace-pre italic drop-shadow-sm"
						>
							<template v-for="(line, idx) in activeLyricLines" :key="idx + '-' + line.time">
								<span v-if="idx > 0" class="text-carpincho-secondary/70 mx-1.5 font-normal not-italic">
									/
								</span>
								<template v-if="line.syllables && line.syllables.length > 0">
									<span
										v-for="(syl, sIdx) in line.syllables"
										:key="sIdx"
										:class="getHeadbarSyllableClass(syl)"
									>
										{{ syl.text }}
									</span>
								</template>
								<span v-else class="text-carpincho-warning">{{ line.text }}</span>
							</template>
						</div>
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
					v-if="headbarCoverUrl"
					:src="headbarCoverUrl"
					class="h-10 w-10 shrink-0 rounded object-cover shadow-sm"
					@error="onHeadbarCoverError"
				/>
				<div v-else class="flex h-10 w-10 shrink-0 items-center justify-center rounded shadow-sm">
					<i class="material-icons text-carpincho-warning">
						{{
							isScanning || scanStatus?.is_analyzing_mood
								? 'sync'
								: isPlaying
									? 'nightlife'
									: 'music_note'
						}}
					</i>
				</div>
			</div>
		</nav>

		<!-- AVISO RÁPIDO ANDROID / HEADLESS -->
		<div
			v-if="isNativeAndroidHost() && isHostMode && androidBootStage === 'extracting_assets'"
			role="status"
			aria-live="polite"
			class="bg-carpincho-panel border-carpincho-border text-carpincho-warning flex w-full shrink-0 flex-col gap-1 border-b px-4 py-1.5 text-xs font-semibold"
		>
			<div class="flex items-center justify-between gap-2">
				<span>Preparando recursos de la Rockola...</span>
				<span>{{ androidExtractProgress }}%</span>
			</div>
			<div class="bg-carpincho-border h-1 w-full overflow-hidden rounded-full">
				<div
					class="bg-carpincho-warning h-full transition-[width] duration-150"
					:style="{ width: `${androidExtractProgress}%` }"
				/>
			</div>
		</div>
		<div
			v-else-if="isNativeAndroidHost() && isHydratedFromSnapshot && localServerState !== 'ready'"
			role="status"
			aria-live="polite"
			class="bg-carpincho-panel border-carpincho-border text-carpincho-muted flex w-full shrink-0 items-center justify-center gap-2 border-b px-4 py-1 text-xs font-semibold"
		>
			<i class="material-icons text-sm" aria-hidden="true">sync</i>
			<span>Actualizando lista...</span>
		</div>
		<div
			v-if="isNativeAndroidHost() && showNotificationPermissionRationale"
			role="region"
			aria-label="Permiso de notificaciones"
			class="bg-carpincho-panel border-carpincho-border flex w-full shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-xs"
		>
			<div class="flex min-w-0 flex-1 items-center gap-2">
				<i class="material-icons text-carpincho-warning text-base" aria-hidden="true">notifications_active</i>
				<span class="text-carpincho-text">
					Activá las notificaciones para ver y controlar la música desde la pantalla de bloqueo.
				</span>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<button
					type="button"
					class="text-carpincho-muted hover:text-carpincho-text rounded-lg px-2.5 py-1.5 font-semibold"
					@click="dismissNotificationPermissionPrompt"
				>
					Ahora no
				</button>
				<button
					type="button"
					class="bg-carpincho-primary rounded-lg px-3 py-1.5 font-bold text-white shadow-sm"
					@click="requestAndroidNotificationPermission"
				>
					Activar
				</button>
			</div>
		</div>
		<div
			v-if="isNativeAndroidHost() && isRemoteMode"
			class="bg-carpincho-panel border-carpincho-border text-carpincho-secondary flex w-full shrink-0 items-center justify-center gap-2 border-b px-4 py-1.5 text-xs font-semibold"
		>
			<i class="material-icons text-sm" aria-hidden="true">dns</i>
			<span class="truncate">Remoto: {{ activeRemoteServerUrl }}</span>
		</div>
		<button
			v-if="showAndroidFolderBanner"
			type="button"
			class="touch-target bg-carpincho-warning text-carpincho-panel flex w-full shrink-0 cursor-pointer items-center justify-center gap-2 px-4 py-2 text-xs font-bold shadow-sm"
			@click="pickAndApplyMusicFolder"
		>
			<i class="material-icons text-base" aria-hidden="true">sd_card</i>
			<span>
				{{
					libraryFolderError ||
					(libraryFolderStatus === 'permission_denied' || libraryFolderStatus === 'storage_unavailable'
						? 'Carpeta sin acceso · Tocá acá para volver a elegirla'
						: 'Elegir la carpeta de música para arrancar la ronda')
				}}
			</span>
		</button>
		<button
			v-else-if="!hasMpv && !listenLocally && !hasLocalPlayer && (!isNativeAndroidHost() || isRemoteMode)"
			type="button"
			class="touch-target bg-carpincho-success flex w-full shrink-0 cursor-pointer items-center justify-center gap-2 px-4 py-2 text-xs font-bold text-white shadow-sm"
			@click="
				listenLocally = true;
				haptic();
			"
		>
			<i class="material-icons text-base" aria-hidden="true">headphones</i>
			<span>El servidor corre sin MPV · Tocá acá para escuchar en este teléfono</span>
		</button>

		<!-- BARRA DE PROGRESO  -->
		<div
			v-show="!isScanning && currentTrackPath"
			class="bg-carpincho-panel group relative flex h-2 w-full shrink-0 cursor-pointer touch-none items-start"
			style="-webkit-tap-highlight-color: transparent"
			@pointerdown="startSeek"
			@pointermove="moveSeek"
			@pointerup="endSeek"
			@pointercancel="endSeek"
		>
			<div
				class="relative h-1 w-full bg-[#38312c] transition-all duration-100 ease-out group-hover:h-2 group-active:h-2"
			>
				<div
					class="bg-carpincho-warning absolute top-0 left-0 z-50 h-full"
					:style="{ width: progressPercent + '%' }"
				/>

				<!-- Bolita que solo aparece al pasar el dedo/mouse -->
				<div
					class="bg-carpincho-warning absolute top-1/2 z-50 h-3 w-3 -translate-y-1/2 rounded-full opacity-0 shadow-md group-hover:opacity-100 group-active:opacity-100"
					:style="{ left: progressPercent + '%', marginLeft: '-6px' }"
				/>
			</div>
		</div>

		<!-- CUERPO PRINCIPAL: NAVEGACIÓN INFERIOR M3 EN MÓVIL / RIEL LATERAL Y DOS PANELES EN PANTALLAS GRANDES -->
		<div class="flex min-h-0 w-full flex-1 flex-col overflow-hidden md:flex-row">
			<!-- PESTAÑAS (barra inferior Material 3 en móvil, riel lateral desde md) -->
			<nav
				aria-label="Secciones principales"
				class="bg-carpincho-panel border-carpincho-border relative z-10 order-2 flex shrink-0 overflow-hidden border-t pb-[var(--rockola-safe-bottom)] shadow-[0_-4px_16px_rgba(0,0,0,0.35)] transition-all duration-300 ease-in-out md:order-1 md:w-24 md:flex-col md:border-t-0 md:border-r md:pb-0 md:shadow-md lg:w-28"
				:class="[
					isTabsBarHidden && isShortScreen
						? 'pointer-events-none max-h-0 translate-y-2 border-t-0 pb-0 opacity-0 md:max-h-none md:translate-y-0 md:opacity-100'
						: 'max-h-24 translate-y-0 opacity-100 md:max-h-none',
				]"
			>
				<div role="tablist" class="flex w-full md:flex-col md:gap-2 md:px-2 md:py-4">
					<button
						v-for="tab in tabs"
						:key="tab.id"
						type="button"
						role="tab"
						:aria-selected="activeTab === tab.id"
						:aria-label="tab.name"
						:class="[
							'touch-target tap-feedback flex flex-1 cursor-pointer touch-manipulation flex-col items-center justify-center gap-0.5 py-2 text-center transition-colors duration-150 md:flex-none md:rounded-xl md:py-3',
							activeTab === tab.id
								? 'text-carpincho-warning'
								: 'hover:bg-carpincho-border/40 text-carpincho-muted',
						]"
						@click="switchTab(tab.id)"
					>
						<div
							class="relative flex items-center justify-center rounded-full px-4 py-0.5 transition-colors duration-150"
							:class="activeTab === tab.id ? 'bg-carpincho-primary/25' : ''"
						>
							<i class="material-icons !text-[22px]" aria-hidden="true">{{ tab.icon }}</i>
							<span
								v-if="tab.id === 'queue' && queueState.length > 0"
								class="bg-carpincho-primary absolute -top-1 -right-0.5 flex h-[14px] min-w-[14px] items-center justify-center rounded-full px-[3px] text-[0.55rem] leading-none font-bold text-white"
							>
								{{ queueState.length > 99 ? '99+' : queueState.length }}
							</span>
						</div>
						<span
							class="max-w-full truncate px-1 text-[0.65rem] leading-tight font-bold tracking-wide sm:text-xs"
						>
							{{ tab.name }}
						</span>
					</button>
				</div>
			</nav>

			<!-- CONTENIDO DE PESTAÑAS (dos paneles en >= lg para biblioteca/tops + cola lateral) -->
			<div
				class="tab-swipe-container relative order-1 min-h-0 w-full flex-1 overflow-hidden md:order-2"
				:class="
					activeTab === 'library' || activeTab === 'top'
						? 'lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(21rem,26rem)]'
						: ''
				"
				@touchstart.passive="onTabContentTouchStart"
				@touchmove.passive="onTabContentTouchMove"
				@touchend="onTabContentTouchEnd"
				@touchcancel="resetTabSwipe"
			>
				<div v-show="activeTab !== 'queue'" class="relative h-full min-h-0 w-full overflow-hidden">
					<Transition name="tab-fade">
						<LibraryTab v-show="activeTab === 'library'" />
					</Transition>

					<Transition name="tab-fade">
						<TopTab v-show="activeTab === 'top'" />
					</Transition>

					<Transition name="tab-fade">
						<ControlsTab v-show="activeTab === 'controls'" />
					</Transition>
				</div>

				<div
					:class="[
						'border-carpincho-border relative h-full min-h-0 w-full overflow-hidden',
						activeTab === 'queue'
							? 'block'
							: activeTab === 'library' || activeTab === 'top'
								? 'hidden lg:block lg:border-l'
								: 'hidden',
					]"
				>
					<QueueTab v-show="activeTab === 'queue' || activeTab === 'library' || activeTab === 'top'" />
				</div>
			</div>
		</div>
	</div>

	<!-- REPRODUCTOR FLOTANTE -->
	<FloatingPlayer v-show="!isLyricsEditorOpen && !isFogonMode" />
</template>
