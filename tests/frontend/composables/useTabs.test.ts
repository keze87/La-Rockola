import { describe, it, expect, beforeEach } from 'vitest';
import { useTabs } from '@/composables/player/useTabs';
import { activeTab } from '@/composables/player/state';

describe('useTabs', () => {
	beforeEach(() => {
		activeTab.value = 'library';
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
});
