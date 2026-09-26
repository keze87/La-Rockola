import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
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

	it('handles HTML5 drag and drop reordering within queue', async () => {
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
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 1 }) })
		);

		// Drag end cleans up
		await rows[0].trigger('dragend');
	});

	it('handles drag and drop to order history', async () => {
		historyState.value = ['/music/h1.mp3', '/music/h2.mp3', '/music/h3.mp3'];

		const wrapper = mount(QueueTab);
		const historyRows = wrapper.findAll('[data-history-path]');
		expect(historyRows.length).toBe(3);

		// Drag start on history row 0
		await historyRows[0].trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drop on history row 1 (clientY: 100 -> dropIndex 1)
		await historyRows[1].trigger('drop', {
			clientY: 100,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 1 }) })
		);
	});

	it('handles dragging from history to queue to play again a song', async () => {
		historyState.value = ['/music/h1.mp3'];
		queueState.value = ['/music/q1.mp3'];

		const wrapper = mount(QueueTab);
		const historyRow = wrapper.find('[data-history-path="/music/h1.mp3"]');
		const queueRow = wrapper.find('.swipe-row');

		await historyRow.trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		await queueRow.trigger('drop', {
			clientY: 100,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 1 }),
			})
		);
	});

	it('handles moving current song below to reorder it in queue', async () => {
		currentTrackPath.value = '/music/current.mp3';
		queueState.value = ['/music/q1.mp3', '/music/q2.mp3'];

		const wrapper = mount(QueueTab);
		const currentRow = wrapper.find('#current-queue-row');
		const queueRows = wrapper.findAll('.swipe-row');

		// Drag current song (playlist index 0)
		await currentRow.trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drop below queue row 0 (playlist index 1, clientY: 100 -> dropIndex 1)
		await queueRows[0].trigger('drop', {
			clientY: 100,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 1 }),
			})
		);
	});

	it('handles moving current song up to reorder it above history tracks', async () => {
		historyState.value = ['/music/h1.mp3', '/music/h2.mp3'];
		currentTrackPath.value = '/music/current.mp3';
		queueState.value = ['/music/q1.mp3'];

		// unifiedQueue: h1 (0), h2 (1), current (2), q1 (3)
		const wrapper = mount(QueueTab);
		const currentRow = wrapper.find('#current-queue-row');
		const historyRows = wrapper.findAll('[data-history-path]');

		// Drag current song (idx 2)
		await currentRow.trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drop onto h1 (idx 0, clientY: -10 -> drop before h1 at idx 0)
		await historyRows[0].trigger('drop', {
			clientY: -10,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 2, new_index: 0 }),
			})
		);
	});

	it('handles moving an already played track to become the next track to play', async () => {
		historyState.value = ['/music/h1.mp3', '/music/h2.mp3'];
		currentTrackPath.value = '/music/current.mp3';
		queueState.value = ['/music/q1.mp3', '/music/q2.mp3'];

		// unifiedQueue: h1 (0), h2 (1), current (2), q1 (3), q2 (4)
		const wrapper = mount(QueueTab);
		const historyRows = wrapper.findAll('[data-history-path]');
		const currentRow = wrapper.find('#current-queue-row');

		// Drag h1 (idx 0)
		await historyRows[0].trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drop on lower half of current track (toIndex: 2, clientY: 100) -> inserts right after current (new_index: 2)
		await currentRow.trigger('drop', {
			clientY: 100,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 2 }),
			})
		);
	});

	it('handles moving the next track before the currently playing track', async () => {
		historyState.value = ['/music/h1.mp3', '/music/h2.mp3'];
		currentTrackPath.value = '/music/current.mp3';
		queueState.value = ['/music/q1.mp3', '/music/q2.mp3'];

		// unifiedQueue: h1 (0), h2 (1), current (2), q1 (3), q2 (4)
		const wrapper = mount(QueueTab);
		const currentRow = wrapper.find('#current-queue-row');
		const queueRows = wrapper.findAll('.swipe-row');

		// Drag next track q1 (idx 3)
		await queueRows[0].trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drop on upper half of current track (toIndex: 2, clientY: -10) -> inserts before current (new_index: 2)
		await currentRow.trigger('drop', {
			clientY: -10,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 3, new_index: 2 }),
			})
		);
	});

	it('handles moving a history track to the next position when currently playing the last track', async () => {
		historyState.value = ['/music/h1.mp3', '/music/h2.mp3'];
		currentTrackPath.value = '/music/current.mp3';
		queueState.value = [];

		// unifiedQueue: h1 (0), h2 (1), current (2) (last track!)
		const wrapper = mount(QueueTab);
		const historyRows = wrapper.findAll('[data-history-path]');
		const currentRow = wrapper.find('#current-queue-row');

		// Drag h1 (idx 0)
		await historyRows[0].trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		// Drop on lower half of current (toIndex: 2, clientY: 100) -> inserts right after current (new_index: 2)
		await currentRow.trigger('drop', {
			clientY: 100,
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 2 }),
			})
		);
	});

	it('handles dragging current song or history track to bottom drop zone', async () => {
		currentTrackPath.value = '/music/current.mp3';
		historyState.value = ['/music/h1.mp3'];
		queueState.value = ['/music/q1.mp3'];

		const wrapper = mount(QueueTab);
		const bottomZone = wrapper.find('#playlist-bottom-drop-zone');
		expect(bottomZone.exists()).toBe(true);

		// unifiedQueue: h1 (0), current (1), q1 (2)
		// 1. Drag current song to bottom drop zone -> moves to last index (2)
		const currentRow = wrapper.find('#current-queue-row');
		await currentRow.trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		await bottomZone.trigger('dragover');
		await bottomZone.trigger('drop');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 1, new_index: 2 }),
			})
		);

		// 2. Drag history song to bottom drop zone -> moves to last index (2)
		fetchMock.mockClear();
		const historyRow = wrapper.find('[data-history-path="/music/h1.mp3"]');
		await historyRow.trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});

		await bottomZone.trigger('drop');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 2 }),
			})
		);
	});

	it('handles dropping onto current track without replacing playback and verifies track status', async () => {
		currentTrackPath.value = '/music/current.mp3';
		historyState.value = ['/music/h1.mp3'];
		queueState.value = ['/music/q1.mp3'];

		const wrapper = mount(QueueTab);
		const currentRow = wrapper.find('#current-queue-row');
		const historyRow = wrapper.find('[data-history-path="/music/h1.mp3"]');

		// Check unified queue attributes
		expect(wrapper.findAll('[data-track-status="history"]').length).toBe(1);
		expect(wrapper.findAll('[data-track-status="current"]').length).toBe(1);
		expect(wrapper.findAll('[data-track-status="queue"]').length).toBe(1);

		// Drag from history to current -> drops next to current track without replacing playback
		await historyRow.trigger('dragstart', {
			dataTransfer: { effectAllowed: 'none' },
		});
		await currentRow.trigger('dragover', { clientY: 100 });
		await currentRow.trigger('drop', { clientY: 100 });

		// Verify move_in_playlist was called, and play was NOT called!
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: JSON.stringify({ cmd: 'move_in_playlist', index: 0, new_index: 1 }),
			})
		);
		expect(fetchMock).not.toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				body: expect.stringContaining('"cmd":"play"'),
			})
		);
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

	it('handles move to first, move to last, and delete queue item buttons', async () => {
		queueState.value = ['/music/q1.mp3', '/music/q2.mp3', '/music/q3.mp3'];
		trackMap.value['/music/q2.mp3'] = { path: '/music/q2.mp3', display_title: 'Q2', display_artist: 'A2' };
		trackMap.value['/music/q3.mp3'] = { path: '/music/q3.mp3', display_title: 'Q3', display_artist: 'A3' };

		const wrapper = mount(QueueTab);

		// Click "Subir a próximo" on index 1
		const moveFirstBtns = wrapper.findAll('button[title="Subir a próximo"]');
		expect(moveFirstBtns.length).toBeGreaterThan(0);
		await moveFirstBtns[1].trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_queue_item', index: 1, new_index: 0 }) })
		);

		// Click "Mover al final" on index 0
		const moveLastBtns = wrapper.findAll('button[title="Mover al final"]');
		expect(moveLastBtns.length).toBeGreaterThan(0);
		await moveLastBtns[0].trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'move_queue_item', index: 0, new_index: 2 }) })
		);

		// Click "Sacar de la fila" on index 0
		const removeBtns = wrapper.findAll('button[title="Sacar de la fila"]');
		expect(removeBtns.length).toBeGreaterThan(0);
		await removeBtns[0].trigger('click');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'remove_queue_item', index: 0 }) })
		);
	});
});
