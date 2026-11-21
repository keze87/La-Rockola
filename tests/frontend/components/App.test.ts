import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import App from '@/App.vue';
import {
	activeTab,
	currentTrackPath,
	isFogonMode,
	isScanning,
	isSynthesizingRadio,
	queueState,
	scanStatus,
	trackMap,
} from '@/composables/player/state';
import { useTabs } from '@/composables/player/useTabs';

describe('App.vue', () => {
	beforeEach(() => {
		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);

		activeTab.value = 'library';
		currentTrackPath.value = null;
		isFogonMode.value = false;
		isScanning.value = false;
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: false,
			phase: 'idle',
			current: 0,
			total: 0,
			message: '',
		};
		queueState.value = [];
		trackMap.value = {};
	});

	it('renders tabs navigation with all main tabs', () => {
		const wrapper = mount(App);

		expect(wrapper.text()).toContain('Los Temazos');
		expect(wrapper.text()).toContain('La Ronda');
		expect(wrapper.text()).toContain('Los Clásicos');
		expect(wrapper.text()).toContain('Las Perillas');
	});

	it('switches active tab when tab header is clicked', async () => {
		const wrapper = mount(App);

		const tabHeaders = wrapper.findAll('.cursor-pointer.touch-manipulation');
		const queueTabBtn = tabHeaders.find((w) => w.text().includes('La Ronda'));
		expect(queueTabBtn).toBeDefined();

		await queueTabBtn!.trigger('click');
		expect(activeTab.value).toBe('queue');
	});

	it('activates fogon mode when navbar header is clicked', async () => {
		const wrapper = mount(App);

		const navHeader = wrapper.find('nav');
		await navHeader.trigger('click');

		expect(isFogonMode.value).toBe(true);
	});

	it('renders scanning indicator when isScanning is true', () => {
		isScanning.value = true;
		const wrapper = mount(App);

		expect(wrapper.text()).toContain('[Avisando] Chusmeando temas, aguantá fiera... 🧉');
	});

	it('renders scanning indicator with counter when scanStatus has total > 0', () => {
		isScanning.value = true;
		scanStatus.value = {
			is_scanning: true,
			phase: 'metadata',
			current: 450,
			total: 1765,
			message: '',
		};
		const wrapper = mount(App);

		expect(wrapper.text()).toContain('[Avisando] Chusmeando temas (450/1765), aguantá fiera... 🧉');
	});

	it('renders current track title in header when a song is playing', () => {
		currentTrackPath.value = '/music/rock.mp3';
		trackMap.value['/music/rock.mp3'] = {
			path: '/music/rock.mp3',
			display_title: 'Seminare',
			display_artist: 'Serú Girán',
		};

		const wrapper = mount(App);
		expect(wrapper.text()).toContain('Serú Girán - Seminare');
	});

	it('renders locutor preparing in header when isSynthesizingRadio is true instead of silencio estampa', () => {
		currentTrackPath.value = null;
		isSynthesizingRadio.value = true;

		const wrapper = mount(App);
		expect(wrapper.text()).toContain('Transmisión de Cabina');
		expect(wrapper.text()).not.toContain('Silencio estampa');
	});

	it('renders "Silencio estampa" when no song is playing and locutor is not preparing', () => {
		currentTrackPath.value = null;
		isSynthesizingRadio.value = false;

		const wrapper = mount(App);
		expect(wrapper.text()).toContain('Silencio estampa. Poné algo, fiera.');
	});

	it('renders karaoke syllables and simultaneous lines in the headbar when ASS is loaded', async () => {
		const assContent = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\kf100}Mate {\\kf100}amargo
Dialogue: 0,0:00:01.00,0:00:06.00,Default,,0,0,0,,{\\kf100}Bizcochitos {\\kf100}de grasa
`;

		global.fetch = vi.fn().mockImplementation((url: string) => {
			if (typeof url === 'string' && url.includes('/lrc')) {
				return Promise.resolve({
					ok: true,
					text: () => Promise.resolve(assContent),
				} as unknown as Response);
			}
			return Promise.resolve({
				ok: true,
				json: () =>
					Promise.resolve({
						status: 'ok',
						data: [
							{
								path: '/music/test_gaps.mp3',
								display_title: 'Canción del Río',
								display_artist: 'El Carpincho',
							},
						],
					}),
			} as unknown as Response);
		});

		const { localTimePos } = await import('@/composables/player/state');
		currentTrackPath.value = '/music/tarde.mp3';
		trackMap.value['/music/tarde.mp3'] = {
			path: '/music/tarde.mp3',
			display_title: 'Tarde campera',
			display_artist: 'Los Carpinchos',
		};

		const wrapper = mount(App);
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 15));
		await wrapper.vm.$nextTick();

		// At 2 seconds: both lines are active
		localTimePos.value = 2;
		await wrapper.vm.$nextTick();

		// Nav bar header contains syllables and separator
		const nav = wrapper.find('nav');
		expect(nav.text()).toContain('Mate amargo');
		expect(nav.text()).toContain('Bizcochitos de grasa');

		// Spans with syllable styling should exist inside nav
		const sylSpans = nav.findAll('.headbar-syllable');
		expect(sylSpans.length).toBe(4);
		const activeSyllable = sylSpans.find((s) => s.text().includes('de grasa'));
		expect(activeSyllable).toBeDefined();
		expect(activeSyllable!.classes()).toContain('text-white');
	});

	it('shows carpincho emoji for short gaps and reverts to track title for long gaps in headbar', async () => {
		const assContent = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:02.00,0:00:05.00,Default,,0,0,0,,{\\kf100}Verso {\\kf100}uno
Dialogue: 0,0:00:06.50,0:00:09.00,Default,,0,0,0,,{\\kf100}Verso {\\kf100}dos
Dialogue: 0,0:00:20.00,0:00:24.00,Default,,0,0,0,,{\\kf100}Verso {\\kf100}tres
`;

		global.fetch = vi.fn().mockImplementation((url: string) => {
			if (typeof url === 'string' && url.includes('/lrc')) {
				return Promise.resolve({
					ok: true,
					text: () => Promise.resolve(assContent),
				} as unknown as Response);
			}
			return Promise.resolve({
				ok: true,
				json: () =>
					Promise.resolve({
						status: 'ok',
						data: [
							{
								path: '/music/test_gaps.mp3',
								display_title: 'Canción del Río',
								display_artist: 'El Carpincho',
							},
						],
					}),
			} as unknown as Response);
		});

		const { localTimePos } = await import('@/composables/player/state');
		currentTrackPath.value = '/music/test_gaps.mp3';
		trackMap.value['/music/test_gaps.mp3'] = {
			path: '/music/test_gaps.mp3',
			display_title: 'Canción del Río',
			display_artist: 'El Carpincho',
		};

		const wrapper = mount(App);
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 15));
		await wrapper.vm.$nextTick();

		const nav = wrapper.find('nav');

		// Durante verso uno (3s)
		localTimePos.value = 3;
		await wrapper.vm.$nextTick();
		expect(nav.text()).toContain('Verso uno');

		// Silencio corto (5s a 6.5s -> 1.5s gap): en 5.5s debe mostrar '🦦' y NO repetir 'Verso uno'
		localTimePos.value = 5.5;
		await wrapper.vm.$nextTick();
		expect(nav.text()).toContain('🦦');
		expect(nav.text()).not.toContain('Verso uno');

		// Durante verso dos (7s)
		localTimePos.value = 7;
		await wrapper.vm.$nextTick();
		expect(nav.text()).toContain('Verso dos');

		// Silencio largo (9s a 20s -> 11s gap): en 12s debe volver al título de la canción
		localTimePos.value = 12;
		await wrapper.vm.$nextTick();
		expect(nav.text()).toContain('El Carpincho - Canción del Río');
		expect(nav.text()).not.toContain('Verso dos');
	});

	it('preserves url search params (?vibra=...) when switching tabs or fogon mode', async () => {
		window.history.replaceState({}, '', '/?vibra=42');
		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		// Cambiar a pestaña La Ronda
		activeTab.value = 'queue';
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/queue');
		expect(window.location.search).toBe('?vibra=42');

		// Activar Modo Fogón
		isFogonMode.value = true;
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/fogon');
		expect(window.location.search).toBe('?vibra=42');

		// Desactivar Modo Fogón
		isFogonMode.value = false;
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/queue');
		expect(window.location.search).toBe('?vibra=42');

		// Volver a Los Temazos
		activeTab.value = 'library';
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/');
		expect(window.location.search).toBe('?vibra=42');
	});

	it('preserves subpath (/rockola) when switching tabs, fogon mode, and lyrics editor', async () => {
		const { isLyricsEditorOpen } = await import('@/stores/useUiStore');
		isLyricsEditorOpen.value = false;
		window.history.replaceState({}, '', '/rockola/?vibra=99');

		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		activeTab.value = 'queue';
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/rockola/queue');
		expect(window.location.search).toBe('?vibra=99');

		isFogonMode.value = true;
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/rockola/fogon');

		isFogonMode.value = false;
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/rockola/queue');

		isLyricsEditorOpen.value = true;
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/rockola/letras');

		isLyricsEditorOpen.value = false;
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/rockola/queue');

		activeTab.value = 'library';
		await wrapper.vm.$nextTick();
		expect(window.location.pathname).toBe('/rockola/');
		expect(window.location.search).toBe('?vibra=99');
	});

	it('updates document favicon with current song cover and falls back to default favicon on error or stop', async () => {
		window.history.replaceState({}, '', '/');
		let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
		if (!link) {
			link = document.createElement('link');
			link.rel = 'icon';
			document.head.appendChild(link);
		}
		link.href = '/favicon.png';

		currentTrackPath.value = '/music/con_tapa.mp3';
		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		expect(link.getAttribute('href')).toContain('/cover?path=%2Fmusic%2Fcon_tapa.mp3');

		// Si la portada da error, vuelve al favicon por defecto
		const img = wrapper.find('nav img');
		expect(img.exists()).toBe(true);
		await img.trigger('error');
		await wrapper.vm.$nextTick();

		expect(link.getAttribute('href')).toBe('/favicon.png');

		// Al cambiar a otro tema válido, vuelve a usar la carátula
		currentTrackPath.value = '/music/otro_tema.mp3';
		await wrapper.vm.$nextTick();
		expect(link.getAttribute('href')).toContain('/cover?path=%2Fmusic%2Fotro_tema.mp3');

		// Al frenar la reproducción, restaura el favicon original
		currentTrackPath.value = null;
		await wrapper.vm.$nextTick();
		expect(link.getAttribute('href')).toBe('/favicon.png');
	});

	it('hides the background navigation, seekbar and tabs when fogon mode is active to optimize performance', async () => {
		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		const appContent = wrapper.find('.app-main-content');
		expect(appContent.exists()).toBe(true);
		expect(appContent.attributes('style')).toBeUndefined();

		isFogonMode.value = true;
		await wrapper.vm.$nextTick();
		await wrapper.vm.$nextTick();

		expect(appContent.attributes('style')).toContain('display: none');
	});

	it('collapses tabs bar on short screens when isTabsBarHidden is true', async () => {
		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		const { isShortScreen, isTabsBarHidden } = useTabs();
		isShortScreen.value = false;
		isTabsBarHidden.value = false;
		await wrapper.vm.$nextTick();

		const tabsBar = wrapper.find('.bg-carpincho-panel.border-carpincho-border.relative.z-10');
		expect(tabsBar.classes()).not.toContain('max-h-0');

		// En pantalla petiza con flag activo
		isShortScreen.value = true;
		isTabsBarHidden.value = true;
		await wrapper.vm.$nextTick();

		expect(tabsBar.classes()).toContain('max-h-0');
		expect(tabsBar.classes()).toContain('opacity-0');
	});

	it('handles Android back navigation via window.__rockolaHandleBack priority order', async () => {
		const { useContextMenu } = await import('@/composables/useContextMenu');
		const { isLyricsEditorOpen } = await import('@/stores/useUiStore');
		const { ctxMenu } = useContextMenu();

		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		expect(typeof window.__rockolaHandleBack).toBe('function');

		// 1. Menú contextual abierto tiene máxima prioridad
		ctxMenu.visible = true;
		isLyricsEditorOpen.value = true;
		isFogonMode.value = true;
		activeTab.value = 'queue';
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(ctxMenu.visible).toBe(false);
		expect(isLyricsEditorOpen.value).toBe(true);

		// 2. Editor de letras
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(isLyricsEditorOpen.value).toBe(false);
		expect(isFogonMode.value).toBe(true);

		// 3. Modo Fogón
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(isFogonMode.value).toBe(false);
		expect(activeTab.value).toBe('queue');

		// 4. Pestaña distinta de biblioteca vuelve a biblioteca
		expect(window.__rockolaHandleBack?.()).toBe(true);
		expect(activeTab.value).toBe('library');

		// 5. En la raíz devuelve false para que Android mande la app a segundo plano
		expect(window.__rockolaHandleBack?.()).toBe(false);

		wrapper.unmount();
		expect(window.__rockolaHandleBack).toBeUndefined();
	});

	it('switches tabs on horizontal swipe and ignores swipes inside queue rows or sliders', async () => {
		const wrapper = mount(App);
		await wrapper.vm.$nextTick();

		const container = wrapper.find('.tab-swipe-container');
		expect(container.exists()).toBe(true);

		// Swipe izquierda desde library -> queue
		await container.trigger('touchstart', { touches: [{ clientX: 280, clientY: 200 }] });
		await container.trigger('touchmove', { touches: [{ clientX: 140, clientY: 205 }] });
		await container.trigger('touchend');
		expect(activeTab.value).toBe('queue');

		// Swipe iniciado sobre una fila de La Ronda ([data-queue-index]) se ignora
		const protectedTarget = document.createElement('div');
		protectedTarget.setAttribute('data-queue-index', '0');
		container.element.appendChild(protectedTarget);

		protectedTarget.dispatchEvent(
			new TouchEvent('touchstart', {
				bubbles: true,
				touches: [{ clientX: 280, clientY: 200 } as Touch],
			})
		);
		protectedTarget.dispatchEvent(
			new TouchEvent('touchmove', {
				bubbles: true,
				touches: [{ clientX: 140, clientY: 205 } as Touch],
			})
		);
		protectedTarget.dispatchEvent(new TouchEvent('touchend', { bubbles: true }));
		expect(activeTab.value).toBe('queue');
		protectedTarget.remove();

		// Swipe izquierda desde queue -> top
		await container.trigger('touchstart', { touches: [{ clientX: 280, clientY: 200 }] });
		await container.trigger('touchmove', { touches: [{ clientX: 140, clientY: 205 }] });
		await container.trigger('touchend');
		expect(activeTab.value).toBe('top');

		// Swipe derecha desde top -> queue
		await container.trigger('touchstart', { touches: [{ clientX: 100, clientY: 200 }] });
		await container.trigger('touchmove', { touches: [{ clientX: 240, clientY: 205 }] });
		await container.trigger('touchend');
		expect(activeTab.value).toBe('queue');
	});

	it('exposes launcher shortcut hooks (__rockolaOpenFogon, __rockolaOpenQueue) and consumes pending Android shortcut on mount', async () => {
		const androidHost = await import('@/composables/useAndroidHost');
		const isNativeSpy = vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		vi.spyOn(androidHost, 'initAndroidServer').mockResolvedValue(true);
		const shortcutSpy = vi
			.spyOn(androidHost as any, 'consumeAndroidPendingShortcut')
			.mockResolvedValue('ar.carpincho.rockola.ACTION_OPEN_FOGON');

		try {
			const wrapper = mount(App);
			await wrapper.vm.$nextTick();
			await new Promise((resolve) => setTimeout(resolve, 10));
			await wrapper.vm.$nextTick();

			expect(typeof (window as any).__rockolaOpenFogon).toBe('function');
			expect(typeof (window as any).__rockolaOpenQueue).toBe('function');
			expect(isFogonMode.value).toBe(true);

			isFogonMode.value = false;
			(window as any).__rockolaOpenQueue();
			expect(activeTab.value).toBe('queue');
			expect(isFogonMode.value).toBe(false);

			(window as any).__rockolaOpenFogon();
			expect(isFogonMode.value).toBe(true);

			wrapper.unmount();
			expect((window as any).__rockolaOpenFogon).toBeUndefined();
			expect((window as any).__rockolaOpenQueue).toBeUndefined();
		} finally {
			isNativeSpy.mockRestore();
			shortcutSpy.mockRestore();
		}
	});
});
