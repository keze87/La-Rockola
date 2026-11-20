import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
	useApi,
	getBasePath,
	apiUrl,
	getWsUrl,
	setApiOrigin,
	getApiOrigin,
	clearApiOrigin,
} from '@/composables/useApi';

describe('useApi.ts', () => {
	const originalLocation = window.location;

	beforeEach(() => {
		// Mock window.location
		delete (window as any).location;
		window.location = {
			...originalLocation,
			protocol: 'http:',
			host: 'localhost:1729',
			pathname: '/',
		} as any;
	});

	afterEach(() => {
		clearApiOrigin();
		window.location = originalLocation;
	});

	it('getBasePath handles root, subpaths, and index.html', () => {
		window.location.pathname = '/';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/rockola/';
		expect(getBasePath()).toBe('/rockola');

		window.location.pathname = '/rockola/index.html';
		expect(getBasePath()).toBe('/rockola');

		window.location.pathname = '/index.html';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/queue';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/fogon';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/vibra';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/letras';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/lyrics';
		expect(getBasePath()).toBe('');

		window.location.pathname = '/rockola/queue';
		expect(getBasePath()).toBe('/rockola');

		window.location.pathname = '/rockola/fogon';
		expect(getBasePath()).toBe('/rockola');

		window.location.pathname = '/rockola/letras';
		expect(getBasePath()).toBe('/rockola');

		window.location.pathname = '/rockola/lyrics';
		expect(getBasePath()).toBe('/rockola');
	});

	it('apiUrl prepends base path and normalizes leading slashes', () => {
		window.location.pathname = '/rockola';
		expect(apiUrl('/command')).toBe('/rockola/command');
		expect(apiUrl('command')).toBe('/rockola/command');

		window.location.pathname = '/';
		expect(apiUrl('library')).toBe('/library');
	});

	it('getWsUrl generates correct websocket URL for http and https', () => {
		window.location.protocol = 'http:';
		window.location.host = '192.168.1.50:1729';
		window.location.pathname = '/rockola';
		expect(getWsUrl()).toBe('ws://192.168.1.50:1729/rockola/ws');

		window.location.protocol = 'https:';
		expect(getWsUrl('/custom-ws')).toBe('wss://192.168.1.50:1729/rockola/custom-ws');
	});

	it('useApi calls endpoints and handles responses', async () => {
		const fetchMock = vi.fn().mockImplementation((url: string, _opts?: any) => {
			if (url.includes('/fail')) {
				return Promise.resolve({ ok: false, status: 500 });
			}
			return Promise.resolve({
				ok: true,
				json: () => Promise.resolve({ status: 'ok', data: url }),
			});
		});
		global.fetch = fetchMock;

		const api = useApi();

		// command
		await api.command('play', { path: '/track.mp3' });
		expect(fetchMock).toHaveBeenCalledWith(
			'/command',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ cmd: 'play', path: '/track.mp3' }),
			})
		);

		// getLibrary
		await api.getLibrary();
		expect(fetchMock).toHaveBeenCalledWith('/library');

		// hideMpv
		await api.hideMpv();
		expect(fetchMock).toHaveBeenCalledWith('/mpv/hide', expect.anything());

		// showMpv
		await api.showMpv();
		expect(fetchMock).toHaveBeenCalledWith('/mpv/show', expect.anything());

		// scanLibrary
		await api.scanLibrary();
		expect(fetchMock).toHaveBeenCalledWith('/scan');
	});

	it('throws error when response is not ok', async () => {
		global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
		const api = useApi();

		await expect(api.getLibrary()).rejects.toThrow('API Error: 404');
		await expect(api.hideMpv()).rejects.toThrow('API Error: 404');
	});

	it('resolves absolute URLs and WebSocket URLs when apiOrigin is configured (Capacitor)', async () => {
		setApiOrigin('http://127.0.0.1:1729/');
		expect(getApiOrigin()).toBe('http://127.0.0.1:1729');
		expect(apiUrl('/command')).toBe('http://127.0.0.1:1729/command');
		expect(apiUrl('stream?path=a.mp3')).toBe('http://127.0.0.1:1729/stream?path=a.mp3');
		expect(getWsUrl('/ws')).toBe('ws://127.0.0.1:1729/ws');

		setApiOrigin('https://rockola.local');
		expect(getWsUrl('/ws')).toBe('wss://rockola.local/ws');

		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ status: 'ok', music_dir: '/storage/ABCD-1234/Musica' }),
		});
		global.fetch = fetchMock;
		const api = useApi();
		await api.setMusicDir('/storage/ABCD-1234/Musica');
		expect(fetchMock).toHaveBeenCalledWith(
			'https://rockola.local/system/music-dir',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ dir: '/storage/ABCD-1234/Musica' }),
			})
		);

		clearApiOrigin();
		expect(getApiOrigin()).toBe('');
		expect(apiUrl('/command')).toBe('/command');
	});
});
