// Persistencia ligera de estado de navegación, búsqueda y scroll para sobrevivir
// a "No conservar actividades", rotación y muerte de proceso por el sistema.

import { watch } from 'vue';
import {
	activeSort,
	hasUserSelectedSort,
	librarySearchQuery,
	showFavoritesOnly,
	urlParams,
} from '../stores/useLibraryStore';
import { activeTab, isFogonMode } from '../stores/useUiStore';

export const UI_PERSISTENCE_KEY = 'rockola_ui_state_v1';
export const UI_SCROLL_KEY = 'rockola_ui_scroll_v1';

const VALID_TABS = new Set(['library', 'queue', 'top', 'controls']);
const VALID_SORTS = new Set(['time', 'artist', 'mood', 'shuffle']);

type SortValue = 'time' | 'artist' | 'mood' | 'shuffle';

interface PersistedUiState {
	activeTab: string;
	searchQuery: string;
	showFavoritesOnly: boolean;
	isFogonMode: boolean;
	activeSort?: SortValue;
	hasUserSelectedSort?: boolean;
	vibra?: string | null;
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
	const vibraVal = typeof urlParams.vibra === 'string' && urlParams.vibra.trim() !== '' ? urlParams.vibra : null;
	const payload: PersistedUiState = {
		activeTab: activeTab.value,
		searchQuery: librarySearchQuery.value,
		showFavoritesOnly: showFavoritesOnly.value,
		isFogonMode: isFogonMode.value,
		activeSort: activeSort.value,
		hasUserSelectedSort: hasUserSelectedSort.value,
		vibra: vibraVal,
	};
	writeStorage(UI_PERSISTENCE_KEY, JSON.stringify(payload));
}

function hasSessionUiState(): boolean {
	try {
		return typeof sessionStorage !== 'undefined' && sessionStorage.getItem(UI_PERSISTENCE_KEY) !== null;
	} catch {
		return false;
	}
}

export function restoreUiState(options?: { restoreTab?: boolean }): boolean {
	const hasSessionState = hasSessionUiState();
	const raw = readStorage(UI_PERSISTENCE_KEY);
	if (!raw) return false;
	try {
		const parsed = JSON.parse(raw) as Partial<PersistedUiState> | null;
		if (!parsed || typeof parsed !== 'object') return false;
		if (
			options?.restoreTab !== false &&
			hasSessionState &&
			typeof parsed.activeTab === 'string' &&
			VALID_TABS.has(parsed.activeTab)
		) {
			activeTab.value = parsed.activeTab;
		}
		if (typeof parsed.searchQuery === 'string') {
			librarySearchQuery.value = parsed.searchQuery;
		}
		if (typeof parsed.showFavoritesOnly === 'boolean') {
			showFavoritesOnly.value = parsed.showFavoritesOnly;
		}
		if (typeof parsed.activeSort === 'string' && VALID_SORTS.has(parsed.activeSort)) {
			activeSort.value = parsed.activeSort as SortValue;
		}
		if (typeof parsed.hasUserSelectedSort === 'boolean') {
			hasUserSelectedSort.value = parsed.hasUserSelectedSort;
		}
		if (urlParams.vibra === undefined && typeof parsed.vibra === 'string' && parsed.vibra.trim() !== '') {
			urlParams.vibra = parsed.vibra;
		}
		return true;
	} catch {
		return false;
	}
}

const scrollDebounceTimers = new Map<string, ReturnType<typeof setTimeout>>();

export function saveTabScrollDebounced(tabId: string, scrollTop: number, delayMs: number = 200): void {
	const prev = scrollDebounceTimers.get(tabId);
	if (prev) clearTimeout(prev);
	scrollDebounceTimers.set(
		tabId,
		setTimeout(() => {
			scrollDebounceTimers.delete(tabId);
			saveTabScroll(tabId, scrollTop);
		}, delayMs)
	);
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
		[
			activeTab,
			librarySearchQuery,
			showFavoritesOnly,
			isFogonMode,
			activeSort,
			hasUserSelectedSort,
			() => urlParams.vibra,
		],
		() => {
			saveUiState();
		},
		{ flush: 'post' }
	);
}
