import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import ToggleRow from '@/components/ui/ToggleRow.vue';

describe('ToggleRow.vue', () => {
	it('renders title, description, and icon', () => {
		const wrapper = mount(ToggleRow, {
			props: {
				modelValue: false,
				title: 'Modo DJ',
				description: 'Tira temas random',
				icon: 'shuffle',
			},
		});

		expect(wrapper.text()).toContain('Modo DJ');
		expect(wrapper.text()).toContain('Tira temas random');
		expect(wrapper.text()).toContain('shuffle');
	});

	it('emits update:modelValue when switch is toggled', async () => {
		const wrapper = mount(ToggleRow, {
			props: {
				modelValue: false,
				title: 'Modo DJ',
			},
		});

		const switchBtn = wrapper.find('button');
		await switchBtn.trigger('click');

		expect(wrapper.emitted('update:modelValue')).toBeTruthy();
		expect(wrapper.emitted('update:modelValue')![0]).toEqual([true]);
	});
});
