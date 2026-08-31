import { describe, it, expect, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import TrackRow from '@/components/ui/TrackRow.vue';
import { currentTrackPath, trackMap } from '@/composables/player/state';

describe('TrackRow.vue', () => {
	beforeEach(() => {
		currentTrackPath.value = null;
		trackMap.value = {};
	});

	it('renders track title and artist', () => {
		const track = {
			path: '/music/spinetta.flac',
			display_title: 'Seguir viviendo sin tu amor',
			display_artist: 'Luis Alberto Spinetta',
			duration_str: '2:40',
		};
		trackMap.value['/music/spinetta.flac'] = track;

		const wrapper = mount(TrackRow, {
			props: {
				track,
			},
		});

		expect(wrapper.text()).toContain('Seguir viviendo sin tu amor');
		expect(wrapper.text()).toContain('Luis Alberto Spinetta');
		expect(wrapper.text()).toContain('2:40');
	});

	it('emits click event when clicked', async () => {
		const track = {
			path: '/music/song.mp3',
			display_title: 'Canción',
			display_artist: 'Artista',
		};
		const wrapper = mount(TrackRow, {
			props: { track },
		});

		await wrapper.trigger('click');
		expect(wrapper.emitted('click')).toBeTruthy();
		expect(wrapper.emitted('click')![0]).toEqual([track]);
	});
});
