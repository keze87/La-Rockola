import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import QueueTab from '@/components/QueueTab.vue';
import TrackRow from '@/components/ui/TrackRow.vue';
import {
	currentTrackPath,
	djCarpinchoEnabled,
	djNextTrack,
	historyState,
	isPaused,
	pauseAfterPath,
	queueState,
	trackMap,
} from '@/composables/player/state';

describe('QueueTab.vue', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		currentTrackPath.value = null;
		djCarpinchoEnabled.value = false;
		djNextTrack.value = null;
		historyState.value = [];
		isPaused.value = false;
		pauseAfterPath.value = null;
		queueState.value = [];
		trackMap.value = {
			'/music/current.mp3': {
				path: '/music/current.mp3',
				display_title: 'Tema Actual',
				display_artist: 'Artista 1',
			},
			'/music/h1.mp3': {
				path: '/music/h1.mp3',
				display_title: 'Historial 1',
				display_artist: 'Artista 2',
			},
			'/music/q1.mp3': {
				path: '/music/q1.mp3',
				display_title: 'En Fila 1',
				display_artist: 'Artista 3',
			},
		};
	});

	it('renders empty queue state message when no tracks are queued or playing', () => {
		const wrapper = mount(QueueTab);
		expect(wrapper.text()).toContain('El Carpincho está esperando el mate...');
		expect(wrapper.text()).toContain('Agregá música para que empiece a cantar.');
	});

	it('renders history, current track, and queue list', () => {
		currentTrackPath.value = '/music/current.mp3';
		historyState.value = ['/music/h1.mp3'];
		queueState.value = ['/music/q1.mp3'];

		const wrapper = mount(QueueTab);

		expect(wrapper.text()).toContain('Historial');
		expect(wrapper.text()).toContain('Historial 1');
		expect(wrapper.text()).toContain('Tema Actual');
		expect(wrapper.text()).toContain('En Fila 1');
	});

	it('submits a new URL using the input and add button', async () => {
		const wrapper = mount(QueueTab);
		const input = wrapper.find('input[type="text"]');
		const addBtn = wrapper.findAll('button').find((b) => b.text().includes('add'));

		await input.setValue('https://www.youtube.com/watch?v=dQw4w9WgXcQ');
		expect(addBtn).toBeDefined();
		await addBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'add_url',
					path: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
				}),
			})
		);
	});

	it('toggles pause after current track when timer button is clicked', async () => {
		currentTrackPath.value = '/music/current.mp3';
		const wrapper = mount(QueueTab);

		const timerBtn = wrapper.find('#current-queue-row button');
		expect(timerBtn.exists()).toBe(true);

		// 1. Enable pause after
		await timerBtn.trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({
					cmd: 'pause_after',
					path: '/music/current.mp3',
				}),
			})
		);

		// 2. Disable pause after
		pauseAfterPath.value = '/music/current.mp3';
		await timerBtn.trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({
					cmd: 'pause_after',
					path: '',
				}),
			})
		);
	});

	it('handles swipe gestures (left swipe deletes, right swipe moves to first)', async () => {
		queueState.value = ['/music/q1.mp3', '/music/current.mp3'];
		const wrapper = mount(QueueTab);

		const rows = wrapper.findAll('.swipe-row');
		expect(rows.length).toBeGreaterThan(0);

		// 1. Left swipe on item 0 (diff = 200 - 50 = 150 > 80) -> Delete
		await rows[0].trigger('touchstart', {
			touches: [{ screenX: 200, screenY: 100 }],
			changedTouches: [{ screenX: 200, screenY: 100 }],
		});
		await rows[0].trigger('touchmove', {
			touches: [{ screenX: 150, screenY: 100 }],
		});
		await rows[0].trigger('touchend', {
			changedTouches: [{ screenX: 50, screenY: 100 }],
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'remove_queue_item', index: 0 }) })
		);

		// 2. Right swipe on item 1 (diff = 50 - 200 = -150 < -80) -> Move to first
		fetchMock.mockClear();
		await rows[1].trigger('touchstart', {
			touches: [{ screenX: 50, screenY: 100 }],
			changedTouches: [{ screenX: 50, screenY: 100 }],
		});
		await rows[1].trigger('touchend', {
			changedTouches: [{ screenX: 200, screenY: 100 }],
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_queue_item', index: 1, new_index: 0 }) })
		);
	});

	it('handles HTML5 drag and drop reordering', async () => {
		queueState.value = ['/music/q1.mp3', '/music/current.mp3'];

		const wrapper = mount(QueueTab);
		const rows = wrapper.findAll('.swipe-row');

		// Drag start on row 0
		await rows[0].trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drag over row 1
		await rows[1].trigger('dragover', {
			clientY: 100,
		});

		// Drag leave
		await rows[1].trigger('dragleave');

		// Drop on row 1
		await rows[1].trigger('drop', {
			clientY: 100,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_queue_item', index: 0, new_index: 1 }) })
		);

		// Drag end cleans up
		await rows[0].trigger('dragend');
	});

	it('jumps to history item or queue item when rows are clicked', async () => {
		currentTrackPath.value = '/music/current.mp3';
		historyState.value = ['/music/h1.mp3'];
		queueState.value = ['/music/q1.mp3'];

		const wrapper = mount(QueueTab);
		const trackRows = wrapper.findAllComponents(TrackRow);

		// 1. History row (first TrackRow)
		await trackRows[0].trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'jump', type: 'history', index: 0 }) })
		);

		// 2. Current track row (second TrackRow)
		await trackRows[1].trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'pause' }) })
		);

		// 3. Queue row (third TrackRow)
		await trackRows[2].trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'jump', type: 'queue', index: 0 }) })
		);
	});

	it('renders DJ Carpincho placeholder when enabled', () => {
		djCarpinchoEnabled.value = true;
		djNextTrack.value = {
			path: '/music/dj.mp3',
			display_title: 'Selección del DJ',
			display_artist: 'DJ Carpincho',
			title: 'Selección del DJ',
			artist: 'DJ Carpincho',
		};

		const wrapper = mount(QueueTab);
		expect(wrapper.text()).toContain('DJ Carpincho eligió: Selección del DJ');
	});
});
