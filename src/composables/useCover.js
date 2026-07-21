import { ref, computed, toValue } from 'vue';

// Shared global caches across the entire app
const brokenCoversCache = ref(new Set());
const coverBlobCache = new Map(); // Stores object URLs for successfully fetched covers

export function useCover(trackOrPath) {
	const path = computed(() => {
		const t = toValue(trackOrPath);
		return typeof t === 'string' ? t : t?.path;
	});

	const coverUrl = computed(() => {
		const currentPath = path.value;
		if (!currentPath || currentPath.startsWith('http')) return null;
		if (brokenCoversCache.value.has(currentPath)) return null;

		// Return memoized blob URL if already cached locally
		if (coverBlobCache.has(currentPath)) {
			return coverBlobCache.get(currentPath);
		}

		return `/cover?path=${encodeURIComponent(currentPath)}`;
	});

	function onCoverError() {
		if (path.value) {
			brokenCoversCache.value.add(path.value);
			coverBlobCache.delete(path.value); // Clean up if it failed
		}
	}

	return {
		coverUrl,
		onCoverError,
	};
}
