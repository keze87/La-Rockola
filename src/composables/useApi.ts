export function useApi() {
	async function post(endpoint: string, data: Record<string, unknown> = {}) {
		const res = await fetch(endpoint, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data),
		});

		if (!res.ok) throw new Error(`API Error: ${res.status}`);

		return await res.json();
	}

	async function get(endpoint: string) {
		const res = await fetch(endpoint);

		if (!res.ok) throw new Error(`API Error: ${res.status}`);

		return await res.json();
	}

	return {
		command: (cmd: string, payload: Record<string, unknown> = {}) => post('/command', { cmd, ...payload }),
		getLibrary: () => get('/library'),
		hideMpv: () => post('/mpv/hide'),
		scanLibrary: () => get('/scan'),
		showMpv: () => post('/mpv/show'),
	};
}
