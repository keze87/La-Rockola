import type { ApiResponse, CommandName, CommandPayloads, Track } from '../types';

/**
 * Returns the subpath the app is mounted under, or an empty string if at the root.
 * Examples:
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
 * Resolves an API or static path relative to the app base path.
 * Examples:
 *   apiUrl('/command') -> "/command" (root) or "/rockola/command" (subpath)
 */
export function apiUrl(endpoint: string): string {
	const base = getBasePath();
	const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
	return `${base}${clean}`;
}

/**
 * Constructs the WebSocket URL using current host, protocol (ws/wss), and base path.
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
		// Enforces that 'payload' precisely matches the requirements of 'cmd'
		command: <C extends CommandName>(cmd: C, payload?: CommandPayloads[C]) =>
			post('/command', { cmd, ...(payload || {}) }),

		// Explicitly tells TS that the 'data' property holds an array of Tracks
		getLibrary: () => get<Track[]>('/library'),
		hideMpv: () => post('/mpv/hide'),
		scanLibrary: () => get<Track[]>('/scan'),
		showMpv: () => post('/mpv/show'),
	};
}
