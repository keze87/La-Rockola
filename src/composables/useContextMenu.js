import { reactive, nextTick, toValue } from 'vue';
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
		ctxMenu.track = track;
		ctxMenu.source = source;
		ctxMenu.index = index;

		// 1. Extract raw coordinates
		const clientX = event.clientX || (event.touches && event.touches[0].clientX) || 0;
		const clientY = event.clientY || (event.touches && event.touches[0].clientY) || 0;

		// 2. Pre-seed the coordinates to prevent the top-left flash
		ctxMenu.x = clientX;
		ctxMenu.y = clientY;
		ctxMenu.visible = true;

		nextTick(() => {
			const menuElement = document.querySelector('.ctx-menu');
			if (!menuElement) return;

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

/**
 * Ready-to-spread event bindings (`v-on="bindings"`) for a single track row:
 * right-click opens the context menu, and a touch long-press does the same.
 *
 * Accepts refs, getters, or plain values for track/source/index and resolves
 * them at event time (not at setup time), so it stays correct even when the
 * row is reused for different data (e.g. a `:key`-stable row in a v-for that
 * gets fresh props on every websocket update).
 *
 * Pass `{ touch: false }` when the caller needs to own touch handling itself
 * (e.g. the queue list's swipe-to-delete gesture), leaving only the
 * right-click binding in place.
 */
export function useContextMenuBindings(track, source = 'library', index = null, { touch = true } = {}) {
	const { openCtxMenu, onCtxTouchStart, onCtxTouchEnd } = useContextMenu();

	const resolve = () => [toValue(track), toValue(source), toValue(index)];

	const bindings = {
		contextmenu: (e) => {
			e.preventDefault();
			openCtxMenu(e, ...resolve());
		},
	};

	if (touch) {
		bindings.touchstart = (e) => onCtxTouchStart(e, ...resolve());
		bindings.touchend = onCtxTouchEnd;
		bindings.touchmove = onCtxTouchEnd;
	}

	return bindings;
}
