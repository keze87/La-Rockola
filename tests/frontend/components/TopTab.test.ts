import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import TopTab from '@/components/TopTab.vue';
import { topPlayedState, trackMap } from '@/composables/player/state';
import * as api from '@/composables/useApi';

describe('TopTab.vue', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);
		global.fetch = fetchMock;

		topPlayedState.value = [];
		trackMap.value = {
			'/music/classic1.mp3': {
				path: '/music/classic1.mp3',
				display_title: 'Jijiji',
				display_artist: 'Patricio Rey',
				title: 'Jijiji',
				artist: 'Patricio Rey',
			},
			'/music/classic2.mp3': {
				path: '/music/classic2.mp3',
				display_title: 'De Música Ligera',
				display_artist: 'Soda Stereo',
				title: 'De Música Ligera',
				artist: 'Soda Stereo',
			},
		};
	});

	it('renders empty state when no tracks have been played', () => {
		const wrapper = mount(TopTab);
		expect(wrapper.text()).toContain('Todavía no sonó nada, maestro.');
	});

	it('renders ranked top played tracks with play counts', () => {
		topPlayedState.value = [
			{ path: '/music/classic1.mp3', count: 42 },
			{ path: '/music/classic2.mp3', count: 28 },
		];

		const wrapper = mount(TopTab);
		expect(wrapper.text()).toContain('#1');
		expect(wrapper.text()).toContain('Jijiji');
		expect(wrapper.text()).toContain('Patricio Rey • Sonó 42 veces');

		expect(wrapper.text()).toContain('#2');
		expect(wrapper.text()).toContain('De Música Ligera');
		expect(wrapper.text()).toContain('Soda Stereo • Sonó 28 veces');
	});

	it('toggles track queue when top played row is clicked', async () => {
		topPlayedState.value = [{ path: '/music/classic1.mp3', count: 42 }];

		const wrapper = mount(TopTab);
		const row = wrapper.find('li');
		await row.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'toggle_queue',
					path: '/music/classic1.mp3',
				}),
			})
		);
	});
});
