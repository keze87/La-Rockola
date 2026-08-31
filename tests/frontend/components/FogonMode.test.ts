import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import FogonMode from '@/components/FogonMode.vue';
import { currentTrackPath, isFogonMode, isPaused, trackMap } from '@/composables/player/state';

describe('FogonMode.vue', () => {
	beforeEach(() => {
		isFogonMode.value = true;
		currentTrackPath.value = '/music/cancion.flac';
		isPaused.value = false;
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
});
