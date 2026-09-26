import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ControlsTab from '@/components/ControlsTab.vue';
import QRCode from 'qrcode.vue';
import {
	currentTracks,
	djCarpinchoEnabled,
	djSafeModeEnabled,
	hasLibrosa,
	listenLocally,
	mpvVisible,
	serverMuted,
	serverUrl,
	volume,
} from '@/composables/player/state';

describe('ControlsTab.vue', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', data: [] }),
		} as unknown as Response);
		global.fetch = fetchMock;

		currentTracks.value = [];
		djCarpinchoEnabled.value = false;
		djSafeModeEnabled.value = false;
		hasLibrosa.value = true;
		listenLocally.value = false;
		mpvVisible.value = true;
		serverMuted.value = false;
		serverUrl.value = null;
		volume.value = 80;
	});

	it('renders volume controls, sort buttons, and toggles', () => {
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).toContain('Acomodando la gilada');
		expect(wrapper.text()).toContain('Como llegaron');
		expect(wrapper.text()).toContain('Por el que canta');
		expect(wrapper.text()).toContain('Más Manija');
		expect(wrapper.text()).toContain('Mezcladito (A lo loco)');
		expect(wrapper.text()).toContain('La Joda');
		expect(wrapper.text()).toContain('DJ Carpincho');
		expect(wrapper.text()).toContain('Escuchar acá');
	});

	it('hides "Más Manija" button when hasLibrosa is false', () => {
		hasLibrosa.value = false;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).not.toContain('Más Manija');
		expect(wrapper.text()).toContain('Como llegaron');
		expect(wrapper.text()).toContain('Por el que canta');
		expect(wrapper.text()).toContain('Mezcladito (A lo loco)');
	});

	it('toggles mute when mute icon or button is clicked', async () => {
		const wrapper = mount(ControlsTab);

		const muteIcon = wrapper.find('.material-icons.mr-3');
		await muteIcon.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_mute', state: true }),
			})
		);
	});

	it('dispatches stop command when "Cortala de una" is clicked', async () => {
		const wrapper = mount(ControlsTab);

		const stopBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Cortala de una'));
		expect(stopBtn).toBeDefined();
		await stopBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'stop' }),
			})
		);
	});

	it('toggles DJ Carpincho mode when toggle is clicked', async () => {
		const wrapper = mount(ControlsTab);

		const toggles = wrapper.findAllComponents({ name: 'ToggleRow' });
		const djToggle = toggles.find((t) => t.props('title') === 'DJ Carpincho');
		expect(djToggle).toBeDefined();

		const switchBtn = djToggle!.find('button');
		await switchBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'toggle_dj_carpincho', state: true }),
			})
		);
	});

	it('uses serverUrl for QR code when opened on localhost', () => {
		serverUrl.value = 'http://192.168.1.100:1729';
		const wrapper = mount(ControlsTab);
		const qrCode = wrapper.findComponent(QRCode);
		expect(qrCode.exists()).toBe(true);
		expect(qrCode.props('value')).toBe('http://192.168.1.100:1729');
	});

	it('triggers mute toggle from PillButton', async () => {
		serverMuted.value = false;
		const wrapper = mount(ControlsTab);

		const muteBtn = wrapper.findAllComponents({ name: 'PillButton' }).find((w) => w.text().includes('Mutear'));
		expect(muteBtn).toBeDefined();
		await muteBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'set_mute', state: true }),
			})
		);
	});

	it('triggers library rescan when clicking "Pegale otra escaneada"', async () => {
		const wrapper = mount(ControlsTab);

		const rescanBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Pegale otra escaneada'));
		expect(rescanBtn).toBeDefined();
		await rescanBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith('/scan');
	});

	it('toggles MPV visibility when clicking MPV toggle button', async () => {
		mpvVisible.value = true;
		const wrapper = mount(ControlsTab);

		const hideBtn = wrapper.findAllComponents({ name: 'PillButton' }).find((w) => w.text().includes('Ocultar MPV'));
		expect(hideBtn).toBeDefined();
		await hideBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith('/mpv/hide', expect.anything());
	});

	it('dispatches fullscreen command when clicking "Todo pantalla, ñeri"', async () => {
		const wrapper = mount(ControlsTab);

		const fsBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Todo pantalla, ñeri'));
		expect(fsBtn).toBeDefined();
		await fsBtn!.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'fullscreen' }),
			})
		);
	});

	it('triggers library sorting when clicking sort buttons', async () => {
		currentTracks.value = [
			{ path: '/a.mp3', title: 'B', artist: 'Z', bpm: 100 },
			{ path: '/b.mp3', title: 'A', artist: 'A', bpm: 140 },
		];
		const wrapper = mount(ControlsTab);

		const pills = wrapper.findAllComponents({ name: 'PillButton' });
		const byArtist = pills.find((w) => w.text().includes('Por el que canta'));
		const byTime = pills.find((w) => w.text().includes('Como llegaron'));
		const byMood = pills.find((w) => w.text().includes('Más Manija'));
		const byShuffle = pills.find((w) => w.text().includes('Mezcladito'));

		await byArtist?.trigger('click');
		expect(currentTracks.value[0].artist).toBe('A');

		await byMood?.trigger('click');
		expect(currentTracks.value[0].bpm).toBe(140);

		await byTime?.trigger('click');
		await byShuffle?.trigger('click');
	});
});
