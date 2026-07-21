export function useApi() {
	async function post(endpoint, data = {}) {
		const res = await fetch(endpoint, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data),
		});
		if (!res.ok) throw new Error(`API Error: ${res.status}`);
		return await res.json();
	}

	async function get(endpoint) {
		const res = await fetch(endpoint);
		if (!res.ok) throw new Error(`API Error: ${res.status}`);
		return await res.json();
	}

	return {
		command: (cmd, payload = {}) => post('/command', { cmd, ...payload }),
		getLibrary: () => get('/library'),
		scanLibrary: () => get('/scan'),
		hideMpv: () => post('/mpv/hide'),
		showMpv: () => post('/mpv/show'),
	};
}
