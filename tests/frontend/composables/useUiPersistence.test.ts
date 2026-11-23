import { beforeEach, describe, expect, it } from 'vitest';
import {
	UI_PERSISTENCE_KEY,
	restoreTabScroll,
	restoreUiState,
	saveTabScroll,
	saveUiState,
} from '../../../src/composables/useUiPersistence';
import { librarySearchQuery, showFavoritesOnly } from '../../../src/stores/useLibraryStore';
import { activeTab, isFogonMode } from '../../../src/stores/useUiStore';

describe('useUiPersistence', () => {
	beforeEach(() => {
		sessionStorage.clear();
		localStorage.clear();
		activeTab.value = 'library';
		librarySearchQuery.value = '';
		showFavoritesOnly.value = false;
		isFogonMode.value = false;
	});

	it('guarda y restaura pestaña activa, búsqueda, favoritos, fogón y scroll por pestaña', () => {
		activeTab.value = 'top';
		librarySearchQuery.value = 'pappo';
		showFavoritesOnly.value = true;
		isFogonMode.value = true;

		saveUiState();
		saveTabScroll('top', 420);

		// Simulamos muerte de proceso / No conservar actividades
		activeTab.value = 'library';
		librarySearchQuery.value = '';
		showFavoritesOnly.value = false;
		isFogonMode.value = false;

		const restored = restoreUiState();
		expect(restored).toBe(true);
		expect(activeTab.value).toBe('top');
		expect(librarySearchQuery.value).toBe('pappo');
		expect(showFavoritesOnly.value).toBe(true);
		expect(isFogonMode.value).toBe(true);
		expect(restoreTabScroll('top')).toBe(420);
		expect(restoreTabScroll('library')).toBe(0);
	});

	it('tolera JSON corrupto en almacenamiento sin fallar', () => {
		sessionStorage.setItem(UI_PERSISTENCE_KEY, '{invalido');
		localStorage.setItem(UI_PERSISTENCE_KEY, '{invalido');
		expect(restoreUiState()).toBe(false);
		expect(activeTab.value).toBe('library');
	});
});
