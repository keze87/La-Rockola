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

	it('renders mood analysis indicator when is_analyzing_mood is true', () => {
		isScanning.value = false;
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: true,
			phase: 'mood',
			current: 12,
			total: 50,
			message: '',
		};
		const wrapper = mount(App);

		expect(wrapper.text()).toContain('Sintonizando la vibra de los temas (12/50)... 🎶');
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
		expect(wrapper.text()).toContain('El locutor carpincho se está preparando... 🎙️');
		expect(wrapper.text()).not.toContain('Silencio estampa');
	});

	it('renders "Silencio estampa" when no song is playing and locutor is not preparing', () => {
		currentTrackPath.value = null;
		isSynthesizingRadio.value = false;

		const wrapper = mount(App);
		expect(wrapper.text()).toContain('Silencio estampa. Poné algo, fiera.');
	});
});
