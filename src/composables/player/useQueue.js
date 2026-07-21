import { useCommands } from './useCommands';
import { useLibrary } from './useLibrary';
import { useToasts } from './useToasts';
import { currentTrackPath, pauseAfterPath, queueState } from './state';

export function useQueue() {
	const { sendCmd } = useCommands();
	const { getTrackInfo } = useLibrary();
	const { showToast } = useToasts();

	async function toggleFavorite(path) {
		await sendCmd('toggle_favorite', { path });
	}

	async function toggleQueue(path, mostrarToast = true) {
		const wasInQueue = queueState.value.includes(path);
		const title = getTrackInfo(path).display_title;
		const res = await sendCmd('toggle_queue', { path });

		if (res && res.status === 'ok') {
			if (mostrarToast) {
				if (!wasInQueue)
					showToast({ prefix: '¡Adentro! ', highlight: title, suffix: ' a la fila.' }, 'success');
				else showToast({ prefix: 'Sacamos ', highlight: title, suffix: ' de la fila.' }, 'warning');
			}
		} else {
			showToast('Uy, no se pudo agregar el tema.', 'error');
		}
	}

	function handleLibraryClick(track) {
		if (currentTrackPath.value === track.path) sendCmd('pause');
		else toggleQueue(track.path, false);
	}

	async function togglePauseAfterCurrent() {
		if (!currentTrackPath.value) return;

		if (pauseAfterPath.value === currentTrackPath.value) {
			pauseAfterPath.value = null;
			await sendCmd('pause_after', { path: '' });
			showToast('Cancelamos la pausa al terminar 🦦', 'info');
		} else {
			pauseAfterPath.value = currentTrackPath.value;
			await sendCmd('pause_after', { path: currentTrackPath.value });
			const title = getTrackInfo(currentTrackPath.value).display_title;
			showToast({ prefix: 'Frenamos la joda después de ', highlight: title, suffix: ' ⏸' }, 'warning');
		}
	}

	return { handleLibraryClick, toggleFavorite, togglePauseAfterCurrent, toggleQueue };
}
