import { useApi } from './useApi';
import { usePlayer } from './usePlayer';
import type { CommandName, CommandPayloads } from '../types';

export function usePlaybackControls() {
	const api = useApi();
	const { showToast } = usePlayer();

	async function execute<C extends CommandName>(
		action: C,
		payload?: CommandPayloads[C],
		successMsg: string | null = null
	) {
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
		addUrl: (path: string) => execute('add_url', { path }, 'Procesando link...'),
		clearQueue: () => execute('clear_queue', undefined, 'La fila quedó limpita.'),
		jumpToHistory: (index: number) => execute('jump', { type: 'history', index }),
		jumpToQueue: (index: number) => execute('jump', { type: 'queue', index }),
		moveQueueItem: (index: number, new_index: number) => execute('move_queue_item', { index, new_index }),
		pause: () => execute('pause'),
		play: (path: string) => execute('play', { path }),
		prev: () => execute('prev'),
		removeQueueItem: (index: number) => execute('remove_queue_item', { index }),
		seek: (amount: number) => execute('seek', { amount }),
		seekAbsolute: (amount: number) => execute('seek_absolute', { amount }),
		setMute: (state: boolean) => execute('set_mute', { state }),
		setVolume: (vollevel: number) => execute('set_volume', { vollevel }),
		skip: () => execute('skip'),
		stop: () => execute('stop'),
		toggleFavorite: (path: string) => execute('toggle_favorite', { path }),
		toggleQueue: (path: string, title?: string) =>
			execute('toggle_queue', { path }, title ? `¡Adentro! ${title} a la fila.` : null),
	};
}
