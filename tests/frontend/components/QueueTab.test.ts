import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import QueueTab from '@/components/QueueTab.vue';
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
import * as api from '@/composables/useApi';

describe('QueueTab.vue', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
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
				duration_str: '3:00',
			},
			'/music/q1.mp3': {
				path: '/music/q1.mp3',
				display_title: 'Primer En Fila',
				display_artist: 'Artista 2',
				duration_str: '2:45',
			},
			'/music/h1.mp3': {
				path: '/music/h1.mp3',
				display_title: 'Tema Pasado',
				display_artist: 'Artista 3',
				duration_str: '4:10',
			},
		};
	});

	it('renders empty state when queue and history are empty and no track playing', () => {
		const wrapper = mount(QueueTab);
		expect(wrapper.text()).toContain('El Carpincho está esperando el mate...');
	});

	it('renders current track, history items, and queued items', () => {
		currentTrackPath.value = '/music/current.mp3';
		historyState.value = ['/music/h1.mp3'];
		queueState.value = ['/music/q1.mp3'];

		const wrapper = mount(QueueTab);
		expect(wrapper.text()).toContain('Tema Actual');
		expect(wrapper.text()).toContain('Tema Pasado');
		expect(wrapper.text()).toContain('Primer En Fila');
	});

	it('allows adding URL via the URL input and button', async () => {
		const wrapper = mount(QueueTab);

		const input = wrapper.find('input[type="text"]');
		await input.setValue('https://youtube.com/watch?v=mock123');

		const addBtn = wrapper.find('button.bg-green-700');
		await addBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'add_url',
					path: 'https://youtube.com/watch?v=mock123',
				}),
			})
		);
	});

	it('toggles pause after current track when timer button clicked', async () => {
		currentTrackPath.value = '/music/current.mp3';
		const wrapper = mount(QueueTab);

		const timerBtn = wrapper.find('button[title="Frenar tras este tema"]');
		expect(timerBtn.exists()).toBe(true);
		await timerBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'pause_after',
					path: '/music/current.mp3',
				}),
			})
		);
	});

	it('moves queued item to first or last position using action buttons', async () => {
		queueState.value = ['/music/q1.mp3', '/music/q2.mp3'];
		trackMap.value['/music/q2.mp3'] = {
			path: '/music/q2.mp3',
			display_title: 'Segundo En Fila',
			display_artist: 'Artista 4',
		};
		const wrapper = mount(QueueTab);

		// Button "Mover al final" for index 0
		const moveBottomBtn = wrapper.find('button[title="Mover al final"]');
		expect(moveBottomBtn.exists()).toBe(true);
		await moveBottomBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					cmd: 'move_queue_item',
					index: 0,
					new_index: 1,
				}),
			})
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
