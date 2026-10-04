import { nextTick } from 'vue';
import { activeTab } from './state';

export function useTabs() {
	function switchTab(tabId: string) {
		activeTab.value = tabId;

		if (tabId === 'queue') {
			nextTick(() => {
				const el = document.getElementById('current-queue-row');

				// 'auto' scrollea al instante sin animación suave
				if (el) el.scrollIntoView({ behavior: 'auto', block: 'center' });
			});
		} else if (tabId === 'controls') {
			nextTick(() => {
				const el = document.getElementById('controls-tab');
				// Reiniciamos al instante la posición del scroll
				if (el) el.scrollTop = 0;
			});
		}
	}

	return { switchTab };
}
