import { describe, it, expect, beforeEach, beforeAll, vi } from 'vitest';
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts';
import {
	currentTrackPath,
	duration,
	favorites,
	isFogonMode,
	localTimePos,
	serverMuted,
	volume,
} from '@/composables/player/state';
import { useContextMenu } from '@/composables/useContextMenu';

describe('useKeyboardShortcuts.ts', () => {
	let fetchMock: any;

	beforeAll(() => {
		useKeyboardShortcuts();
	});

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;

		currentTrackPath.value = null;
		duration.value = 200;
		favorites.value = [];
		isFogonMode.value = false;
		localTimePos.value = 50;
		serverMuted.value = false;
		volume.value = 80;
	});

	function dispatchKey(key: string, options: Partial<KeyboardEventInit> = {}) {
		const event = new KeyboardEvent('keydown', {
			key,
			bubbles: true,
			cancelable: true,
			...options,
		});
		window.dispatchEvent(event);
	}

	it('triggers pause on Space key', () => {
		dispatchKey(' ');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'pause' }) })
		);
	});

	it('seeks forward on ArrowRight and skips with Shift+ArrowRight', () => {
		// ArrowRight (seek +10)
		dispatchKey('ArrowRight');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'seek', amount: 10 }) })
		);
		expect(localTimePos.value).toBe(60);

		// Shift + ArrowRight (skip)
		dispatchKey('ArrowRight', { shiftKey: true });
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'skip' }) })
		);
	});

	it('seeks backward on ArrowLeft and goes previous with Shift+ArrowLeft', () => {
		// ArrowLeft (seek -10)
		dispatchKey('ArrowLeft');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'seek', amount: -10 }) })
		);

		// Shift + ArrowLeft (prev)
		dispatchKey('ArrowLeft', { shiftKey: true });
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'prev' }) })
		);
	});

	it('adjusts volume with ArrowUp and ArrowDown', () => {
		dispatchKey('ArrowUp');
		expect(volume.value).toBe(85);
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'set_volume', vollevel: 85 }) })
		);

		dispatchKey('ArrowDown');
		expect(volume.value).toBe(80);
	});

	it('toggles mute with m or M key', () => {
		dispatchKey('m');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'set_mute', state: true }) })
		);
	});

	it('toggles fogon mode with f or F key', () => {
		dispatchKey('f');
		expect(isFogonMode.value).toBe(true);

		dispatchKey('f');
		expect(isFogonMode.value).toBe(false);
	});

	it('toggles favorite for current track with l or L key', () => {
		currentTrackPath.value = '/m/song.mp3';
		dispatchKey('l');

		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'toggle_favorite', path: '/m/song.mp3' }) })
		);
	});

	it('skips on n/N and goes previous on p/P', () => {
		dispatchKey('n');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'skip' }) })
		);

		dispatchKey('p');
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({ body: JSON.stringify({ cmd: 'prev' }) })
		);
	});

	it('handles Escape key to dismiss fogon mode and context menu', () => {
		const { ctxMenu, openCtxMenu } = useContextMenu();
		isFogonMode.value = true;
		openCtxMenu({ clientX: 0, clientY: 0 } as any, { path: '/m/1.mp3' } as any);

		dispatchKey('Escape');
		expect(isFogonMode.value).toBe(false);
		expect(ctxMenu.visible).toBe(false);
	});

	it('ignores keystrokes when typing in an input element', () => {
		const input = document.createElement('input');
		document.body.appendChild(input);

		const event = new KeyboardEvent('keydown', {
			key: ' ',
			bubbles: true,
			cancelable: true,
		});
		input.dispatchEvent(event);

		expect(fetchMock).not.toHaveBeenCalled();
		input.remove();
	});
});
