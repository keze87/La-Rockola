import { describe, expect, it, vi } from 'vitest';
import { createFaintNoiseBlob, getSilentBlobUrl } from '../../src/audio/morseKeepalive';
import {
	clearTrackChanging,
	getBufferedAhead,
	isChangingTrack,
	markTrackChanging,
	playWhenBuffered,
} from '../../src/audio/localAudioEngine';
import {
	bindMediaSessionHandlers,
	syncMediaSessionMetadata,
	syncMediaSessionPosition,
} from '../../src/audio/mediaSession';
import { usePlaybackStore } from '../../src/stores/usePlaybackStore';
import { useQueueStore } from '../../src/stores/useQueueStore';
import { useLibraryStore } from '../../src/stores/useLibraryStore';
import { useRadioStore } from '../../src/stores/useRadioStore';
import { useUiStore } from '../../src/stores/useUiStore';

describe('Stage 4 — Modular Audio Engine & Domain Stores', () => {
	it('genera un blob WAV válido con código morse CARPINCHO en morseKeepalive', () => {
		const blob = createFaintNoiseBlob();
		expect(blob).toBeInstanceOf(Blob);
		expect(blob.type).toBe('audio/wav');
		expect(blob.size).toBeGreaterThan(44);

		const url = getSilentBlobUrl();
		expect(typeof url).toBe('string');
	});

	it('calcula buffer ahead y administra estado de transición en localAudioEngine', () => {
		markTrackChanging();
		expect(isChangingTrack.value).toBe(true);
		clearTrackChanging();
		expect(isChangingTrack.value).toBe(false);

		const mockAudio = {
			currentTime: 5,
			duration: 30,
			buffered: {
				length: 1,
				start: () => 0,
				end: () => 15,
			},
			play: vi.fn().mockResolvedValue(undefined),
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
		} as unknown as HTMLAudioElement;

		expect(getBufferedAhead(mockAudio)).toBe(10);
		playWhenBuffered(mockAudio, 6, 500, false);
		expect(mockAudio.play).toHaveBeenCalled();
	});

	it('sincroniza metadatos, posición y acciones en mediaSession', () => {
		const setActionHandler = vi.fn();
		const setPositionState = vi.fn();
		Object.defineProperty(navigator, 'mediaSession', {
			configurable: true,
			writable: true,
			value: {
				metadata: null,
				playbackState: 'none',
				setActionHandler,
				setPositionState,
			},
		});
		if (typeof globalThis.MediaMetadata === 'undefined') {
			// @ts-expect-error polyfill para entorno de test
			globalThis.MediaMetadata = class {
				title: string;
				artist: string;
				album: string;
				artwork: unknown[];
				constructor(init: { title: string; artist: string; album: string; artwork: unknown[] }) {
					this.title = init.title;
					this.artist = init.artist;
					this.album = init.album;
					this.artwork = init.artwork;
				}
			};
		}

		syncMediaSessionMetadata('/music/test.mp3', false, () => ({
			path: '/music/test.mp3',
			display_title: 'Zamba del Carpincho',
			display_artist: 'Los Esteros',
		}));
		expect(navigator.mediaSession.playbackState).toBe('playing');

		syncMediaSessionPosition('/music/test.mp3', 120, 30);
		expect(setPositionState).toHaveBeenCalledWith({
			duration: 120,
			playbackRate: 1.0,
			position: 30,
		});

		bindMediaSessionHandlers('/music/test.mp3', false, {
			pause: vi.fn(),
			prev: vi.fn(),
			skip: vi.fn(),
			seek: vi.fn(),
			seekAbsolute: vi.fn(),
			onOptimisticSeek: vi.fn(),
		});
		expect(setActionHandler).toHaveBeenCalled();
	});

	it('expone stores reactivos cohesivos por dominio sin duplicar estado', () => {
		const playback = usePlaybackStore();
		const queue = useQueueStore();
		const library = useLibraryStore();
		const radio = useRadioStore();
		const ui = useUiStore();

		playback.volume.value = 65;
		expect(playback.volIcon.value).toBe('volume_up');

		queue.queueState.value = ['/music/a.mp3'];
		expect(queue.queueState.value).toEqual(['/music/a.mp3']);

		library.librarySearchQuery.value = 'chacarera';
		expect(library.librarySearchQuery.value).toBe('chacarera');

		radio.djBaraEnabled.value = true;
		expect(radio.djBaraEnabled.value).toBe(true);

		ui.activeTab.value = 'queue';
		expect(ui.activeTab.value).toBe('queue');
	});
});
