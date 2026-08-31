import { describe, it, expect, vi } from 'vitest';
import { ref } from 'vue';
import { useSliderFactory } from '@/composables/useSliderFactory';

describe('useSliderFactory & useDragSlider', () => {
	it('calculates progress percentage correctly', () => {
		const source = ref(30);
		const max = ref(120);
		const onUpdate = vi.fn();

		const { createSlider } = useSliderFactory();
		const slider = createSlider(source, max, onUpdate);

		expect(slider.progressPercent.value).toBe(25);

		source.value = 60;
		expect(slider.progressPercent.value).toBe(50);
	});

	it('handles drag calculation and clamping', () => {
		const source = ref(0);
		const max = 200;
		const onUpdate = vi.fn();
		const onCommit = vi.fn();

		const { createSlider } = useSliderFactory();
		const slider = createSlider(source, max, onUpdate, onCommit);

		const mockElement = {
			getBoundingClientRect: () => ({
				left: 100,
				width: 500,
			}),
		};

		const mockEvent = {
			currentTarget: mockElement,
			clientX: 350,
		} as unknown as MouseEvent;

		slider.startDrag(mockEvent);
		expect(slider.isDragging.value).toBe(true);
		expect(slider.displayValue.value).toBe(100);
		expect(onUpdate).toHaveBeenCalledWith(100);

		const moveEvent = {
			currentTarget: mockElement,
			clientX: 600,
		} as unknown as MouseEvent;
		slider.moveDrag(moveEvent);
		expect(slider.displayValue.value).toBe(200);
		expect(onUpdate).toHaveBeenCalledWith(200);

		const endEvent = {
			currentTarget: mockElement,
			clientX: 225,
		} as unknown as MouseEvent;
		slider.endDrag(endEvent);
		expect(slider.isDragging.value).toBe(false);
		expect(onCommit).toHaveBeenCalledWith(50);
	});
});
