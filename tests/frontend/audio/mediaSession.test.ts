import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as androidHost from '@/composables/useAndroidHost';
import { bindMediaSessionHandlers, syncMediaSessionMetadata, syncMediaSessionPosition } from '@/audio/mediaSession';

describe('mediaSession.ts', () => {
	const originalMediaSession = (navigator as any).mediaSession;
	const originalMediaMetadata = (globalThis as any).MediaMetadata;

	let mockMediaSession: {
		metadata: any;
		playbackState: string;
		setPositionState: ReturnType<typeof vi.fn>;
		setActionHandler: ReturnType<typeof vi.fn>;
	};

	beforeEach(() => {
		mockMediaSession = {
			metadata: null,
			playbackState: 'none',
			setPositionState: vi.fn(),
			setActionHandler: vi.fn(),
		};
		Object.defineProperty(navigator, 'mediaSession', {
			configurable: true,
			value: mockMediaSession,
		});
		(globalThis as any).MediaMetadata = class MockMediaMetadata {
			title: string;
			artist: string;
			album: string;
			artwork: any[];
			constructor(init: any) {
				this.title = init.title;
				this.artist = init.artist;
				this.album = init.album;
				this.artwork = init.artwork;
			}
		};
	});

	afterEach(() => {
		vi.restoreAllMocks();
		if (originalMediaSession !== undefined) {
			Object.defineProperty(navigator, 'mediaSession', {
				configurable: true,
				value: originalMediaSession,
			});
		} else {
			delete (navigator as any).mediaSession;
		}
		if (originalMediaMetadata !== undefined) {
			(globalThis as any).MediaMetadata = originalMediaMetadata;
		} else {
			delete (globalThis as any).MediaMetadata;
		}
	});

	it('updates navigator.mediaSession normally on web', () => {
		vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(false);

		syncMediaSessionMetadata('/music/alma.mp3', false, (path) => ({
			path,
			display_title: 'Alma de Diamante',
			display_artist: 'Spinetta Jade',
		}));

		expect(mockMediaSession.metadata).not.toBeNull();
		expect(mockMediaSession.metadata.title).toBe('Alma de Diamante');
		expect(mockMediaSession.playbackState).toBe('playing');

		syncMediaSessionPosition('/music/alma.mp3', 180, 42, false);
		expect(mockMediaSession.setPositionState).toHaveBeenCalledWith({
			duration: 180,
			playbackRate: 1.0,
			position: 42,
		});

		bindMediaSessionHandlers('/music/alma.mp3', false, {
			pause: vi.fn(),
			prev: vi.fn(),
			skip: vi.fn(),
			seek: vi.fn(),
			seekAbsolute: vi.fn(),
		});
		expect(mockMediaSession.setActionHandler).toHaveBeenCalledWith('play', expect.any(Function));
		expect(mockMediaSession.setActionHandler).toHaveBeenCalledWith('nexttrack', expect.any(Function));
	});

	it('skips Android bridge notification sync on local Android server (handled natively by backend) and keeps it for remote servers', () => {
		vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const syncNotifSpy = vi.spyOn(androidHost, 'syncAndroidMediaNotification').mockResolvedValue();
		const syncPosSpy = vi.spyOn(androidHost, 'syncAndroidMediaPosition').mockResolvedValue();
		const prevRemote = androidHost.activeRemoteServerUrl.value;

		try {
			androidHost.activeRemoteServerUrl.value = null;

			syncMediaSessionMetadata(
				'/music/alma.mp3',
				false,
				(path) => ({
					path,
					display_title: 'Alma de Diamante',
					display_artist: 'Spinetta Jade',
				}),
				{ duration: 180, position: 15, isFavorite: true, isPauseAfter: false }
			);
			syncMediaSessionPosition('/music/alma.mp3', 180, 42, false);

			expect(syncNotifSpy).not.toHaveBeenCalled();
			expect(syncPosSpy).not.toHaveBeenCalled();
			expect(mockMediaSession.metadata).toBeNull();
			expect(mockMediaSession.playbackState).toBe('none');
			expect(mockMediaSession.setPositionState).not.toHaveBeenCalled();

			androidHost.activeRemoteServerUrl.value = 'http://192.168.1.50:1729';
			syncMediaSessionMetadata(
				'/music/alma.mp3',
				false,
				(path) => ({
					path,
					display_title: 'Alma de Diamante',
					display_artist: 'Spinetta Jade',
				}),
				{ duration: 180, position: 15, isFavorite: true, isPauseAfter: false }
			);
			syncMediaSessionPosition('/music/alma.mp3', 180, 42, false);

			expect(syncNotifSpy).toHaveBeenCalledWith(
				expect.objectContaining({
					title: 'Alma de Diamante',
					artist: 'Spinetta Jade',
					paused: false,
					isFavorite: true,
				})
			);
			expect(syncPosSpy).toHaveBeenCalledWith({
				duration: 180,
				position: 42,
				paused: false,
			});

			bindMediaSessionHandlers('/music/alma.mp3', false, {
				pause: vi.fn(),
				prev: vi.fn(),
				skip: vi.fn(),
				seek: vi.fn(),
				seekAbsolute: vi.fn(),
			});
			expect(mockMediaSession.setActionHandler).not.toHaveBeenCalled();

			// Al conectar a un servidor remoto con otra URL, la carátula debe apuntar al origen remoto
			const call = syncNotifSpy.mock.calls.at(-1)?.[0];
			expect(call?.coverUrl).toContain('http://192.168.1.50:1729/cover');
		} finally {
			androidHost.activeRemoteServerUrl.value = prevRemote;
		}
	});

	it('updates native Android media target when switching between host and remote servers', async () => {
		const { setApiOrigin, clearApiOrigin } = await import('@/composables/useApi');
		const { resetServerConnectionStore, setHostMode, setRemoteMode } =
			await import('@/stores/useServerConnectionStore');
		vi.spyOn(androidHost, 'isNativeAndroidHost').mockReturnValue(true);
		const syncTargetSpy = vi.spyOn(androidHost, 'syncAndroidMediaTarget').mockResolvedValue();

		resetServerConnectionStore();
		setRemoteMode('http://192.168.0.55:1729');
		setApiOrigin('http://192.168.0.55:1729');
		await androidHost.syncAndroidMediaTarget();
		expect(syncTargetSpy).toHaveBeenCalled();

		setHostMode();
		setApiOrigin('http://127.0.0.1:1729');
		await androidHost.syncAndroidMediaTarget();
		expect(syncTargetSpy).toHaveBeenCalledTimes(2);
		clearApiOrigin();
	});
});
