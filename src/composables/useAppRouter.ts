// Composable de enrutamiento liviano para sincronizar pestañas, Modo Fogón y vibra con la URL del navegador.

import { ref } from 'vue';
import { urlParams } from '../stores/useLibraryStore';
import { activeTab, isFogonMode, isLyricsEditorOpen } from '../stores/useUiStore';
import { getBasePath } from './useApi';

export const currentRoute = ref<string>('/');

// Normaliza el pathname quitando barras sobrantes y minúsculas
export function normalizePath(path: string): string {
	if (!path || path === '/') return '/';
	const clean = path.replace(/\/+$/, '');
	return clean.startsWith('/') ? clean.toLowerCase() : `/${clean.toLowerCase()}`;
}

// Extrae la ruta interna de la SPA descontando cualquier subruta de montaje (ej: /rockola/queue -> /queue)
export function extractSpaRoute(pathname: string): string {
	const base = getBasePath(pathname);
	if (base && pathname.toLowerCase().startsWith(base.toLowerCase())) {
		const sub = pathname.slice(base.length);
		return normalizePath(sub);
	}
	return normalizePath(pathname);
}

// Construye el pathname completo preservando la subruta de montaje (ej: /queue -> /rockola/queue)
export function buildSpaPath(route: string, pathnameHint?: string): string {
	const base = getBasePath(pathnameHint);
	const normRoute = normalizePath(route);
	if (!base) return normRoute;
	return normRoute === '/' ? `${base}/` : `${base}${normRoute}`;
}

export function useAppRouter() {
	function applyRoute(pathname: string, triggerSort: boolean = true) {
		const base = getBasePath(pathname) || getBasePath();
		const norm = extractSpaRoute(pathname);
		currentRoute.value = norm;

		if (norm === '/fogon') {
			isFogonMode.value = true;
			isLyricsEditorOpen.value = false;
			return;
		}

		if (norm === '/letras' || norm === '/lyrics') {
			isLyricsEditorOpen.value = true;
			isFogonMode.value = false;
			return;
		}

		// En cualquier otra ruta, salimos de Modo Fogón y del Editor de Letras
		if (isFogonMode.value) {
			isFogonMode.value = false;
		}
		if (isLyricsEditorOpen.value) {
			isLyricsEditorOpen.value = false;
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
		const targetPathname = buildSpaPath(path);
		if (typeof window !== 'undefined' && window.location.pathname !== targetPathname) {
			const target = `${targetPathname}${window.location.search}${window.location.hash}`;
			window.history.pushState({}, '', target);
		}
		applyRoute(targetPathname);
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
