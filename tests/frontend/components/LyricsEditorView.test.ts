import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import LyricsEditorView from '@/components/lyrics/LyricsEditorView.vue';
import { lyricsEditorTrack, isLyricsEditorOpen } from '@/stores/useUiStore';
import type { Track } from '@/types';

describe('LyricsEditorView.vue', () => {
	const sampleTrack: Track = {
		path: '/music/spinetta - bajan.flac',
		display_title: 'Bajan',
		display_artist: 'Pescado Rabioso',
		title: 'Bajan',
		artist: 'Pescado Rabioso',
	};

	let fetchMock: any;

	beforeEach(() => {
		lyricsEditorTrack.value = sampleTrack;
		isLyricsEditorOpen.value = true;

		fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.includes('/api/lyrics/token')) {
				return Promise.resolve({
					ok: true,
					json: () =>
						Promise.resolve({
							is_configured: true,
							status_text: 'Token activo',
							hours_remaining: 24,
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
									name: 'Apple Music (binimum) - Sincronizado palabra por palabra',
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

			return Promise.resolve({
				ok: true,
				json: () => Promise.resolve({ success: true }),
			} as unknown as Response);
		});

		global.fetch = fetchMock;
	});

	it('renders full-screen view with track title, search inputs, token button and provider selector', async () => {
		const wrapper = mount(LyricsEditorView);
		await flushPromises();

		// Header items
		expect(wrapper.text()).toContain('Taller de Letras');
		expect(wrapper.text()).toContain('Bajan');

		// Inputs preloaded
		const titleInput = wrapper.find('.search-title-input');
		const artistInput = wrapper.find('.search-artist-input');
		expect(titleInput.exists()).toBe(true);
		expect(artistInput.exists()).toBe(true);

		// Token button
		const tokenBtn = wrapper.find('.btn-token');
		expect(tokenBtn.exists()).toBe(true);

		// Provider selector dropdown
		const providerSelect = wrapper.find('.provider-select');
		expect(providerSelect.exists()).toBe(true);
	});

	it('navigates back and closes editor when clicking Volver button', async () => {
		const wrapper = mount(LyricsEditorView);
		await flushPromises();

		const backBtn = wrapper.find('.btn-back');
		expect(backBtn.exists()).toBe(true);

		await backBtn.trigger('click');
		expect(isLyricsEditorOpen.value).toBe(false);
	});

	it('allows streaming audio playback controls and seekbar interaction', async () => {
		const wrapper = mount(LyricsEditorView);
		await flushPromises();

		const playBtn = wrapper.find('.btn-play');
		expect(playBtn.exists()).toBe(true);

		const audio = wrapper.find('audio');
		expect(audio.exists()).toBe(true);
		expect(audio.attributes('src')).toContain('/stream?path=');

		// Mock audio element methods
		const audioEl = audio.element as HTMLAudioElement;
		const playMock = vi.fn().mockResolvedValue(undefined);
		const pauseMock = vi.fn();
		audioEl.play = playMock;
		audioEl.pause = pauseMock;

		// 1. Click play button
		await playBtn.trigger('click');
		expect(playMock).toHaveBeenCalled();

		// 2. Seekbar input
		const seekInput = wrapper.find('input[type="range"]');
		expect(seekInput.exists()).toBe(true);
		(seekInput.element as HTMLInputElement).value = '42';
		await seekInput.trigger('input');
		expect(audioEl.currentTime).toBe(42);
	});

	it('applies custom offset adjustments', async () => {
		const wrapper = mount(LyricsEditorView);
		await flushPromises();

		// Initial search executed
		expect(wrapper.find('textarea').element.value).toContain('{\\kf100}Tengo');

		const plusBtn = wrapper.find('.offset-plus-100-btn');
		expect(plusBtn.exists()).toBe(true);

		await plusBtn.trigger('click');
		// Offset shifted by 100ms (0.10s -> 0:00:01.10)
		expect(wrapper.find('textarea').element.value).toContain('0:00:01.10');
	});
});
