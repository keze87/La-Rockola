// Motor de reproducción de audio HTML5 local: gestiona el búfer progresivo,
// transiciones de pista, precarga inteligente y recuperación ante microcortes.

import { ref } from 'vue';
import { apiUrl } from '../composables/useApi';

export const isChangingTrack = ref<boolean>(false);
let changeTrackTimer: ReturnType<typeof setTimeout> | null = null;
let bufferWaitCleanup: (() => void) | null = null;

export function markTrackChanging(): void {
	isChangingTrack.value = true;
	if (changeTrackTimer) clearTimeout(changeTrackTimer);
	changeTrackTimer = setTimeout(() => {
		isChangingTrack.value = false;
	}, 2000);
}

export function clearTrackChanging(): void {
	isChangingTrack.value = false;
	if (changeTrackTimer) {
		clearTimeout(changeTrackTimer);
		changeTrackTimer = null;
	}
}

export function cleanupBufferWait(): void {
	if (bufferWaitCleanup) {
		bufferWaitCleanup();
		bufferWaitCleanup = null;
	}
}

export function getBufferedAhead(lp: HTMLAudioElement): number {
	const current = lp.currentTime || 0;
	for (let i = 0; i < lp.buffered.length; i++) {
		if (lp.buffered.start(i) <= current && current <= lp.buffered.end(i)) {
			return lp.buffered.end(i) - current;
		}
	}
	return 0;
}

export function playWhenBuffered(
	lp: HTMLAudioElement,
	minBufferSeconds = 6,
	maxWaitMs = 2500,
	isPausedOrGetter: (() => boolean) | boolean = false
): void {
	cleanupBufferWait();

	const checkPaused = typeof isPausedOrGetter === 'function' ? isPausedOrGetter : () => isPausedOrGetter;
	if (checkPaused()) return;

	let started = false;

	const doPlay = () => {
		if (started || checkPaused()) return;
		started = true;
		cleanupBufferWait();
		lp.play().catch(() => {});
	};

	const checkBuffer = () => {
		if (started || checkPaused()) return;
		const dur = lp.duration || 0;
		const ahead = getBufferedAhead(lp);
		const target = dur > 0 ? Math.min(minBufferSeconds, dur) : minBufferSeconds;

		if (ahead >= target) {
			doPlay();
		}
	};

	const onCanPlayThrough = () => doPlay();
	const onProgress = () => checkBuffer();
	const onLoadedMetadata = () => checkBuffer();

	// Timeout de seguridad para no congelar indefinidamente si la red anda lenta
	const timeout = setTimeout(() => {
		doPlay();
	}, maxWaitMs);

	bufferWaitCleanup = () => {
		clearTimeout(timeout);
		lp.removeEventListener('progress', onProgress);
		lp.removeEventListener('canplaythrough', onCanPlayThrough);
		lp.removeEventListener('loadedmetadata', onLoadedMetadata);
	};

	lp.addEventListener('progress', onProgress);
	lp.addEventListener('canplaythrough', onCanPlayThrough);
	lp.addEventListener('loadedmetadata', onLoadedMetadata);

	checkBuffer();
}

export function prefetchNextTrack(path: string | null | undefined): void {
	if (!path || path.startsWith('http')) return;
	const url = apiUrl('/stream?path=' + encodeURIComponent(path));
	// Precarga los primeros 4MB del próximo tema para que arranque al toque
	fetch(url, { headers: { Range: 'bytes=0-4194303' } }).catch(() => {});
}
