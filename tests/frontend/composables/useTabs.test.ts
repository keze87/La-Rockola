import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useTabs } from '@/composables/player/useTabs';
import { activeTab } from '@/composables/player/state';

describe('useTabs', () => {
	beforeEach(() => {
		activeTab.value = 'library';
		document.body.innerHTML = '';
	});

	it('switches activeTab reactively', () => {
		const { switchTab } = useTabs();

		switchTab('queue');
		expect(activeTab.value).toBe('queue');

		switchTab('controls');
		expect(activeTab.value).toBe('controls');

		switchTab('library');
		expect(activeTab.value).toBe('library');
	});

	it('manages tabs visibility on scroll down/up only for short screens (<= 600px)', () => {
		const { isTabsBarHidden, handleScroll, isShortScreen } = useTabs();

		// Pantalla normal (altura > 600px)
		isShortScreen.value = false;
		isTabsBarHidden.value = false;

		// Scrollear hacia abajo en pantalla alta no debe ocultar las pestañas
		handleScroll(100);
		expect(isTabsBarHidden.value).toBe(false);

		// Pantalla petiza (altura <= 600px)
		isShortScreen.value = true;

		// Scrollear hacia abajo debe ocultar las pestañas
		handleScroll(150);
		expect(isTabsBarHidden.value).toBe(true);

		// Scrollear hacia arriba debe volver a mostrarlas
		handleScroll(80);
		expect(isTabsBarHidden.value).toBe(false);

		// Si vuelve arriba de todo (scrollTop <= 10), siempre visibles
		isTabsBarHidden.value = true;
		handleScroll(5);
		expect(isTabsBarHidden.value).toBe(false);
	});

	it('scrolls active tab container smoothly to top when re-tapping the already active tab', () => {
		const { switchTab } = useTabs();
		activeTab.value = 'library';

		const container = document.createElement('section');
		container.className = 'tab-content';
		container.dataset.tabPanel = 'library';
		Object.defineProperty(container, 'scrollTop', { configurable: true, writable: true, value: 320 });
		const scrollToSpy = vi.fn();
		container.scrollTo = scrollToSpy;
		document.body.appendChild(container);

		const onScrollToTop = vi.fn();
		const scrolled = switchTab('library', { onScrollToTop });

		expect(scrolled).toBe(true);
		expect(scrollToSpy).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
		expect(onScrollToTop).toHaveBeenCalledTimes(1);
	});
});
