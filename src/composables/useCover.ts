import { ref, computed, toValue, watch, type MaybeRefOrGetter } from 'vue';
import { apiOriginRef, apiUrl } from './useApi';
import { isNativeAndroidHost } from './useAndroidHost';
import type { Track } from '../types';

// Caché global compartida en toda la app para portadas no encontradas
const brokenCoversCache = ref<Set<string>>(new Set());

watch(apiOriginRef, () => {
	// Al conectarse o cambiar de origen (p. ej. tras el snapshot inicial), reintentar portadas
	brokenCoversCache.value.clear();
});

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

		// En Android nativo durante el snapshot local todavía no hay origen de servidor
		if (isNativeAndroidHost() && !apiOriginRef.value) return null;

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
