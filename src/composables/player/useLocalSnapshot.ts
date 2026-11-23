// Snapshot local de arranque rápido para mostrar biblioteca, cola y pista actual
// inmediatamente mientras el servidor embebido (Python/FastAPI) termina de iniciar.

import { ref } from 'vue';
import { currentTracks, favorites, originalTracks, trackMap } from '../../stores/useLibraryStore';
import { currentTrackPath, duration } from '../../stores/usePlaybackStore';
import { queueState } from '../../stores/useQueueStore';
import type { Track } from '../../types';

export const BOOT_SNAPSHOT_STORAGE_KEY = 'rockola_boot_snapshot_v1';
export const MAX_SNAPSHOT_TRACKS = 80;

export const isHydratedFromSnapshot = ref<boolean>(false);

interface BootSnapshotPayload {
	version: 1;
	targetKey: string;
	savedAt: number;
	currentTrackPath: string | null;
	duration: number;
	queue: string[];
	favorites: string[];
	tracks: Track[];
}

export function clearSnapshotHydrationFlag(): void {
	isHydratedFromSnapshot.value = false;
}

export function saveBootSnapshot(targetKey: string): void {
	if (typeof localStorage === 'undefined') return;
	try {
		const sourceTracks = originalTracks.value.length > 0 ? originalTracks.value : currentTracks.value;
		const payload: BootSnapshotPayload = {
			version: 1,
			targetKey,
			savedAt: Date.now(),
			currentTrackPath: currentTrackPath.value,
			duration: Number.isFinite(duration.value) ? duration.value : 0,
			queue: queueState.value.slice(0, MAX_SNAPSHOT_TRACKS),
			favorites: favorites.value.slice(0, MAX_SNAPSHOT_TRACKS * 2),
			tracks: sourceTracks.slice(0, MAX_SNAPSHOT_TRACKS),
		};
		localStorage.setItem(BOOT_SNAPSHOT_STORAGE_KEY, JSON.stringify(payload));
	} catch {
		// Ignoramos errores de cuota o acceso restringido en localStorage
	}
}

export function hydrateFromBootSnapshot(targetKey: string): boolean {
	if (typeof localStorage === 'undefined') return false;
	try {
		const raw = localStorage.getItem(BOOT_SNAPSHOT_STORAGE_KEY);
		if (!raw) return false;
		const parsed = JSON.parse(raw) as Partial<BootSnapshotPayload> | null;
		if (!parsed || parsed.version !== 1 || parsed.targetKey !== targetKey) return false;
		if (!Array.isArray(parsed.tracks) && !Array.isArray(parsed.queue) && !parsed.currentTrackPath) {
			return false;
		}

		const tracks = Array.isArray(parsed.tracks) ? parsed.tracks.slice(0, MAX_SNAPSHOT_TRACKS) : [];
		if (tracks.length > 0 && originalTracks.value.length === 0) {
			originalTracks.value = tracks;
			currentTracks.value = tracks;
			const map: Record<string, Track> = {};
			for (const t of tracks) {
				if (t && typeof t.path === 'string') map[t.path] = t;
			}
			trackMap.value = map;
		}
		if (Array.isArray(parsed.queue) && queueState.value.length === 0) {
			queueState.value = parsed.queue;
		}
		if (Array.isArray(parsed.favorites) && favorites.value.length === 0) {
			favorites.value = parsed.favorites;
		}
		if (parsed.currentTrackPath && !currentTrackPath.value) {
			currentTrackPath.value = parsed.currentTrackPath;
		}
		if (typeof parsed.duration === 'number' && parsed.duration > 0 && duration.value === 0) {
			duration.value = parsed.duration;
		}
		isHydratedFromSnapshot.value = true;
		return true;
	} catch {
		return false;
	}
}
