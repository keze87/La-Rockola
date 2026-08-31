import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import App from '@/App.vue';
import {
	activeTab,
	currentTrackPath,
	isFogonMode,
	isScanning,
	queueState,
	trackMap,
} from '@/composables/player/state';
import * as api from '@/composables/useApi';

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
});
