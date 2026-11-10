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
	activeSort,
	currentTracks,
	defaultSort,
	favorites,
	filteredTracks,
	isScanning,
	librarySearchQuery,
	originalTracks,
	scanStatus,
	showFavoritesOnly,
	trackMap,
	urlMetadata,
	urlParams,
} from '../../stores/useLibraryStore';

export {
	djBaraEnabled,
	djMode,
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
	isTabsBarHidden,
	isFogonMode,
	isSocketConnected,
	localIp,
	sendRaw,
	serverUrl,
	setWsSend,
	showFogonVolume,
} from '../../stores/useUiStore';
