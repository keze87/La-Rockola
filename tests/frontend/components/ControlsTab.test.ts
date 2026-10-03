import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ControlsTab from '@/components/ControlsTab.vue';
import QRCode from 'qrcode.vue';
import {
	currentTracks,
	djCarpinchoEnabled,
	djSafeModeEnabled,
	hasEdgeTts,
	hasFfmpeg,
	isScanning,
	listenLocally,
	mpvVisible,
	radioModeEnabled,
	scanStatus,
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
		hasEdgeTts.value = true;
		hasFfmpeg.value = true;
		listenLocally.value = false;
		mpvVisible.value = true;
		radioModeEnabled.value = false;
		serverMuted.value = false;
		serverUrl.value = null;
		volume.value = 80;
		isScanning.value = false;
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: false,
			phase: 'idle',
			current: 0,
			total: 0,
			message: '',
		};
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
		expect(wrapper.text()).toContain('Carpincho locutor');
		expect(wrapper.text()).toContain('Escuchar acá');
	});

	it('hides "Más Manija" button when hasFfmpeg is false', () => {
		hasFfmpeg.value = false;
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

	it('dispatches toggle_radio_mode when clicking Carpincho locutor toggle', async () => {
		radioModeEnabled.value = false;
		hasEdgeTts.value = true;
		const wrapper = mount(ControlsTab);

		const toggles = wrapper.findAllComponents({ name: 'ToggleRow' });
		const radioToggle = toggles.find((t) => t.props('title') === 'Carpincho locutor');
		expect(radioToggle).toBeDefined();

		const switchBtn = radioToggle!.find('button');
		await switchBtn.trigger('click');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'toggle_radio_mode', state: true }),
			})
		);
	});

	it('hides Carpincho locutor toggle when hasEdgeTts is false', () => {
		hasEdgeTts.value = false;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).not.toContain('Carpincho locutor');
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

	it('disables "Más Manija" and displays "Sintonizando vibra..." when is_analyzing_mood is true', () => {
		scanStatus.value = {
			is_scanning: false,
			is_analyzing_mood: true,
			phase: 'mood',
			current: 10,
			total: 50,
			message: '',
		};
		const wrapper = mount(ControlsTab);

		const moodBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Sintonizando vibra'));
		expect(moodBtn).toBeDefined();
		expect(moodBtn?.attributes('disabled')).toBeDefined();
	});

	it('disables "Pegale otra escaneada" and displays progress when isScanning is true', () => {
		isScanning.value = true;
		scanStatus.value = {
			is_scanning: true,
			phase: 'metadata',
			current: 120,
			total: 500,
			message: '',
		};
		const wrapper = mount(ControlsTab);

		const scanBtn = wrapper
			.findAllComponents({ name: 'PillButton' })
			.find((w) => w.text().includes('Escaneando...'));
		expect(scanBtn).toBeDefined();
		expect(scanBtn?.text()).toContain('120/500');
		expect(scanBtn?.attributes('disabled')).toBeDefined();
	});

	it('displays current weather location and opens weather modal when clicked', async () => {
		hasEdgeTts.value = true;
		const wrapper = mount(ControlsTab);

		expect(wrapper.text()).toContain('Clima radial');
		expect(wrapper.text()).toContain('San Miguel de Tucumán');

		const weatherRow = wrapper.find('.bg-carpincho-panel.border-carpincho-warning.max-w-lg');
		expect(weatherRow.exists()).toBe(true);

		const mapBtn = wrapper.findAllComponents({ name: 'PillButton' }).find((b) => b.text().includes('Cambiar mapa'));
		expect(mapBtn).toBeDefined();
		expect(wrapper.find('.material-symbols-outlined').exists()).toBe(false);

		await mapBtn!.trigger('click');

		const modal = wrapper.findComponent({ name: 'WeatherLocationModal' });
		expect(modal.exists()).toBe(true);
		expect(modal.props('isOpen')).toBe(true);
	});
});
