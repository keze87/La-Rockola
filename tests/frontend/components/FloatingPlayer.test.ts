import { describe, it, expect, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import FloatingPlayer from '@/components/FloatingPlayer.vue';
import { currentTrackPath, isPaused, queueState, trackMap, djCarpinchoEnabled } from '@/composables/player/state';

describe('FloatingPlayer.vue', () => {
	beforeEach(() => {
		currentTrackPath.value = null;
		isPaused.value = false;
		queueState.value = [];
		trackMap.value = {};
		djCarpinchoEnabled.value = false;
	});

	it('renders queue prompt when stopped and queue is empty', () => {
		const wrapper = mount(FloatingPlayer);
		expect(wrapper.text()).toContain("Agregá algo pa' escuchar");
	});

	it('renders up-next track info when queue has items', () => {
		const nextPath = '/music/next_song.flac';
		trackMap.value[nextPath] = {
			path: nextPath,
			display_title: 'Hablando a tu corazón',
			display_artist: 'García / Aznar',
		};
		queueState.value = [nextPath];

		const wrapper = mount(FloatingPlayer);
		expect(wrapper.text()).toContain('Hablando a tu corazón');
		expect(wrapper.text()).toContain('García / Aznar');
	});

	it('handles timer, play/pause, and skip buttons', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		currentTrackPath.value = '/music/song.mp3';
		isPaused.value = false;
		const wrapper = mount(FloatingPlayer);

		// Click timer button
		const timerBtn = wrapper.find('button[title="Frenar tras este tema"]');
		expect(timerBtn.exists()).toBe(true);
		await timerBtn.trigger('click');

		// Click play/pause button
		const pauseBtn = wrapper.findAll('button').find((b) => b.text().includes('pause'));
		expect(pauseBtn).toBeDefined();
		await pauseBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'pause' }),
			})
		);

		// Click skip button
		const skipBtn = wrapper.findAll('button').find((b) => b.text().includes('skip_next'));
		expect(skipBtn).toBeDefined();
		await skipBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'skip' }),
			})
		);
	});
});
