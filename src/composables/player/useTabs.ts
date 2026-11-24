import { nextTick, ref } from 'vue';
import { activeTab, isTabsBarHidden } from './state';

const SHORT_SCREEN_MAX_HEIGHT = 600;

// Estado reactivo compartido para saber si la ventana actual es petiza
const isShortScreen = ref(typeof window !== 'undefined' ? window.innerHeight <= SHORT_SCREEN_MAX_HEIGHT : false);

if (typeof window !== 'undefined') {
	window.addEventListener('resize', () => {
		isShortScreen.value = window.innerHeight <= SHORT_SCREEN_MAX_HEIGHT;
		if (!isShortScreen.value) {
			isTabsBarHidden.value = false;
		}
	});
}

let lastScrollTop = 0;

export interface SwitchTabOptions {
	onScrollToTop?: () => void;
}

export function scrollActiveTabToTop(tabId: string): boolean {
	if (typeof document === 'undefined') return false;
	const selector = `[data-tab-panel="${tabId}"].tab-content, [data-tab-panel="${tabId}"] .tab-content`;
	const el = document.querySelector<HTMLElement>(selector);
	if (!el || el.scrollTop <= 0) return false;
	if (typeof el.scrollTo === 'function') {
		el.scrollTo({ top: 0, behavior: 'smooth' });
	} else {
		el.scrollTop = 0;
	}
	return true;
}

export function useTabs() {
	function switchTab(tabId: string, options?: SwitchTabOptions): boolean {
		const isSameTab = activeTab.value === tabId;
		activeTab.value = tabId;
		isTabsBarHidden.value = false;

		if (isSameTab) {
			const scrolled = scrollActiveTabToTop(tabId);
			if (scrolled) {
				options?.onScrollToTop?.();
			}
			return scrolled;
		}

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
		return false;
	}

	function handleScroll(scrollTop: number) {
		if (!isShortScreen.value) {
			isTabsBarHidden.value = false;
			lastScrollTop = scrollTop;
			return;
		}

		if (scrollTop <= 10) {
			isTabsBarHidden.value = false;
		} else if (scrollTop > lastScrollTop + 10) {
			// Scrolldown marcado: ocultamos la barra
			isTabsBarHidden.value = true;
		} else if (scrollTop < lastScrollTop - 10) {
			// Scrollup: mostramos la barra de nuevo
			isTabsBarHidden.value = false;
		}

		lastScrollTop = Math.max(0, scrollTop);
	}

	return {
		activeTab,
		isTabsBarHidden,
		isShortScreen,
		switchTab,
		handleScroll,
	};
}
