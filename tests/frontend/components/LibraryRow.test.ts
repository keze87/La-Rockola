import { describe, it, expect, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import LibraryRow from '@/components/ui/LibraryRow.vue';
import { currentTrackPath, trackMap, favorites } from '@/composables/player/state';

describe('LibraryRow.vue', () => {
	const mockTrack = {
		path: '/music/tango.flac',
		display_title: 'Mi Buenos Aires Querido',
		display_artist: 'Carlos Gardel',
		title: 'Mi Buenos Aires Querido',
		artist: 'Carlos Gardel',
		duration_str: '2:35',
	};

	beforeEach(() => {
		currentTrackPath.value = null;
		trackMap.value = { [mockTrack.path]: mockTrack };
		favorites.value = [];
	});

	it('renders track title, artist, and duration', () => {
		const wrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: false,
				isPaused: false,
				queuePosition: -1,
			},
		});

		expect(wrapper.text()).toContain('Mi Buenos Aires Querido');
		expect(wrapper.text()).toContain('Carlos Gardel');
		expect(wrapper.text()).toContain('2:35');
	});

	it('emits click event with track data when clicked', async () => {
		const wrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: false,
				isPaused: false,
				queuePosition: -1,
			},
		});

		await wrapper.trigger('click');
		expect(wrapper.emitted('click')).toBeTruthy();
		expect(wrapper.emitted('click')![0]).toEqual([mockTrack]);
	});

	it('displays equalizer indicator when isCurrent is true', () => {
		const wrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: true,
				isPaused: false,
				queuePosition: -1,
			},
		});

		expect(wrapper.find('.equalizer').exists()).toBe(true);
		expect(wrapper.find('.equalizer.paused').exists()).toBe(false);
	});

	it('displays paused equalizer indicator when isPaused is true', () => {
		const wrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: true,
				isPaused: true,
				queuePosition: -1,
			},
		});

		expect(wrapper.find('.equalizer.paused').exists()).toBe(true);
	});

	it('displays queue position overlay when queued', () => {
		const wrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: false,
				isPaused: false,
				queuePosition: 2,
			},
		});

		expect(wrapper.text()).toContain('3'); // 0-indexed position 2 renders '3'
	});

	it('triggers toggleFavorite when clicking on equalizer or queue position overlay', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const currentWrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: true,
				isPaused: false,
				queuePosition: -1,
				contextSource: 'custom_source',
				index: 5,
			},
		});

		const eqContainer = currentWrapper.find('.bg-carpincho-panel.absolute');
		expect(eqContainer.exists()).toBe(true);
		await eqContainer.trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'toggle_favorite', path: mockTrack.path }),
			})
		);

		fetchMock.mockClear();
		const queuedWrapper = mount(LibraryRow, {
			props: {
				track: mockTrack,
				isCurrent: false,
				isPaused: false,
				queuePosition: 0,
			},
		});

		const qBadge = queuedWrapper.find('.bg-carpincho-panel.text-carpincho-warning');
		expect(qBadge.exists()).toBe(true);
		await qBadge.trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'toggle_favorite', path: mockTrack.path }),
			})
		);
	});
});
