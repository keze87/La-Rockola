import { useApi } from './useApi';
import { usePlayer } from './usePlayer';

export function usePlaybackControls() {
	const api = useApi();
	const { showToast } = usePlayer();

	async function execute(action, payload = {}, successMsg = null) {
		try {
			const res = await api.command(action, payload);
			if (res?.status === 'ok' && successMsg) {
				showToast(successMsg, 'success');
			}
			return res;
		} catch (error) {
			console.error(error);
			showToast('Error mandando comando fiera.', 'error');
			return null;
		}
	}

	return {
		play: (path) => execute('play', { path }),
		pause: () => execute('pause'),
		stop: () => execute('stop'),
		skip: () => execute('skip'),
		prev: () => execute('prev'),
		toggleQueue: (path, title) => execute('toggle_queue', { path }, title ? `¡Adentro! ${title} a la fila.` : null),
		clearQueue: () => execute('clear_queue', {}, 'La fila quedó limpita.'),
		seek: (amount) => execute('seek', { amount }),
		seekAbsolute: (amount) => execute('seek_absolute', { amount }),
		setVolume: (vollevel) => execute('set_volume', { vollevel }),
		setMute: (state) => execute('set_mute', { state }),
		toggleFavorite: (path) => execute('toggle_favorite', { path }),
		addUrl: (path) => execute('add_url', { path }, 'Procesando link...'),
		jumpToQueue: (index) => execute('jump', { type: 'queue', index }),
		jumpToHistory: (index) => execute('jump', { type: 'history', index }),
		removeQueueItem: (index) => execute('remove_queue_item', { index }),
		moveQueueItem: (index, new_index) => execute('move_queue_item', { index, new_index }),
	};
}
