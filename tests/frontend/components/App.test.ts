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
				json: () => Promise.resolve({ status: 'ok', data: [] }),
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
});
