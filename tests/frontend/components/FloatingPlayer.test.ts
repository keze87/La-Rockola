import { describe, it, expect, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import FloatingPlayer from '@/components/FloatingPlayer.vue';
import {
	activeTab,
	currentTrackPath,
	isFogonMode,
	isPaused,
	queueState,
	trackMap,
	djBaraEnabled,
} from '@/composables/player/state';

describe('FloatingPlayer.vue', () => {
	beforeEach(() => {
		activeTab.value = 'library';
		currentTrackPath.value = null;
		isFogonMode.value = false;
		isPaused.value = false;
		queueState.value = [];
		trackMap.value = {};
		djBaraEnabled.value = false;
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

	it('supports horizontal swipe left/right to skip/prev and swipe up to open FogonMode', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		const wrapper = mount(FloatingPlayer);
		const playerEl = wrapper.find('.floating-player');
		expect(playerEl.exists()).toBe(true);

		// Swipe izquierda -> skip
		await playerEl.trigger('touchstart', { touches: [{ clientX: 220, clientY: 100 }] });
		await playerEl.trigger('touchmove', { touches: [{ clientX: 130, clientY: 104 }] });
		await playerEl.trigger('touchend');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'skip' }),
			})
		);

		fetchMock.mockClear();

		// Swipe derecha -> prev
		await playerEl.trigger('touchstart', { touches: [{ clientX: 100, clientY: 100 }] });
		await playerEl.trigger('touchmove', { touches: [{ clientX: 190, clientY: 103 }] });
		await playerEl.trigger('touchend');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'prev' }),
			})
		);

		fetchMock.mockClear();

		// Swipe arriba -> abre Modo Fogón sin ir a la cola
		await playerEl.trigger('touchstart', { touches: [{ clientX: 150, clientY: 200 }] });
		await playerEl.trigger('touchmove', { touches: [{ clientX: 152, clientY: 120 }] });
		await playerEl.trigger('touchend');
		expect(isFogonMode.value).toBe(true);
		expect(activeTab.value).toBe('library');

		// Movimiento corto no dispara nada
		isFogonMode.value = false;
		await playerEl.trigger('touchstart', { touches: [{ clientX: 150, clientY: 150 }] });
		await playerEl.trigger('touchmove', { touches: [{ clientX: 130, clientY: 145 }] });
		await playerEl.trigger('touchend');
		expect(fetchMock).not.toHaveBeenCalled();
		expect(isFogonMode.value).toBe(false);
	});

	it('exposes accessible button roles, aria-labels, and decorative icons marked aria-hidden', () => {
		currentTrackPath.value = '/music/song.mp3';
		isPaused.value = false;
		const wrapper = mount(FloatingPlayer);

		expect(wrapper.find('button[aria-label="Abrir fila de reproducción"]').exists()).toBe(true);
		expect(wrapper.find('button[aria-label="Frenar tras este tema"]').exists()).toBe(true);
		expect(wrapper.find('button[aria-label="Pausar"]').exists()).toBe(true);
		expect(wrapper.find('button[aria-label="Siguiente tema"]').exists()).toBe(true);
		for (const icon of wrapper.findAll('i.material-icons')) {
			expect(icon.attributes('aria-hidden')).toBe('true');
		}
	});
});
