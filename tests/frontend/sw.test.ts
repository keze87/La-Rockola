import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const SW_PATH = resolve(process.cwd(), 'public/sw.js');

function loadServiceWorkerEnv(fetchMock: ReturnType<typeof vi.fn>) {
	const listeners = new Map<string, (event: unknown) => void>();
	const store = new Map<string, Map<string, Response>>();

	const makeCache = (name: string) => {
		if (!store.has(name)) store.set(name, new Map());
		const entries = store.get(name)!;
		return {
			addAll: vi.fn(async (urls: string[]) => {
				for (const u of urls) {
					entries.set(new URL(u, 'http://localhost:1729').href, new Response('cached', { status: 200 }));
				}
			}),
			put: vi.fn(async (req: Request | string, res: Response) => {
				const key = typeof req === 'string' ? req : req.url;
				entries.set(key, res);
			}),
			match: vi.fn(async (req: Request | string) => {
				const key = typeof req === 'string' ? req : req.url;
				return entries.get(key);
			}),
		};
	};

	const cacheObjects = new Map<string, ReturnType<typeof makeCache>>();
	const cachesMock = {
		open: vi.fn(async (name: string) => {
			if (!cacheObjects.has(name)) cacheObjects.set(name, makeCache(name));
			return cacheObjects.get(name)!;
		}),
		keys: vi.fn(async () => [...store.keys()]),
		delete: vi.fn(async (name: string) => {
			cacheObjects.delete(name);
			return store.delete(name);
		}),
		match: vi.fn(async (req: Request | string) => {
			const key = typeof req === 'string' ? req : req.url;
			for (const map of store.values()) {
				if (map.has(key)) return map.get(key);
			}
			return undefined;
		}),
	};

	const selfObj = {
		location: { origin: 'http://localhost:1729', href: 'http://localhost:1729/sw.js' },
		skipWaiting: vi.fn().mockResolvedValue(undefined),
		clients: { claim: vi.fn().mockResolvedValue(undefined) },
		addEventListener: vi.fn((type: string, cb: (e: unknown) => void) => {
			listeners.set(type, cb);
		}),
	};

	const context = {
		self: selfObj,
		caches: cachesMock,
		fetch: fetchMock,
		URL,
		Request,
		Response,
		Headers,
		Promise,
		console,
	};
	vm.runInNewContext(readFileSync(SW_PATH, 'utf-8'), context);

	return { listeners, cachesMock, cacheObjects, store, selfObj };
}

describe('public/sw.js lifecycle & offline resilience', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('install pre-caches app shell inside event.waitUntil and calls skipWaiting', async () => {
		const fetchMock = vi.fn();
		const { listeners, cachesMock, selfObj } = loadServiceWorkerEnv(fetchMock);
		const waitPromises: Promise<unknown>[] = [];
		const installHandler = listeners.get('install');
		expect(installHandler).toBeDefined();

		installHandler!({ waitUntil: (p: Promise<unknown>) => waitPromises.push(p) });
		expect(waitPromises.length).toBe(1);
		await Promise.all(waitPromises);

		expect(cachesMock.open).toHaveBeenCalledWith('rockola-shell-v2');
		const shellCache = await cachesMock.open('rockola-shell-v2');
		expect(shellCache.addAll).toHaveBeenCalled();
		expect(selfObj.skipWaiting).toHaveBeenCalledTimes(1);
	});

	it('activate removes stale caches and claims clients inside event.waitUntil', async () => {
		const fetchMock = vi.fn();
		const { listeners, cachesMock, store, selfObj } = loadServiceWorkerEnv(fetchMock);
		store.set('rockola-shell-v1', new Map());
		store.set('obsolete-v0', new Map());
		store.set('rockola-shell-v2', new Map());

		const waitPromises: Promise<unknown>[] = [];
		listeners.get('activate')!({ waitUntil: (p: Promise<unknown>) => waitPromises.push(p) });
		await Promise.all(waitPromises);

		expect(cachesMock.delete).toHaveBeenCalledWith('rockola-shell-v1');
		expect(cachesMock.delete).toHaveBeenCalledWith('obsolete-v0');
		expect(cachesMock.delete).not.toHaveBeenCalledWith('rockola-shell-v2');
		expect(selfObj.clients.claim).toHaveBeenCalledTimes(1);
	});

	it('caches navigation responses via event.waitUntil and falls back to cache in airplane mode', async () => {
		const fetchMock = vi.fn().mockResolvedValue(
			new Response('<html>Shell OK</html>', {
				status: 200,
				headers: { 'Content-Type': 'text/html' },
			})
		);
		const { listeners, cacheObjects } = loadServiceWorkerEnv(fetchMock);

		const waitPromises: Promise<unknown>[] = [];
		let respondPromise: Promise<Response> | null = null;
		const navReq = { method: 'GET', url: 'http://localhost:1729/', mode: 'navigate' } as Request;

		listeners.get('fetch')!({
			request: navReq,
			waitUntil: (p: Promise<unknown>) => waitPromises.push(p),
			respondWith: (p: Promise<Response>) => {
				respondPromise = p;
			},
		});

		const firstRes = await respondPromise!;
		expect(firstRes.status).toBe(200);
		expect(waitPromises.length).toBeGreaterThan(0);
		await Promise.all(waitPromises);

		expect(cacheObjects.get('rockola-shell-v2')?.put).toHaveBeenCalled();

		// Segundo pedido en modo avión (network rejects) -> responde desde caché
		fetchMock.mockRejectedValueOnce(new Error('Offline'));
		let offlinePromise: Promise<Response> | null = null;
		listeners.get('fetch')!({
			request: navReq,
			waitUntil: vi.fn(),
			respondWith: (p: Promise<Response>) => {
				offlinePromise = p;
			},
		});
		const cachedRes = await offlinePromise!;
		expect(cachedRes.status).toBe(200);
		expect(await cachedRes.text()).toContain('Shell OK');
	});

	it('returns valid 503 HTML offline fallback for uncached route when offline', async () => {
		const fetchMock = vi.fn().mockRejectedValue(new Error('Network down'));
		const { listeners } = loadServiceWorkerEnv(fetchMock);

		let respondPromise: Promise<Response> | null = null;
		listeners.get('fetch')!({
			request: { method: 'GET', url: 'http://localhost:1729/queue', mode: 'navigate' } as Request,
			waitUntil: vi.fn(),
			respondWith: (p: Promise<Response>) => {
				respondPromise = p;
			},
		});

		const res = await respondPromise!;
		expect(res.status).toBe(503);
		expect(res.headers.get('Content-Type')).toContain('text/html');
		expect(await res.text()).toMatch(/sin conexión|reconectar/i);
	});

	it('returns network response cleanly even when cache.put fails with QuotaExceededError', async () => {
		const fetchMock = vi.fn().mockResolvedValue(new Response('console.log("asset")', { status: 200 }));
		const { listeners, cachesMock } = loadServiceWorkerEnv(fetchMock);
		const c = await cachesMock.open('rockola-shell-v2');
		c.put.mockRejectedValue(new DOMException('Quota exceeded', 'QuotaExceededError'));

		const waitPromises: Promise<unknown>[] = [];
		let respondPromise: Promise<Response> | null = null;
		listeners.get('fetch')!({
			request: { method: 'GET', url: 'http://localhost:1729/assets/app.js', mode: 'same-origin' } as Request,
			waitUntil: (p: Promise<unknown>) => waitPromises.push(p),
			respondWith: (p: Promise<Response>) => {
				respondPromise = p;
			},
		});

		const res = await respondPromise!;
		expect(res.status).toBe(200);
		expect(waitPromises.length).toBeGreaterThan(0);
		await expect(Promise.all(waitPromises)).resolves.toBeDefined();
	});

	it('bypasses API, stream, cover, ws, lyrics, command, health, non-GET and cross-origin requests', () => {
		const fetchMock = vi.fn();
		const { listeners } = loadServiceWorkerEnv(fetchMock);

		const bypassUrls = [
			'http://localhost:1729/api/v1/library',
			'http://localhost:1729/stream?path=song.mp3',
			'http://localhost:1729/cover?path=song.mp3',
			'http://localhost:1729/ws',
			'http://localhost:1729/lyrics/content?path=song.mp3',
			'http://localhost:1729/command',
			'http://localhost:1729/health',
			'https://other-host.local/assets/app.js',
		];

		for (const url of bypassUrls) {
			const respondWith = vi.fn();
			listeners.get('fetch')!({
				request: { method: 'GET', url, mode: 'cors' } as Request,
				waitUntil: vi.fn(),
				respondWith,
			});
			expect(respondWith).not.toHaveBeenCalled();
		}

		const respondPost = vi.fn();
		listeners.get('fetch')!({
			request: { method: 'POST', url: 'http://localhost:1729/', mode: 'navigate' } as Request,
			waitUntil: vi.fn(),
			respondWith: respondPost,
		});
		expect(respondPost).not.toHaveBeenCalled();
		expect(fetchMock).not.toHaveBeenCalled();
	});
});
