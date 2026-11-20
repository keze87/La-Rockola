import type { ApiResponse, CommandName, CommandPayloads, Track } from '../types';

let apiOrigin = '';

export function setApiOrigin(origin: string | null): void {
	const cleaned = (origin ?? '').trim().replace(/\/+$/, '');
	apiOrigin = cleaned;
}

export function getApiOrigin(): string {
	return apiOrigin;
}

export function clearApiOrigin(): void {
	apiOrigin = '';
}

/**
 * Devuelve la subruta bajo la cual está montada la app, o un string vacío si está en la raíz.
 * Ejemplos:
 *   http://example.com/           -> ""
 *   http://example.com/rockola/   -> "/rockola"
 *   http://example.com/rockola    -> "/rockola"
 *   http://example.com/index.html -> ""
 */
export function getBasePath(pathname?: string): string {
	if (typeof window === 'undefined' && pathname === undefined) return '';
	const rawPath = pathname !== undefined ? pathname : window.location.pathname;
	let path = rawPath.replace(/\/index\.html$/, '').replace(/\/+$/, '');
	// Descontamos rutas SPA conocidas al final del pathname para no confundirlas con subrutas de montaje del servidor
	const spaPattern = /\/(fogon|queue|ronda|top|clasicos|controls|perillas|temazos|library|vibra|letras|lyrics)$/i;
	path = path.replace(spaPattern, '');
	return path.replace(/\/+$/, '');
}

/**
 * Resuelve una ruta de API o estática relativa a la ruta base de la app.
 * Ejemplos:
 *   apiUrl('/command') -> "/command" (raíz) o "/rockola/command" (subruta)
 */
export function apiUrl(endpoint: string): string {
	const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
	if (apiOrigin) {
		return `${apiOrigin}${clean}`;
	}
	const base = getBasePath();
	return `${base}${clean}`;
}

/**
 * Construye la URL del WebSocket usando el host actual, protocolo (ws/wss) y ruta base.
 */
export function getWsUrl(endpoint = '/ws'): string {
	const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
	if (apiOrigin) {
		const wsOrigin = apiOrigin.replace(/^https:\/\//i, 'wss://').replace(/^http:\/\//i, 'ws://');
		return `${wsOrigin}${clean}`;
	}
	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
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
		setMusicDir: (dir: string, dir2?: string | null) =>
			post('/system/music-dir', { dir, ...(dir2 ? { dir2 } : {}) }),
		showMpv: () => post('/mpv/show'),
	};
}
