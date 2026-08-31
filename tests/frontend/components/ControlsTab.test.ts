import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ControlsTab from '@/components/ControlsTab.vue';
import {
	currentTracks,
	djCarpinchoEnabled,
	djSafeModeEnabled,
	listenLocally,
	mpvVisible,
	serverMuted,
	volume,
} from '@/composables/player/state';
import * as api from '@/composables/useApi';

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
		listenLocally.value = false;
		mpvVisible.value = true;
		serverMuted.value = false;
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

		const stopBtn = wrapper.findAllComponents({ name: 'PillButton' }).find((w) => w.text().includes('Cortala de una'));
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
});
