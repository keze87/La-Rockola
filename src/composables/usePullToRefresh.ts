import { ref } from 'vue';

export interface PullToRefreshOptions {
	threshold?: number;
	maxPullPx?: number;
	cooldownMs?: number;
	canRefresh?: () => boolean;
	onRefresh: () => void | Promise<void>;
	onHaptic?: () => void;
}

/**
 * Composable reutilizable para gesto táctil pull-to-refresh en listados scrolleables.
 */
export function usePullToRefresh(options: PullToRefreshOptions) {
	const pullThreshold = options.threshold ?? 64;
	const maxPullPx = options.maxPullPx ?? 108;
	const cooldownMs = options.cooldownMs ?? 5000;

	const pullDistance = ref(0);
	const isPulling = ref(false);
	let pullStartX = 0;
	let pullStartY = 0;
	let pullAxis: 'vertical' | 'horizontal' | null = null;
	let lastPullRefreshAt = 0;

	function resetPull() {
		isPulling.value = false;
		pullDistance.value = 0;
		pullAxis = null;
	}

	function canStartPull(): boolean {
		return options.canRefresh ? options.canRefresh() : true;
	}

	function onPullTouchStart(e: TouchEvent) {
		const section = e.currentTarget as HTMLElement | null;
		const target = e.target as HTMLElement | null;
		if (!section || section.scrollTop > 0) return;
		if (!canStartPull()) return;
		if (target?.closest('input, textarea')) return;

		const touch = e.touches[0];
		if (!touch) return;
		pullStartX = touch.clientX;
		pullStartY = touch.clientY;
		pullAxis = null;
		isPulling.value = true;
		pullDistance.value = 0;
	}

	function onPullTouchMove(e: TouchEvent) {
		if (!isPulling.value) return;
		const section = e.currentTarget as HTMLElement | null;
		if (section && section.scrollTop > 0) {
			resetPull();
			return;
		}
		const touch = e.touches[0];
		if (!touch) return;

		const dx = touch.clientX - pullStartX;
		const dy = touch.clientY - pullStartY;

		if (!pullAxis && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
			if (Math.abs(dx) > Math.abs(dy)) {
				// Es un swipe horizontal de pestañas: soltamos el pull para no interferir
				resetPull();
				return;
			}
			pullAxis = dy > 0 ? 'vertical' : null;
			if (!pullAxis) {
				resetPull();
				return;
			}
		}

		if (pullAxis === 'vertical') {
			pullDistance.value = Math.max(0, Math.min(maxPullPx, Math.round(dy * 0.6)));
			if (pullDistance.value > 0 && e.cancelable) {
				e.preventDefault();
			}
		}
	}

	function onPullTouchEnd() {
		if (!isPulling.value) return;
		const ready = pullDistance.value >= pullThreshold;
		resetPull();
		const now = Date.now();
		if (ready && canStartPull() && now - lastPullRefreshAt >= cooldownMs) {
			lastPullRefreshAt = now;
			options.onHaptic?.();
			void options.onRefresh();
		}
	}

	return {
		pullThreshold,
		pullDistance,
		onPullTouchStart,
		onPullTouchMove,
		onPullTouchEnd,
		resetPull,
	};
}
