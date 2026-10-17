// Store de dominio para la fila de reproducción de la rockola.

import { ref } from 'vue';

export const queueState = ref<string[]>([]);

export function useQueueStore() {
	return {
		queueState,
	};
}
