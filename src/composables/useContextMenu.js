import { reactive, nextTick } from 'vue';
import { computePosition, flip, shift, offset } from '@floating-ui/vue';

const ctxMenu = reactive({
	visible: false,
	x: 0,
	y: 0,
	track: null,
	source: 'library', // 'library', 'queue', 'history'
	index: null,
});

export function useContextMenu() {
	function openCtxMenu(event, track, source = 'library', index = null) {
		ctxMenu.visible = true;
		ctxMenu.track = track;
		ctxMenu.source = source;
		ctxMenu.index = index;

		nextTick(() => {
			const menuElement = document.querySelector('.ctx-menu');
			if (!menuElement) return;

			// Extract client coordinates whether it's a mouse click or a touch
			const clientX = event.clientX || (event.touches && event.touches[0].clientX) || 0;
			const clientY = event.clientY || (event.touches && event.touches[0].clientY) || 0;

			// Create a virtual element at the click/touch coordinates
			const virtualEl = {
				getBoundingClientRect() {
					return {
						width: 0,
						height: 0,
						x: clientX,
						y: clientY,
						top: clientY,
						left: clientX,
						right: clientX,
						bottom: clientY,
					};
				},
			};

			computePosition(virtualEl, menuElement, {
				placement: 'bottom-start',
				middleware: [offset(12), flip(), shift({ padding: 12 })],
			}).then(({ x, y }) => {
				ctxMenu.x = x;
				ctxMenu.y = y;
			});
		});
	}

	function closeCtxMenu() {
		ctxMenu.visible = false;
	}

	let ctxLongPressTimer = null;

	function onCtxTouchStart(e, track, source = 'library', index = null) {
		ctxLongPressTimer = setTimeout(() => {
			if (window.navigator.vibrate) window.navigator.vibrate([10, 30, 20]);

			openCtxMenu(e, track, source, index); // Pass the original event to openCtxMenu
		}, 500);
	}

	function onCtxTouchEnd() {
		clearTimeout(ctxLongPressTimer);
	}

	return {
		closeCtxMenu,
		ctxMenu,
		onCtxTouchEnd,
		onCtxTouchStart,
		openCtxMenu,
	};
}
