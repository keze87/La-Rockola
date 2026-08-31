import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useMpvWindow } from '@/composables/player/useMpvWindow';
import { mpvVisible } from '@/composables/player/state';

describe('useMpvWindow.ts', () => {
	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok' }),
		} as unknown as Response);
		global.fetch = fetchMock;
	});

	it('calls showMpv when mpv is currently hidden', async () => {
		mpvVisible.value = false;
		const { toggleMpvVisibility } = useMpvWindow();

		await toggleMpvVisibility();
		expect(fetchMock).toHaveBeenCalledWith('/mpv/show', expect.objectContaining({ method: 'POST' }));
	});

	it('calls hideMpv when mpv is currently visible', async () => {
		mpvVisible.value = true;
		const { toggleMpvVisibility } = useMpvWindow();

		await toggleMpvVisibility();
		expect(fetchMock).toHaveBeenCalledWith('/mpv/hide', expect.objectContaining({ method: 'POST' }));
	});

	it('handles errors when API call fails', async () => {
		global.fetch = vi.fn().mockRejectedValue(new Error('MPV socket failed'));
		const { toggleMpvVisibility } = useMpvWindow();

		await expect(toggleMpvVisibility()).resolves.not.toThrow();
	});
});
