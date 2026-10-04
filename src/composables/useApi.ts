import type { ApiResponse, CommandName, CommandPayloads, Track } from '../types';

/**
 * Devuelve la subruta bajo la cual está montada la app, o un string vacío si está en la raíz.
 * Ejemplos:
 *   http://example.com/           -> ""
 *   http://example.com/rockola/   -> "/rockola"
 *   http://example.com/rockola    -> "/rockola"
 *   http://example.com/index.html -> ""
 */
export function getBasePath(): string {
	if (typeof window === 'undefined') return '';
	return window.location.pathname.replace(/\/index\.html$/, '').replace(/\/+$/, '');
}

/**
 * Resuelve una ruta de API o estática relativa a la ruta base de la app.
 * Ejemplos:
 *   apiUrl('/command') -> "/command" (raíz) o "/rockola/command" (subruta)
 */
export function apiUrl(endpoint: string): string {
	const base = getBasePath();
	const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
	return `${base}${clean}`;
}

/**
 * Construye la URL del WebSocket usando el host actual, protocolo (ws/wss) y ruta base.
 */
export function getWsUrl(endpoint = '/ws'): string {
	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
	return `${protocol}//${window.location.host}${getBasePath()}${clean}`;
}

export function useApi() {
	async function post<T = unknown>(endpoint: string, data: Record<string, unknown> = {}): Promise<ApiResponse<T>> {
		const res = await fetch(apiUrl(endpoint), {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data),
		});

		if (!res.ok) throw new Error(`API Error: ${res.status}`);

		return (await res.json()) as ApiResponse<T>;
	}

	async function get<T = unknown>(endpoint: string): Promise<ApiResponse<T>> {
		const res = await fetch(apiUrl(endpoint));

		if (!res.ok) throw new Error(`API Error: ${res.status}`);

		return (await res.json()) as ApiResponse<T>;
	}

	return {
		// Asegura que 'payload' coincida estrictamente con los requerimientos del 'cmd'
		command: <C extends CommandName>(cmd: C, payload?: CommandPayloads[C]) =>
			post('/command', { cmd, ...(payload || {}) }),

		// Le indica a TypeScript que la propiedad 'data' contiene un arreglo de pistas
		getLibrary: () => get<Track[]>('/library'),
		hideMpv: () => post('/mpv/hide'),
		scanLibrary: () => get<Track[]>('/scan'),
		showMpv: () => post('/mpv/show'),
	};
}
