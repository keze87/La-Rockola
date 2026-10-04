import { ref, computed, toValue, type MaybeRefOrGetter } from 'vue';

type SliderInputEvent = PointerEvent | MouseEvent | TouchEvent;

export interface DragSliderOptions {
	max?: MaybeRefOrGetter<number>;
	getValue: () => number;
	onUpdate?: (val: number) => void;
	onCommit?: (val: number) => void;
}

export function useDragSlider(options: DragSliderOptions) {
	const { max = 100, getValue, onUpdate, onCommit } = options;
	const isDragging = ref(false);
	const dragValue = ref(0);

	// Al arrastrar mostramos la posición inmediata del arrastre. Si no, el valor real de origen.
	const displayValue = computed(() => (isDragging.value ? dragValue.value : getValue()));

	const progressPercent = computed(() => {
		const maximum = toValue(max);

		if (!maximum) return 0;

		return (displayValue.value / maximum) * 100;
	});

	function calculateValue(e: SliderInputEvent): number | null {
		const maximum = toValue(max);

		if (!maximum) return null;

		const el = e.currentTarget as HTMLElement;
		const rect = el.getBoundingClientRect();

		// Soporta Pointer Events nativos, con fallback a Touch/Mouse si hace falta
		let clientX = 0;

		if ('touches' in e && (e as TouchEvent).touches.length > 0) {
			clientX = (e as TouchEvent).touches[0].clientX;
		} else if ('changedTouches' in e && (e as TouchEvent).changedTouches.length > 0) {
			clientX = (e as TouchEvent).changedTouches[0].clientX;
		} else if ('clientX' in e) {
			clientX = (e as MouseEvent).clientX;
		}

		let clickX = clientX - rect.left;
		clickX = Math.max(0, Math.min(clickX, rect.width)); // Limitamos entre 0 y el ancho
		return (clickX / rect.width) * maximum;
	}

	function startDrag(e: SliderInputEvent) {
		isDragging.value = true;

		if ('pointerId' in e) (e.target as Element).setPointerCapture(e.pointerId);

		const val = calculateValue(e);

		if (val !== null) {
			dragValue.value = val;

			if (onUpdate) onUpdate(val);
		}
	}

	function moveDrag(e: SliderInputEvent) {
		if (!isDragging.value) return;

		const val = calculateValue(e);

		if (val !== null) {
			dragValue.value = val;

			if (onUpdate) onUpdate(val);
		}
	}

	function endDrag(e: SliderInputEvent) {
		if (!isDragging.value) return;

		isDragging.value = false;

		if ('pointerId' in e) (e.target as Element).releasePointerCapture(e.pointerId);

		const val = calculateValue(e);

		if (val !== null) {
			dragValue.value = val;

			if (onCommit) onCommit(val);
		}
	}

	return { displayValue, endDrag, isDragging, moveDrag, progressPercent, startDrag };
}
