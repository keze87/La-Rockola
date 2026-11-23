import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	UI_PERSISTENCE_KEY,
	UI_SCROLL_KEY,
	restoreTabScroll,
	restoreUiState,
	saveTabScroll,
	saveTabScrollDebounced,
	saveUiState,
} from '../../../src/composables/useUiPersistence';
import {
	activeSort,
	hasUserSelectedSort,
	librarySearchQuery,
	showFavoritesOnly,
	urlParams,
} from '../../../src/stores/useLibraryStore';
import { activeTab, isFogonMode } from '../../../src/stores/useUiStore';

describe('useUiPersistence', () => {
	beforeEach(() => {
		sessionStorage.clear();
		localStorage.clear();
		activeTab.value = 'library';
		librarySearchQuery.value = '';
		showFavoritesOnly.value = false;
		isFogonMode.value = false;
		activeSort.value = 'time';
		hasUserSelectedSort.value = false;
		delete urlParams.vibra;
	});

	afterEach(() => {
		vi.useRealTimers();
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
		expect(isFogonMode.value).toBe(false);
		expect(restoreTabScroll('top')).toBe(420);
		expect(restoreTabScroll('library')).toBe(0);
	});

	it('tolera JSON corrupto en almacenamiento sin fallar', () => {
		sessionStorage.setItem(UI_PERSISTENCE_KEY, '{invalido');
		localStorage.setItem(UI_PERSISTENCE_KEY, '{invalido');
		expect(restoreUiState()).toBe(false);
		expect(activeTab.value).toBe('library');
	});

	it('guarda y restaura orden de libreria (activeSort, hasUserSelectedSort, vibra) y filtros', () => {
		activeSort.value = 'shuffle';
		hasUserSelectedSort.value = true;
		urlParams.vibra = '424242';
		librarySearchQuery.value = 'cerati';
		showFavoritesOnly.value = true;

		saveUiState();

		activeSort.value = 'time';
		hasUserSelectedSort.value = false;
		delete urlParams.vibra;
		librarySearchQuery.value = '';
		showFavoritesOnly.value = false;

		expect(restoreUiState({ restoreTab: false })).toBe(true);
		expect(activeSort.value).toBe('shuffle');
		expect(hasUserSelectedSort.value).toBe(true);
		expect(urlParams.vibra).toBe('424242');
		expect(librarySearchQuery.value).toBe('cerati');
		expect(showFavoritesOnly.value).toBe(true);
	});

	it('agrupa múltiples llamadas de saveTabScrollDebounced en una sola escritura', () => {
		vi.useFakeTimers();
		const setItemSpy = vi.spyOn(localStorage, 'setItem');

		saveTabScrollDebounced('library', 100, 200);
		saveTabScrollDebounced('library', 250, 200);
		saveTabScrollDebounced('library', 480, 200);

		expect(setItemSpy).not.toHaveBeenCalled();

		vi.advanceTimersByTime(200);

		const scrollCalls = setItemSpy.mock.calls.filter((c) => c[0] === UI_SCROLL_KEY);
		expect(scrollCalls.length).toBe(1);
		expect(restoreTabScroll('library')).toBe(480);

		setItemSpy.mockRestore();
	});
});
