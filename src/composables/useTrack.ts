import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { useCover } from './useCover';
import { usePlayer } from './usePlayer';
import type { Track } from '../types';

export function useTrack(trackOrPath: MaybeRefOrGetter<Track | string>) {
	const player = usePlayer();

	// Normalize input to a reactive path
	const path = computed(() => {
		const t = toValue(trackOrPath);
		return typeof t === 'string' ? t : (t?.path ?? '');
	});

	// Reactive metadata lookup
	const info = computed(() => player.getTrackInfo(path.value));

	// Inject the cover composable
	const { coverUrl, onCoverError } = useCover(path);

	// Compute track states relative to global player state
	const isFavorite = computed(() => player.favorites.value.includes(path.value));
	const isNext = computed(() => player.queueState.value[0] === path.value);
	const isPaused = computed(() => player.isPaused.value);
	const isPlaying = computed(() => player.currentTrackPath.value === path.value);
	const queueIndex = computed(() => player.queueIndex(path.value));

	return {
		coverUrl,
		displayArtist: computed(() => info.value.display_artist),
		displayTitle: computed(() => info.value.display_title),
		durationStr: computed(() => info.value.duration_str),
		isFavorite,
		isNext,
		isPaused,
		isPlaying,
		onCoverError,
		path,
		queueIndex,
		trackInfo: info,
		toggleFavorite: () => {
			player.toggleFavorite(path.value);
			player.haptic();
		},
	};
}
