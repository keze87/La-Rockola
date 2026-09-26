import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useHaptics } from '@/composables/player/useHaptics';

const { mockVibrate } = vi.hoisted(() => ({
	mockVibrate: vi.fn(),
}));

vi.mock('@vueuse/core', async (importOriginal) => {
	const actual = await importOriginal<typeof import('@vueuse/core')>();
	return {
		...actual,
		useVibrate: () => ({ vibrate: mockVibrate }),
	};
});

describe('useHaptics.ts', () => {
	const originalAudioContext = window.AudioContext;
	const originalVibrate = (navigator as any).vibrate;

	beforeEach(() => {
		vi.clearAllMocks();
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		if (originalVibrate !== undefined) {
			Object.defineProperty(navigator, 'vibrate', { value: originalVibrate, configurable: true });
		} else {
			delete (navigator as any).vibrate;
		}
		window.AudioContext = originalAudioContext;
	});

	it('uses navigator.vibrate when available', () => {
		Object.defineProperty(navigator, 'vibrate', {
			value: vi.fn(),
			configurable: true,
		});

		const { haptic } = useHaptics();
		haptic(false);
		expect(mockVibrate).toHaveBeenCalledWith(10);

		haptic(true);
		expect(mockVibrate).toHaveBeenCalledWith([10, 30, 20]);
	});

	it('falls back to Web Audio API when navigator.vibrate is unavailable', () => {
		vi.stubGlobal('navigator', {
			...navigator,
			vibrate: undefined,
		});

		const mockGain = {
			setValueAtTime: vi.fn(),
			exponentialRampToValueAtTime: vi.fn(),
		};
		const mockFreq = {
			setValueAtTime: vi.fn(),
		};
		const mockOsc = {
			connect: vi.fn(),
			start: vi.fn(),
			stop: vi.fn(),
			frequency: mockFreq,
			onended: null as (() => void) | null,
		};
		const mockCtx = {
			currentTime: 10,
			destination: {},
			createOscillator: vi.fn(() => mockOsc),
			createGain: vi.fn(() => ({
				gain: mockGain,
				connect: vi.fn(),
			})),
			close: vi.fn(),
		};

		window.AudioContext = class {
			constructor() {
				return mockCtx;
			}
		} as any;

		const { haptic } = useHaptics();
		haptic(false);
		expect(mockCtx.createOscillator).toHaveBeenCalled();
		expect(mockFreq.setValueAtTime).toHaveBeenCalledWith(400, 10);
		expect(mockGain.setValueAtTime).toHaveBeenCalledWith(0.01, 10);

		// Trigger onended to close context
		if (mockOsc.onended) {
			mockOsc.onended();
			expect(mockCtx.close).toHaveBeenCalled();
		}

		// Test heavy audio haptic
		haptic(true);
		expect(mockFreq.setValueAtTime).toHaveBeenCalledWith(200, 10);
		expect(mockGain.setValueAtTime).toHaveBeenCalledWith(0.03, 10);
	});

	it('fails gracefully when AudioContext throws', () => {
		vi.stubGlobal('navigator', {
			...navigator,
			vibrate: undefined,
		});
		window.AudioContext = class {
			constructor() {
				throw new Error('Not allowed');
			}
		} as any;

		const { haptic } = useHaptics();
		expect(() => haptic(false)).not.toThrow();
	});
});
