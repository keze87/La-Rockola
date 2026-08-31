import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useContextMenu, useContextMenuBindings, menuRef } from '@/composables/useContextMenu';
import type { Track } from '@/types';

describe('useContextMenu.ts', () => {
	const sampleTrack: Track = {
		path: '/m/tango.flac',
		display_title: 'Adiós Nonino',
		display_artist: 'Astor Piazzolla',
	};

	beforeEach(() => {
		const { closeCtxMenu } = useContextMenu();
		closeCtxMenu();
		vi.useFakeTimers();
	});

	it('openCtxMenu opens menu with mouse event coordinates and metadata', () => {
		const { ctxMenu, openCtxMenu } = useContextMenu();
		const mouseEvent = {
			clientX: 120,
			clientY: 240,
			currentTarget: document.createElement('div'),
		} as unknown as MouseEvent;

		openCtxMenu(mouseEvent, sampleTrack, 'library', 2);

		expect(ctxMenu.visible).toBe(true);
		expect(ctxMenu.x).toBe(120);
		expect(ctxMenu.y).toBe(240);
		expect(ctxMenu.track).toEqual(sampleTrack);
		expect(ctxMenu.source).toBe('library');
		expect(ctxMenu.index).toBe(2);
	});

	it('openCtxMenu handles touch event coordinates', () => {
		const { ctxMenu, openCtxMenu } = useContextMenu();
		const touchEvent = {
			touches: [{ clientX: 85, clientY: 190 }],
		} as unknown as TouchEvent;

		openCtxMenu(touchEvent, sampleTrack, 'queue', 0);

		expect(ctxMenu.visible).toBe(true);
		expect(ctxMenu.x).toBe(85);
		expect(ctxMenu.y).toBe(190);
	});

	it('closeCtxMenu closes menu and restores triggerEl focus', () => {
		const { ctxMenu, openCtxMenu, closeCtxMenu } = useContextMenu();
		const trigger = document.createElement('button');
		document.body.appendChild(trigger);
		const focusSpy = vi.spyOn(trigger, 'focus');

		openCtxMenu(
			{ clientX: 10, clientY: 10, currentTarget: trigger } as unknown as MouseEvent,
			sampleTrack
		);
		expect(ctxMenu.visible).toBe(true);

		closeCtxMenu();
		expect(ctxMenu.visible).toBe(false);
		expect(focusSpy).toHaveBeenCalled();
		trigger.remove();
	});

	it('onCtxTouchStart triggers long press after 500ms and calls vibrate', () => {
		const vibrateSpy = vi.fn();
		Object.defineProperty(window.navigator, 'vibrate', { value: vibrateSpy, configurable: true });

		const { ctxMenu, onCtxTouchStart } = useContextMenu();
		const touchEvent = {
			touches: [{ screenX: 50, screenY: 50 }],
			currentTarget: document.createElement('div'),
		} as unknown as TouchEvent;

		onCtxTouchStart(touchEvent, sampleTrack, 'library', 1);
		expect(ctxMenu.visible).toBe(false);

		vi.advanceTimersByTime(500);

		expect(ctxMenu.visible).toBe(true);
		expect(vibrateSpy).toHaveBeenCalledWith([10, 30, 20]);
	});

	it('onCtxTouchMove cancels long press if movement exceeds 10px', () => {
		const { ctxMenu, onCtxTouchStart, onCtxTouchMove } = useContextMenu();
		const touchStartEvent = {
			touches: [{ screenX: 50, screenY: 50 }],
			currentTarget: document.createElement('div'),
		} as unknown as TouchEvent;

		onCtxTouchStart(touchStartEvent, sampleTrack);

		// Move 20px
		onCtxTouchMove({
			touches: [{ screenX: 70, screenY: 50 }],
		} as unknown as TouchEvent);

		vi.advanceTimersByTime(500);
		expect(ctxMenu.visible).toBe(false);
	});

	it('useContextMenuBindings creates contextmenu and touch handlers', () => {
		const bindings = useContextMenuBindings(sampleTrack, 'library', 0);
		expect(bindings.contextmenu).toBeDefined();
		expect(bindings.touchstart).toBeDefined();
		expect(bindings.touchmove).toBeDefined();
		expect(bindings.touchend).toBeDefined();

		const preventDefault = vi.fn();
		bindings.contextmenu({
			preventDefault,
			clientX: 100,
			clientY: 150,
		} as unknown as MouseEvent);

		expect(preventDefault).toHaveBeenCalled();
	});

	it('useContextMenuBindings excludes touch when touch: false', () => {
		const bindings = useContextMenuBindings(sampleTrack, 'queue', null, { touch: false });
		expect(bindings.contextmenu).toBeDefined();
		expect((bindings as any).touchstart).toBeUndefined();
	});
});
