// Composable de interacción de la fila unificada: cálculo de lista (historial + actual + fila),
// gestos táctiles de deslizamiento (swipe) y arrastrar/soltar (drag & drop).

import { computed, ref, type Ref } from 'vue';
import type { Track } from '../../types';

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
	haptic: (heavy?: boolean) => void;
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

	let touchStartX = 0;
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

	function queueTouchStart(e: TouchEvent, path: string, i: number) {
		touchStartX = e.changedTouches[0].screenX;
		queueLongPressFired = false;

		queueLongPressTimer = setTimeout(() => {
			queueLongPressFired = true;
			haptic(true);
			openCtxMenu(e, getTrackInfo(path), 'queue', i);
		}, 500);
	}

	function queueTouchMove(e: TouchEvent, index: number) {
		if (Math.abs(e.touches[0].screenX - touchStartX) > 10 && queueLongPressTimer) {
			clearTimeout(queueLongPressTimer);
		}
		const diff = e.touches[0].screenX - touchStartX;
		if (diff < 100 && diff > -100) {
			swipeOffsets.value.set(index, diff);
		}
	}

	function queueTouchEnd(e: TouchEvent, index: number) {
		if (queueLongPressTimer) {
			clearTimeout(queueLongPressTimer);
		}

		if (queueLongPressFired) return;

		const diff = touchStartX - e.changedTouches[0].screenX;

		if (diff > 80) {
			haptic(true);
			removeQueueItemCmd(index);
		} else if (diff < -80) {
			haptic();
			moveQueueItem(index, 'first');
		}

		swipeOffsets.value.delete(index);
	}

	function dragStart(e: DragEvent, index: number) {
		dragFromIndex.value = index;
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
		dragStart,
		dragOver,
		dragLeave,
		dragDrop,
		dragEnd,
		dropAtEnd,
	};
}
