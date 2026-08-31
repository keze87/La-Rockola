import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import PillButton from '@/components/ui/PillButton.vue';

describe('PillButton.vue', () => {
	it('renders slot content and icon', () => {
		const wrapper = mount(PillButton, {
			props: {
				icon: 'shuffle',
				colorClass: 'bg-emerald-600',
			},
			slots: {
				default: 'Mezclar',
			},
		});

		expect(wrapper.text()).toContain('Mezclar');
		expect(wrapper.find('.material-icons').text()).toBe('shuffle');
		expect(wrapper.classes()).toContain('bg-emerald-600');
	});

	it('emits click event on press', async () => {
		const wrapper = mount(PillButton, {
			slots: { default: 'Click Me' },
		});

		await wrapper.trigger('click');
		expect(wrapper.emitted('click')).toBeTruthy();
	});
});
