import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import FavoritableCover from '@/components/ui/FavoritableCover.vue';
import { favorites, trackMap } from '@/composables/player/state';

describe('FavoritableCover.vue', () => {
	const mockTrack = {
		path: '/music/fav_song.mp3',
		display_title: 'Tema Favorito',
		display_artist: 'Artista Genial',
	};
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);
		global.fetch = fetchMock;

		favorites.value = [];
		trackMap.value = { [mockTrack.path]: mockTrack };
	});

	it('renders favorite_border when not favorited', () => {
		const wrapper = mount(FavoritableCover, {
			props: {
				track: mockTrack,
			},
		});

		expect(wrapper.text()).toContain('favorite_border');
		expect(wrapper.find('button').attributes('aria-label')).toBe('Agregar a favoritos');
	});

	it('renders filled favorite icon when favorited', () => {
		favorites.value = [mockTrack.path];
		const wrapper = mount(FavoritableCover, {
			props: {
				track: mockTrack,
			},
		});

		expect(wrapper.text()).toContain('favorite');
		expect(wrapper.find('button').attributes('aria-label')).toBe('Quitar de favoritos');
	});

	it('toggles favorite status when button is clicked', async () => {
		const wrapper = mount(FavoritableCover, {
			props: {
				track: mockTrack,
			},
		});

		const btn = wrapper.find('button');
		await btn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'toggle_favorite', path: mockTrack.path }),
			})
		);
	});

	it('applies custom buttonPosition when provided and defaults to -right-2 -bottom-2', () => {
		const defaultWrapper = mount(FavoritableCover, {
			props: { track: mockTrack },
		});
		expect(defaultWrapper.find('button').classes()).toContain('-right-2');
		expect(defaultWrapper.find('button').classes()).toContain('-bottom-2');

		const customWrapper = mount(FavoritableCover, {
			props: {
				track: mockTrack,
				buttonPosition: 'right-3 bottom-3 md:right-4 md:bottom-4',
			},
		});
		expect(customWrapper.find('button').classes()).toContain('right-3');
		expect(customWrapper.find('button').classes()).toContain('bottom-3');
	});
});
