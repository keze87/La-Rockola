import { computed, onMounted, onUnmounted, ref, watch, type Ref } from 'vue';

export interface MarqueeOptions {
	minDuration?: number;
	baseDuration?: number;
	speedFactor?: number;
	extraPadding?: number;
}

/**
 * Composable reutilizable para detectar desborde horizontal y calcular el desplazamiento
 * de marquesina estilo radio vieja con soporte de ResizeObserver y prefers-reduced-motion.
 */
export function useMarquee(
	containerRef: Ref<HTMLElement | null>,
	textRef: Ref<HTMLElement | null>,
	options: MarqueeOptions = {}
) {
	const { minDuration = 6, baseDuration = 4, speedFactor = 0.035, extraPadding = 12 } = options;

	const isOverflowing = ref(false);
	const offset = ref(0);
	let resizeObserver: ResizeObserver | null = null;

	function prefersReducedMotion(): boolean {
		if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
			return false;
		}
		return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	}

	function checkOverflow() {
		if (prefersReducedMotion()) {
			isOverflowing.value = false;
			offset.value = 0;
			return;
		}

		const container = containerRef.value;
		const text = textRef.value;
		if (!container || !text) {
			isOverflowing.value = false;
			offset.value = 0;
			return;
		}

		const cWidth = container.clientWidth;
		const sWidth = text.scrollWidth;
		if (sWidth > cWidth + 4 && cWidth > 0) {
			isOverflowing.value = true;
			offset.value = sWidth - cWidth;
		} else {
			isOverflowing.value = false;
			offset.value = 0;
		}
	}

	function resetOverflow() {
		isOverflowing.value = false;
		offset.value = 0;
	}

	const marqueeStyle = computed(() => {
		if (!isOverflowing.value) return {};
		const duration = Math.max(minDuration, baseDuration + offset.value * speedFactor);
		return {
			'--marquee-offset': `-${offset.value + extraPadding}px`,
			'--marquee-duration': `${duration}s`,
		};
	});

	function bindObserver() {
		if (resizeObserver) {
			resizeObserver.disconnect();
		}
		if (typeof ResizeObserver === 'undefined') return;
		resizeObserver = new ResizeObserver(() => {
			checkOverflow();
		});
		if (containerRef.value) resizeObserver.observe(containerRef.value);
		if (textRef.value) resizeObserver.observe(textRef.value);
	}

	watch([containerRef, textRef], () => {
		bindObserver();
		checkOverflow();
	});

	onMounted(() => {
		bindObserver();
		checkOverflow();
	});

	onUnmounted(() => {
		if (resizeObserver) {
			resizeObserver.disconnect();
			resizeObserver = null;
		}
	});

	return {
		isOverflowing,
		offset,
		marqueeStyle,
		checkOverflow,
		resetOverflow,
	};
}
