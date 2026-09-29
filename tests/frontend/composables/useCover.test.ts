import { describe, it, expect } from 'vitest';
import { useCover } from '@/composables/useCover';

describe('useCover', () => {
	it('generates encoded cover URL for local audio paths', () => {
		const path = '/music/Rock Nacional/Charly García - Clics Modernos.flac';
		const { coverUrl } = useCover(path);

		expect(coverUrl.value).toBe(
			'/cover?path=%2Fmusic%2FRock%20Nacional%2FCharly%20Garc%C3%ADa%20-%20Clics%20Modernos.flac'
		);
	});

	it('returns null for HTTP/YouTube stream URLs', () => {
		const { coverUrl } = useCover('https://youtube.com/watch?v=123');
		expect(coverUrl.value).toBeNull();
	});

	it('returns null for empty or null paths', () => {
		const { coverUrl: nullUrl } = useCover(null);
		expect(nullUrl.value).toBeNull();

		const { coverUrl: emptyUrl } = useCover('');
		expect(emptyUrl.value).toBeNull();
	});

	it('marks broken covers in cache when onCoverError is invoked', () => {
		const path = '/music/broken_cover.mp3';
		const { coverUrl, onCoverError } = useCover(path);

		expect(coverUrl.value).not.toBeNull();

		onCoverError();

		expect(coverUrl.value).toBeNull();
	});

	it('appends size query parameter when size option is provided', () => {
		const path = '/music/song.mp3';
		const { coverUrl: url256 } = useCover(path, { size: 256 });
		expect(url256.value).toBe('/cover?path=%2Fmusic%2Fsong.mp3&size=256');

		const { coverUrl: url512 } = useCover(path, { size: 512 });
		expect(url512.value).toBe('/cover?path=%2Fmusic%2Fsong.mp3&size=512');

		const { coverUrl: urlOriginal } = useCover(path, { size: null });
		expect(urlOriginal.value).toBe('/cover?path=%2Fmusic%2Fsong.mp3');
	});
});
