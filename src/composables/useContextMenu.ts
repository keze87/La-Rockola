import { computePosition, flip, shift, offset } from '@floating-ui/vue';
import { reactive, nextTick, toValue, type MaybeRefOrGetter } from 'vue';
import type { Track } from '../types';

interface CtxMenuState {
	visible: boolean;
	x: number;
	y: number;
	track: Track | null;
	source: string;
	index: number | null;
}

const ctxMenu = reactive<CtxMenuState>({
	visible: false,
	x: 0,
	y: 0,
	track: null,
	source: 'library', // 'library', 'queue', 'history'
	index: null,
});

// The element that opened the menu (a table row, typically), so we can
// return keyboard focus to it once the menu closes. Module-level like
// ctxMenu itself, since there's only ever one menu instance in the app.
let triggerEl: HTMLElement | null = null;

// Touch state stored outside the composable so it persists accurately
let ctxLongPressTimer: ReturnType<typeof setTimeout> | null = null;
let touchStartX = 0;
let touchStartY = 0;
let ctxLongPressFired = false;

export function useContextMenu() {
	function openCtxMenu(
		event: MouseEvent | TouchEvent,
		track: Track,
		source = 'library',
		index: number | null = null
	) {
		// Only valid for handlers invoked synchronously (e.g. a real
		// `contextmenu` event) — for the touch long-press path this is
		// captured earlier by onCtxTouchStart, since `currentTarget` is
		// already null by the time its setTimeout fires.
		if (event.currentTarget) triggerEl = event.currentTarget as HTMLElement;

		ctxMenu.track = track;
		ctxMenu.source = source;
		ctxMenu.index = index;

		// 1. Extract raw coordinates
		const clientX = 'touches' in event ? (event.touches[0]?.clientX ?? 0) : event.clientX;
		const clientY = 'touches' in event ? (event.touches[0]?.clientY ?? 0) : event.clientY;

		// 2. Pre-seed the coordinates to prevent the top-left flash
		ctxMenu.x = clientX;
		ctxMenu.y = clientY;
		ctxMenu.visible = true;

		nextTick(() => {
			const menuElement = document.querySelector('.ctx-menu') as HTMLElement;
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
					} as DOMRect;
				},
			};

			computePosition(virtualEl, menuElement, {
				placement: 'bottom-start',
				middleware: [offset(12), flip(), shift({ padding: 12 })],
			}).then(({ x, y }) => {
				ctxMenu.x = x;
				ctxMenu.y = y;
			});

			// Move keyboard focus into the menu so it's usable without a mouse
			(menuElement.querySelector('[role="menuitem"]') as HTMLElement)?.focus();
		});
	}

	function closeCtxMenu() {
		ctxMenu.visible = false;

		// Return focus to whatever opened the menu, if it's still around
		if (triggerEl && document.contains(triggerEl) && typeof triggerEl.focus === 'function') {
			triggerEl.focus();
		}
		triggerEl = null;
	}

	function onCtxTouchStart(e: TouchEvent, track: Track, source = 'library', index: number | null = null) {
		// Capture now, synchronously — `e.currentTarget` is nulled out by the
		// browser once the touchstart event finishes dispatching, so it would
		// already be gone by the time the setTimeout below fires.
		const el = e.currentTarget as HTMLElement;

		touchStartX = e.touches[0].screenX;
		touchStartY = e.touches[0].screenY;
		ctxLongPressFired = false;

		ctxLongPressTimer = setTimeout(() => {
			ctxLongPressFired = true;

			if (window.navigator.vibrate) window.navigator.vibrate([10, 30, 20]);

			triggerEl = el;
			openCtxMenu(e, track, source, index); // Pass the original event to openCtxMenu
		}, 500);
	}

	function onCtxTouchMove(e: TouchEvent) {
		if (!ctxLongPressTimer) return;

		const diffX = Math.abs(e.touches[0].screenX - touchStartX);
		const diffY = Math.abs(e.touches[0].screenY - touchStartY);

		// Cancel the long press if the finger moves more than 10px
		if (diffX > 10 || diffY > 10) {
			clearTimeout(ctxLongPressTimer);
			ctxLongPressTimer = null;
		}
	}

	function onCtxTouchEnd(e: TouchEvent) {
		if (ctxLongPressTimer) {
			clearTimeout(ctxLongPressTimer);
			ctxLongPressTimer = null;
		}

		// If the context menu opened, prevent the subsequent click event
		if (ctxLongPressFired && e && typeof e.preventDefault === 'function') {
			e.preventDefault();
		}
	}

	return { closeCtxMenu, ctxMenu, onCtxTouchEnd, onCtxTouchMove, onCtxTouchStart, openCtxMenu };
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
export function useContextMenuBindings(
	track: MaybeRefOrGetter<Track>,
	source: MaybeRefOrGetter<string> = 'library',
	index: MaybeRefOrGetter<number | null> = null,
	{ touch = true } = {}
) {
	const { openCtxMenu, onCtxTouchStart, onCtxTouchEnd, onCtxTouchMove } = useContextMenu();

	const resolve = () => [toValue(track), toValue(source), toValue(index)] as const;

	const bindings = {
		contextmenu: (e: MouseEvent) => {
			e.preventDefault();
			openCtxMenu(e, ...(resolve() as [Track, string, number | null]));
		},
		...(touch
			? {
					touchstart: (e: TouchEvent) => onCtxTouchStart(e, ...(resolve() as [Track, string, number | null])),
					touchend: onCtxTouchEnd,
					touchcancel: onCtxTouchEnd,
					touchmove: onCtxTouchMove,
				}
			: {}),
	};

	return bindings;
}
