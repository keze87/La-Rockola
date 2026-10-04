import {
	activeTab,
	currentTrackPath,
	currentTracks,
	djCarpinchoEnabled,
	djNextTrack,
	djSafeModeEnabled,
	duration,
	favorites,
	hasEdgeTts,
	hasFfmpeg,
	historyState,
	pendingSeekTime,
	isDraggingSeek,
	isFogonMode,
	isPaused,
	isPlaying,
	isPlayingRadioAnnouncement,
	isScanning,
	isSynthesizingRadio,
	librarySearchQuery,
	listenLocally,
	localPlayerRef,
	localTimePos,
	mpvVisible,
	originalTracks,
	pauseAfterPath,
	queueState,
	radioModeEnabled,
	scanStatus,
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

// Punto de entrada público único para el estado y comportamiento del reproductor,
// usado en toda la app exactamente como siempre (`const { ... } = usePlayer()`).
// Internamente actúa como composition root: cada responsabilidad (transporte, librería,
// fila, reproducción local, notificaciones, etc.) vive en su propio archivo dentro de
// ./player/, y esta función las ensambla y reexporta con la misma API plana para no
// romper ningún componente consumidor.
export function usePlayer() {
	const { _sendLocalPlayerUpdate, setVolume } = useLocalPlayback();
	const { connectWebSocket } = useSocket();
	const { getTrackInfo, loadLibrary, queueIndex, sortLibrary } = useLibrary();
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
		hasEdgeTts,
		hasFfmpeg,
		historyState,
		pendingSeekTime,
		isDraggingSeek,
		isFogonMode,
		isPaused,
		isPlaying,
		isPlayingRadioAnnouncement,
		isScanning,
		isSynthesizingRadio,
		librarySearchQuery,
		listenLocally,
		loadLibrary,
		localPlayerRef,
		localTimePos,
		mpvVisible,
		originalTracks,
		pauseAfterPath,
		queueIndex,
		queueState,
		radioModeEnabled,
		scanStatus,
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
