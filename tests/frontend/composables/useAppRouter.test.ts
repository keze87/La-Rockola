import { describe, it, expect, beforeEach } from 'vitest';
import { useAppRouter } from '@/composables/useAppRouter';
import { activeTab, isFogonMode } from '@/stores/useUiStore';
import { urlParams } from '@/stores/useLibraryStore';

describe('useAppRouter', () => {
	beforeEach(() => {
		activeTab.value = 'library';
		isFogonMode.value = false;
		delete urlParams.vibra;
		window.history.replaceState({}, '', '/');
	});

	it('routes to /fogon activating fogon mode', () => {
		const { applyRoute } = useAppRouter();
		applyRoute('/fogon');
		expect(isFogonMode.value).toBe(true);
	});

	it('routes to /queue and /ronda activating queue tab and exiting fogon', () => {
		const { applyRoute } = useAppRouter();
		isFogonMode.value = true;
		applyRoute('/queue');
		expect(activeTab.value).toBe('queue');
		expect(isFogonMode.value).toBe(false);

		applyRoute('/ronda');
		expect(activeTab.value).toBe('queue');
	});

	it('routes to /top and /clasicos activating top tab', () => {
		const { applyRoute } = useAppRouter();
		applyRoute('/clasicos');
		expect(activeTab.value).toBe('top');
		expect(isFogonMode.value).toBe(false);

		applyRoute('/top');
		expect(activeTab.value).toBe('top');
	});

	it('routes to /controls and /perillas activating controls tab', () => {
		const { applyRoute } = useAppRouter();
		applyRoute('/perillas');
		expect(activeTab.value).toBe('controls');
		expect(isFogonMode.value).toBe(false);

		applyRoute('/controls');
		expect(activeTab.value).toBe('controls');
	});

	it('routes to /vibra generating a random seed and selecting library', () => {
		const { applyRoute } = useAppRouter();
		applyRoute('/vibra');
		expect(activeTab.value).toBe('library');
		expect(isFogonMode.value).toBe(false);
		expect(urlParams.vibra).toBeDefined();
		expect(Number(urlParams.vibra)).toBeGreaterThanOrEqual(0);
	});

	it('updates url history upon navigation', () => {
		const { navigateTo } = useAppRouter();
		navigateTo('/queue');
		expect(window.location.pathname).toBe('/queue');
		expect(activeTab.value).toBe('queue');
	});
});
