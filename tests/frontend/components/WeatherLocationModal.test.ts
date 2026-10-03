import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import WeatherLocationModal from '@/components/WeatherLocationModal.vue';
import { weatherLocation } from '@/composables/player/state';

describe('WeatherLocationModal.vue', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.includes('/api/weather/preview')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							ok: true,
							location: '-34.6037,-58.3816',
							area_name: 'Constitución',
							temp_c: 20,
							phrase: 'Mirá cómo está el tiempo en Constitución: 20 grados.',
						}),
				} as unknown as Response);
			}
			return Promise.resolve({
				ok: true,
				json: () => Promise.resolve({ status: 'ok' }),
			} as unknown as Response);
		});
		global.fetch = fetchMock;
		weatherLocation.value = 'San Miguel de Tucumán';
	});

	it('renders dialog elements when isOpen is true', () => {
		const wrapper = mount(WeatherLocationModal, {
			props: { isOpen: true },
		});

		expect(wrapper.text()).toContain('Ubicación del clima radial');
		expect(wrapper.text()).toContain('Detectar mi ubicación');
		expect(wrapper.text()).toContain('Probar reporte');
		expect(wrapper.text()).toContain('Guardar ubicación');
	});

	it('selects a preset city when clicked', async () => {
		const wrapper = mount(WeatherLocationModal, {
			props: { isOpen: true },
		});

		const cordobaBtn = wrapper.findAll('button').find((b) => b.text().includes('Córdoba'));
		expect(cordobaBtn).toBeDefined();
		await cordobaBtn?.trigger('click');

		const latInput = wrapper.find<HTMLInputElement>('input[placeholder="Latitud"]');
		const lngInput = wrapper.find<HTMLInputElement>('input[placeholder="Longitud"]');
		expect(latInput.element.value).toBe('-31.4201');
		expect(lngInput.element.value).toBe('-64.1888');
	});

	it('fetches and displays preview when "Probar reporte" is clicked', async () => {
		const wrapper = mount(WeatherLocationModal, {
			props: { isOpen: true },
		});

		const previewBtn = wrapper.findAll('button').find((b) => b.text().includes('Probar reporte'));
		expect(previewBtn).toBeDefined();
		await previewBtn?.trigger('click');
		await flushPromises();

		expect(wrapper.text()).toContain('Constitución');
		expect(wrapper.text()).toContain('20°C');
		expect(wrapper.text()).toContain('Mirá cómo está el tiempo en Constitución');
	});

	it('saves the selected coordinates via command and emits close', async () => {
		const wrapper = mount(WeatherLocationModal, {
			props: { isOpen: true },
		});

		// Select a preset first
		const cordobaBtn = wrapper.findAll('button').find((b) => b.text().includes('Córdoba'));
		await cordobaBtn?.trigger('click');

		const saveBtn = wrapper.findAll('button').find((b) => b.text().includes('Guardar ubicación'));
		await saveBtn?.trigger('click');
		await flushPromises();

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: expect.stringContaining('set_weather_location'),
			})
		);
		expect(wrapper.emitted('close')).toBeTruthy();
	});
});
