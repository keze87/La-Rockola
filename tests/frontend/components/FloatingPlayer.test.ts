import { describe, it, expect, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import FloatingPlayer from '@/components/FloatingPlayer.vue';
import { currentTrackPath, isPaused, queueState, trackMap, djCarpinchoEnabled } from '@/composables/player/state';

describe('FloatingPlayer.vue', () => {
	beforeEach(() => {
		currentTrackPath.value = null;
		isPaused.value = false;
		queueState.value = [];
		trackMap.value = {};
		djCarpinchoEnabled.value = false;
	});

	it('renders queue prompt when stopped and queue is empty', () => {
		const wrapper = mount(FloatingPlayer);
		expect(wrapper.text()).toContain("Agregá algo pa' escuchar");
	});

	it('renders up-next track info when queue has items', () => {
		const nextPath = '/music/next_song.flac';
		trackMap.value[nextPath] = {
			path: nextPath,
			display_title: 'Hablando a tu corazón',
			display_artist: 'García / Aznar',
		};
		queueState.value = [nextPath];

		const wrapper = mount(FloatingPlayer);
		expect(wrapper.text()).toContain('Hablando a tu corazón');
		expect(wrapper.text()).toContain('García / Aznar');
	});
});
