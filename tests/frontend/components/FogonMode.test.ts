import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import FogonMode from '@/components/FogonMode.vue';
import {
	currentTrackPath,
	djBaraEnabled,
	djNextTrack,
	isFogonMode,
	isPaused,
	trackMap,
	volume,
} from '@/composables/player/state';

describe('FogonMode.vue', () => {
	beforeEach(() => {
		isFogonMode.value = true;
		currentTrackPath.value = '/music/cancion.flac';
		isPaused.value = false;
		djBaraEnabled.value = false;
		djNextTrack.value = null;
		volume.value = 80;
		trackMap.value = {
			'/music/cancion.flac': {
				path: '/music/cancion.flac',
				display_title: 'Canción para mi muerte',
				display_artist: 'Sui Generis',
			},
		};

		global.fetch = vi.fn().mockResolvedValue({
			ok: false,
			status: 404,
		} as unknown as Response);
	});

	it('renders now playing title and artist in full screen mode', () => {
		const wrapper = mount(FogonMode);

		expect(wrapper.text()).toContain('Canción para mi muerte');
		expect(wrapper.text()).toContain('Sui Generis');
	});

	it('closes fogon mode when clicking the close button', async () => {
		const wrapper = mount(FogonMode);
		const closeBtn = wrapper.find('button[aria-label="Cerrar vista de fogón"]');
		expect(closeBtn.exists()).toBe(true);

		await closeBtn.trigger('click');
		expect(isFogonMode.value).toBe(false);
	});

	it('renders DJ next track preview when stopped but DJ is active', () => {
		currentTrackPath.value = null;
		djBaraEnabled.value = true;
		djNextTrack.value = {
			path: '/music/dj_track.mp3',
			title: 'Jijiji',
			artist: 'Patricio Rey',
		};

		const wrapper = mount(FogonMode);
		expect(wrapper.text()).toContain('Se viene...');
		expect(wrapper.text()).toContain('Jijiji');
		expect(wrapper.text()).toContain('Patricio Rey');
	});

	it('handles seek and volume controls', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const wrapper = mount(FogonMode);

		// Seek interaction
		const seekBar = wrapper.find('.group.flex.h-10.w-full.cursor-pointer');
		expect(seekBar.exists()).toBe(true);
		const el = seekBar.element as HTMLElement;
		vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
			left: 0,
			top: 0,
			right: 200,
			bottom: 40,
			width: 200,
			height: 40,
			x: 0,
			y: 0,
			toJSON: () => {},
		});

		await seekBar.trigger('pointerdown', { clientX: 50, pointerId: 1 });
		await seekBar.trigger('pointermove', { clientX: 100, pointerId: 1 });
		await seekBar.trigger('pointerup', { clientX: 100, pointerId: 1 });

		// Volume button opens volume popup
		const volIconBtn = wrapper.findAll('button').find((b) => b.text().includes('volume_up'));
		expect(volIconBtn).toBeDefined();
		await volIconBtn!.trigger('click');

		// Volume popup overlay can be clicked to close
		const overlay = wrapper.find('.fixed.inset-0.z-10');
		if (overlay.exists()) {
			await overlay.trigger('click');
		}

		// Play/pause button in fogon
		const playBtn = wrapper.findAll('button').find((b) => b.text().includes('pause'));
		expect(playBtn).toBeDefined();
		await playBtn!.trigger('click');

		// Skip button in fogon
		const skipBtn = wrapper.findAll('button').find((b) => b.text().includes('skip_next'));
		expect(skipBtn).toBeDefined();
		await skipBtn!.trigger('click');
	});

	it('only hides cursor when inactive and shows it when mouse moves', async () => {
		vi.useFakeTimers();
		try {
			const wrapper = mount(FogonMode);
			const container = wrapper.find('.fixed.inset-0.z-\\[10000\\]');
			expect(container.exists()).toBe(true);

			// Inicialmente el cursor está visible
			expect(container.classes()).not.toContain('cursor-none');

			// Tras 3 segundos de inactividad, se oculta el cursor
			vi.advanceTimersByTime(3000);
			await wrapper.vm.$nextTick();
			expect(container.classes()).toContain('cursor-none');

			// Al mover el mouse, el cursor reaparece de inmediato
			window.dispatchEvent(new MouseEvent('mousemove'));
			await wrapper.vm.$nextTick();
			expect(container.classes()).not.toContain('cursor-none');

			// Tras otros 3 segundos quieto, se vuelve a ocultar
			vi.advanceTimersByTime(3000);
			await wrapper.vm.$nextTick();
			expect(container.classes()).toContain('cursor-none');
		} finally {
			vi.useRealTimers();
		}
	});

	it('renders karaoke syllables and multiple simultaneous lines in fogon mode', async () => {
		const assContent = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\kf100}Café {\\kf100}caliente
Dialogue: 0,0:00:01.00,0:00:06.00,Default,,0,0,0,,{\\kf100}Taza {\\kf100}llena
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
				json: () => Promise.resolve({ status: 'ok' }),
			} as unknown as Response);
		});

		const wrapper = mount(FogonMode);

		// Trigger track change to load lyrics
		currentTrackPath.value = '/music/test_karaoke.mp3';
		await wrapper.vm.$nextTick();
		// Await fetch promise
		await new Promise((resolve) => setTimeout(resolve, 10));
		await wrapper.vm.$nextTick();

		// At 2 seconds: both lines are active
		const { localTimePos } = await import('@/composables/player/state');
		localTimePos.value = 2;
		await wrapper.vm.$nextTick();

		expect(wrapper.text()).toContain('Café caliente');
		expect(wrapper.text()).toContain('Taza llena');

		// Verificar que los spans de sílabas están presentes
		const spans = wrapper.findAll('.whitespace-pre-wrap span');
		expect(spans.length).toBeGreaterThanOrEqual(4);
	});

	it('supports Apple Music style vertical scrolling, fade mask and clicking lines to seek', async () => {
		const assContent = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:10.00,0:00:15.00,Default,,0,0,0,,{\\kf100}Primera {\\kf100}linea
Dialogue: 0,0:00:20.00,0:00:25.00,Default,,0,0,0,,{\\kf100}Segunda {\\kf100}linea
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
				json: () => Promise.resolve({ status: 'ok' }),
			} as unknown as Response);
		});

		const wrapper = mount(FogonMode);
		currentTrackPath.value = '/music/seek_test.mp3';
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 15));
		await wrapper.vm.$nextTick();

		// Contenedor con máscara de desvanecimiento estilo Apple Music
		const maskContainer = wrapper.find('.lyrics-mask');
		expect(maskContainer.exists()).toBe(true);

		// Contenedor con scrollbar oculta
		const scrollContainer = wrapper.find('.no-scrollbar');
		expect(scrollContainer.exists()).toBe(true);

		// Click en la segunda línea
		const lines = scrollContainer.findAll('.whitespace-pre-wrap');
		expect(lines.length).toBe(2);
		await lines[1].trigger('click');

		// Modo vertical muestra únicamente entre 2 y 3 líneas
		const portraitContainer = wrapper.find('.lyrics-mask-vertical');
		expect(portraitContainer.exists()).toBe(true);
		const portraitLines = portraitContainer.findAll('.whitespace-pre-wrap');
		expect(portraitLines.length).toBeGreaterThanOrEqual(1);
		expect(portraitLines.length).toBeLessThanOrEqual(3);
	});

	it('applies Apple Music depth-of-field blur on inactive lines and pure white glow on active syllables', async () => {
		const assContent = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\kf100}Hola {\\kf100}mundo
Dialogue: 0,0:00:06.00,0:00:10.00,Default,,0,0,0,,{\\kf100}Segunda {\\kf100}frase
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
				json: () => Promise.resolve({ status: 'ok' }),
			} as unknown as Response);
		});

		const wrapper = mount(FogonMode);
		currentTrackPath.value = '/music/glow_test.mp3';
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 15));
		await wrapper.vm.$nextTick();

		const { localTimePos } = await import('@/composables/player/state');
		localTimePos.value = 1; // Primera línea activa
		await wrapper.vm.$nextTick();

		const scrollContainer = wrapper.find('.no-scrollbar');
		const lines = scrollContainer.findAll('.whitespace-pre-wrap');
		expect(lines.length).toBe(2);

		// Línea activa: sin desenfoque (blur-none) y escala destacada
		expect(lines[0].classes()).toContain('blur-none');
		// Línea inactiva: con desenfoque de profundidad de campo (blur-[1.5px] o blur-sm)
		expect(lines[1].classes()).toContain('blur-[1.5px]');

		// La sílaba activa no debe tener subrayado tosco y debe tener resplandor blanco puro
		const activeSyllable = lines[0].find('.inline-block');
		expect(activeSyllable.exists()).toBe(true);
		expect(activeSyllable.classes()).not.toContain('underline');
		expect(activeSyllable.classes()).toContain('drop-shadow-[0_0_16px_rgba(255,255,255,1)]');
	});

	it('uses centered layout with reduced vertical spacing on narrow screens', async () => {
		const assContent = `[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\kf100}Hola
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
				json: () => Promise.resolve({ status: 'ok' }),
			} as unknown as Response);
		});

		const wrapper = mount(FogonMode);
		currentTrackPath.value = '/music/narrow_screen.mp3';
		await wrapper.vm.$nextTick();
		await new Promise((resolve) => setTimeout(resolve, 15));
		await wrapper.vm.$nextTick();

		// Contenedor principal debe centrar verticalmente en mobile sin desparramar con justify-between
		const mainLayout = wrapper.find('.max-w-7xl');
		expect(mainLayout.classes()).toContain('justify-center');
		expect(mainLayout.classes()).not.toContain('justify-between');

		// La columna del reproductor en móviles debe estar centrada verticalmente sin justify-between
		const playerColumn = wrapper.find('.max-w-7xl > div');
		expect(playerColumn.classes()).toContain('justify-center');
		expect(playerColumn.classes()).not.toContain('justify-between');

		// En pantallas estrechas, la carátula usa el 90% del ancho y las letras ocupan el 100% del ancho y toda la altura debajo de los controles
		const coverWrapper = wrapper.find('.bg-carpincho-bg');
		expect(coverWrapper.classes()).toContain('w-[90vw]');
		expect(coverWrapper.classes()).toContain('h-[90vw]');

		const portraitLyrics = wrapper.find('.lyrics-mask-vertical');
		expect(portraitLyrics.classes()).toContain('w-full');
		expect(portraitLyrics.classes()).toContain('flex-1');

		// El título queda clavado en el centro vertical de la pantalla dividiendo el espacio en dos bloques flex-1 simétricos
		const topCoverSection = coverWrapper.element.parentElement;
		expect(topCoverSection?.classList.contains('flex-1')).toBe(true);

		const trackInfoSection = wrapper.find('.fogon-track-info');
		expect(trackInfoSection.exists()).toBe(true);
		expect(trackInfoSection.classes()).toContain('shrink-0');

		const bottomSection = portraitLyrics.element.parentElement;
		expect(bottomSection?.classList.contains('flex-1')).toBe(true);
	});

	it('maintains symmetrical centered alignment on wide screens with or without lyrics or during DJ wait', async () => {
		// Estado 1: Sin canción ("Silencio estampa")
		currentTrackPath.value = null;
		djBaraEnabled.value = false;
		djNextTrack.value = null;

		const wrapper = mount(FogonMode);
		const playerColumn = wrapper.find('.max-w-7xl > div');

		// La columna debe estar centrada y no tener clases que tiren elementos a la izquierda (como md:items-start o md:text-left)
		expect(playerColumn.classes()).toContain('items-center');
		expect(playerColumn.classes()).toContain('text-center');
		expect(playerColumn.classes()).not.toContain('md:items-start');
		expect(playerColumn.classes()).not.toContain('md:text-left');

		// Los controles deben estar centrados
		const controlsRow = wrapper.find('.relative.z-30.flex.w-full.items-center');
		expect(controlsRow.classes()).toContain('justify-center');
		expect(controlsRow.classes()).not.toContain('md:justify-start');

		// No debe mostrar texto fuera de lugar de "Sin letras sincronizadas" en estado detenido
		expect(wrapper.text()).not.toContain('Sin letras sincronizadas');
	});
});
