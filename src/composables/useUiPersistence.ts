// Persistencia ligera de estado de navegación, búsqueda y scroll para sobrevivir
// a "No conservar actividades", rotación y muerte de proceso por el sistema.

import { watch } from 'vue';
import { librarySearchQuery, showFavoritesOnly } from '../stores/useLibraryStore';
import { activeTab, isFogonMode } from '../stores/useUiStore';

export const UI_PERSISTENCE_KEY = 'rockola_ui_state_v1';
export const UI_SCROLL_KEY = 'rockola_ui_scroll_v1';

const VALID_TABS = new Set(['library', 'queue', 'top', 'controls']);

interface PersistedUiState {
	activeTab: string;
	searchQuery: string;
	showFavoritesOnly: boolean;
	isFogonMode: boolean;
}

function readStorage(key: string): string | null {
	try {
		if (typeof sessionStorage !== 'undefined') {
			const val = sessionStorage.getItem(key);
			if (val !== null) return val;
		}
	} catch {
		// Ignorar
	}
	try {
		if (typeof localStorage !== 'undefined') {
			return localStorage.getItem(key);
		}
	} catch {
		// Ignorar
	}
	return null;
}

function writeStorage(key: string, value: string): void {
	try {
		if (typeof sessionStorage !== 'undefined') {
			sessionStorage.setItem(key, value);
		}
	} catch {
		// Ignorar
	}
	try {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(key, value);
		}
	} catch {
		// Ignorar
	}
}

export function saveUiState(): void {
	const payload: PersistedUiState = {
		activeTab: activeTab.value,
		searchQuery: librarySearchQuery.value,
		showFavoritesOnly: showFavoritesOnly.value,
		isFogonMode: isFogonMode.value,
	};
	writeStorage(UI_PERSISTENCE_KEY, JSON.stringify(payload));
}

export function restoreUiState(): boolean {
	const raw = readStorage(UI_PERSISTENCE_KEY);
	if (!raw) return false;
	try {
		const parsed = JSON.parse(raw) as Partial<PersistedUiState> | null;
		if (!parsed || typeof parsed !== 'object') return false;
		if (typeof parsed.activeTab === 'string' && VALID_TABS.has(parsed.activeTab)) {
			activeTab.value = parsed.activeTab;
		}
		if (typeof parsed.searchQuery === 'string') {
			librarySearchQuery.value = parsed.searchQuery;
		}
		if (typeof parsed.showFavoritesOnly === 'boolean') {
			showFavoritesOnly.value = parsed.showFavoritesOnly;
		}
		if (typeof parsed.isFogonMode === 'boolean') {
			isFogonMode.value = parsed.isFogonMode;
		}
		return true;
	} catch {
		return false;
	}
}

export function saveTabScroll(tabId: string, scrollTop: number): void {
	const safeScroll = Math.max(0, Math.round(scrollTop));
	let map: Record<string, number> = {};
	try {
		const raw = readStorage(UI_SCROLL_KEY);
		if (raw) {
			const parsed = JSON.parse(raw) as Record<string, number> | null;
			if (parsed && typeof parsed === 'object') map = parsed;
		}
	} catch {
		map = {};
	}
	map[tabId] = safeScroll;
	writeStorage(UI_SCROLL_KEY, JSON.stringify(map));
}

export function restoreTabScroll(tabId: string): number {
	try {
		const raw = readStorage(UI_SCROLL_KEY);
		if (!raw) return 0;
		const parsed = JSON.parse(raw) as Record<string, unknown> | null;
		const val = parsed?.[tabId];
		return typeof val === 'number' && Number.isFinite(val) && val > 0 ? val : 0;
	} catch {
		return 0;
	}
}

export function initUiPersistence(): () => void {
	return watch(
		[activeTab, librarySearchQuery, showFavoritesOnly, isFogonMode],
		() => {
			saveUiState();
		},
		{ flush: 'post' }
	);
}
