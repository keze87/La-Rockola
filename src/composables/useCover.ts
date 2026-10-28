import { ref, computed, toValue, type MaybeRefOrGetter } from 'vue';
import { apiUrl } from './useApi';
import type { Track } from '../types';

// Caché global compartida en toda la app para portadas no encontradas
const brokenCoversCache = ref<Set<string>>(new Set());

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
		}
	}

	return { coverUrl, onCoverError };
}
