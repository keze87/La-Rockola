import { toValue, type MaybeRefOrGetter } from 'vue';
import { useDragSlider } from './useDragSlider';

export function useSliderFactory() {
	/**
	 * @param {Ref|Number|Function} source - The reactive value for the slider's current position
	 * @param {Ref|Number|Function} max - The reactive value for the slider's maximum limit
	 * @param {Function} onUpdate - Fires continuously while dragging
	 * @param {Function} onCommit - Fires once when the user releases the slider
	 */
	function createSlider(
		source: MaybeRefOrGetter<number>,
		max: MaybeRefOrGetter<number>,
		onUpdate: (val: number) => void,
		onCommit?: (val: number) => void
	) {
		return useDragSlider({
			// toValue automatically unwraps refs or executes getter functions
			max: () => toValue(max),
			getValue: () => toValue(source),
			onUpdate,
			onCommit: onCommit || onUpdate, // Fallback to onUpdate if no distinct commit is needed
		});
	}

	return { createSlider };
}
