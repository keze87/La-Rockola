// Composable de interacción de la fila unificada: cálculo de lista (historial + actual + fila),
// gestos táctiles de deslizamiento (swipe) y arrastrar/soltar (drag & drop).

import { computed, ref, type Ref } from 'vue';
import type { Track } from '../../types';
import { useRowSwipe } from '../useRowSwipe';
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
	addHistoryToQueueCmd: (path: string) => void;
	removeHistoryItemCmd: (index: number) => void;
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
		addHistoryToQueueCmd,
		removeHistoryItemCmd,
	} = options;

	const dragFromIndex = ref<number | null>(null);
	const longPressPathByIndex = new Map<number, string>();
	const historyLongPressPathByIndex = new Map<number, string>();

	const {
		swipeOffsets,
		touchStart: baseTouchStart,
		touchMove: queueTouchMove,
		touchEnd: queueTouchEnd,
		cancelTouch: cancelQueueTouch,
	} = useRowSwipe<number>({
		haptic,
		onLongPress: (e, index) => {
			const path = longPressPathByIndex.get(index);
			if (path) {
				openCtxMenu(e, getTrackInfo(path), 'queue', index);
			}
		},
		onSwipeLeft: (index) => removeQueueItemCmd(index),
		onSwipeRight: (index) => moveQueueItem(index, 'first'),
	});

	const {
		swipeOffsets: historySwipeOffsets,
		touchStart: baseHistoryTouchStart,
		touchMove: historyTouchMove,
		touchEnd: historyTouchEnd,
		cancelTouch: cancelHistoryTouch,
	} = useRowSwipe<number>({
		haptic,
		onLongPress: (e, historyIndex) => {
			const path = historyLongPressPathByIndex.get(historyIndex) ?? historyState.value[historyIndex];
			if (path) {
				openCtxMenu(e, getTrackInfo(path), 'history', historyIndex);
			}
		},
		onSwipeLeft: (historyIndex) => removeHistoryItemCmd(historyIndex),
		onSwipeRight: (historyIndex) => {
			const path = historyState.value[historyIndex] ?? historyLongPressPathByIndex.get(historyIndex);
			if (path) {
				addHistoryToQueueCmd(path);
			}
		},
	});

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

	function queueTouchStart(e: TouchEvent, path: string, i: number) {
		longPressPathByIndex.set(i, path);
		baseTouchStart(e, i);
	}

	function historyTouchStart(e: TouchEvent, path: string, historyIndex: number) {
		historyLongPressPathByIndex.set(historyIndex, path);
		baseHistoryTouchStart(e, historyIndex);
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
		historySwipeOffsets,
		historyTouchStart,
		historyTouchMove,
		historyTouchEnd,
		cancelHistoryTouch,
		dragStart,
		dragOver,
		dragLeave,
		dragDrop,
		dragEnd,
		dropAtEnd,
	};
}
