import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ContextMenu from '@/components/ContextMenu.vue';
import { useContextMenu } from '@/composables/useContextMenu';
import {
	currentTrackPath,
	favorites,
	historyState,
	librarySearchQuery,
	pauseAfterPath,
	queueState,
} from '@/composables/player/state';

describe('ContextMenu.vue', () => {
	const { ctxMenu, closeCtxMenu } = useContextMenu();
	const sampleTrack = {
		path: '/music/spinetta.flac',
		display_title: 'Bajan',
		display_artist: 'Pescado Rabioso',
		title: 'Bajan',
		artist: 'Pescado Rabioso',
	};
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);
		global.fetch = fetchMock;

		closeCtxMenu();
		currentTrackPath.value = null;
		favorites.value = [];
		historyState.value = [];
		queueState.value = [];
		pauseAfterPath.value = null;
		librarySearchQuery.value = '';
	});

	it('renders nothing when ctxMenu is not visible', () => {
		const wrapper = mount(ContextMenu);
		expect(wrapper.find('.ctx-menu').exists()).toBe(false);
	});

	it('triggers play now from library source', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;

		const wrapper = mount(ContextMenu);
		const playNowBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Mandale play de una'));
		expect(playNowBtn).toBeDefined();
		await playNowBtn!.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'play', path: sampleTrack.path }) })
		);
		expect(ctxMenu.visible).toBe(false);
	});

	it('triggers play next from library source', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;
		queueState.value = ['/music/other.mp3', sampleTrack.path];

		const wrapper = mount(ContextMenu);
		const playNextBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Que suene de próximo'));
		expect(playNextBtn).toBeDefined();
		await playNextBtn!.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_queue', path: sampleTrack.path }) })
		);
		expect(ctxMenu.visible).toBe(false);
	});

	it('triggers add to queue from library source', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;
		queueState.value = [];

		const wrapper = mount(ContextMenu);
		const addToQueueBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Al fondo de la fila'));
		expect(addToQueueBtn).toBeDefined();
		await addToQueueBtn!.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_queue', path: sampleTrack.path }) })
		);
	});

	it('toggles favorites from context menu', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;
		favorites.value = [sampleTrack.path];

		const wrapper = mount(ContextMenu);
		expect(wrapper.text()).toContain('Sacar de favoritos');
		const toggleFavBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Sacar de favoritos'));
		await toggleFavBtn!.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_favorite', path: sampleTrack.path }) })
		);
	});

	it('filters library by artist from context menu', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;

		const wrapper = mount(ContextMenu);
		const filterArtistBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Chusmear más del artista'));
		expect(filterArtistBtn).toBeDefined();
		await filterArtistBtn!.trigger('click');
		await flushPromises();

		expect(librarySearchQuery.value).toBe('Pescado Rabioso');
	});

	it('sets pause after track from context menu', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;
		queueState.value = [sampleTrack.path];
		pauseAfterPath.value = null;

		const wrapper = mount(ContextMenu);
		const pauseAfterBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Frenar la chata tras este tema'));
		expect(pauseAfterBtn).toBeDefined();
		await pauseAfterBtn!.trigger('click');
		await flushPromises();

		expect(pauseAfterPath.value).toBe(sampleTrack.path);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'pause_after', path: sampleTrack.path }) })
		);
	});

	it('cancels pause after track from context menu', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;
		pauseAfterPath.value = sampleTrack.path;

		const wrapper = mount(ContextMenu);
		const pauseAfterBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Frenar la chata tras este tema'));
		expect(pauseAfterBtn).toBeDefined();
		await pauseAfterBtn!.trigger('click');
		await flushPromises();

		expect(pauseAfterPath.value).toBeNull();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'pause_after', path: '' }) })
		);
	});

	it('renders queue actions and handles moving / removing', async () => {
		// 1. Move to next
		ctxMenu.visible = true;
		ctxMenu.source = 'queue';
		ctxMenu.track = sampleTrack;
		ctxMenu.index = 2;

		const wrapper = mount(ContextMenu);
		const playNextQBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Subir a próximo'));
		await playNextQBtn!.trigger('click');
		await flushPromises();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_queue_item', index: 2, new_index: 0 }) })
		);

		// 2. Remove
		ctxMenu.visible = true;
		ctxMenu.source = 'queue';
		ctxMenu.track = sampleTrack;
		ctxMenu.index = 1;
		const wrapper2 = mount(ContextMenu);
		const deleteBtn = wrapper2.find('.delete-item');
		await deleteBtn.trigger('click');
		await flushPromises();
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'remove_queue_item', index: 1 }) })
		);
	});

	it('renders history actions and handles removing from history', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'history';
		ctxMenu.track = sampleTrack;
		ctxMenu.index = 0;
		historyState.value = [sampleTrack.path];

		const wrapper = mount(ContextMenu);
		const deleteHistBtn = wrapper.find('.delete-item');
		await deleteHistBtn.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'remove_history_item', index: 0 }) })
		);
	});

	it('navigates with keyboard (ArrowDown, ArrowUp, Tab, Escape)', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;

		const wrapper = mount(ContextMenu, { attachTo: document.body });
		const menu = wrapper.find('.ctx-menu');
		expect(menu.exists()).toBe(true);

		// Keyboard down & up
		await menu.trigger('keydown', { key: 'ArrowDown' });
		expect(wrapper.find('.ctx-menu.kbd-nav').exists()).toBe(true);

		await menu.trigger('keydown', { key: 'ArrowUp' });

		// Tab & Shift+Tab
		await menu.trigger('keydown', { key: 'Tab' });
		await menu.trigger('keydown', { key: 'Tab', shiftKey: true });

		// Pointerdown resets kbd-nav
		await menu.trigger('pointerdown');
		expect(wrapper.find('.ctx-menu.kbd-nav').exists()).toBe(false);

		// Escape closes menu
		await menu.trigger('keydown', { key: 'Escape' });
		expect(ctxMenu.visible).toBe(false);
		wrapper.unmount();
	});

	it('closes context menu when clicking outside backdrop', async () => {
		ctxMenu.visible = true;
		ctxMenu.track = sampleTrack;

		const wrapper = mount(ContextMenu);
		const backdrop = wrapper.find('.fixed.inset-0');
		await backdrop.trigger('click');

		expect(ctxMenu.visible).toBe(false);
	});
});
