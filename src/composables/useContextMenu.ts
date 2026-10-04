import { computePosition, flip, shift, offset } from '@floating-ui/vue';
import { reactive, nextTick, toValue, type MaybeRefOrGetter, ref } from 'vue';
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

// El elemento que abrió el menú (típicamente una fila), para poder
// devolverle el foco del teclado al cerrarse. A nivel de módulo como ctxMenu,
// ya que solo existe una instancia del menú en toda la app.
let triggerEl: HTMLElement | null = null;

// Estado táctil guardado fuera del composable para persistir correctamente
let ctxLongPressTimer: ReturnType<typeof setTimeout> | null = null;
let touchStartX = 0;
let touchStartY = 0;
let ctxLongPressFired = false;

export const menuRef = ref<HTMLElement | null>(null);

export function useContextMenu() {
	function openCtxMenu(
		event: MouseEvent | TouchEvent,
		track: Track,
		source = 'library',
		index: number | null = null
	) {
		// Solo válido para manejadores invocados de forma sincrónica (un evento `contextmenu` real);
		// para pulsación larga táctil esto se captura antes en onCtxTouchStart,
		// ya que `currentTarget` queda en null cuando se dispara el setTimeout.
		if (event.currentTarget) triggerEl = event.currentTarget as HTMLElement;

		ctxMenu.track = track;
		ctxMenu.source = source;
		ctxMenu.index = index;

		// 1. Extraemos las coordenadas crudas
		const clientX = 'touches' in event ? (event.touches[0]?.clientX ?? 0) : event.clientX;
		const clientY = 'touches' in event ? (event.touches[0]?.clientY ?? 0) : event.clientY;

		// 2. Precargamos coordenadas para evitar el parpadeo en la esquina superior izquierda
		ctxMenu.x = clientX;
		ctxMenu.y = clientY;
		ctxMenu.visible = true;

		nextTick(() => {
			const menuElement = menuRef.value;
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

			// Movemos el foco del teclado al menú para que sea usable sin mouse
			(menuElement.querySelector('[role="menuitem"]') as HTMLElement)?.focus();
		});
	}

	function closeCtxMenu() {
		ctxMenu.visible = false;

		// Devolvemos el foco al elemento que abrió el menú, si todavía existe
		if (triggerEl && document.contains(triggerEl) && typeof triggerEl.focus === 'function') {
			triggerEl.focus();
		}
		triggerEl = null;
	}

	function onCtxTouchStart(e: TouchEvent, track: Track, source = 'library', index: number | null = null) {
		// Capturamos de forma sincrónica ahora: el navegador limpia `e.currentTarget`
		// apenas termina el evento touchstart, por lo que ya no estaría cuando corra el setTimeout.
		const el = e.currentTarget as HTMLElement;

		touchStartX = e.touches[0].screenX;
		touchStartY = e.touches[0].screenY;
		ctxLongPressFired = false;

		ctxLongPressTimer = setTimeout(() => {
			ctxLongPressFired = true;

			if (window.navigator.vibrate) window.navigator.vibrate([10, 30, 20]);

			triggerEl = el;
			openCtxMenu(e, track, source, index); // Le pasamos el evento original a openCtxMenu
		}, 500);
	}

	function onCtxTouchMove(e: TouchEvent) {
		if (!ctxLongPressTimer) return;

		const diffX = Math.abs(e.touches[0].screenX - touchStartX);
		const diffY = Math.abs(e.touches[0].screenY - touchStartY);

		// Cancelamos la pulsación larga si el dedo se mueve más de 10px
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

		// Si se abrió el menú contextual, evitamos el evento click posterior
		if (ctxLongPressFired && e && typeof e.preventDefault === 'function') {
			e.preventDefault();
		}
	}

	return { closeCtxMenu, ctxMenu, onCtxTouchEnd, onCtxTouchMove, onCtxTouchStart, openCtxMenu };
}

/**
 * Bindings de eventos listos para propagar (`v-on="bindings"`) en una fila de tema:
 * click derecho abre el menú contextual, y la pulsación larga táctil hace lo mismo.
 *
 * Acepta refs, getters o valores planos para track/source/index y los resuelve
 * en el momento del evento (no en setup), manteniéndose consistente incluso si
 * la fila se reutiliza para otros datos (ej. fila con `:key` estable en un v-for).
 *
 * Pasá `{ touch: false }` cuando el llamador maneje sus propios eventos táctiles
 * (ej. el swipe para borrar en la fila de reproducción), dejando solo el click derecho.
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
