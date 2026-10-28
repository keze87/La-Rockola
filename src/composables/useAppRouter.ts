// Composable de enrutamiento liviano para sincronizar pestañas, Modo Fogón y vibra con la URL del navegador.

import { ref } from 'vue';
import { urlParams } from '../stores/useLibraryStore';
import { activeTab, isFogonMode } from '../stores/useUiStore';
import { getBasePath } from './useApi';

export const currentRoute = ref<string>('/');

// Normaliza el pathname quitando barras sobrantes y minúsculas
export function normalizePath(path: string): string {
	if (!path || path === '/') return '/';
	const clean = path.replace(/\/+$/, '');
	return clean.startsWith('/') ? clean.toLowerCase() : `/${clean.toLowerCase()}`;
}

export function useAppRouter() {
	function applyRoute(pathname: string, triggerSort: boolean = true) {
		const norm = normalizePath(pathname);
		currentRoute.value = norm;

		if (norm === '/fogon') {
			isFogonMode.value = true;
			return;
		}

		// En cualquier otra ruta, salimos de Modo Fogón
		if (isFogonMode.value) {
			isFogonMode.value = false;
		}

		if (norm === '/queue' || norm === '/ronda') {
			activeTab.value = 'queue';
		} else if (norm === '/top' || norm === '/clasicos') {
			activeTab.value = 'top';
		} else if (norm === '/controls' || norm === '/perillas') {
			activeTab.value = 'controls';
		} else if (norm === '/vibra' || norm.endsWith('/vibra')) {
			activeTab.value = 'library';
			currentRoute.value = '/';
			const seed = Math.floor(Math.random() * 1000000);

			if (typeof window !== 'undefined') {
				const base = getBasePath();
				const targetPath = `${base}/?vibra=${seed}${window.location.hash || ''}`;
				window.history.replaceState(window.history.state, '', targetPath);
			}

			urlParams.vibra = seed.toString();

			if (triggerSort && typeof window !== 'undefined') {
				// Despachamos un evento de ventana para que useLibrary pueda escuchar y re-mezclar si ya está cargada
				window.dispatchEvent(new CustomEvent('rockola:vibra', { detail: { seed } }));
			}
		} else if (norm === '/temazos' || norm === '/library' || norm === '/') {
			activeTab.value = 'library';
		}
	}

	function navigateTo(path: string) {
		const norm = normalizePath(path);
		if (typeof window !== 'undefined' && window.location.pathname !== norm) {
			const target = `${norm}${window.location.search}${window.location.hash}`;
			window.history.pushState({}, '', target);
		}
		applyRoute(norm);
	}

	function initRouter(): () => void {
		if (typeof window === 'undefined') return () => {};

		// Aplicar ruta inicial de arranque
		applyRoute(window.location.pathname);

		const onPopState = () => {
			applyRoute(window.location.pathname);
		};

		window.addEventListener('popstate', onPopState);

		return () => {
			window.removeEventListener('popstate', onPopState);
		};
	}

	return {
		currentRoute,
		applyRoute,
		navigateTo,
		initRouter,
	};
}
