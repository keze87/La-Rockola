// Composable compartido para deslizamiento horizontal estilo Gmail y pulsación larga segura frente al scroll vertical.

import { ref } from 'vue';
import type { HapticKind } from './player/useHaptics';

export interface UseRowSwipeOptions<K extends string | number> {
	haptic: (kindOrHeavy?: HapticKind | boolean) => void;
	onLongPress?: (e: TouchEvent, key: K) => void;
	onSwipeLeft?: (key: K) => void;
	onSwipeRight?: (key: K) => void;
	commitThresholdPx?: number;
	maxOffsetPx?: number;
	longPressDelayMs?: number;
}

const LONG_PRESS_CANCEL_PX = 8;
const VERTICAL_SCROLL_LOCK_PX = 10;
const HORIZONTAL_SWIPE_LOCK_PX = 16;

export function useRowSwipe<K extends string | number>(options: UseRowSwipeOptions<K>) {
	const {
		haptic,
		onLongPress,
		onSwipeLeft,
		onSwipeRight,
		commitThresholdPx = 80,
		maxOffsetPx = 124,
		longPressDelayMs = 500,
	} = options;

	const swipeOffsets = ref(new Map<K, number>());

	let touchStartX = 0;
	let touchStartY = 0;
	let touchGestureMode: 'idle' | 'vertical-scroll' | 'horizontal-swipe' = 'idle';
	let thresholdHapticFired = false;
	let longPressTimer: ReturnType<typeof setTimeout> | null = null;
	let longPressFired = false;

	function clearLongPress() {
		if (longPressTimer) {
			clearTimeout(longPressTimer);
			longPressTimer = null;
		}
	}

	function cancelTouch(key?: K) {
		clearLongPress();
		longPressFired = false;
		touchGestureMode = 'idle';
		thresholdHapticFired = false;
		if (key !== undefined) {
			swipeOffsets.value.delete(key);
		} else {
			swipeOffsets.value.clear();
		}
	}

	function touchStart(e: TouchEvent, key: K) {
		clearLongPress();
		const touch = e.changedTouches[0] ?? e.touches[0];
		if (!touch) return;

		touchStartX = touch.screenX;
		touchStartY = touch.screenY ?? 0;
		touchGestureMode = 'idle';
		thresholdHapticFired = false;
		longPressFired = false;

		if (onLongPress) {
			longPressTimer = setTimeout(() => {
				longPressTimer = null;
				if (touchGestureMode !== 'idle') return;
				longPressFired = true;
				haptic(true);
				onLongPress(e, key);
			}, longPressDelayMs);
		}
	}

	function touchMove(e: TouchEvent, key: K) {
		const touch = e.touches[0];
		if (!touch) return;

		const dx = touch.screenX - touchStartX;
		const dy = (touch.screenY ?? touchStartY) - touchStartY;
		const absDx = Math.abs(dx);
		const absDy = Math.abs(dy);

		// Cancelamos pulsación larga ante cualquier movimiento real en X o Y (scroll incluido)
		if (absDx > LONG_PRESS_CANCEL_PX || absDy > LONG_PRESS_CANCEL_PX) {
			clearLongPress();
		}

		if (touchGestureMode === 'idle') {
			if (absDy >= VERTICAL_SCROLL_LOCK_PX && absDy >= absDx) {
				touchGestureMode = 'vertical-scroll';
				swipeOffsets.value.delete(key);
				return;
			}
			if (absDx >= HORIZONTAL_SWIPE_LOCK_PX && absDx > absDy * 1.4) {
				touchGestureMode = 'horizontal-swipe';
			} else {
				return;
			}
		}

		if (touchGestureMode === 'vertical-scroll') {
			return;
		}

		if (typeof e.stopPropagation === 'function') {
			e.stopPropagation();
		}

		const clampedDiff = Math.max(-maxOffsetPx, Math.min(maxOffsetPx, dx));
		swipeOffsets.value.set(key, clampedDiff);

		if (!thresholdHapticFired && Math.abs(clampedDiff) >= commitThresholdPx) {
			thresholdHapticFired = true;
			haptic('tick');
		}
	}

	function touchEnd(e: TouchEvent, key: K) {
		clearLongPress();

		if (longPressFired) {
			if (typeof e.preventDefault === 'function') e.preventDefault();
			longPressFired = false;
			touchGestureMode = 'idle';
			thresholdHapticFired = false;
			return;
		}

		const prevMode = touchGestureMode;
		touchGestureMode = 'idle';
		thresholdHapticFired = false;

		const touch = e.changedTouches[0];
		if (touch && prevMode !== 'vertical-scroll') {
			const dx = touch.screenX - touchStartX;
			const dy = (touch.screenY ?? touchStartY) - touchStartY;
			const isHorizontalFlick =
				prevMode === 'horizontal-swipe' ||
				(Math.abs(dx) > commitThresholdPx && Math.abs(dx) > Math.abs(dy) * 1.4);

			if (isHorizontalFlick) {
				const diff = -dx;
				if (diff > commitThresholdPx) {
					haptic('confirm');
					onSwipeLeft?.(key);
				} else if (diff < -commitThresholdPx) {
					haptic('confirm');
					onSwipeRight?.(key);
				}
			}
		}

		swipeOffsets.value.delete(key);
	}

	return {
		swipeOffsets,
		touchStart,
		touchMove,
		touchEnd,
		cancelTouch,
	};
}
