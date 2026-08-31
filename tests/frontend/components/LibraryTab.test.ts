import { describe, it, expect, beforeEach, vi } from 'vitest';
import { computed, ref, type Ref } from 'vue';
import { mount } from '@vue/test-utils';
import LibraryTab from '@/components/LibraryTab.vue';
import {
	currentTrackPath,
	currentTracks,
	favorites,
	isPaused,
	librarySearchQuery,
	queueState,
	trackMap,
} from '@/composables/player/state';

vi.mock('@vueuse/core', async (importOriginal) => {
	const actual = await importOriginal<typeof import('@vueuse/core')>();
	return {
		...actual,
		useVirtualList: (list: Ref<any[]>, options: any) => {
			const currentList = computed(() => list.value.map((data, index) => ({ data, index })));
			return {
				list: currentList,
				scrollTo: vi.fn(),
				containerProps: {
					ref: ref(null),
					onScroll: vi.fn(),
					style: { overflowY: 'auto' },
				},
				wrapperProps: computed(() => ({
					style: {
						width: '100%',
						height: `${list.value.length * (options?.itemHeight || 72)}px`,
					},
				})),
			};
		},
	};
});

describe('LibraryTab.vue', () => {
	const mockTracks = [
		{
			path: '/music/spinetta.mp3',
			display_title: 'Barro Tal Vez',
			display_artist: 'Luis Alberto Spinetta',
			title: 'Barro Tal Vez',
			artist: 'Luis Alberto Spinetta',
			album: 'Kamikaze',
			duration_str: '3:20',
		},
		{
			path: '/music/charly.mp3',
			display_title: 'Nos Siguen Pegando Abajo',
			display_artist: 'Charly García',
			title: 'Nos Siguen Pegando Abajo',
			artist: 'Charly García',
			album: 'Clics Modernos',
			duration_str: '3:30',
		},
		{
			path: '/music/fito.mp3',
			display_title: '11 y 6',
			display_artist: 'Fito Páez',
			title: '11 y 6',
			artist: 'Fito Páez',
			album: 'Giros',
			duration_str: '3:10',
		},
	];

	beforeEach(() => {
		Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
			configurable: true,
			value: 800,
		});
		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);

		currentTrackPath.value = null;
		currentTracks.value = [...mockTracks];
		favorites.value = [];
		isPaused.value = false;
		librarySearchQuery.value = '';
		queueState.value = [];
		trackMap.value = {
			'/music/spinetta.mp3': mockTracks[0],
			'/music/charly.mp3': mockTracks[1],
			'/music/fito.mp3': mockTracks[2],
		};
	});

	it('renders all library tracks initially', () => {
		const wrapper = mount(LibraryTab);
		expect(wrapper.text()).toContain('Barro Tal Vez');
		expect(wrapper.text()).toContain('Nos Siguen Pegando Abajo');
		expect(wrapper.text()).toContain('11 y 6');
	});

	it('filters tracks using Fuse.js search query', async () => {
		const wrapper = mount(LibraryTab);
		const input = wrapper.find('input[type="text"]');

		await input.setValue('Charly');
		expect(wrapper.text()).toContain('Nos Siguen Pegando Abajo');
		expect(wrapper.text()).not.toContain('Barro Tal Vez');
		expect(wrapper.text()).not.toContain('11 y 6');

		// Clear search via close icon
		const closeIcon = wrapper.find('.material-icons.text-carpincho-secondary');
		await closeIcon.trigger('click');
		expect(librarySearchQuery.value).toBe('');
	});

	it('filters tracks by favorites toggle button', async () => {
		favorites.value = ['/music/fito.mp3'];
		const wrapper = mount(LibraryTab);

		// Button for favorites filter
		const favButton = wrapper.find('button[title="Mostrar sólo favoritos"]');
		await favButton.trigger('click');

		expect(wrapper.text()).toContain('11 y 6');
		expect(wrapper.text()).not.toContain('Barro Tal Vez');
		expect(wrapper.text()).not.toContain('Nos Siguen Pegando Abajo');
	});

	it('shows empty state when no tracks match search', async () => {
		const wrapper = mount(LibraryTab);
		const input = wrapper.find('input[type="text"]');

		await input.setValue('NonexistentSongQueryXYZ');
		expect(wrapper.text()).toContain("No hay nada por acá con ese nombre, fiera.");
	});

	it('handles track row click by sending toggle_queue or play', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const wrapper = mount(LibraryTab);

		const firstRow = wrapper.findComponent({ name: 'LibraryRow' });
		expect(firstRow.exists()).toBe(true);

		await firstRow.trigger('click');
		expect(fetchMock).toHaveBeenCalled();
	});
});
