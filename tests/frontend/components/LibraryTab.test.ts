import { describe, it, expect, beforeEach, vi } from 'vitest';
import { computed, ref, type Ref } from 'vue';
import { mount } from '@vue/test-utils';
import LibraryTab from '@/components/LibraryTab.vue';
import {
	currentTrackPath,
	currentTracks,
	favorites,
	historyState,
	isPaused,
	isScanning,
	librarySearchQuery,
	queueState,
	scanStatus,
	showFavoritesOnly,
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
		historyState.value = [];
		isPaused.value = false;
		isScanning.value = false;
		showFavoritesOnly.value = false;
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: false,
			phase: 'idle',
			current: 0,
			total: 0,
			message: '',
		};
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
		expect(wrapper.text()).toContain('No hay nada por acá con ese nombre, fiera.');
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

	it('scrolls to current playing track when clicking "Ir al tema actual"', async () => {
		currentTrackPath.value = '/music/charly.mp3';
		const wrapper = mount(LibraryTab);

		const scrollBtn = wrapper.find('button[title="Ir al tema actual"]');
		expect(scrollBtn.exists()).toBe(true);
		await scrollBtn.trigger('click');
	});

	it('renders scanning banner with progress when isScanning is true', () => {
		isScanning.value = true;
		scanStatus.value = {
			is_scanning: true,
			phase: 'metadata',
			current: 50,
			total: 200,
			message: '',
		};
		const wrapper = mount(LibraryTab);

		expect(wrapper.text()).toContain('50 de 200 listos');
	});

	it('renders initial empty state message when isScanning is true and no tracks yet', () => {
		isScanning.value = true;
		currentTracks.value = [];
		const wrapper = mount(LibraryTab);

		expect(wrapper.text()).toContain(
			'Chusmeando la biblioteca por primera vez... Aguantá que ya asoman los temazos.'
		);
	});

	it('passes hasPlayed=true to LibraryRow when track is in historyState', () => {
		historyState.value = ['/music/spinetta.mp3'];
		const wrapper = mount(LibraryTab);

		const rows = wrapper.findAllComponents({ name: 'LibraryRow' });
		const spinettaRow = rows.find((r) => r.props('track').path === '/music/spinetta.mp3');
		const charlyRow = rows.find((r) => r.props('track').path === '/music/charly.mp3');

		expect(spinettaRow?.props('hasPlayed')).toBe(true);
		expect(charlyRow?.props('hasPlayed')).toBe(false);
	});

	it('triggers lightweight library refresh (/library) on pull-to-refresh when scrolled at top, and ignores when scrolled down or scanning', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: mockTracks }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const wrapper = mount(LibraryTab);
		const section = wrapper.find('section.tab-content');
		expect(section.exists()).toBe(true);

		// Con scrollTop > 0 no debe disparar pull-to-refresh
		Object.defineProperty(section.element, 'scrollTop', { configurable: true, writable: true, value: 120 });
		await section.trigger('touchstart', { touches: [{ clientX: 150, clientY: 100 }] });
		await section.trigger('touchmove', { touches: [{ clientX: 150, clientY: 240 }] });
		await section.trigger('touchend');
		expect(fetchMock).not.toHaveBeenCalledWith('/scan');

		// En la cima pero con escaneo en curso tampoco dispara
		Object.defineProperty(section.element, 'scrollTop', { configurable: true, writable: true, value: 0 });
		isScanning.value = true;
		await section.trigger('touchstart', { touches: [{ clientX: 150, clientY: 100 }] });
		await section.trigger('touchmove', { touches: [{ clientX: 150, clientY: 240 }] });
		await section.trigger('touchend');
		expect(fetchMock).not.toHaveBeenCalledWith('/scan');

		// En la cima y sin escaneo activo, pull >= umbral dispara refresh liviano (/library, NO /scan)
		isScanning.value = false;
		await section.trigger('touchstart', { touches: [{ clientX: 150, clientY: 100 }] });
		await section.trigger('touchmove', { touches: [{ clientX: 152, clientY: 240 }] });
		expect(wrapper.find('.library-pull-indicator').exists()).toBe(true);
		await section.trigger('touchend');

		expect(fetchMock).toHaveBeenCalledWith('/library');
		expect(fetchMock).not.toHaveBeenCalledWith('/scan');

		// Segundo pull inmediato dentro del cooldown no vuelve a llamar /library
		fetchMock.mockClear();
		await section.trigger('touchstart', { touches: [{ clientX: 150, clientY: 100 }] });
		await section.trigger('touchmove', { touches: [{ clientX: 152, clientY: 240 }] });
		await section.trigger('touchend');
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('shows actionable folder error/unconfigured state on Android Host and semantic clear-search button', async () => {
		const androidHost = await import('@/composables/useAndroidHost');
		const store = await import('@/stores/useServerConnectionStore');
		const isNativeSpy = vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const pickSpy = vi.spyOn(androidHost, 'pickAndApplyMusicFolder').mockResolvedValue('content://tree/abc');

		store.resetServerConnectionStore();
		store.setHostMode();
		store.libraryFolderStatus.value = 'permission_denied';
		store.libraryFolderError.value = 'El permiso sobre la carpeta fue revocado';
		currentTracks.value = [];
		isScanning.value = false;

		try {
			const wrapper = mount(LibraryTab);
			expect(wrapper.find('button[aria-label="Limpiar búsqueda"]').exists()).toBe(true);
			expect(wrapper.text()).toContain('El permiso sobre la carpeta fue revocado');
			expect(wrapper.text()).not.toContain('No hay nada por acá con ese nombre, fiera.');

			const pickBtn = wrapper.findAll('button').find((b) => b.text().includes('Elegir carpeta'));
			expect(pickBtn).toBeDefined();
			await pickBtn!.trigger('click');
			expect(pickSpy).toHaveBeenCalledTimes(1);
		} finally {
			store.resetServerConnectionStore();
			isNativeSpy.mockRestore();
			pickSpy.mockRestore();
		}
	});
});
