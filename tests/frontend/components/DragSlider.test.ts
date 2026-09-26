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

	it('handles pointer drag interactions and emits dragging, update:modelValue, and commit', async () => {
		const wrapper = mount(DragSlider, {
			props: {
				modelValue: 20,
				max: 100,
			},
		});

		const rootEl = wrapper.element as HTMLElement;
		vi.spyOn(rootEl, 'getBoundingClientRect').mockReturnValue({
			left: 0,
			top: 0,
			right: 200,
			bottom: 40,
			width: 200,
			height: 40,
			x: 0,
			y: 0,
			toJSON: () => {},
		});

		// Start drag at x = 100 (50%)
		await wrapper.trigger('pointerdown', { clientX: 100, pointerId: 1 });
		expect(wrapper.emitted('dragging')).toBeTruthy();
		expect(wrapper.emitted('update:modelValue')).toBeTruthy();

		// Move drag at x = 150 (75%)
		await wrapper.trigger('pointermove', { clientX: 150, pointerId: 1 });
		expect(wrapper.emitted('update:modelValue')!.length).toBeGreaterThanOrEqual(1);

		// End drag
		await wrapper.trigger('pointerup', { clientX: 150, pointerId: 1 });
		expect(wrapper.emitted('commit')).toBeTruthy();

		// Cancel drag
		await wrapper.trigger('pointercancel', { clientX: 150, pointerId: 1 });
	});
});
