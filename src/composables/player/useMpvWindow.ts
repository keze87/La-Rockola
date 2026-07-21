import { useApi } from '../useApi';
import { useHaptics } from './useHaptics';
import { useToasts } from './useToasts';
import { mpvVisible } from './state';

export function useMpvWindow() {
	const api = useApi();
	const { showToast } = useToasts();
	const { haptic } = useHaptics();

	async function toggleMpvVisibility() {
		const targetState = !mpvVisible.value;

		try {
			await (targetState ? api.showMpv() : api.hideMpv());
			showToast(targetState ? 'Mostrando ventana de MPV' : 'Ocultando ventana de MPV', 'info');
			haptic();
		} catch (err) {
			console.error(err);
			showToast('Error cambiando visibilidad de MPV', 'error');
		}
	}

	return { toggleMpvVisibility };
}
