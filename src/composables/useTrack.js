import { computed, toValue } from 'vue';
import { usePlayer } from './usePlayer'; // Assumes getTrackInfo and state remain here for now
import { useCover } from './useCover';

export function useTrack(trackOrPath) {
	const player = usePlayer();

	// Normalize input to a reactive path
	const path = computed(() => {
		const t = toValue(trackOrPath);
		return typeof t === 'string' ? t : t?.path;
	});

	// Reactive metadata lookup
	const info = computed(() => player.getTrackInfo(path.value));

	// Inject the cover composable
	const { coverUrl, onCoverError } = useCover(path);

	// Compute track states relative to global player state
	const isPlaying = computed(() => player.currentTrackPath.value === path.value);
	const isPaused = computed(() => player.isPaused.value);
	const isFavorite = computed(() => player.favorites.value.includes(path.value));
	const queueIndex = computed(() => player.queueIndex(path.value));
	const isNext = computed(() => player.queueState.value[0] === path.value);

	return {
		path,
		displayTitle: computed(() => info.value.display_title),
		displayArtist: computed(() => info.value.display_artist),
		durationStr: computed(() => info.value.duration_str),
		coverUrl,
		onCoverError,
		isPlaying,
		isPaused,
		isFavorite,
		queueIndex,
		isNext,
		toggleFavorite: () => {
			player.toggleFavorite(path.value);
			player.haptic();
		},
	};
}
