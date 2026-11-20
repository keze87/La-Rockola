const CACHE_NAME = 'rockola-shell-v1';
const BYPASS_PREFIXES = [
	'/api',
	'/stream',
	'/ws',
	'/cover',
	'/lrc',
	'/command',
	'/scan',
	'/library',
	'/system',
	'/health',
];

self.addEventListener('install', (event) => {
	event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

self.addEventListener('fetch', (event) => {
	const req = event.request;
	if (req.method !== 'GET') return;

	const url = new URL(req.url);
	if (url.origin !== self.location.origin) return;
	if (BYPASS_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) return;

	if (req.mode === 'navigate' || url.pathname.startsWith('/assets/')) {
		event.respondWith(
			fetch(req)
				.then((res) => {
					if (res.ok) {
						const copy = res.clone();
						caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
					}
					return res;
				})
				.catch(() => caches.match(req))
		);
	}
});
