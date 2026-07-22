import type { ApiResponse, CommandName, CommandPayloads, Track } from '../types';

export function useApi() {
	async function post<T = unknown>(endpoint: string, data: Record<string, unknown> = {}): Promise<ApiResponse<T>> {
		const res = await fetch(endpoint, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data),
		});

		if (!res.ok) throw new Error(`API Error: ${res.status}`);

		return (await res.json()) as ApiResponse<T>;
	}

	async function get<T = unknown>(endpoint: string): Promise<ApiResponse<T>> {
		const res = await fetch(endpoint);

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
