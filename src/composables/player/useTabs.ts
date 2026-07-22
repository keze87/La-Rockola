import { activeTab } from './state';

export function useTabs() {
	function switchTab(tabId: string) {
		activeTab.value = tabId;

		if (tabId === 'queue') {
			setTimeout(() => {
				const el = document.getElementById('current-queue-row');

				if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}, 200);
		}
	}

	return { switchTab };
}
