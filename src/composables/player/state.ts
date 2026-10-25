// Fachada de re-exportación del estado reactivo modularizado en src/stores/.
// Garantiza que ningún componente ni composable tenga estado duplicado,
// manteniendo un único punto de verdad por dominio (Playback, Queue, Library, Radio, UI).

export {
	currentTrackPath,
	duration,
	hasLocalPlayer,
	historyState,
	isDraggingSeek,
	isPaused,
	isPlaying,
	listenLocally,
	localPlayerRef,
	localTimePos,
	mpvVisible,
	pauseAfterPath,
	pendingSeekTime,
	serverMuted,
	timePos,
	topPlayedState,
	volIcon,
	volume,
} from '../../stores/usePlaybackStore';

export { queueState } from '../../stores/useQueueStore';

export {
	currentTracks,
	favorites,
	isScanning,
	librarySearchQuery,
	originalTracks,
	scanStatus,
	trackMap,
	urlMetadata,
	urlParams,
} from '../../stores/useLibraryStore';

export {
	djBaraEnabled,
	djNextTrack,
	djSafeModeEnabled,
	hasEdgeTts,
	hasFfmpeg,
	isPlayingRadioAnnouncement,
	isSynthesizingRadio,
	radioModeEnabled,
	weatherLocation,
} from '../../stores/useRadioStore';

export {
	activeTab,
	isFogonMode,
	isSocketConnected,
	localIp,
	sendRaw,
	serverUrl,
	setWsSend,
	showFogonVolume,
} from '../../stores/useUiStore';
