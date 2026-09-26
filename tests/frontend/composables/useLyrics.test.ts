import { describe, it, expect, vi } from 'vitest';
import { ref } from 'vue';
import { useLyrics } from '@/composables/useLyrics';

describe('useLyrics', () => {
	it('parses LRC timestamps correctly and synchronizes active line', async () => {
		const localTimePos = ref(0);
		const { lyrics, currentLyricLine, loadLyrics } = useLyrics({ localTimePos });

		const lrcContent = `
[00:05.00]Primera línea del fogón
[00:15.50]Segunda línea con acordes
[00:30.00]Tercera línea final
`;

		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			text: () => Promise.resolve(lrcContent),
		} as unknown as Response);

		await loadLyrics('/music/cancion.mp3');

		expect(lyrics.value.length).toBe(3);
		expect(lyrics.value[0]).toEqual({ time: 5, text: 'Primera línea del fogón' });
		expect(lyrics.value[1]).toEqual({ time: 15.5, text: 'Segunda línea con acordes' });
		expect(lyrics.value[2]).toEqual({ time: 30, text: 'Tercera línea final' });

		// Before first line
		localTimePos.value = 2;
		expect(currentLyricLine.value).toBe(' ');

		// At 10s: first line active
		localTimePos.value = 10;
		expect(currentLyricLine.value).toBe('Primera línea del fogón');

		// At 20s: second line active
		localTimePos.value = 20;
		expect(currentLyricLine.value).toBe('Segunda línea con acordes');

		// At 35s: third line active
		localTimePos.value = 35;
		expect(currentLyricLine.value).toBe('Tercera línea final');
	});

	it('handles empty lyrics or 404 responses gracefully', async () => {
		const localTimePos = ref(10);
		const { lyrics, currentLyricLine, loadLyrics } = useLyrics({ localTimePos });

		global.fetch = vi.fn().mockResolvedValue({
			ok: false,
			status: 404,
		} as unknown as Response);

		await loadLyrics('/music/sin_letra.mp3');
		expect(lyrics.value).toEqual([]);
		expect(currentLyricLine.value).toBeNull();
	});

	it('skips web/HTTP streams for lyrics fetching', async () => {
		const localTimePos = ref(0);
		const { lyrics, loadLyrics } = useLyrics({ localTimePos });

		const fetchSpy = vi.fn();
		global.fetch = fetchSpy;

		await loadLyrics('https://youtube.com/watch?v=123');
		expect(fetchSpy).not.toHaveBeenCalled();
		expect(lyrics.value).toEqual([]);
	});

	it('handles instrumental pauses and inserts carpincho emoji for short gaps', async () => {
		const localTimePos = ref(0);
		const { lyrics, loadLyrics } = useLyrics({ localTimePos });

		const lrcContent = `
[00:05.00]Primera
[00:10.00]
[00:11.50]Segunda
[00:15.00]
[00:18.00]Tercera
[00:20.00]
`;

		global.fetch = vi.fn().mockResolvedValue({
			ok: true,
			text: () => Promise.resolve(lrcContent),
		} as unknown as Response);

		await loadLyrics('/music/instrumental.mp3');

		// Check the items
		// 10.0s gap to 11.5s is 1.5s -> '🦦'
		expect(lyrics.value.find((l) => l.time === 10)?.text).toBe('🦦');
		// 15.0s gap to 18.0s is 3.0s -> ' '
		expect(lyrics.value.find((l) => l.time === 15)?.text).toBe(' ');
		// 20.0s has no subsequent lines -> ' '
		expect(lyrics.value.find((l) => l.time === 20)?.text).toBe(' ');
	});
});
