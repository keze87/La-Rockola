import { ref, computed, toValue } from 'vue';

// Declared outside the function so the cache is shared across the entire app
const brokenCoversCache = ref(new Set());

export function useCover(trackOrPath) {
	const path = computed(() => {
		const t = toValue(trackOrPath);
		return typeof t === 'string' ? t : t?.path;
	});

	const coverUrl = computed(() => {
		const currentPath = path.value;
		if (!currentPath || currentPath.startsWith('http')) return null;
		if (brokenCoversCache.value.has(currentPath)) return null;

		return `/cover?path=${encodeURIComponent(currentPath)}`;
	});

	function onCoverError() {
		if (path.value) {
			brokenCoversCache.value.add(path.value);
		}
	}

	return {
		coverUrl,
		onCoverError,
	};
}
