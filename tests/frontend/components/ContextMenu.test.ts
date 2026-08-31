import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ContextMenu from '@/components/ContextMenu.vue';
import { useContextMenu } from '@/composables/useContextMenu';
import { currentTrackPath, favorites, historyState, queueState } from '@/composables/player/state';

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
	});

	it('renders nothing when ctxMenu is not visible', () => {
		const wrapper = mount(ContextMenu);
		expect(wrapper.find('.ctx-menu').exists()).toBe(false);
	});

	it('renders library actions when source is library', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'library';
		ctxMenu.track = sampleTrack;
		ctxMenu.x = 100;
		ctxMenu.y = 200;

		const wrapper = mount(ContextMenu);
		expect(wrapper.find('.ctx-menu').exists()).toBe(true);
		expect(wrapper.text()).toContain('Bajan');
		expect(wrapper.text()).toContain('Que suene de próximo');
		expect(wrapper.text()).toContain('Mandale play de una');
		expect(wrapper.text()).toContain('Al fondo de la fila');
		expect(wrapper.text()).toContain('A los favoritos');
		expect(wrapper.text()).toContain('Chusmear más del artista');
	});

	it('renders queue actions and handles removing from queue', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'queue';
		ctxMenu.track = sampleTrack;
		ctxMenu.index = 0;

		const wrapper = mount(ContextMenu);
		expect(wrapper.text()).toContain('Subir a próximo');
		expect(wrapper.text()).toContain('Pegarle un voleo');

		const deleteBtn = wrapper.find('.delete-item');
		await deleteBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'remove_queue_item',
					index: 0,
				}),
			})
		);
		expect(ctxMenu.visible).toBe(false);
	});

	it('renders history actions and handles adding back to queue', async () => {
		ctxMenu.visible = true;
		ctxMenu.source = 'history';
		ctxMenu.track = sampleTrack;
		ctxMenu.index = 1;
		historyState.value = ['/music/prev.mp3', sampleTrack.path];

		const wrapper = mount(ContextMenu);
		expect(wrapper.text()).toContain('Agregar a la fila');
		expect(wrapper.text()).toContain('Borrar del historial');

		const addAgainBtn = wrapper.findAll('.ctx-menu-item').find((b) => b.text().includes('Agregar a la fila'));
		expect(addAgainBtn).toBeDefined();
		await addAgainBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'toggle_queue',
					path: sampleTrack.path,
				}),
			})
		);
		expect(ctxMenu.visible).toBe(false);
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
