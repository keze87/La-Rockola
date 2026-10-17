// Adaptador de Media Session del navegador para sincronizar carátula, título,
// estado de reproducción y teclas multimedia físicas con el sistema operativo.

import { apiUrl } from '../composables/useApi';
import type { Track } from '../types';

export interface MediaSessionActionCallbacks {
	pause: () => void;
	prev: () => void;
	skip: () => void;
	seek: (amount: number) => void;
	seekAbsolute: (position: number) => void;
	onOptimisticSeek?: (newPos: number) => void;
}

export function syncMediaSessionMetadata(
	trackPath: string | null,
	paused: boolean,
	getTrackInfo: (path: string) => Track
): void {
	if (!('mediaSession' in navigator)) return;

	if (trackPath) {
		const info = getTrackInfo(trackPath);
		const artworkSrc = !trackPath.startsWith('http')
			? `${window.location.origin}${apiUrl(`/cover?path=${encodeURIComponent(trackPath)}&size=512`)}`
			: null;

		navigator.mediaSession.metadata = new MediaMetadata({
			title: info.display_title || 'Desconocido',
			artist: info.display_artist || 'Desconocido',
			album: 'La Rockola del Carpincho',
			artwork: artworkSrc ? [{ src: artworkSrc, sizes: '512x512', type: 'image/jpeg' }] : [],
		});

		navigator.mediaSession.playbackState = paused ? 'paused' : 'playing';
	} else {
		navigator.mediaSession.metadata = null;
		navigator.mediaSession.playbackState = 'none';
	}
}

export function syncMediaSessionPosition(trackPath: string | null, totalDuration: number, currentPos: number): void {
	if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;

	if (totalDuration > 0 && trackPath) {
		try {
			navigator.mediaSession.setPositionState({
				duration: totalDuration,
				playbackRate: 1.0,
				position: Math.min(Math.max(0, currentPos), totalDuration),
			});
		} catch {
			// Ignoramos errores transitorios al cambiar de tema
		}
	}
}

export function bindMediaSessionHandlers(
	trackPath: string | null,
	isPausedFn: (() => boolean) | boolean,
	callbacks: MediaSessionActionCallbacks,
	getCurrentPos: () => number = () => 0,
	getDuration: () => number = () => 0
): void {
	if (!('mediaSession' in navigator)) return;

	const checkPaused = typeof isPausedFn === 'function' ? isPausedFn : () => isPausedFn;

	if (trackPath) {
		navigator.mediaSession.setActionHandler('play', () => {
			if (checkPaused()) callbacks.pause();
		});
		navigator.mediaSession.setActionHandler('pause', () => {
			if (!checkPaused()) callbacks.pause();
		});
		navigator.mediaSession.setActionHandler('previoustrack', () => callbacks.prev());
		navigator.mediaSession.setActionHandler('nexttrack', () => callbacks.skip());
		navigator.mediaSession.setActionHandler('seekbackward', (details) => {
			const amount = -(details.seekOffset ?? 10);
			const nextPos = Math.max(0, getCurrentPos() + amount);
			callbacks.onOptimisticSeek?.(nextPos);
			callbacks.seek(amount);
		});
		navigator.mediaSession.setActionHandler('seekforward', (details) => {
			const amount = details.seekOffset ?? 10;
			const nextPos = Math.min(getDuration(), getCurrentPos() + amount);
			callbacks.onOptimisticSeek?.(nextPos);
			callbacks.seek(amount);
		});
		try {
			navigator.mediaSession.setActionHandler('seekto', (details) => {
				if (details.seekTime !== undefined && details.seekTime !== null) {
					callbacks.onOptimisticSeek?.(details.seekTime);
					callbacks.seekAbsolute(details.seekTime);
				}
			});
		} catch {
			// seekto no está soportado en todos los navegadores
		}
	} else {
		navigator.mediaSession.setActionHandler('play', null);
		navigator.mediaSession.setActionHandler('pause', null);
		navigator.mediaSession.setActionHandler('previoustrack', null);
		navigator.mediaSession.setActionHandler('nexttrack', null);
		navigator.mediaSession.setActionHandler('seekbackward', null);
		navigator.mediaSession.setActionHandler('seekforward', null);
		try {
			navigator.mediaSession.setActionHandler('seekto', null);
		} catch {
			// seekto no está soportado en todos los navegadores
		}
	}
}
