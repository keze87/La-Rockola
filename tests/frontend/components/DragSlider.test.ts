import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import DragSlider from '@/components/ui/DragSlider.vue';

describe('DragSlider.vue', () => {
	it('renders progress bar with appropriate percentage style width', () => {
		const wrapper = mount(DragSlider, {
			props: {
				modelValue: 40,
				max: 100,
			},
		});

		const filledBar = wrapper.find('.h-full.rounded-full');
		expect(filledBar.attributes('style')).toContain('width: 40%');
	});
});
