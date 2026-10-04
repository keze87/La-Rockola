import { ref, computed, toValue, type MaybeRefOrGetter } from 'vue';
import { apiUrl } from './useApi';
import type { Track } from '../types';

// Cachés globales compartidas en toda la app
const brokenCoversCache = ref<Set<string>>(new Set());
const coverBlobCache = new Map<string, string>(); // Guarda URLs de objeto para las portadas descargadas con éxito

export interface UseCoverOptions {
	size?: MaybeRefOrGetter<number | null | undefined>;
}

export function useCover(trackOrPath: MaybeRefOrGetter<Track | string | null>, options?: UseCoverOptions) {
	const path = computed(() => {
		const t = toValue(trackOrPath);
		return typeof t === 'string' ? t : t?.path;
	});

	const coverUrl = computed(() => {
		const currentPath = path.value;

		if (!currentPath || currentPath.startsWith('http')) return null;

		if (brokenCoversCache.value.has(currentPath)) return null;

		// Devolvemos la URL del blob en memoria si ya fue cacheada localmente
		if (coverBlobCache.has(currentPath)) {
			return coverBlobCache.get(currentPath);
		}

		const sizeVal = options?.size !== undefined ? toValue(options.size) : undefined;
		const query =
			sizeVal && sizeVal > 0
				? `/cover?path=${encodeURIComponent(currentPath)}&size=${sizeVal}`
				: `/cover?path=${encodeURIComponent(currentPath)}`;

		return apiUrl(query);
	});

	function onCoverError() {
		if (path.value) {
			brokenCoversCache.value.add(path.value);
			coverBlobCache.delete(path.value); // Limpiamos si falló
		}
	}

	return { coverUrl, onCoverError };
}
