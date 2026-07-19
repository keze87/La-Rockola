import { ref, computed } from 'vue';

export function useDragSlider(options = {}) {
	const { max = 100, getValue, onUpdate, onCommit } = options;

	const isDragging = ref(false);
	const dragValue = ref(0);

	// When dragging, show the immediate drag position. Otherwise, show the actual source value.
	const displayValue = computed(() => (isDragging.value ? dragValue.value : getValue()));

	const progressPercent = computed(() => {
		const maximum = typeof max === 'function' ? max() : max;

		if (!maximum) return 0;

		return (displayValue.value / maximum) * 100;
	});

	function calculateValue(e) {
		const maximum = typeof max === 'function' ? max() : max;

		if (!maximum) return null;

		const el = e.currentTarget;
		const rect = el.getBoundingClientRect();

		// Supports native Pointer Events, falling back to Touch/Mouse if needed
		const clientX =
			e.touches?.length > 0
				? e.touches[0].clientX
				: e.changedTouches?.length > 0
					? e.changedTouches[0].clientX
					: e.clientX;

		let clickX = clientX - rect.left;
		clickX = Math.max(0, Math.min(clickX, rect.width)); // Clamp between 0 and width
		return (clickX / rect.width) * maximum;
	}

	function startDrag(e) {
		isDragging.value = true;

		if (e.pointerId !== undefined) e.target.setPointerCapture(e.pointerId);

		const val = calculateValue(e);
		if (val !== null) {
			dragValue.value = val;
			if (onUpdate) onUpdate(val);
		}
	}

	function moveDrag(e) {
		if (!isDragging.value) return;
		const val = calculateValue(e);
		if (val !== null) {
			dragValue.value = val;
			if (onUpdate) onUpdate(val);
		}
	}

	function endDrag(e) {
		if (!isDragging.value) return;
		isDragging.value = false;

		if (e.pointerId !== undefined) e.target.releasePointerCapture(e.pointerId);

		const val = calculateValue(e);
		if (val !== null) {
			dragValue.value = val;

			if (onCommit) onCommit(val);
		}
	}

	return {
		displayValue,
		endDrag,
		isDragging,
		moveDrag,
		progressPercent,
		startDrag,
	};
}
