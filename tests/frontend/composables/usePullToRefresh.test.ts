import { describe, expect, it, vi } from 'vitest';
import { usePullToRefresh } from '../../../src/composables/usePullToRefresh';

describe('usePullToRefresh', () => {
	it('dispara onThresholdCrossed al cruzar el umbral y excluye gestos desde los bordes laterales', async () => {
		const onThresholdCrossed = vi.fn();
		const onRefresh = vi.fn();
		const onHaptic = vi.fn();

		const { pullDistance, onPullTouchStart, onPullTouchMove, onPullTouchEnd } = usePullToRefresh({
			threshold: 60,
			onThresholdCrossed,
			onRefresh,
			onHaptic,
		});

		const section = { scrollTop: 0 } as HTMLElement;
		const target = document.createElement('div');

		// Gesto desde borde izquierdo (< 24px): debe ignorarse para no chocar con back predictivo
		onPullTouchStart({
			currentTarget: section,
			target,
			touches: [{ clientX: 10, clientY: 100 }],
		} as unknown as TouchEvent);
		onPullTouchMove({
			currentTarget: section,
			touches: [{ clientX: 10, clientY: 250 }],
			cancelable: true,
			preventDefault: vi.fn(),
		} as unknown as TouchEvent);
		expect(pullDistance.value).toBe(0);

		// Gesto válido en el centro de la pantalla
		onPullTouchStart({
			currentTarget: section,
			target,
			touches: [{ clientX: 180, clientY: 100 }],
		} as unknown as TouchEvent);
		onPullTouchMove({
			currentTarget: section,
			touches: [{ clientX: 180, clientY: 150 }],
			cancelable: true,
			preventDefault: vi.fn(),
		} as unknown as TouchEvent);
		expect(onThresholdCrossed).not.toHaveBeenCalled();

		// Cruza el umbral (dy=120 * 0.6 = 72 >= 60) -> solo dispara una vez aunque siga bajando
		onPullTouchMove({
			currentTarget: section,
			touches: [{ clientX: 180, clientY: 220 }],
			cancelable: true,
			preventDefault: vi.fn(),
		} as unknown as TouchEvent);
		onPullTouchMove({
			currentTarget: section,
			touches: [{ clientX: 180, clientY: 240 }],
			cancelable: true,
			preventDefault: vi.fn(),
		} as unknown as TouchEvent);
		expect(onThresholdCrossed).toHaveBeenCalledTimes(1);

		onPullTouchEnd();
		expect(onHaptic).toHaveBeenCalledTimes(1);
		expect(onRefresh).toHaveBeenCalledTimes(1);
	});
});
