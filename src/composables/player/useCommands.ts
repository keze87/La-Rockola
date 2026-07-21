import { useApi } from '../useApi';
import { useToasts } from './useToasts';

export function useCommands() {
	const api = useApi();
	const { showToast } = useToasts();

	async function sendCmd(cmd: string, data: Record<string, unknown> = {}) {
		try {
			return await api.command(cmd, data);
		} catch (err) {
			console.error(err);
			showToast('Error mandando comando fiera.', 'error');
		}
	}

	return { sendCmd };
}
