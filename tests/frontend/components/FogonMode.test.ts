import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import FogonMode from '@/components/FogonMode.vue';
import {
	currentTrackPath,
	djCarpinchoEnabled,
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
		djCarpinchoEnabled.value = false;
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
		djCarpinchoEnabled.value = true;
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
});
