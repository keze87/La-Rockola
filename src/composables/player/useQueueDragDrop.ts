// Composable de interacción de la fila unificada: cálculo de lista (historial + actual + fila),
// gestos táctiles de deslizamiento (swipe) y arrastrar/soltar (drag & drop).

import { computed, ref, type Ref } from 'vue';
import type { Track } from '../../types';
import type { HapticKind } from './useHaptics';

export interface UnifiedTrackItem {
	id: string;
	path: string;
	status: 'history' | 'current' | 'queue';
	index: number;
	historyIndex?: number;
	queueIndex?: number;
}

export interface UseQueueDragDropOptions {
	historyState: Ref<string[]>;
	currentTrackPath: Ref<string | null>;
	queueState: Ref<string[]>;
	getTrackInfo: (path: string) => Track;
	haptic: (kindOrHeavy?: HapticKind | boolean) => void;
	openCtxMenu: (e: MouseEvent | TouchEvent, track: Track, source: string, index: number | null) => void;
	moveInPlaylist: (fromIndex: number, toIndex: number) => void;
	moveQueueItem: (index: number, target: 'first' | 'last' | number) => void;
	removeQueueItemCmd: (index: number) => void;
}

export function useQueueDragDrop(options: UseQueueDragDropOptions) {
	const {
		historyState,
		currentTrackPath,
		queueState,
		getTrackInfo,
		haptic,
		openCtxMenu,
		moveInPlaylist,
		moveQueueItem,
		removeQueueItemCmd,
	} = options;

	const swipeOffsets = ref(new Map<number, number>());
	const dragFromIndex = ref<number | null>(null);

	const LONG_PRESS_CANCEL_PX = 8;
	const VERTICAL_SCROLL_LOCK_PX = 10;
	const HORIZONTAL_SWIPE_LOCK_PX = 16;
	const SWIPE_COMMIT_THRESHOLD_PX = 80;
	const SWIPE_MAX_OFFSET_PX = 124;

	let touchStartX = 0;
	let touchStartY = 0;
	let touchGestureMode: 'idle' | 'vertical-scroll' | 'horizontal-swipe' = 'idle';
	let thresholdHapticFired = false;
	let queueLongPressTimer: ReturnType<typeof setTimeout> | null = null;
	let queueLongPressFired = false;

	const unifiedQueue = computed<UnifiedTrackItem[]>(() => {
		const list: UnifiedTrackItem[] = [];
		let idx = 0;

		for (let i = 0; i < historyState.value.length; i++) {
			const path = historyState.value[i];
			list.push({
				id: `hist-${i}-${path}`,
				path,
				status: 'history',
				index: idx++,
				historyIndex: i,
			});
		}

		if (currentTrackPath.value) {
			list.push({
				id: `current-${currentTrackPath.value}`,
				path: currentTrackPath.value,
				status: 'current',
				index: idx++,
			});
		}

		for (let i = 0; i < queueState.value.length; i++) {
			const path = queueState.value[i];
			list.push({
				id: `queue-${i}-${path}`,
				path,
				status: 'queue',
				index: idx++,
				queueIndex: i,
			});
		}

		return list;
	});

	function clearQueueLongPress() {
		if (queueLongPressTimer) {
			clearTimeout(queueLongPressTimer);
			queueLongPressTimer = null;
		}
	}

	function cancelQueueTouch(index?: number) {
		clearQueueLongPress();
		queueLongPressFired = false;
		touchGestureMode = 'idle';
		thresholdHapticFired = false;
		if (index !== undefined) {
			swipeOffsets.value.delete(index);
		} else {
			swipeOffsets.value.clear();
		}
	}

	function queueTouchStart(e: TouchEvent, path: string, i: number) {
		clearQueueLongPress();
		const touch = e.changedTouches[0] ?? e.touches[0];
		if (!touch) return;

		touchStartX = touch.screenX;
		touchStartY = touch.screenY ?? 0;
		touchGestureMode = 'idle';
		thresholdHapticFired = false;
		queueLongPressFired = false;

		queueLongPressTimer = setTimeout(() => {
			queueLongPressTimer = null;
			if (touchGestureMode !== 'idle') return;
			queueLongPressFired = true;
			haptic(true);
			openCtxMenu(e, getTrackInfo(path), 'queue', i);
		}, 500);
	}

	function queueTouchMove(e: TouchEvent, index: number) {
		const touch = e.touches[0];
		if (!touch) return;

		const dx = touch.screenX - touchStartX;
		const dy = (touch.screenY ?? touchStartY) - touchStartY;
		const absDx = Math.abs(dx);
		const absDy = Math.abs(dy);

		// Cancelamos pulsación larga ante cualquier desplazamiento vertical u horizontal real (incluyendo scroll)
		if (absDx > LONG_PRESS_CANCEL_PX || absDy > LONG_PRESS_CANCEL_PX) {
			clearQueueLongPress();
		}

		if (touchGestureMode === 'idle') {
			if (absDy >= VERTICAL_SCROLL_LOCK_PX && absDy >= absDx) {
				touchGestureMode = 'vertical-scroll';
				swipeOffsets.value.delete(index);
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

		const clampedDiff = Math.max(-SWIPE_MAX_OFFSET_PX, Math.min(SWIPE_MAX_OFFSET_PX, dx));
		swipeOffsets.value.set(index, clampedDiff);

		if (!thresholdHapticFired && Math.abs(clampedDiff) >= SWIPE_COMMIT_THRESHOLD_PX) {
			thresholdHapticFired = true;
			haptic('tick');
		}
	}

	function queueTouchEnd(e: TouchEvent, index: number) {
		clearQueueLongPress();

		if (queueLongPressFired) {
			if (typeof e.preventDefault === 'function') e.preventDefault();
			queueLongPressFired = false;
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
				(Math.abs(dx) > SWIPE_COMMIT_THRESHOLD_PX && Math.abs(dx) > Math.abs(dy) * 1.4);

			if (isHorizontalFlick) {
				const diff = -dx;
				if (diff > SWIPE_COMMIT_THRESHOLD_PX) {
					haptic('confirm');
					removeQueueItemCmd(index);
				} else if (diff < -SWIPE_COMMIT_THRESHOLD_PX) {
					haptic('confirm');
					moveQueueItem(index, 'first');
				}
			}
		}

		swipeOffsets.value.delete(index);
	}

	function dragStart(e: DragEvent, index: number) {
		dragFromIndex.value = index;
		haptic('gesture_start');
		(e.currentTarget as HTMLElement)?.classList?.add('opacity-40');

		if (e.dataTransfer) {
			e.dataTransfer.effectAllowed = 'move';
			const item = unifiedQueue.value[index];
			if (item && typeof e.dataTransfer.setData === 'function') {
				e.dataTransfer.setData('text/plain', item.path);
			}
		}
	}

	function dragOver(e: DragEvent, index: number) {
		if (dragFromIndex.value === null || dragFromIndex.value === index) return;

		const target = e.currentTarget as HTMLElement | null;
		if (!target) return;

		const rect = target.getBoundingClientRect ? target.getBoundingClientRect() : { top: 0, height: 0 };
		const midY = (rect.top || 0) + (rect.height || 0) / 2;

		target.classList?.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

		if ((e.clientY ?? 0) < midY) {
			target.classList?.add('border-t-2', 'border-carpincho-primary');
		} else {
			target.classList?.add('border-b-2', 'border-carpincho-primary');
		}
	}

	function dragLeave(e: DragEvent) {
		const target = e.currentTarget as HTMLElement | null;
		target?.classList?.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');
	}

	function dragDrop(e: DragEvent, toIndex: number) {
		const target = e.currentTarget as HTMLElement | null;
		target?.classList?.remove('border-t-2', 'border-b-2', 'border-carpincho-primary');

		if (dragFromIndex.value === null || dragFromIndex.value === toIndex) return;

		const rect = target?.getBoundingClientRect ? target.getBoundingClientRect() : { top: 0, height: 0 };
		const midY = (rect.top || 0) + (rect.height || 0) / 2;

		let finalIndex = (e.clientY ?? 0) < midY ? toIndex : toIndex + 1;
		if (finalIndex > dragFromIndex.value) finalIndex--;

		if (finalIndex !== dragFromIndex.value) {
			haptic('gesture_end');
			moveInPlaylist(dragFromIndex.value, finalIndex);
		}

		dragFromIndex.value = null;
	}

	function dragEnd(e: DragEvent) {
		const target = e.currentTarget as HTMLElement | null;
		target?.classList?.remove('opacity-40', 'border-t-2', 'border-b-2', 'border-carpincho-primary');
		dragFromIndex.value = null;
	}

	function dropAtEnd() {
		if (dragFromIndex.value === null) return;
		const lastIndex = unifiedQueue.value.length - 1;
		if (lastIndex >= 0 && dragFromIndex.value !== lastIndex) {
			haptic('gesture_end');
			moveInPlaylist(dragFromIndex.value, lastIndex);
		}
		dragFromIndex.value = null;
	}

	return {
		unifiedQueue,
		swipeOffsets,
		dragFromIndex,
		queueTouchStart,
		queueTouchMove,
		queueTouchEnd,
		cancelQueueTouch,
		dragStart,
		dragOver,
		dragLeave,
		dragDrop,
		dragEnd,
		dropAtEnd,
	};
}
