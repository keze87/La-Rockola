import {
	activeTab,
	currentTrackPath,
	currentTracks,
	djCarpinchoEnabled,
	djNextTrack,
	djSafeModeEnabled,
	duration,
	favorites,
	historyState,
	ignoreServerTimeUntil,
	isDraggingSeek,
	isFogonMode,
	isPaused,
	isPlaying,
	isScanning,
	librarySearchQuery,
	listenLocally,
	localPlayerRef,
	localTimePos,
	mpvVisible,
	originalTracks,
	pauseAfterPath,
	queueState,
	serverMuted,
	showFogonVolume,
	timePos,
	topPlayedState,
	volIcon,
	volume,
} from './player/state';

import { useCommands } from './player/useCommands';
import { useHaptics } from './player/useHaptics';
import { useLibrary } from './player/useLibrary';
import { useLocalPlayback } from './player/useLocalPlayback';
import { useMpvWindow } from './player/useMpvWindow';
import { useQueue } from './player/useQueue';
import { useSocket } from './player/useSocket';
import { useTabs } from './player/useTabs';
import { useToasts } from './player/useToasts';

// The single public entry point for player state/behavior, used throughout
// the app exactly as before (`const { ... } = usePlayer()`). Internally
// it's now just a composition root: each concern (transport, library,
// queue, local playback, toasts, ...) lives in its own file under
// ./player/, and this function wires them together and re-exports the
// same flat API so no consuming component needs to change.
export function usePlayer() {
	const { _sendLocalPlayerUpdate, setVolume } = useLocalPlayback();
	const { connectWebSocket } = useSocket();
	const { getTrackInfo, loadLibrary, normalizeString, queueIndex, sortLibrary } = useLibrary();
	const { handleLibraryClick, toggleFavorite, togglePauseAfterCurrent, toggleQueue } = useQueue();
	const { haptic } = useHaptics();
	const { sendCmd } = useCommands();
	const { showToast } = useToasts();
	const { switchTab } = useTabs();
	const { toggleMpvVisibility } = useMpvWindow();

	return {
		_sendLocalPlayerUpdate,
		activeTab,
		connectWebSocket,
		currentTrackPath,
		currentTracks,
		djCarpinchoEnabled,
		djNextTrack,
		djSafeModeEnabled,
		duration,
		favorites,
		getTrackInfo,
		handleLibraryClick,
		haptic,
		historyState,
		ignoreServerTimeUntil,
		isDraggingSeek,
		isFogonMode,
		isPaused,
		isPlaying,
		isScanning,
		librarySearchQuery,
		listenLocally,
		loadLibrary,
		localPlayerRef,
		localTimePos,
		mpvVisible,
		normalizeString,
		originalTracks,
		pauseAfterPath,
		queueIndex,
		queueState,
		sendCmd,
		serverMuted,
		setVolume,
		showFogonVolume,
		showToast,
		sortLibrary,
		switchTab,
		timePos,
		toggleFavorite,
		toggleMpvVisibility,
		togglePauseAfterCurrent,
		toggleQueue,
		topPlayedState,
		volIcon,
		volume,
	};
}
