import { ref, computed } from 'vue';

export function useDragSlider(options = {}) {
	const { max = 100, getValue, onCommit } = options;

	const isDragging = ref(false);
	const dragValue = ref(0);

	const displayValue = computed(() => (isDragging.value ? dragValue.value : getValue()));

	const progressPercent = computed(() => {
		const maximum = typeof max === 'function' ? max() : max;

		if (!maximum) return 0;

		return (displayValue.value / maximum) * 100;
	});

	function calculateValueFromEvent(e) {
		const maximum = typeof max === 'function' ? max() : max;

		if (!maximum) return null;

		const el = e.currentTarget;
		const rect = el.getBoundingClientRect();

		// Normalize touch/pointer events
		const clientX = e.touches?.length
			? e.touches[0].clientX
			: e.changedTouches?.length
				? e.changedTouches[0].clientX
				: e.clientX;

		const clickX = Math.max(0, Math.min(clientX - rect.left, rect.width));
		return (clickX / rect.width) * maximum;
	}

	function startDrag(e) {
		isDragging.value = true;

		if (e.pointerId !== undefined) e.target.setPointerCapture(e.pointerId);

		const val = calculateValueFromEvent(e);

		if (val !== null) dragValue.value = val;
	}

	function moveDrag(e) {
		if (!isDragging.value) return;

		const val = calculateValueFromEvent(e);

		if (val !== null) dragValue.value = val;
	}

	function endDrag(e) {
		if (!isDragging.value) return;

		const val = calculateValueFromEvent(e);
		isDragging.value = false;

		if (e.pointerId !== undefined) e.target.releasePointerCapture(e.pointerId);

		if (val !== null) {
			dragValue.value = val;

			if (onCommit) onCommit(val);
		}
	}

	return { isDragging, progressPercent, startDrag, moveDrag, endDrag };
}
