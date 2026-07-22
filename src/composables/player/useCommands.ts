import { useApi } from '../useApi';
import { useToasts } from './useToasts';
import type { CommandName, CommandPayloads } from '../../types';

export function useCommands() {
	const api = useApi();
	const { showToast } = useToasts();

	async function sendCmd<C extends CommandName>(cmd: C, data?: CommandPayloads[C]) {
		try {
			return await api.command(cmd, data);
		} catch (err) {
			console.error(err);
			showToast('Error mandando comando fiera.', 'error');
		}
	}

	return { sendCmd };
}
