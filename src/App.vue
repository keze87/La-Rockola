<script setup lang="ts">
	import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
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
		subscribeAndroidNativeEvents,
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

	const { currentLyricLine, activeLyricLines, loadLyrics, lyrics } = useLyrics({ localTimePos });
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
			// Ya sonó: bien destacada con el ámbar cálido
			return 'headbar-syllable text-[var(--accent-primary)] font-bold transition-colors duration-150 inline';
		} else if (pos >= syl.start && pos < syl.end) {
			// Cantándose en este instante: crema brillante para captar el ojo
			return 'headbar-syllable text-[var(--text-primary)] font-extrabold drop-shadow-[0_0_8px_rgba(212,150,66,0.75)] underline decoration-[var(--accent-primary)]/50 transition-all duration-100 inline-block';
		}
		// Futura: atenuada para dar efecto de lectura karaoke
		return 'headbar-syllable text-[var(--text-tertiary)] font-medium transition-colors duration-150 inline';
	}

	// Conectamos los atajos de teclado (espacio, flechas, f, l, t, n, p, m, esc...)
	useKeyboardShortcuts();

	const tabs = [
		{ id: 'library', name: 'Temazos', icon: 'library_music' },
		{ id: 'queue', name: 'Ronda', icon: 'queue_music' },
		{ id: 'top', name: 'Clásicos', icon: 'local_fire_department' },
		{ id: 'controls', name: 'Perillas', icon: 'settings' },
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

	function navigateSpaHistory(target: string): void {
		if (typeof window === 'undefined') return;
		if (isNativeAndroidHost()) {
			window.history.replaceState(window.history.state, '', target);
		} else {
			window.history.pushState({}, '', target);
		}
	}

	watch(isFogonMode, (fogon) => {
		if (typeof window === 'undefined') return;
		const currentSpaRoute = extractSpaRoute(window.location.pathname);
		if (fogon) {
			if (currentSpaRoute !== '/fogon') {
				const target = `${buildSpaPath('/fogon')}${window.location.search}${window.location.hash}`;
				navigateSpaHistory(target);
			}
		} else if (currentSpaRoute === '/fogon') {
			const tabRoute = activeTab.value === 'library' ? '/' : `/${activeTab.value}`;
			const target = `${buildSpaPath(tabRoute)}${window.location.search}${window.location.hash}`;
			navigateSpaHistory(target);
		}
	});

	watch(isLyricsEditorOpen, (open) => {
		if (typeof window === 'undefined') return;
		const currentSpaRoute = extractSpaRoute(window.location.pathname);
		if (open) {
			if (currentSpaRoute !== '/letras') {
				const target = `${buildSpaPath('/letras')}${window.location.search}${window.location.hash}`;
				navigateSpaHistory(target);
			}
		} else if (currentSpaRoute === '/letras' || currentSpaRoute === '/lyrics') {
			const tabRoute = activeTab.value === 'library' ? '/' : `/${activeTab.value}`;
			const target = `${buildSpaPath(tabRoute)}${window.location.search}${window.location.hash}`;
			navigateSpaHistory(target);
		}
	});

	watch(activeTab, (tab) => {
		if (typeof window === 'undefined') return;
		if (!isFogonMode.value) {
			const tabRoute = tab === 'library' ? '/' : `/${tab}`;
			const targetPathname = buildSpaPath(tabRoute);
			if (window.location.pathname !== targetPathname) {
				const target = `${targetPathname}${window.location.search}${window.location.hash}`;
				navigateSpaHistory(target);
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

	const isPredictiveBackOnTab = computed(
		() =>
			activeTab.value !== 'library' &&
			!isFogonMode.value &&
			!isLyricsEditorOpen.value &&
			!ctxMenu.visible &&
			!hasOpenModal.value &&
			!isInputFocused.value
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
	let stopAndroidEvents: (() => void) | null = null;
	const headbarRef = ref<HTMLElement | null>(null);
	let headbarResizeObserver: ResizeObserver | null = null;

	function syncHeadbarHeight() {
		if (typeof document === 'undefined' || !headbarRef.value) return;
		const h = headbarRef.value.getBoundingClientRect().height;
		if (h > 0) {
			document.documentElement.style.setProperty('--headbar-h', `${Math.floor(h)}px`);
		}
	}

	onMounted(() => {
		initRouter();
		if (typeof window !== 'undefined') {
			restoreUiState({ restoreTab: extractSpaRoute(window.location.pathname) === '/' });
			window.addEventListener('resize', syncHeadbarHeight);
		}
		nextTick(() => {
			syncHeadbarHeight();
			if (typeof ResizeObserver !== 'undefined' && headbarRef.value) {
				headbarResizeObserver = new ResizeObserver(() => syncHeadbarHeight());
				headbarResizeObserver.observe(headbarRef.value);
			}
		});
		stopUiPersistence = initUiPersistence();
		window.__rockolaHandleBack = handleAndroidBack;
		stopAndroidEvents = subscribeAndroidNativeEvents({
			onBackProgress: handleAndroidBackProgress,
			onImeInsetsChanged: handleAndroidImeInsets,
			onPipModeChanged: handleAndroidPipMode,
			onMediaVolumeChanged: handleAndroidMediaVolumeChanged,
			onNativeCommandError: handleNativeCommandError,
			onShortcutAction: applyShortcutAction,
		});
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
				if (currentTrackPath.value && lyrics.value.length === 0) {
					void loadLyrics(currentTrackPath.value, true);
				}
			});
			if (typeof document !== 'undefined') {
				document.addEventListener('visibilitychange', handleAndroidVisibilityChange);
			}
		} else {
			loadLibrary(false);
			connectWebSocket();
		}
	});

	watch(localServerState, (nextState) => {
		if (nextState === 'ready' && currentTrackPath.value && lyrics.value.length === 0) {
			void loadLyrics(currentTrackPath.value, true);
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
		stopAndroidEvents?.();
		stopAndroidEvents = null;
		headbarResizeObserver?.disconnect();
		headbarResizeObserver = null;
		if (typeof window !== 'undefined') {
			window.removeEventListener('resize', syncHeadbarHeight);
		}
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
				toast: 'bg-[var(--bg-elevated)] text-[var(--text-primary)] border border-[var(--glass-border)] shadow-xl rounded-[var(--radius-lg)] font-sans backdrop-blur-xl',
				title: 'font-bold text-[var(--text-primary)]',
				description: 'text-[var(--text-secondary)] text-sm',
				success: '!bg-[var(--accent-mate)] !text-[var(--text-primary)] !border-[var(--accent-mate)]',
				warning: '!bg-[var(--accent-primary)] !text-[#120e0b] !border-[var(--accent-primary)] font-semibold',
				error: '!bg-[var(--accent-danger)] !text-[var(--text-primary)] !border-[var(--accent-danger)]',
				actionButton: 'bg-[var(--accent-primary)] text-[#120e0b] font-semibold',
				cancelButton: 'bg-[var(--bg-input)] text-[var(--text-secondary)]',
				closeButton:
					'text-[var(--text-primary)] hover:text-white bg-[var(--bg-input)] border-[var(--hairline)]',
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
			<img src="/favicon.png" alt="La Rockola del Carpincho" class="mb-4 h-20 w-20 rounded-2xl shadow" />
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
		<!-- BARRA SUPERIOR DE NAVEGACIÓN (fixed con efecto glass cubriendo también la barra de estado) -->
		<nav
			ref="headbarRef"
			class="head-bar fixed top-0 right-0 left-0 z-40 cursor-pointer overflow-hidden border-b-[0.5px] border-[var(--glass-border)] bg-[var(--glass-bg-strong)] px-4 pt-[calc(10px+var(--rockola-safe-top))] pb-2.5 [backdrop-filter:var(--glass-blur)] [-webkit-backdrop-filter:var(--glass-blur)]"
			@click="
				isFogonMode = true;
				haptic();
			"
		>
			<div class="flex w-full items-center justify-start gap-3 font-semibold text-[var(--text-primary)]">
				<div class="flex h-[38px] min-w-0 flex-1 items-center overflow-hidden">
					<transition name="lyric" mode="out-in">
						<span v-if="isScanning" class="flex w-full items-center gap-2 truncate text-left text-[14px]">
							<span
								class="h-2 w-2 shrink-0 animate-pulse rounded-full bg-[var(--accent-primary)]"
								aria-hidden="true"
							/>
							<span class="truncate">
								{{
									scanStatus?.total
										? `Chusmeando temas (${scanStatus.current}/${scanStatus.total}), aguantá fiera... 🧉`
										: 'Chusmeando temas, aguantá fiera... 🧉'
								}}
							</span>
						</span>
						<div
							v-else-if="currentTrackPath && activeLyricLines.length > 0"
							:key="activeLyricLines.map((l) => l.text).join('-')"
							class="block w-full truncate text-left text-[0.95rem] font-medium whitespace-pre italic drop-shadow-sm"
						>
							<template v-for="(line, idx) in activeLyricLines" :key="idx + '-' + line.time">
								<span
									v-if="idx > 0"
									class="mx-1.5 font-normal text-[var(--text-secondary)]/70 not-italic"
								>
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
								<span v-else class="text-[var(--accent-primary)]">{{ line.text }}</span>
							</template>
						</div>
						<span
							v-else-if="currentTrackPath && currentLyricLine && currentLyricLine.trim() !== ''"
							:key="currentLyricLine"
							class="block w-full truncate text-left text-[0.95rem] font-medium text-[var(--accent-primary)] italic drop-shadow-sm"
						>
							{{ currentLyricLine }}
						</span>
						<span v-else class="block w-full truncate text-left text-[14px] font-semibold">
							{{ currentTrackTitle }}
						</span>
					</transition>
				</div>

				<img
					v-if="headbarCoverUrl"
					:src="headbarCoverUrl"
					class="h-9 w-9 shrink-0 rounded-[6px] border border-[var(--hairline)] object-cover shadow-[0_2px_8px_rgba(0,0,0,0.35)]"
					@error="onHeadbarCoverError"
				/>
				<div
					v-else
					class="flex h-9 w-9 shrink-0 items-center justify-center rounded-[6px] border border-[var(--hairline)] bg-[var(--bg-input)]"
				>
					<i class="material-icons !text-[20px] text-[var(--accent-primary)]">
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
		<div class="headbar-banners fixed top-[var(--headbar-h)] right-0 left-0 z-[38] flex w-full flex-col">
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
					<i class="material-icons text-carpincho-warning text-base" aria-hidden="true">
						notifications_active
					</i>
					<span class="text-carpincho-text">
						Activá las notificaciones para ver y controlar la música desde la pantalla de bloqueo.
					</span>
				</div>
				<div class="flex shrink-0 items-center gap-2">
					<button
						type="button"
						class="touch-target tap-feedback text-carpincho-muted hover:text-carpincho-text rounded-lg px-2.5 py-1.5 font-semibold"
						@click="dismissNotificationPermissionPrompt"
					>
						Ahora no
					</button>
					<button
						type="button"
						class="touch-target tap-feedback bg-carpincho-primary rounded-lg px-3 py-1.5 font-bold text-white shadow-sm"
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
		</div>

		<!-- BARRA DE PROGRESO (anclada justo debajo del head-bar fijo) -->
		<div
			v-show="!isScanning && currentTrackPath"
			class="headbar-progress-bar group fixed top-[var(--headbar-h)] right-0 left-0 z-40 flex h-2 w-full cursor-pointer touch-none items-start bg-transparent"
			style="-webkit-tap-highlight-color: transparent"
			@pointerdown="startSeek"
			@pointermove="moveSeek"
			@pointerup="endSeek"
			@pointercancel="endSeek"
		>
			<div
				class="relative h-[2px] w-full bg-[rgba(255,235,208,0.1)] transition-all duration-100 ease-out group-hover:h-1.5 group-active:h-1.5"
			>
				<div
					class="absolute top-0 left-0 z-10 h-full bg-[var(--accent-primary)]"
					:style="{ width: progressPercent + '%' }"
				/>

				<!-- Bolita que solo aparece al pasar el dedo/mouse -->
				<div
					class="absolute top-1/2 z-10 h-3 w-3 -translate-y-1/2 rounded-full bg-[var(--accent-primary)] opacity-0 shadow-md group-hover:opacity-100 group-active:opacity-100"
					:style="{ left: progressPercent + '%', marginLeft: '-6px' }"
				/>
			</div>
		</div>

		<!-- CUERPO PRINCIPAL: TAB BAR INFERIOR iOS EN MÓVIL / RIEL LATERAL Y DOS PANELES EN PANTALLAS GRANDES -->
		<div class="flex min-h-0 w-full flex-1 flex-col overflow-hidden md:flex-row">
			<!-- PESTAÑAS (anclada borde a borde en móvil cubriendo safe-bottom, riel lateral desde md) -->
			<nav
				aria-label="Secciones principales"
				class="floating-tab-bar fixed z-40 order-2 flex min-h-[var(--tabbar-h)] shrink-0 items-center overflow-hidden border-t-[0.5px] border-[var(--glass-border)] bg-[var(--glass-bg-strong)] px-2 pt-1.5 [backdrop-filter:var(--glass-blur)] transition-all duration-200 ease-out [-webkit-backdrop-filter:var(--glass-blur)] md:top-auto md:right-auto md:bottom-[calc(12px+var(--safe-bottom))] md:left-4 md:z-50 md:order-1 md:h-[var(--floating-player-h)] md:min-h-0 md:w-auto md:flex-row md:items-center md:overflow-visible md:rounded-[var(--radius-lg)] md:border md:border-[var(--glass-border)] md:bg-[var(--glass-bg-strong)] md:px-2 md:py-1.5 md:pt-1.5 md:pb-1.5 md:[box-shadow:var(--glass-highlight),0_12px_32px_rgba(0,0,0,0.45)] lg:w-[calc(var(--queue-col-w)-32px)] lg:justify-center"
				:class="[
					isTabsBarHidden && isShortScreen
						? 'pointer-events-none max-h-0 translate-y-2 border-0 py-0 opacity-0 md:pointer-events-auto md:max-h-none md:translate-y-0 md:py-1.5 md:opacity-100'
						: 'translate-y-0 opacity-100',
				]"
			>
				<div
					role="tablist"
					class="flex w-full items-center justify-around gap-1 md:w-auto md:flex-row md:justify-start md:gap-0.5 md:p-0 lg:w-full lg:justify-evenly"
				>
					<button
						v-for="tab in tabs"
						:key="tab.id"
						type="button"
						role="tab"
						:aria-selected="activeTab === tab.id"
						:aria-label="tab.name"
						:title="tab.name"
						:class="[
							'touch-target tap-feedback relative flex flex-1 cursor-pointer touch-manipulation flex-col items-center justify-center gap-0.5 rounded-xl py-1 text-center transition-colors duration-150 md:min-w-[60px] md:flex-none md:rounded-[var(--radius-md)] md:px-2 md:py-1 lg:min-w-0 lg:flex-1',
							tab.id === 'queue' ? 'lg:hidden' : '',
							activeTab === tab.id
								? 'text-[var(--accent-primary)]'
								: 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]',
						]"
						@click="switchTab(tab.id, { onScrollToTop: () => haptic('tick') })"
					>
						<div
							class="relative flex items-center justify-center rounded-full px-3 py-0.5 transition-colors duration-150"
							:class="activeTab === tab.id ? 'bg-[var(--accent-primary-soft)]' : ''"
						>
							<i class="material-icons !text-[22px]" aria-hidden="true">{{ tab.icon }}</i>
							<span
								v-if="tab.id === 'queue' && queueState.length > 0"
								class="absolute -top-1.5 -right-1.5 flex h-[15px] min-w-[15px] items-center justify-center rounded-full bg-[var(--accent-primary)] px-1 text-[10px] leading-none font-bold text-[#120e0b] tabular-nums shadow-[0_0_0_2px_var(--bg-canvas)]"
							>
								{{ queueState.length > 99 ? '99+' : queueState.length }}
							</span>
						</div>
						<span class="px-0.5 text-[11px] leading-tight font-semibold tracking-tight whitespace-nowrap">
							{{ tab.name }}
						</span>
					</button>
				</div>
			</nav>

			<!-- CONTENIDO DE PESTAÑAS (dos paneles en >= lg: cola fija a la izquierda y sección activa a la derecha) -->
			<div
				class="tab-swipe-container relative order-1 min-h-0 w-full flex-1 overflow-hidden md:order-2 lg:grid lg:grid-cols-[var(--queue-col-w)_minmax(0,1fr)]"
				:class="[{ 'predictive-back-target': isPredictiveBackOnTab }]"
			>
				<div
					:class="[
						'relative h-full min-h-0 w-full overflow-hidden border-[var(--hairline)] lg:order-1 lg:block lg:border-r',
						activeTab === 'queue' ? 'block' : 'hidden',
					]"
				>
					<QueueTab />
				</div>

				<div
					:class="[
						'relative h-full min-h-0 w-full overflow-hidden lg:order-2 lg:block',
						activeTab !== 'queue' ? 'block' : 'hidden',
					]"
				>
					<Transition name="tab-fade">
						<LibraryTab v-show="activeTab === 'library' || activeTab === 'queue'" />
					</Transition>

					<Transition name="tab-fade">
						<TopTab v-show="activeTab === 'top'" />
					</Transition>

					<Transition name="tab-fade">
						<ControlsTab v-show="activeTab === 'controls'" />
					</Transition>
				</div>
			</div>
		</div>
	</div>

	<!-- SCRIM INFERIOR DETRÁS DEL DOCK FLOTANTE -->
	<div v-show="!isLyricsEditorOpen && !isFogonMode" class="bottom-dock-scrim" aria-hidden="true" />

	<!-- REPRODUCTOR FLOTANTE -->
	<FloatingPlayer v-show="!isLyricsEditorOpen && !isFogonMode" />
</template>
