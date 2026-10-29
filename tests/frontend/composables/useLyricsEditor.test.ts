import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useLyricsEditor, shiftAssTimestamps } from '@/composables/useLyricsEditor';
import type { Track } from '@/types';

describe('useLyricsEditor composable', () => {
	const mockTrack: Track = {
		path: '/music/spinetta - bajan.flac',
		display_title: 'Bajan',
		display_artist: 'Pescado Rabioso',
		title: 'Bajan',
		artist: 'Pescado Rabioso',
	};

	let fetchMock: any;

	beforeEach(() => {
		fetchMock = vi.fn().mockImplementation((url: string, opts?: any) => {
			if (url.includes('/api/lyrics/token')) {
				if (opts?.method === 'POST') {
					return Promise.resolve({
						ok: true,
						json: () =>
							Promise.resolve({ success: true, status_text: 'Token guardado', hours_remaining: 72 }),
					} as unknown as Response);
				}
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							is_configured: true,
							status_text: 'Token activo',
							hours_remaining: 48,
						}),
				} as unknown as Response);
			}

			if (url.includes('/api/lyrics/content')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							exists: false,
							content: '',
							format: '',
						}),
				} as unknown as Response);
			}

			if (url.includes('/api/lyrics/search')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							title: 'Bajan',
							artist: 'Pescado Rabioso',
							providers: [
								{
									provider: 'binimum',
									name: 'Apple Music (binimum)',
									has_syllables: true,
									ass: '[Events]\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\kf100}Tengo {\\kf100}tiempo',
								},
								{
									provider: 'lrclib',
									name: 'LRCLib',
									has_syllables: false,
									ass: '[Events]\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Tengo tiempo para saber',
								},
							],
						}),
				} as unknown as Response);
			}

			if (url.includes('/api/lyrics/save')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							success: true,
							path: '/music/spinetta - bajan.ass',
						}),
				} as unknown as Response);
			}

			return Promise.resolve({
				ok: true,
				json: () => Promise.resolve({}),
			} as unknown as Response);
		});

		global.fetch = fetchMock;
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('initializes with preloaded track metadata and audio stream url', () => {
		const editor = useLyricsEditor(mockTrack);
		expect(editor.searchTitle.value).toBe('Bajan');
		expect(editor.searchArtist.value).toBe('Pescado Rabioso');
		expect(editor.audioStreamUrl.value).toContain('/stream?path=');
		expect(editor.audioStreamUrl.value).toContain(encodeURIComponent(mockTrack.path));
	});

	it('searches BetterLyrics and loads pre-converted ASS providers', async () => {
		const editor = useLyricsEditor(mockTrack);
		await editor.searchLyrics();

		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/lyrics/search?title=Bajan&artist=Pescado%20Rabioso')
		);
		expect(editor.providers.value.length).toBe(2);
		expect(editor.selectedProvider.value).toBe('binimum');
		expect(editor.editorContent.value).toContain('{\\kf100}Tengo');
	});

	it('switches provider and updates editor content without frontend conversions', async () => {
		const editor = useLyricsEditor(mockTrack);
		await editor.searchLyrics();

		editor.selectProvider('lrclib');
		expect(editor.selectedProvider.value).toBe('lrclib');
		expect(editor.editorContent.value).toContain('Tengo tiempo para saber');
	});

	it('shifts ASS dialogue timestamps with custom offset', () => {
		const sampleAss = `[Events]
Dialogue: 0,0:00:01.50,0:00:03.80,Default,,0,0,0,,Hola
Dialogue: 0,0:01:10.00,0:01:15.25,Default,,0,0,0,,Mundo`;

		// +500 ms (0.50 s)
		const shiftedPlus = shiftAssTimestamps(sampleAss, 500);
		expect(shiftedPlus).toContain('Dialogue: 0,0:00:02.00,0:00:04.30,Default,,0,0,0,,Hola');
		expect(shiftedPlus).toContain('Dialogue: 0,0:01:10.50,0:01:15.75,Default,,0,0,0,,Mundo');

		// -1000 ms (-1.00 s)
		const shiftedMinus = shiftAssTimestamps(sampleAss, -1000);
		expect(shiftedMinus).toContain('Dialogue: 0,0:00:00.50,0:00:02.80,Default,,0,0,0,,Hola');
		expect(shiftedMinus).toContain('Dialogue: 0,0:01:09.00,0:01:14.25,Default,,0,0,0,,Mundo');

		// Clamps below zero to 0:00:00.00
		const clamped = shiftAssTimestamps(sampleAss, -5000);
		expect(clamped).toContain('Dialogue: 0,0:00:00.00,0:00:00.00,Default,,0,0,0,,Hola');
	});

	it('finds and replaces text in editor content', () => {
		const editor = useLyricsEditor(mockTrack);
		editor.editorContent.value = 'Hola mundo, chau mundo';

		editor.findText.value = 'mundo';
		editor.replaceText.value = 'carpincho';

		expect(editor.matchCount.value).toBe(2);

		editor.replaceNext();
		expect(editor.editorContent.value).toBe('Hola carpincho, chau mundo');

		editor.replaceAll();
		expect(editor.editorContent.value).toBe('Hola carpincho, chau carpincho');
	});

	it('detects changes and triggers diff modal when overwriting existing file', async () => {
		fetchMock.mockImplementationOnce((url: string) => {
			if (url.includes('/api/lyrics/content')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							exists: true,
							content: '[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Original',
							format: 'ass',
						}),
				} as unknown as Response);
			}
			return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
		});

		const editor = useLyricsEditor(mockTrack);
		await editor.loadInitialLyrics();

		expect(editor.editorContent.value).toContain('Original');
		expect(editor.hasChanges.value).toBe(false);

		// Make an edit
		editor.editorContent.value = '[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Modificado';
		expect(editor.hasChanges.value).toBe(true);

		// Save triggers diff modal because existing file would be overwritten
		await editor.saveLyrics();
		expect(editor.isDiffModalOpen.value).toBe(true);

		// Confirm save persists custom edited file
		await editor.confirmSave();
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/lyrics/save',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({
					path: mockTrack.path,
					content: editor.editorContent.value,
					format: 'ass',
				}),
			})
		);
		expect(editor.isDiffModalOpen.value).toBe(false);
	});

	it('saves and checks BetterLyrics token', async () => {
		const editor = useLyricsEditor(mockTrack);
		await editor.loadTokenStatus();

		expect(editor.tokenStatus.value.is_configured).toBe(true);
		expect(editor.tokenStatus.value.hours_remaining).toBe(48);

		await editor.saveToken('eyJhbGciOiJIUzI1NiJ9.newtoken');
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/lyrics/token',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ token: 'eyJhbGciOiJIUzI1NiJ9.newtoken' }),
			})
		);
	});
});
